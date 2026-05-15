from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AwsAccount(Base):
    """
    Stores the AWS accounts a user has connected to CloudGuard.

    One AwsAccount has many CostRecords — one per day per service.
    """
    __tablename__ = "aws_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)

    # The 12-digit AWS account number, e.g. "123456789012".
    # unique=True prevents the same account from being added twice.
    account_id: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)

    # A human-readable name like "production" or "personal".
    # nullable=True because the user may not provide one.
    alias: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # server_default=func.now() means the database fills this in automatically
    # when a new row is inserted — we never need to set it manually.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # SQLAlchemy relationship — lets us do account.cost_records to get all
    # cost records for this account without writing a JOIN manually.
    cost_records: Mapped[list["CostRecord"]] = relationship(
        back_populates="aws_account"
    )


class CostRecord(Base):
    """
    One row = one service's cost on one day for one AWS account.

    Example row:
        aws_account_id=1, date=2026-05-14, service_name="Amazon EC2", amount_usd=12.50
    """
    __tablename__ = "cost_records"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Foreign key — links this record back to the aws_accounts table.
    aws_account_id: Mapped[int] = mapped_column(
        ForeignKey("aws_accounts.id"), nullable=False
    )

    date: Mapped[date] = mapped_column(Date, nullable=False)

    # Full service name as AWS returns it, e.g. "Amazon Elastic Compute Cloud - Compute"
    service_name: Mapped[str] = mapped_column(String(256), nullable=False)

    # Numeric(12, 4) = up to 12 total digits, 4 after the decimal point.
    # e.g. 12345678.9012 — gives us cent-level precision without float rounding errors.
    # We use Numeric (not Float) because money math needs to be exact.
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship — lets us do record.aws_account to get the parent account.
    aws_account: Mapped["AwsAccount"] = relationship(back_populates="cost_records")

    __table_args__ = (
        # Prevents duplicate rows for the same account + day + service.
        # If we accidentally sync the same day twice, the database rejects
        # the duplicate instead of silently storing it twice.
        UniqueConstraint(
            "aws_account_id", "date", "service_name",
            name="uq_cost_record_account_date_service",
        ),
    )
