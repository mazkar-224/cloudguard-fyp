"""
End-to-end test for the full anomaly pipeline.

Asserts the complete demo path in one test:
    spike injected → sync runs detection → Alert row created →
    email sent (SendGrid mocked) → alert visible via GET /alerts.

This mirrors the live demo (scripts/inject_spike.py → "Sync now" → alert +
email) but with AWS and SendGrid mocked, so no network call ever happens.

Data design (same shape as the inject_spike script / test_cost_sync):
    Baseline: 20 days alternating $4.50 / $5.50 → mean=$5.00, std=$0.50
    Spike:    $50.00 on the most recent completed day → z = 90 → high
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.jobs.cost_sync import sync_cost_data
from app.models.alert import Alert
from app.models.cost import AwsAccount, CostRecord
from app.services.aws_cost_service import AwsCostService


# ── helpers ───────────────────────────────────────────────────────────────────

async def _seed_baseline(db_session, account_id_str: str) -> AwsAccount:
    """Insert an AwsAccount + 20 normal days of Amazon EC2 spend."""
    today = date.today()
    account = AwsAccount(account_id=account_id_str)
    db_session.add(account)
    await db_session.flush()

    for i in range(20):
        day = today - timedelta(days=21 - i)
        amount = Decimal("4.50") if i % 2 == 0 else Decimal("5.50")
        db_session.add(CostRecord(
            aws_account_id=account.id,
            date=day,
            service_name="Amazon EC2",
            amount_usd=amount,
        ))
    await db_session.commit()
    return account


def _spike_aws_mock() -> AwsCostService:
    """Mock AWS returning a single spike row for yesterday."""
    spike_date = str(date.today() - timedelta(days=1))
    mock = MagicMock(spec=AwsCostService)
    mock.get_daily_costs = AsyncMock(return_value=[
        {"date": spike_date, "service": "Amazon EC2", "cost": 50.00},
    ])
    return mock


def _configure_sendgrid(monkeypatch):
    monkeypatch.setattr("app.config.settings.sendgrid_api_key", "SG.fake_test_key")
    monkeypatch.setattr("app.config.settings.alert_sender_email", "sender@test.com")
    monkeypatch.setattr("app.config.settings.alert_recipient_email", "recipient@test.com")


# ── the end-to-end test ───────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_spike_flows_to_alert_email_and_api(client, db_session, monkeypatch):
    """Full pipeline in one shot: spike → alert → email → API + count."""
    await _seed_baseline(db_session, "777777777777")
    mock_aws = _spike_aws_mock()
    _configure_sendgrid(monkeypatch)

    with patch(
        "app.jobs.cost_sync._fetch_account_id_sync", return_value="777777777777"
    ), patch(
        "app.services.email_service.SendGridAPIClient"
    ) as MockSendGrid:
        sendgrid_instance = MagicMock()
        MockSendGrid.return_value = sendgrid_instance
        sendgrid_instance.send.return_value = MagicMock(status_code=202)

        summary = await sync_cost_data(db_session, mock_aws)

    # 1. Detection created at least one alert.
    assert summary.new_alerts_created >= 1

    alerts = (await db_session.execute(select(Alert))).scalars().all()
    spike_alert = next(a for a in alerts if float(a.amount_usd) == 50.0)
    assert spike_alert.severity == "high"

    # 2. An email was sent for every alert and notified flipped to True.
    assert sendgrid_instance.send.call_count >= 1
    assert all(a.notified for a in alerts)

    # 3. The spike is visible through the public list API.
    resp = await client.get("/api/v1/alerts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert any(float(item["amount_usd"]) == 50.0 for item in body["items"])

    # 4. And reflected in the count endpoint.
    counts = (await client.get("/api/v1/alerts/count")).json()
    assert counts["total"] >= 1
