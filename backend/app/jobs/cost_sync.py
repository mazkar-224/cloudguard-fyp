"""
Background sync job — pulls the last 7 days of AWS costs and upserts them
into the cost_records table.

Why upsert and not plain insert?
  Running the same sync twice should not create duplicate rows.
  PostgreSQL's ON CONFLICT ... DO UPDATE updates the amount if it changed
  (AWS sometimes revises costs after the fact) and silently skips it if
  nothing changed.
"""

import asyncio
import logging
from datetime import date

import boto3
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_aws_service
from app.config import settings
from app.db.session import AsyncSessionLocal
from app.models.cost import AwsAccount, CostRecord
from app.services.aws_cost_service import AwsCostService

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fetch_account_id_sync() -> str:
    """
    Call AWS STS to get the 12-digit account number for the current credentials.
    Runs in a thread (via asyncio.to_thread) so it doesn't block the event loop.
    """
    sts = boto3.client(
        "sts",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    return sts.get_caller_identity()["Account"]


async def _get_or_create_account(db: AsyncSession, account_id_str: str) -> AwsAccount:
    """
    Return the AwsAccount row for this account ID, creating it if it doesn't exist.
    flush() writes the new row to the DB inside the current transaction so we get
    its auto-generated id — without committing yet.
    """
    result = await db.execute(
        select(AwsAccount).where(AwsAccount.account_id == account_id_str)
    )
    account = result.scalar_one_or_none()

    if not account:
        account = AwsAccount(account_id=account_id_str)
        db.add(account)
        await db.flush()
        logger.info("cost_sync: created new AwsAccount account_id=%s", account_id_str)

    return account


# ── Core sync function ────────────────────────────────────────────────────────

async def sync_cost_data(db: AsyncSession, aws: AwsCostService) -> int:
    """
    Fetch the last 7 days of cost data from AWS and upsert into cost_records.

    Returns the number of rows upserted (insert + update combined).
    Called by both the APScheduler job and the manual POST /admin/sync endpoint.
    """
    logger.info("cost_sync: started")

    # ── Step 1: identify the AWS account ─────────────────────────────────────
    try:
        account_id_str = await asyncio.to_thread(_fetch_account_id_sync)
        logger.info("cost_sync: account_id=%s", account_id_str)
    except Exception as exc:
        # STS might be blocked by IAM policy — fall back to a placeholder so
        # the rest of the sync can still proceed.
        logger.warning("cost_sync: STS call failed, using placeholder — %s", exc)
        account_id_str = "000000000000"

    # ── Step 2: ensure the account row exists ─────────────────────────────────
    account = await _get_or_create_account(db, account_id_str)

    # ── Step 3: fetch costs from AWS ──────────────────────────────────────────
    cost_rows = await aws.get_daily_costs(days=7)

    if not cost_rows:
        logger.info("cost_sync: AWS returned no data, nothing to upsert")
        await db.commit()
        return 0

    # ── Step 4: upsert into cost_records ──────────────────────────────────────
    # Build a list of plain dicts — one per (date, service) pair.
    rows = [
        {
            "aws_account_id": account.id,
            "date": date.fromisoformat(row["date"]),
            "service_name": row["service"],
            "amount_usd": row["cost"],
        }
        for row in cost_rows
    ]

    # pg_insert is PostgreSQL-specific INSERT that supports ON CONFLICT.
    # stmt.excluded refers to the row that *would* have been inserted —
    # so we're saying "if the row already exists, update amount_usd to the new value."
    stmt = pg_insert(CostRecord).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_cost_record_account_date_service",
        set_={"amount_usd": stmt.excluded.amount_usd},
    )
    await db.execute(stmt)
    await db.commit()

    logger.info("cost_sync: completed — %d rows upserted", len(rows))
    return len(rows)


# ── APScheduler wrapper ───────────────────────────────────────────────────────

async def run_sync_job() -> None:
    """
    Thin wrapper that the scheduler calls every 6 hours.

    APScheduler has no knowledge of FastAPI's dependency injection, so this
    function creates its own DB session and AWS service instance.
    """
    try:
        async with AsyncSessionLocal() as db:
            aws = get_aws_service()
            count = await sync_cost_data(db, aws)
            logger.info("cost_sync: scheduled run finished — %d rows", count)
    except Exception as exc:
        # Log and swallow — a failed sync should not crash the entire app.
        logger.error("cost_sync: scheduled run failed — %s", exc, exc_info=True)
