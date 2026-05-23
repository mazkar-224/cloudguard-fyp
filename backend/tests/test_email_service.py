"""
Tests for the SendGrid email-notification path.

We mock SendGridAPIClient at the email_service boundary so no real HTTP
call ever leaves the process.  The tests assert:

  1. send() is called exactly once per un-notified alert
  2. alert.notified flips to True after a successful send
  3. A SendGrid exception is non-fatal — the sync keeps going, and any
     un-sent alert stays notified=False so the next cycle retries it
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import func, select

from app.jobs.cost_sync import _send_pending_notifications
from app.models.alert import Alert
from app.models.cost import AwsAccount


# ── helpers ───────────────────────────────────────────────────────────────────

def _configure_sendgrid(monkeypatch):
    """Inject fake SendGrid settings so the notification path is enabled."""
    monkeypatch.setattr("app.config.settings.sendgrid_api_key", "SG.fake_test_key")
    monkeypatch.setattr("app.config.settings.alert_sender_email", "sender@test.com")
    monkeypatch.setattr("app.config.settings.alert_recipient_email", "recipient@test.com")


async def _seed_account_with_alerts(db_session, account_id_str: str, n_alerts: int):
    """Create an AwsAccount with *n_alerts* un-notified alerts."""
    account = AwsAccount(account_id=account_id_str)
    db_session.add(account)
    await db_session.flush()

    today = date.today()
    for i in range(n_alerts):
        # Mix total and service scope to exercise both code paths in the HTML
        scope = "total" if i == 0 else "service"
        service_name = None if scope == "total" else f"Amazon Service {i}"
        db_session.add(Alert(
            aws_account_id=account.id,
            alert_date=today,
            scope=scope,
            service_name=service_name,
            amount_usd=Decimal(f"{50 + i}.00"),
            baseline_mean=Decimal("5.00"),
            z_score=Decimal(f"{90 - i}.00"),
            severity="high",
        ))
    await db_session.commit()
    return account


# ── Test 1: send called once per un-notified alert + notified flips ──────────

@pytest.mark.anyio
async def test_email_sent_once_per_pending_alert(db_session, monkeypatch):
    _configure_sendgrid(monkeypatch)
    account = await _seed_account_with_alerts(db_session, "333333333333", n_alerts=2)

    with patch("app.services.email_service.SendGridAPIClient") as MockClient:
        mock_client_instance = MagicMock()
        MockClient.return_value = mock_client_instance
        mock_client_instance.send.return_value = MagicMock(status_code=202)

        sent = await _send_pending_notifications(db_session, account)

    # Exactly one send per un-notified alert
    assert mock_client_instance.send.call_count == 2
    assert sent == 2

    # Every alert is now notified=True
    notified_count = await db_session.scalar(
        select(func.count()).select_from(Alert).where(Alert.notified == True)  # noqa: E712
    )
    assert notified_count == 2


# ── Test 2: SendGrid failure is non-fatal, notified stays False ───────────────

@pytest.mark.anyio
async def test_email_failure_is_non_fatal(db_session, monkeypatch):
    """SendGrid raising must not crash the sync; alerts stay notified=False."""
    _configure_sendgrid(monkeypatch)
    account = await _seed_account_with_alerts(db_session, "444444444444", n_alerts=1)

    with patch("app.services.email_service.SendGridAPIClient") as MockClient:
        mock_client_instance = MagicMock()
        MockClient.return_value = mock_client_instance
        mock_client_instance.send.side_effect = Exception("SendGrid is down")

        # Must NOT raise out of the sync
        sent = await _send_pending_notifications(db_session, account)

    assert sent == 0

    notified_count = await db_session.scalar(
        select(func.count()).select_from(Alert).where(Alert.notified == True)  # noqa: E712
    )
    assert notified_count == 0


# ── Test 3: empty config → notifications skipped, no crash ───────────────────

@pytest.mark.anyio
async def test_unconfigured_sendgrid_skipped(db_session):
    """When SENDGRID_API_KEY is empty, the step is a no-op."""
    account = await _seed_account_with_alerts(db_session, "555555555555", n_alerts=1)

    # No monkeypatch — settings keep their empty defaults
    sent = await _send_pending_notifications(db_session, account)

    assert sent == 0
    notified_count = await db_session.scalar(
        select(func.count()).select_from(Alert).where(Alert.notified == True)  # noqa: E712
    )
    assert notified_count == 0


# ── Test 4: re-run is idempotent — already-notified alerts not re-sent ───────

@pytest.mark.anyio
async def test_already_notified_alerts_skipped_on_rerun(db_session, monkeypatch):
    _configure_sendgrid(monkeypatch)
    account = await _seed_account_with_alerts(db_session, "666666666666", n_alerts=1)

    with patch("app.services.email_service.SendGridAPIClient") as MockClient:
        mock_client_instance = MagicMock()
        MockClient.return_value = mock_client_instance
        mock_client_instance.send.return_value = MagicMock(status_code=202)

        first = await _send_pending_notifications(db_session, account)
        second = await _send_pending_notifications(db_session, account)

    assert first == 1
    assert second == 0
    # Only one send across both runs
    assert mock_client_instance.send.call_count == 1
