"""
Integration tests for anomaly detection wired into the sync job.

Strategy
--------
We bypass the HTTP layer and call sync_cost_data() directly so we can
control the DB state precisely.

Setup for each test:
  1. Insert an AwsAccount + 20 days of normal cost records directly.
  2. Mock AWS to return one spike day (today-1).
  3. Patch _fetch_account_id_sync so the job finds our seeded account.
  4. Call sync_cost_data() — it upserts the spike then runs detection.

Data design
-----------
Baseline: 20 days alternating $4.50 / $5.50 → mean=$5.00, std=$0.50
Spike:    $50.00 on the most recent day → z = (50-5)/0.5 = 90 → high

Both total-scope and service-scope (Amazon EC2) anomalies fire.
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import func, select

from app.jobs.cost_sync import sync_cost_data
from app.models.alert import Alert
from app.models.cost import AwsAccount, CostRecord
from app.services.aws_cost_service import AwsCostService


# ── helpers ───────────────────────────────────────────────────────────────────

async def _seed_baseline(db_session, account_id_str: str):
    """
    Insert an AwsAccount + 20 normal days into the test DB.
    Returns the seeded AwsAccount so callers can verify FK relationships.
    """
    today = date.today()
    account = AwsAccount(account_id=account_id_str)
    db_session.add(account)
    await db_session.flush()

    for i in range(20):
        # Rows span today-21 (oldest) through today-2 (newest normal day).
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


def _spike_aws_mock():
    """Mock AWS service that returns a single spike row for yesterday."""
    spike_date = str(date.today() - timedelta(days=1))
    mock = MagicMock(spec=AwsCostService)
    mock.get_daily_costs = AsyncMock(return_value=[
        {"date": spike_date, "service": "Amazon EC2", "cost": 50.00},
    ])
    return mock


# ── Test 1: spike creates a total-scope alert ─────────────────────────────────

@pytest.mark.anyio
async def test_spike_creates_total_alert(db_session):
    """
    20 normal days + 1 spike day must produce at least one Alert row
    with scope='total'.
    """
    await _seed_baseline(db_session, "111111111111")
    mock_aws = _spike_aws_mock()

    with patch("app.jobs.cost_sync._fetch_account_id_sync", return_value="111111111111"):
        summary = await sync_cost_data(db_session, mock_aws)

    # At least one alert was created (total + possibly service-scope)
    assert summary.new_alerts_created >= 1

    # A total-scope alert exists
    total_count = await db_session.scalar(
        select(func.count()).select_from(Alert).where(Alert.scope == "total")
    )
    assert total_count == 1

    # Check the alert has sensible values
    alert = (await db_session.execute(
        select(Alert).where(Alert.scope == "total")
    )).scalar_one()

    assert alert.severity == "high"          # z=90 is well above the high threshold
    assert alert.status == "new"             # default lifecycle state
    assert alert.notified is False           # email not sent yet
    assert float(alert.z_score) > 2.0
    assert float(alert.amount_usd) == 50.0
    assert alert.service_name is None        # total scope has no service


# ── Test 2: second run creates zero new alerts ────────────────────────────────

@pytest.mark.anyio
async def test_sync_detection_idempotent(db_session):
    """
    Running the sync twice must not create duplicate Alert rows.
    The ON CONFLICT DO NOTHING constraint makes the second run a silent no-op.
    """
    await _seed_baseline(db_session, "222222222222")
    mock_aws = _spike_aws_mock()

    with patch("app.jobs.cost_sync._fetch_account_id_sync", return_value="222222222222"):
        first = await sync_cost_data(db_session, mock_aws)
        second = await sync_cost_data(db_session, mock_aws)

    assert first.new_alerts_created >= 1     # first run creates alerts
    assert second.new_alerts_created == 0    # second run is a no-op

    # Total alert count equals what the first run created — nothing added
    total_alerts = await db_session.scalar(
        select(func.count()).select_from(Alert)
    )
    assert total_alerts == first.new_alerts_created
