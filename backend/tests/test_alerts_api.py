"""
Tests for the /api/v1/alerts endpoints.

Uses the `client` fixture (get_db → test session, AWS mocked to raise) and
seeds alerts directly into the test DB. No AWS or SendGrid is involved here.

Seeded fixture (three alerts on three distinct days so the unique constraint
is never hit):
    A: today        status=new          severity=high    scope=total
    B: yesterday    status=new          severity=low     scope=service (EC2)
    C: two days ago status=acknowledged severity=medium  scope=service (S3)

    by_status   → new: 2, acknowledged: 1
    by_severity → low: 1, medium: 1, high: 1
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.alert import Alert
from app.models.cost import AwsAccount


@pytest.fixture
async def seeded_alerts(db_session):
    """Insert one account and three alerts with known status/severity/dates.

    Returns the three Alert objects so tests can reference their ids.
    """
    today = date.today()

    account = AwsAccount(account_id="123456789012")
    db_session.add(account)
    await db_session.flush()  # populate account.id

    alert_a = Alert(
        aws_account_id=account.id,
        alert_date=today,
        scope="total",
        service_name=None,
        amount_usd=Decimal("120.00"),
        baseline_mean=Decimal("10.00"),
        z_score=Decimal("8.50"),
        severity="high",
        status="new",
    )
    alert_b = Alert(
        aws_account_id=account.id,
        alert_date=today - timedelta(days=1),
        scope="service",
        service_name="Amazon EC2",
        amount_usd=Decimal("30.00"),
        baseline_mean=Decimal("12.00"),
        z_score=Decimal("2.30"),
        severity="low",
        status="new",
    )
    alert_c = Alert(
        aws_account_id=account.id,
        alert_date=today - timedelta(days=2),
        scope="service",
        service_name="Amazon S3",
        amount_usd=Decimal("45.00"),
        baseline_mean=Decimal("9.00"),
        z_score=Decimal("3.40"),
        severity="medium",
        status="acknowledged",
    )

    for a in (alert_a, alert_b, alert_c):
        db_session.add(a)
    await db_session.commit()

    return {"a": alert_a, "b": alert_b, "c": alert_c}


# ── GET /alerts ───────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_list_returns_all_newest_first(client, seeded_alerts):
    """All three alerts are returned, ordered newest alert_date first."""
    resp = await client.get("/api/v1/alerts")
    assert resp.status_code == 200

    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3
    # A (today) → B (yesterday) → C (two days ago)
    assert data["items"][0]["id"] == seeded_alerts["a"].id
    assert data["items"][-1]["id"] == seeded_alerts["c"].id


@pytest.mark.anyio
async def test_list_filter_by_status(client, seeded_alerts):
    """status=new returns only the two new alerts."""
    data = (await client.get("/api/v1/alerts?status=new")).json()

    assert data["total"] == 2
    assert {item["status"] for item in data["items"]} == {"new"}


@pytest.mark.anyio
async def test_list_filter_by_severity(client, seeded_alerts):
    """severity=high returns only the single high-severity alert."""
    data = (await client.get("/api/v1/alerts?severity=high")).json()

    assert data["total"] == 1
    assert data["items"][0]["id"] == seeded_alerts["a"].id
    assert data["items"][0]["severity"] == "high"


@pytest.mark.anyio
async def test_list_invalid_severity_returns_422(client):
    """An out-of-enum severity is rejected by FastAPI before the handler runs."""
    resp = await client.get("/api/v1/alerts?severity=catastrophic")
    assert resp.status_code == 422


# ── GET /alerts/count ─────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_count_groups_by_status_and_severity(client, seeded_alerts):
    data = (await client.get("/api/v1/alerts/count")).json()

    assert data["by_status"] == {"new": 2, "acknowledged": 1}
    assert data["by_severity"] == {"low": 1, "medium": 1, "high": 1}
    assert data["total"] == 3


@pytest.mark.anyio
async def test_count_zero_filled_when_empty(client):
    """With no alerts, all known keys are present and zero."""
    data = (await client.get("/api/v1/alerts/count")).json()

    assert data["by_status"] == {"new": 0, "acknowledged": 0}
    assert data["by_severity"] == {"low": 0, "medium": 0, "high": 0}
    assert data["total"] == 0


@pytest.mark.anyio
async def test_count_respects_days_window(client, seeded_alerts):
    """count uses the same days window as the list, so the badge can't count
    alerts the default list would hide. days=1 keeps today (A) + yesterday (B)
    and drops the two-days-ago acknowledged alert (C)."""
    data = (await client.get("/api/v1/alerts/count?days=1")).json()

    assert data["by_status"] == {"new": 2, "acknowledged": 0}
    assert data["by_severity"] == {"low": 1, "medium": 0, "high": 1}
    assert data["total"] == 2


# ── PATCH /alerts/{id} ────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_acknowledge_flips_status(client, seeded_alerts):
    """Acknowledging a 'new' alert flips its status and returns the update."""
    alert_id = seeded_alerts["a"].id

    resp = await client.patch(f"/api/v1/alerts/{alert_id}")
    assert resp.status_code == 200

    body = resp.json()
    assert body["id"] == alert_id
    assert body["status"] == "acknowledged"

    # And it's reflected in the counts.
    counts = (await client.get("/api/v1/alerts/count")).json()
    assert counts["by_status"] == {"new": 1, "acknowledged": 2}


@pytest.mark.anyio
async def test_acknowledge_nonexistent_returns_404(client, seeded_alerts):
    resp = await client.patch("/api/v1/alerts/999999")
    assert resp.status_code == 404
