from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.recommendation import Recommendation
from app.schemas.recommendation import (
    RecommendationListOut,
    RecommendationOut,
    RecommendationSummary,
    RecommendationUpdate,
    ResourceTypeBreakdown,
)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def _apply_filters(
    stmt: Select,
    resource_type: Optional[str],
    status_filter: Optional[str],
) -> Select:
    """Apply the shared list filters to a SELECT.

    Reused by the page query and the aggregate (count + sum) query so the
    reported `total`/`total_estimated_savings` always match the listed rows.
    """
    if resource_type is not None:
        stmt = stmt.where(Recommendation.resource_type == resource_type)
    if status_filter is not None:
        stmt = stmt.where(Recommendation.status == status_filter)
    return stmt


# ── Endpoint 1: list recommendations ──────────────────────────────────────────

@router.get("", response_model=RecommendationListOut)
async def list_recommendations(
    resource_type: Optional[str] = Query(
        None, description="Filter by resource type (e.g. 'ebs_volume')"
    ),
    # `status` is aliased so the query string stays ?status=... while the Python
    # name avoids shadowing fastapi.status (used for HTTP codes below). Defaults
    # to 'open' — the actionable recommendations a user wants to see.
    status_filter: str = Query(
        "open", alias="status", description="Filter by status (open/dismissed/resolved)"
    ),
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Rows to skip (pagination)"),
    db: AsyncSession = Depends(get_db),
):
    """List recommendations, biggest estimated savings first.

    Filterable by `resource_type` and `status` (defaults to `open`), with
    `limit`/`offset` pagination. Always sorted by `estimated_monthly_usd`
    descending so the most valuable cleanups sit at the top. Returns the page
    of `items` plus the `total` row count and `total_estimated_savings` for the
    whole filtered set (before pagination).
    """
    # One round-trip for both aggregates over the filtered set.
    agg_stmt = _apply_filters(
        select(
            func.count(Recommendation.id),
            func.coalesce(func.sum(Recommendation.estimated_monthly_usd), 0),
        ),
        resource_type,
        status_filter,
    )
    total, total_savings = (await db.execute(agg_stmt)).one()

    list_stmt = _apply_filters(select(Recommendation), resource_type, status_filter)
    list_stmt = (
        list_stmt
        # Dollars descending is the headline sort; id breaks ties so pagination
        # is stable when several rows share an estimate (e.g. many $0 idles).
        .order_by(Recommendation.estimated_monthly_usd.desc(), Recommendation.id.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(list_stmt)).scalars().all()

    return RecommendationListOut(
        items=[RecommendationOut.model_validate(r) for r in rows],
        total=total,
        total_estimated_savings=float(total_savings),
        limit=limit,
        offset=offset,
    )


# ── Endpoint 2: summary (hero banner) ─────────────────────────────────────────

@router.get("/summary", response_model=RecommendationSummary)
async def recommendations_summary(db: AsyncSession = Depends(get_db)):
    """Aggregate savings for the "Potential savings: $X/month" hero banner.

    Scoped to OPEN recommendations only (dismissed/resolved are no longer
    actionable). Returns the total monthly savings, the open count, and a
    per-resource-type breakdown sorted by savings descending.
    """
    rows = (
        await db.execute(
            select(
                Recommendation.resource_type,
                func.count(Recommendation.id),
                func.coalesce(func.sum(Recommendation.estimated_monthly_usd), 0),
            )
            .where(Recommendation.status == "open")
            .group_by(Recommendation.resource_type)
            .order_by(func.sum(Recommendation.estimated_monthly_usd).desc())
        )
    ).all()

    by_resource_type = [
        ResourceTypeBreakdown(
            resource_type=rt,
            count=count,
            monthly_savings=float(savings),
        )
        for rt, count, savings in rows
    ]

    return RecommendationSummary(
        total_monthly_savings=sum(b.monthly_savings for b in by_resource_type),
        open_count=sum(b.count for b in by_resource_type),
        by_resource_type=by_resource_type,
    )


# ── Endpoint 3: dismiss / resolve ─────────────────────────────────────────────

@router.patch("/{recommendation_id}", response_model=RecommendationOut)
async def update_recommendation_status(
    recommendation_id: int,
    body: RecommendationUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Set a recommendation's status to `dismissed` or `resolved`.

    The body's `status` is validated against those two values (any other value
    is rejected with 422). Returns the updated row, or 404 if no recommendation
    has the given id.
    """
    rec = await db.get(Recommendation, recommendation_id)
    if rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recommendation {recommendation_id} not found",
        )

    rec.status = body.status
    await db.commit()
    await db.refresh(rec)

    return RecommendationOut.model_validate(rec)
