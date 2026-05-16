"""
Tests for the three cost endpoints.

All tests use the `client` fixture which seeds data directly into the test DB.
Because the endpoints check the DB first, AWS is never called here — we're
testing the DB path exclusively.

Known values in the seeded fixture
====================================
  yesterday:   Amazon EC2  $18.50
  yesterday:   Amazon S3    $4.25
  two_days_ago Amazon EC2  $20.00
  ─────────────────────────────────
  EC2 total:               $38.50
  S3  total:                $4.25
  Grand total:             $42.75
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal

from app.models.cost import AwsAccount, CostRecord


# ── Fixture: seed the test database with known data ───────────────────────────

@pytest.fixture
async def seeded_costs(db_session):
    """
    Inserts one AWS account and three cost records with predictable values.
    Dates are relative to today so they always fall inside the default 30-day
    query window.
    """
    today = date.today()
    yesterday = today - timedelta(days=1)
    two_days_ago = today - timedelta(days=2)

    account = AwsAccount(account_id="123456789012")
    db_session.add(account)
    await db_session.flush()  # get account.id without committing

    records = [
        CostRecord(
            aws_account_id=account.id,
            date=yesterday,
            service_name="Amazon EC2",
            amount_usd=Decimal("18.50"),
        ),
        CostRecord(
            aws_account_id=account.id,
            date=yesterday,
            service_name="Amazon S3",
            amount_usd=Decimal("4.25"),
        ),
        CostRecord(
            aws_account_id=account.id,
            date=two_days_ago,
            service_name="Amazon EC2",
            amount_usd=Decimal("20.00"),
        ),
    ]
    for r in records:
        db_session.add(r)
    await db_session.commit()


# ── GET /costs/daily ──────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_daily_costs_returns_list(client, seeded_costs):
    """Endpoint returns a non-empty list when the DB has data."""
    response = await client.get("/api/v1/costs/daily?days=30")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


@pytest.mark.anyio
async def test_daily_costs_row_shape(client, seeded_costs):
    """Every row must have exactly date, service, and cost — nothing else."""
    data = (await client.get("/api/v1/costs/daily?days=30")).json()

    for row in data:
        assert "date" in row
        assert "service" in row
        assert "cost" in row
        assert isinstance(row["cost"], float)


@pytest.mark.anyio
async def test_daily_costs_invalid_days_returns_422(client):
    """
    Negative test: days=0 is below the Query(ge=1) minimum.
    FastAPI should reject it with 422 Unprocessable Entity before the
    handler even runs.
    """
    response = await client.get("/api/v1/costs/daily?days=0")
    assert response.status_code == 422


# ── GET /costs/by-service ─────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_by_service_aggregates_correctly(client, seeded_costs):
    """
    EC2 appears on two days ($18.50 + $20.00 = $38.50).
    The endpoint should sum them into a single row.
    """
    start = (date.today() - timedelta(days=7)).isoformat()
    end = date.today().isoformat()

    data = (
        await client.get(f"/api/v1/costs/by-service?start_date={start}&end_date={end}")
    ).json()

    ec2 = next((r for r in data if r["service"] == "Amazon EC2"), None)
    assert ec2 is not None
    assert ec2["cost"] == pytest.approx(38.50)


@pytest.mark.anyio
async def test_by_service_sorted_descending(client, seeded_costs):
    """Most expensive service must come first."""
    start = (date.today() - timedelta(days=7)).isoformat()
    end = date.today().isoformat()

    data = (
        await client.get(f"/api/v1/costs/by-service?start_date={start}&end_date={end}")
    ).json()

    costs = [r["cost"] for r in data]
    assert costs == sorted(costs, reverse=True)


# ── GET /costs/summary ────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_summary_total_is_correct(client, seeded_costs):
    """Grand total must equal the sum of all seeded records: $42.75."""
    data = (await client.get("/api/v1/costs/summary?days=30")).json()

    assert data["total_usd"] == pytest.approx(42.75)


@pytest.mark.anyio
async def test_summary_top_service_is_ec2(client, seeded_costs):
    """
    EC2 has $38.50 total vs S3's $4.25 — it must be the top service.
    top_service_cost must also be correct.
    """
    data = (await client.get("/api/v1/costs/summary?days=30")).json()

    assert data["top_service"] == "Amazon EC2"
    assert data["top_service_cost"] == pytest.approx(38.50)


@pytest.mark.anyio
async def test_summary_source_is_database(client, seeded_costs):
    """When the DB has data, source must be 'database'."""
    data = (await client.get("/api/v1/costs/summary?days=30")).json()

    assert data["source"] == "database"
