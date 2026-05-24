from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Recommendation(Base):
    """
    One row = one cost-saving recommendation for one AWS account, produced by
    the resource scanner (an unattached volume, an idle instance, etc.).

    Unlike a raw scan finding (which is ephemeral), a recommendation PERSISTS
    across scans. The unique constraint on
    (aws_account_id, resource_type, resource_id) lets the daily scan UPSERT:
      - first time we see a resource  → INSERT (first_seen_at = last_seen_at = now)
      - every scan after that         → UPDATE last_seen_at / estimate / reason,
                                         leaving first_seen_at and status untouched

    Keeping first_seen_at lets the UI say "this volume has been wasting money
    for 23 days" — a more compelling pitch than a point-in-time snapshot.

    status lifecycle: "open" → "dismissed" / "resolved" (set by the user later).
    """

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)

    aws_account_id: Mapped[int] = mapped_column(
        ForeignKey("aws_accounts.id"), nullable=False
    )

    # e.g. "ebs_volume", "elastic_ip", "ec2_instance", "ebs_snapshot",
    # "ec2_instance_idle" — the resource_type from the scan finding.
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)

    # The AWS id of the resource (volume id, allocation id, instance id, ...).
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False)

    region: Mapped[str] = mapped_column(String(32), nullable=False)

    # Human-readable "why this is wasteful" text from the scan finding. Text
    # (not String) because the reason can be long and we don't want a cap.
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    # Approximate monthly USD saved by cleaning this up. Numeric (not Float)
    # for exact money math; matches CostRecord.amount_usd precision.
    estimated_monthly_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False
    )

    # "open" = active, "dismissed" = user said ignore, "resolved" = cleaned up.
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="open"
    )

    # When this resource was FIRST flagged. Set on insert, never updated on
    # conflict — so it truly records the first sighting.
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # When this resource was LAST flagged. Bumped to now() on every scan that
    # still sees it — a recommendation whose last_seen_at stops advancing has
    # been cleaned up and could be auto-resolved later.
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    aws_account: Mapped["AwsAccount"] = relationship()  # type: ignore[name-defined]

    __table_args__ = (
        # Makes the daily scan's ON CONFLICT DO UPDATE clean: one row per
        # (account, resource_type, resource_id), so re-scanning never duplicates.
        UniqueConstraint(
            "aws_account_id", "resource_type", "resource_id",
            name="uq_recommendation_account_type_resource",
        ),
    )
