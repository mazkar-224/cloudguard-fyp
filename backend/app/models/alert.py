from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Alert(Base):
    """
    One row = one detected spending anomaly for one AWS account.

    scope="total"   → the account's total daily spend was anomalous
    scope="service" → a single service's spend was anomalous (service_name is set)

    Lifecycle:
        status:   "new" → "acknowledged" (user has seen it)
        notified: False → True (email has been sent)

    The unique constraint on (aws_account_id, alert_date, scope, service_name)
    means the 6-hour background sync can safely re-run without creating
    duplicate alerts for the same anomaly.
    """

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)

    aws_account_id: Mapped[int] = mapped_column(
        ForeignKey("aws_accounts.id"), nullable=False
    )

    # The calendar day the anomaly was detected.
    alert_date: Mapped[date] = mapped_column(Date, nullable=False)

    # "total" = whole-account daily spend anomaly
    # "service" = single-service spend anomaly
    scope: Mapped[str] = mapped_column(String(16), nullable=False)

    # Only set when scope="service". NULL when scope="total".
    service_name: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # The actual spend on alert_date (USD).
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)

    # The 14-day rolling mean that the spend was compared against.
    baseline_mean: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)

    # z = (amount - mean) / std — how many standard deviations above normal.
    # Numeric(8,2): up to 999999.99 — handles extreme spikes (e.g. baseline
    # $0.01/day, today $100 gives z≈19998; Numeric(6,2) max of 9999.99 overflows).
    z_score: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)

    # "low" (z∈[2,3)), "medium" (z∈[3,4)), "high" (z≥4)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)

    # "new" = not yet seen by user, "acknowledged" = user has dismissed it
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="new")

    # False until the email notification has been successfully sent.
    notified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    aws_account: Mapped["AwsAccount"] = relationship()  # type: ignore[name-defined]

    __table_args__ = (
        # Prevents duplicate alerts for the same anomaly across sync runs.
        # service_name is NULL for scope="total" — PostgreSQL treats each NULL
        # as distinct, so we'd get duplicates. We handle this in the sync job
        # by using ON CONFLICT DO NOTHING with this constraint name.
        # postgresql_nulls_not_distinct=True (PG 15+) makes the constraint treat
        # NULL == NULL, so two total-scope alerts on the same day (both with
        # service_name=NULL) are correctly blocked as duplicates.
        UniqueConstraint(
            "aws_account_id", "alert_date", "scope", "service_name",
            name="uq_alert_account_date_scope_service",
            postgresql_nulls_not_distinct=True,
        ),
    )
