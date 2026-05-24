from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class RecommendationOut(BaseModel):
    """One cost-saving recommendation as returned by the API.

    Built from the ORM Recommendation via from_attributes — the raw ORM object
    never goes out to the client. The Numeric `estimated_monthly_usd` column is
    exposed as a float so the JSON is clean for the frontend to format.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    aws_account_id: int
    resource_type: str
    resource_id: str
    region: str
    reason: str
    estimated_monthly_usd: float
    status: str                # "open" | "dismissed" | "resolved"
    first_seen_at: datetime
    last_seen_at: datetime
    created_at: datetime


class RecommendationListOut(BaseModel):
    """A page of recommendations plus aggregates for the filtered set.

    `total` and `total_estimated_savings` are computed over the WHOLE filtered
    set (before pagination), so the frontend can show "showing 50 of 1240" and
    a running savings figure without fetching every row.
    """

    items: list[RecommendationOut]
    total: int
    total_estimated_savings: float
    limit: int
    offset: int


class ResourceTypeBreakdown(BaseModel):
    """One row of the summary's per-resource-type breakdown."""

    resource_type: str
    count: int
    monthly_savings: float


class RecommendationSummary(BaseModel):
    """Aggregates that drive the "Potential savings: $X/month" hero banner.

    Scoped to OPEN recommendations only — dismissed/resolved ones are no longer
    actionable savings, so they don't belong in the headline number.
    """

    total_monthly_savings: float
    open_count: int
    by_resource_type: list[ResourceTypeBreakdown]


class RecommendationUpdate(BaseModel):
    """PATCH body — the only mutation the API allows is a status transition.

    Literal restricts the value to the two user-driven terminal states; any
    other value is rejected with a 422 automatically by FastAPI/Pydantic.
    """

    status: Literal["dismissed", "resolved"]
