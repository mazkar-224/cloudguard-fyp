"""
Background sync job — pulls the last 7 days of AWS costs, upserts them
into cost_records, then runs anomaly detection on the trailing 21 days.

Why upsert and not plain insert?
  Running the same sync twice should not create duplicate rows.
  PostgreSQL's ON CONFLICT ... DO UPDATE updates the amount if it changed
  (AWS sometimes revises costs after the fact) and silently skips it if
  nothing changed.

Detection runs after every sync:
  1. Total daily spend — catches account-level spikes.
  2. Per-service (top 5) — catches a single runaway service even when the
     total looks calm (e.g. a GPU instance left on).
  Alert rows use ON CONFLICT DO NOTHING so re-runs are silent no-ops.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, timedelta

import boto3
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_aws_service
from app.config import settings
from app.db.session import AsyncSessionLocal
from app.models.alert import Alert
from app.models.cost import AwsAccount, CostRecord
from app.services.anomaly_detector import detect_anomalies
from app.services.aws_cost_service import AwsCostService

logger = logging.getLogger(__name__)


@dataclass
class SyncSummary:
    cost_rows_upserted: int
    new_alerts_created: int


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


async def _run_detection(db: AsyncSession, account: AwsAccount) -> int:
    """
    Run anomaly detection over the trailing 21 days of cost data for *account*.

    Checks total daily spend (scope='total') and each of the top-5 services
    individually (scope='service').  Any anomaly found is persisted as an Alert
    row.  ON CONFLICT DO NOTHING means re-running this is always a safe no-op.

    Returns the number of NEW Alert rows actually inserted.
    """
    end = date.today()
    start = end - timedelta(days=21)

    alert_values: list[dict] = []

    # ── 1. Total daily spend ──────────────────────────────────────────────────
    total_result = await db.execute(
        select(
            CostRecord.date,
            func.sum(CostRecord.amount_usd).label("total"),
        )
        .where(
            CostRecord.aws_account_id == account.id,
            CostRecord.date >= start,
            CostRecord.date < end,
        )
        .group_by(CostRecord.date)
        .order_by(CostRecord.date.asc())
    )
    total_rows = total_result.all()

    if total_rows:
        daily_totals = [
            {"date": str(r.date), "amount_usd": float(r.total)}
            for r in total_rows
        ]
        result = detect_anomalies(daily_totals)
        if result.is_anomaly:
            candidate_date = date.fromisoformat(daily_totals[-1]["date"])
            logger.warning(
                "cost_sync: ANOMALY scope=total date=%s amount=$%.2f "
                "z=%.2f severity=%s — %s",
                candidate_date, result.today_amount,
                result.z_score, result.severity, result.reason,
            )
            alert_values.append({
                "aws_account_id": account.id,
                "alert_date": candidate_date,
                "scope": "total",
                "service_name": None,
                "amount_usd": result.today_amount,
                "baseline_mean": result.baseline_mean,
                "z_score": result.z_score,
                "severity": result.severity,
            })

    # ── 2. Per-service (top 5 by spend) ──────────────────────────────────────
    svc_result = await db.execute(
        select(CostRecord.service_name)
        .where(
            CostRecord.aws_account_id == account.id,
            CostRecord.date >= start,
            CostRecord.date < end,
        )
        .group_by(CostRecord.service_name)
        .order_by(func.sum(CostRecord.amount_usd).desc())
        .limit(5)
    )
    top_services = [row.service_name for row in svc_result.all()]

    for service_name in top_services:
        svc_daily_result = await db.execute(
            select(
                CostRecord.date,
                func.sum(CostRecord.amount_usd).label("total"),
            )
            .where(
                CostRecord.aws_account_id == account.id,
                CostRecord.service_name == service_name,
                CostRecord.date >= start,
                CostRecord.date < end,
            )
            .group_by(CostRecord.date)
            .order_by(CostRecord.date.asc())
        )
        svc_rows = svc_daily_result.all()

        if not svc_rows:
            continue

        svc_daily = [
            {"date": str(r.date), "amount_usd": float(r.total)}
            for r in svc_rows
        ]
        result = detect_anomalies(svc_daily)
        if result.is_anomaly:
            candidate_date = date.fromisoformat(svc_daily[-1]["date"])
            logger.warning(
                "cost_sync: ANOMALY scope=service service=%s date=%s "
                "amount=$%.2f z=%.2f severity=%s — %s",
                service_name, candidate_date, result.today_amount,
                result.z_score, result.severity, result.reason,
            )
            alert_values.append({
                "aws_account_id": account.id,
                "alert_date": candidate_date,
                "scope": "service",
                "service_name": service_name,
                "amount_usd": result.today_amount,
                "baseline_mean": result.baseline_mean,
                "z_score": result.z_score,
                "severity": result.severity,
            })

    # ── Insert alerts (DO NOTHING on duplicate) ───────────────────────────────
    if not alert_values:
        return 0

    stmt = pg_insert(Alert).values(alert_values)
    stmt = stmt.on_conflict_do_nothing(
        constraint="uq_alert_account_date_scope_service"
    )
    # RETURNING only yields rows that were actually inserted, not conflicted ones.
    stmt = stmt.returning(Alert.id)
    insert_result = await db.execute(stmt)
    new_count = len(insert_result.all())
    await db.commit()

    logger.info("cost_sync: detection complete — %d new alert(s)", new_count)
    return new_count


# ── Core sync function ────────────────────────────────────────────────────────

async def sync_cost_data(db: AsyncSession, aws: AwsCostService) -> SyncSummary:
    """
    Fetch the last 7 days of cost data from AWS, upsert into cost_records,
    then run anomaly detection on the trailing 21 days.

    Returns a SyncSummary with cost_rows_upserted and new_alerts_created.
    Called by both the APScheduler job and the manual POST /admin/sync endpoint.
    """
    logger.info("cost_sync: started")

    # ── Step 1: identify the AWS account ─────────────────────────────────────
    try:
        account_id_str = await asyncio.to_thread(_fetch_account_id_sync)
        logger.info("cost_sync: account_id=%s", account_id_str)
    except Exception as exc:
        logger.warning("cost_sync: STS call failed, using placeholder — %s", exc)
        account_id_str = "000000000000"

    # ── Step 2: ensure the account row exists ─────────────────────────────────
    account = await _get_or_create_account(db, account_id_str)

    # ── Step 3: fetch costs from AWS ──────────────────────────────────────────
    cost_rows = await aws.get_daily_costs(days=7)

    # ── Step 4: upsert into cost_records ──────────────────────────────────────
    rows_upserted = 0
    if cost_rows:
        rows = [
            {
                "aws_account_id": account.id,
                "date": date.fromisoformat(row["date"]),
                "service_name": row["service"],
                "amount_usd": row["cost"],
            }
            for row in cost_rows
        ]
        stmt = pg_insert(CostRecord).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_cost_record_account_date_service",
            set_={"amount_usd": stmt.excluded.amount_usd},
        )
        await db.execute(stmt)
        rows_upserted = len(rows)
        logger.info("cost_sync: %d rows upserted", rows_upserted)
    else:
        logger.info("cost_sync: AWS returned no data")

    await db.commit()

    # ── Step 5: anomaly detection ─────────────────────────────────────────────
    new_alerts = await _run_detection(db, account)

    logger.info(
        "cost_sync: completed — %d rows upserted, %d new alerts",
        rows_upserted, new_alerts,
    )
    return SyncSummary(cost_rows_upserted=rows_upserted, new_alerts_created=new_alerts)


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
            summary = await sync_cost_data(db, aws)
            logger.info(
                "cost_sync: scheduled run finished — %d rows, %d new alerts",
                summary.cost_rows_upserted, summary.new_alerts_created,
            )
    except Exception as exc:
        logger.error("cost_sync: scheduled run failed — %s", exc, exc_info=True)
