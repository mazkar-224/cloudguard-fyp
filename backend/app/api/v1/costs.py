from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_aws_service
from app.db.session import get_db
from app.models.cost import CostRecord
from app.schemas.cost import CostSummary, DailyCostItem, ServiceCostItem
from app.services.aws_cost_service import AwsCostService

router = APIRouter(prefix="/costs", tags=["costs"])


def _to_http_error(exc: Exception) -> HTTPException:
    """
    Convert exceptions from AwsCostService into FastAPI HTTP responses.

    PermissionError → 403  (wrong IAM permissions or Cost Explorer not enabled)
    ValueError      → 400  (bad credentials)
    anything else   → 502  (unexpected AWS error — our fault to investigate)
    """
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


# ── Endpoint 1: daily costs ───────────────────────────────────────────────────

@router.get("/daily", response_model=list[DailyCostItem])
async def get_daily_costs(
    days: int = Query(default=30, ge=1, le=365, description="How many past days to include"),
    db: AsyncSession = Depends(get_db),
    aws: AwsCostService = Depends(get_aws_service),
):
    """
    Daily AWS costs broken down by service for the last N days.

    Response shape:
        [{"date": "2026-05-08", "service": "Amazon EC2", "cost": 18.50}, ...]

    The database is checked first. If it has no records for the period,
    we call AWS directly and return live data.
    """
    end = date.today()
    start = end - timedelta(days=days)

    # ── Try database ──────────────────────────────────────────────────────────
    result = await db.execute(
        select(CostRecord)
        .where(CostRecord.date >= start, CostRecord.date < end)
        .order_by(CostRecord.date.desc())
    )
    records = result.scalars().all()

    if records:
        return [
            DailyCostItem(
                date=str(r.date),
                service=r.service_name,
                cost=round(float(r.amount_usd), 2),
            )
            for r in records
        ]

    # ── Fallback: live AWS call ───────────────────────────────────────────────
    try:
        live = await aws.get_daily_costs(days=days)
    except Exception as exc:
        raise _to_http_error(exc) from exc

    return [DailyCostItem(**item) for item in live]


# ── Endpoint 2: cost by service ───────────────────────────────────────────────

@router.get("/by-service", response_model=list[ServiceCostItem])
async def get_cost_by_service(
    start_date: date = Query(..., description="Start date inclusive, e.g. 2026-05-01"),
    end_date: date = Query(..., description="End date exclusive, e.g. 2026-05-31"),
    db: AsyncSession = Depends(get_db),
    aws: AwsCostService = Depends(get_aws_service),
):
    """
    Total cost per service across a date range, sorted most expensive first.

    Response shape:
        [{"service": "Amazon EC2", "cost": 450.00}, ...]

    Useful for pie charts. Dates follow the same convention as AWS Cost Explorer:
    start_date is inclusive, end_date is exclusive.
    """
    if start_date >= end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date must be before end_date",
        )

    # ── Try database ──────────────────────────────────────────────────────────
    # One SQL query: group all matching rows by service, sum their costs.
    result = await db.execute(
        select(
            CostRecord.service_name,
            func.sum(CostRecord.amount_usd).label("total"),
        )
        .where(CostRecord.date >= start_date, CostRecord.date < end_date)
        .group_by(CostRecord.service_name)
        .order_by(func.sum(CostRecord.amount_usd).desc())
    )
    rows = result.all()

    if rows:
        return [
            ServiceCostItem(service=r.service_name, cost=round(float(r.total), 2))
            for r in rows
        ]

    # ── Fallback: live AWS call ───────────────────────────────────────────────
    try:
        live = await aws.get_cost_by_service(start_date=start_date, end_date=end_date)
    except Exception as exc:
        raise _to_http_error(exc) from exc

    return [ServiceCostItem(**item) for item in live]


# ── Endpoint 3: summary ───────────────────────────────────────────────────────

@router.get("/summary", response_model=CostSummary)
async def get_cost_summary(
    days: int = Query(default=30, ge=1, le=365, description="How many past days to summarise"),
    db: AsyncSession = Depends(get_db),
    aws: AwsCostService = Depends(get_aws_service),
):
    """
    High-level cost summary for the last N days.

    Response shape:
        {
            "total_usd": 488.50,
            "top_service": "Amazon EC2",
            "top_service_cost": 450.00,
            "days_covered": 30,
            "record_count": 45,
            "source": "database"   ← or "live" when DB had no data
        }

    Designed for a dashboard header card that shows at a glance
    how much was spent and what cost the most.
    """
    end = date.today()
    start = end - timedelta(days=days)

    # ── Try database ──────────────────────────────────────────────────────────
    # Single query: total spend + how many records exist for the period.
    agg_result = await db.execute(
        select(
            func.sum(CostRecord.amount_usd).label("total"),
            func.count(CostRecord.id).label("count"),
        )
        .where(CostRecord.date >= start, CostRecord.date < end)
    )
    agg = agg_result.one()

    if agg.total:
        # Second query: find which service cost the most.
        top_result = await db.execute(
            select(
                CostRecord.service_name,
                func.sum(CostRecord.amount_usd).label("svc_total"),
            )
            .where(CostRecord.date >= start, CostRecord.date < end)
            .group_by(CostRecord.service_name)
            .order_by(func.sum(CostRecord.amount_usd).desc())
            .limit(1)
        )
        top = top_result.one_or_none()

        return CostSummary(
            total_usd=round(float(agg.total), 2),
            top_service=top.service_name if top else None,
            top_service_cost=round(float(top.svc_total), 2) if top else None,
            days_covered=days,
            record_count=agg.count,
            source="database",
        )

    # ── Fallback: live AWS call ───────────────────────────────────────────────
    try:
        live = await aws.get_daily_costs(days=days)
    except Exception as exc:
        raise _to_http_error(exc) from exc

    if not live:
        return CostSummary(
            total_usd=0.0,
            top_service=None,
            top_service_cost=None,
            days_covered=days,
            record_count=0,
            source="live",
        )

    total = sum(item["cost"] for item in live)

    # Aggregate per-service across all days to find the top spender.
    by_service: dict[str, float] = {}
    for item in live:
        by_service[item["service"]] = by_service.get(item["service"], 0.0) + item["cost"]

    top_svc = max(by_service, key=lambda k: by_service[k])

    return CostSummary(
        total_usd=round(total, 2),
        top_service=top_svc,
        top_service_cost=round(by_service[top_svc], 2),
        days_covered=days,
        record_count=len(live),
        source="live",
    )
