"""
Tests for app/jobs/resource_scan.py — the scan → estimate → upsert pipeline.

These are DB-backed (they hit cloudguard_test) but use a FAKE ResourceScanner
whose scan_all() returns canned findings, so no AWS/CloudWatch is ever touched.
_fetch_account_id_sync is patched too (it would otherwise call real STS).

What we prove:
  - Findings become recommendation rows, priced by the offline estimator.
  - Re-running is idempotent: existing rows are UPDATED (last_seen_at bumped,
    estimate/reason refreshed) and never duplicated; first_seen_at is preserved.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import func, select

from app.jobs.resource_scan import scan_resources
from app.models.recommendation import Recommendation
from app.services.resource_scanner import ResourceScanner
from app.services.savings_estimator import PRICING

ACCOUNT_ID = "123456789012"


def _fake_scanner(findings: list[dict]) -> ResourceScanner:
    """A ResourceScanner stand-in whose scan_all() returns *findings*."""
    scanner = MagicMock(spec=ResourceScanner)
    scanner.scan_all = AsyncMock(return_value=findings)
    return scanner


def _finding(resource_type, resource_id, raw, reason="needs cleanup"):
    return {
        "check": "test",
        "resource_type": resource_type,
        "resource_id": resource_id,
        "region": "us-east-1",
        "reason": reason,
        "raw": raw,
    }


@pytest.mark.anyio
async def test_findings_create_priced_recommendations(db_session):
    findings = [
        _finding("ebs_volume", "vol-001", {"Size": 100}),
        _finding("elastic_ip", "eipalloc-001", {"PublicIp": "1.2.3.4"}),
        # Idle instance currently estimates $0 ("no estimate") — verify it still
        # persists with a 0.00 figure rather than being dropped.
        _finding("ec2_instance_idle", "i-001", {"avg_cpu_percent": 1.2}),
    ]

    with patch("app.jobs.resource_scan._fetch_account_id_sync", return_value=ACCOUNT_ID):
        summary = await scan_resources(db_session, _fake_scanner(findings))

    assert summary.findings_scanned == 3
    assert summary.recommendations_upserted == 3

    rows = (
        await db_session.execute(
            select(Recommendation).order_by(Recommendation.resource_id)
        )
    ).scalars().all()
    assert len(rows) == 3

    by_id = {r.resource_id: r for r in rows}
    assert float(by_id["vol-001"].estimated_monthly_usd) == round(100 * PRICING["ebs_gb_month"], 2)
    assert float(by_id["eipalloc-001"].estimated_monthly_usd) == round(PRICING["elastic_ip_month"], 2)
    assert float(by_id["i-001"].estimated_monthly_usd) == 0.0

    # Defaults applied on insert.
    assert all(r.status == "open" for r in rows)
    assert all(r.first_seen_at is not None and r.last_seen_at is not None for r in rows)


@pytest.mark.anyio
async def test_rescan_is_idempotent_and_updates_in_place(db_session):
    first = [_finding("ebs_volume", "vol-001", {"Size": 100}, reason="first reason")]

    with patch("app.jobs.resource_scan._fetch_account_id_sync", return_value=ACCOUNT_ID):
        await scan_resources(db_session, _fake_scanner(first))

    row = (await db_session.execute(select(Recommendation))).scalar_one()
    original_first_seen = row.first_seen_at
    original_last_seen = row.last_seen_at
    original_id = row.id

    # Second scan: same resource, but the volume grew and the reason changed.
    second = [_finding("ebs_volume", "vol-001", {"Size": 200}, reason="second reason")]
    with patch("app.jobs.resource_scan._fetch_account_id_sync", return_value=ACCOUNT_ID):
        await scan_resources(db_session, _fake_scanner(second))

    # Re-read fresh from the DB.
    db_session.expire_all()
    rows = (await db_session.execute(select(Recommendation))).scalars().all()

    # No duplicate row.
    assert len(rows) == 1
    row = rows[0]
    assert row.id == original_id

    # first_seen_at preserved; last_seen_at advanced; estimate + reason refreshed.
    assert row.first_seen_at == original_first_seen
    assert row.last_seen_at >= original_last_seen
    assert float(row.estimated_monthly_usd) == round(200 * PRICING["ebs_gb_month"], 2)
    assert row.reason == "second reason"


@pytest.mark.anyio
async def test_scan_resources_endpoint(client, db_session):
    """POST /admin/scan-resources runs the same pipeline and reports counts.

    The route builds its scanner from the logged-in user's saved credentials, so
    we patch `build_scanner_for_user` to return a fake scanner with canned
    findings — no real credential row or AWS call needed.
    """
    findings = [_finding("ebs_volume", "vol-099", {"Size": 50})]

    with patch(
        "app.api.v1.admin.build_scanner_for_user",
        AsyncMock(return_value=_fake_scanner(findings)),
    ), patch("app.jobs.resource_scan._fetch_account_id_sync", return_value=ACCOUNT_ID):
        resp = await client.post("/api/v1/admin/scan-resources")

    assert resp.status_code == 200
    body = resp.json()
    assert body["findings_scanned"] == 1
    assert body["recommendations_upserted"] == 1
    assert "duration_seconds" in body

    count = (
        await db_session.execute(select(func.count()).select_from(Recommendation))
    ).scalar_one()
    assert count == 1
