from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class AlertOut(BaseModel):
    """One anomaly alert as returned by the API.

    Built from the ORM Alert via from_attributes — we never hand a raw ORM
    object back to the client. Decimal columns are exposed as floats so the
    JSON is clean for the frontend to format.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    alert_date: date
    scope: str                 # "total" | "service"
    service_name: str | None   # set only when scope == "service"
    amount_usd: float
    baseline_mean: float
    z_score: float
    severity: str              # "low" | "medium" | "high"
    status: str                # "new" | "acknowledged"
    notified: bool
    created_at: datetime


class AlertListOut(BaseModel):
    """A page of alerts plus the total matching the filters (pre-pagination).

    `total` lets the frontend render "showing 50 of 1240" and compute pages
    without fetching everything.
    """

    items: list[AlertOut]
    total: int
    limit: int
    offset: int


class AlertCounts(BaseModel):
    """Alert counts grouped by status and by severity — drives the sidebar badge.

    Every known key is always present (zero-filled) so the frontend never has
    to guard against missing keys.
    """

    by_status: dict[str, int]    # {"new": 3, "acknowledged": 1}
    by_severity: dict[str, int]  # {"low": 1, "medium": 2, "high": 1}
    total: int
