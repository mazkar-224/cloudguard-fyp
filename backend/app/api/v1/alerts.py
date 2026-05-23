from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.alert import Alert
from app.schemas.alert import AlertCounts, AlertListOut, AlertOut

router = APIRouter(prefix="/alerts", tags=["alerts"])

# Keys we always report counts for, so the frontend never sees a missing key.
STATUS_KEYS = ("new", "acknowledged")
SEVERITY_KEYS = ("low", "medium", "high")


def _apply_filters(
    stmt: Select,
    status_filter: Optional[str],
    severity: Optional[str],
    cutoff: date,
) -> Select:
    """Apply the shared list/count filters to a SELECT statement.

    Using the same helper for both the page query and the total-count query
    guarantees `total` always matches what the list would return.
    """
    stmt = stmt.where(Alert.alert_date >= cutoff)
    if status_filter is not None:
        stmt = stmt.where(Alert.status == status_filter)
    if severity is not None:
        stmt = stmt.where(Alert.severity == severity)
    return stmt


# ── Endpoint 1: list alerts ───────────────────────────────────────────────────

@router.get("", response_model=AlertListOut)
async def list_alerts(
    # `status` is aliased so the query string stays ?status=... while the Python
    # name avoids shadowing fastapi.status (used for HTTP codes below).
    status_filter: Optional[Literal["new", "acknowledged"]] = Query(
        None, alias="status", description="Filter by alert status"
    ),
    severity: Optional[Literal["low", "medium", "high"]] = Query(
        None, description="Filter by severity band"
    ),
    days: int = Query(30, ge=1, le=365, description="Only alerts from the last N days"),
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Rows to skip (pagination)"),
    db: AsyncSession = Depends(get_db),
):
    """List anomaly alerts, newest first.

    Supports optional `status`, `severity`, and `days` filters plus
    `limit`/`offset` pagination. Returns the page of `items` along with the
    `total` number of alerts matching the filters (before pagination), so the
    frontend can render page counts without fetching everything.
    """
    cutoff = date.today() - timedelta(days=days)

    count_stmt = _apply_filters(select(func.count(Alert.id)), status_filter, severity, cutoff)
    total = await db.scalar(count_stmt) or 0

    list_stmt = _apply_filters(select(Alert), status_filter, severity, cutoff)
    list_stmt = (
        list_stmt
        # alert_date is the primary sort; created_at and id break ties so
        # pagination is stable when many alerts share a date.
        .order_by(Alert.alert_date.desc(), Alert.created_at.desc(), Alert.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(list_stmt)).scalars().all()

    return AlertListOut(
        items=[AlertOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


# ── Endpoint 2: counts ────────────────────────────────────────────────────────

@router.get("/count", response_model=AlertCounts)
async def count_alerts(
    days: int = Query(30, ge=1, le=365, description="Only alerts from the last N days"),
    db: AsyncSession = Depends(get_db),
):
    """Alert counts grouped by status and by severity.

    Drives the sidebar badge (e.g. number of `new` alerts). Uses the same
    `days` window (default 30) as `GET /alerts`, so the badge can never count
    alerts that the default list view would hide. All known keys are
    zero-filled so the response shape is stable even with no alerts.
    """
    cutoff = date.today() - timedelta(days=days)
    by_status = {k: 0 for k in STATUS_KEYS}
    by_severity = {k: 0 for k in SEVERITY_KEYS}

    status_rows = await db.execute(
        select(Alert.status, func.count(Alert.id))
        .where(Alert.alert_date >= cutoff)
        .group_by(Alert.status)
    )
    for row_status, n in status_rows.all():
        by_status[row_status] = n

    severity_rows = await db.execute(
        select(Alert.severity, func.count(Alert.id))
        .where(Alert.alert_date >= cutoff)
        .group_by(Alert.severity)
    )
    for row_severity, n in severity_rows.all():
        by_severity[row_severity] = n

    return AlertCounts(
        by_status=by_status,
        by_severity=by_severity,
        total=sum(by_status.values()),
    )


# ── Endpoint 3: acknowledge ───────────────────────────────────────────────────

@router.patch("/{alert_id}", response_model=AlertOut)
async def acknowledge_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    """Mark an alert as acknowledged and return the updated alert.

    Returns 404 if no alert has the given id.
    """
    alert = await db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found",
        )

    alert.status = "acknowledged"
    await db.commit()
    await db.refresh(alert)

    return AlertOut.model_validate(alert)
