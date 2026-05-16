from pydantic import BaseModel


class DailyCostItem(BaseModel):
    """One row in the daily-costs response: a single service on a single day."""
    date: str       # "2026-05-08"
    service: str    # "Amazon EC2"
    cost: float     # 18.50


class ServiceCostItem(BaseModel):
    """One row in the by-service response: a service with its total cost."""
    service: str
    cost: float


class CostSummary(BaseModel):
    """High-level summary for a dashboard header card."""
    total_usd: float
    top_service: str | None
    top_service_cost: float | None
    days_covered: int
    record_count: int
    # "database" = data came from our PostgreSQL cache
    # "live"     = data was fetched directly from AWS (DB was empty)
    source: str
