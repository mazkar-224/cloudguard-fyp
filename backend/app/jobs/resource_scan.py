"""
Resource-scan job — the resource-layer sibling of cost_sync.

Where cost_sync pulls *spending* from Cost Explorer, this job inspects the
*resources themselves*: it runs every waste check in ResourceScanner.scan_all()
(unattached EBS, unassociated Elastic IPs, stopped instances, old snapshots, and
the CloudWatch-based idle-instance check), prices each finding with the offline
savings estimator, then UPSERTS the results into the recommendations table.

Why upsert and not plain insert?
  The same resource shows up on every scan. ON CONFLICT
  (aws_account_id, resource_type, resource_id) DO UPDATE bumps last_seen_at and
  refreshes the estimate/reason, but deliberately leaves first_seen_at untouched
  so we keep the true first-sighting date ("idle for 23 days").

Runs daily (resource scans are heavier and change slowly, so 6-hourly like the
cost sync would be overkill) and on-demand via POST /api/v1/admin/scan-resources.
"""

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_resource_scanner
from app.db.session import AsyncSessionLocal
# Reused as-is — account identification and the get-or-create pattern are
# identical to the cost sync, so there's no reason to duplicate them.
from app.jobs.cost_sync import _fetch_account_id_sync, _get_or_create_account
from app.models.recommendation import Recommendation
from app.services.resource_scanner import ResourceScanner
from app.services.savings_estimator import estimate_monthly_savings

logger = logging.getLogger(__name__)


@dataclass
class ScanSummary:
    findings_scanned: int
    recommendations_upserted: int


async def scan_resources(db: AsyncSession, scanner: ResourceScanner) -> ScanSummary:
    """
    Run every waste check, estimate savings, and upsert recommendations.

    Returns a ScanSummary. Called by both the APScheduler job and the manual
    POST /admin/scan-resources endpoint.

    Note: scan_all() ALREADY includes the idle-instance check (it's the fifth
    check), so we do NOT call find_idle_running_instances() separately — that
    would just re-do work the upsert would dedupe anyway.
    """
    logger.info("resource_scan: started")

    # ── Step 1: identify the AWS account (same as cost_sync) ─────────────────
    try:
        account_id_str = await asyncio.to_thread(_fetch_account_id_sync)
        logger.info("resource_scan: account_id=%s", account_id_str)
    except Exception as exc:
        logger.warning("resource_scan: STS call failed, using placeholder — %s", exc)
        account_id_str = "000000000000"

    account = await _get_or_create_account(db, account_id_str)

    # ── Step 2: run all checks ───────────────────────────────────────────────
    findings = await scanner.scan_all()
    logger.info("resource_scan: %d finding(s) returned", len(findings))

    if not findings:
        await db.commit()
        logger.info("resource_scan: completed — no findings")
        return ScanSummary(findings_scanned=0, recommendations_upserted=0)

    # ── Step 3: price each finding and build upsert rows ─────────────────────
    rows = [
        {
            "aws_account_id": account.id,
            "resource_type": f["resource_type"],
            "resource_id": f["resource_id"],
            "region": f["region"],
            "reason": f["reason"],
            "estimated_monthly_usd": estimate_monthly_savings(f)["estimated_monthly_usd"],
        }
        for f in findings
    ]

    # ── Step 4: upsert into recommendations ──────────────────────────────────
    # On conflict we refresh the moving parts (estimate, reason) and bump
    # last_seen_at, but never overwrite first_seen_at or status — those record
    # history and user intent. func.now() resolves to the DB transaction time.
    stmt = pg_insert(Recommendation).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_recommendation_account_type_resource",
        set_={
            "last_seen_at": func.now(),
            "estimated_monthly_usd": stmt.excluded.estimated_monthly_usd,
            "reason": stmt.excluded.reason,
        },
    )
    await db.execute(stmt)
    await db.commit()

    logger.info(
        "resource_scan: completed — %d finding(s), %d recommendation(s) upserted",
        len(findings), len(rows),
    )
    return ScanSummary(
        findings_scanned=len(findings),
        recommendations_upserted=len(rows),
    )


# ── APScheduler wrapper ───────────────────────────────────────────────────────

async def run_scan_job() -> None:
    """
    Thin wrapper the scheduler calls once a day.

    APScheduler knows nothing about FastAPI's dependency injection, so this
    creates its own DB session and ResourceScanner instance.
    """
    try:
        async with AsyncSessionLocal() as db:
            scanner = get_resource_scanner()
            summary = await scan_resources(db, scanner)
            logger.info(
                "resource_scan: scheduled run finished — %d findings, %d upserted",
                summary.findings_scanned, summary.recommendations_upserted,
            )
    except Exception as exc:
        logger.error("resource_scan: scheduled run failed — %s", exc, exc_info=True)
