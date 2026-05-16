"""
Tests for POST /api/v1/admin/sync.

Uses `sync_client` which:
  - Overrides get_db with the test DB session
  - Overrides get_aws_service with a mock returning MOCK_COST_ROWS (3 rows)
  - Patches _fetch_account_id_sync to return "123456789012"

MOCK_COST_ROWS (defined in conftest.py):
  2026-05-10  Amazon EC2  $18.50
  2026-05-10  Amazon S3    $4.25
  2026-05-11  Amazon EC2  $20.00
  → 3 rows expected in cost_records after sync
"""

import pytest
from sqlalchemy import func, select

from app.models.cost import CostRecord


@pytest.mark.anyio
async def test_sync_returns_200(sync_client):
    """Manual sync endpoint must return HTTP 200."""
    response = await sync_client.post("/api/v1/admin/sync")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_sync_response_shape(sync_client):
    """Response must contain rows_upserted (int) and duration_seconds (float)."""
    data = (await sync_client.post("/api/v1/admin/sync")).json()

    assert "rows_upserted" in data
    assert "duration_seconds" in data
    assert isinstance(data["rows_upserted"], int)
    assert isinstance(data["duration_seconds"], float)


@pytest.mark.anyio
async def test_sync_populates_database(sync_client, db_session):
    """
    After a sync the test database must contain exactly as many cost_records
    as the mock AWS service returned (3 rows from MOCK_COST_ROWS).
    """
    await sync_client.post("/api/v1/admin/sync")

    count = await db_session.scalar(
        select(func.count()).select_from(CostRecord)
    )
    assert count == 3


@pytest.mark.anyio
async def test_sync_reports_correct_row_count(sync_client):
    """rows_upserted in the response must equal the number of rows processed."""
    data = (await sync_client.post("/api/v1/admin/sync")).json()

    # MOCK_COST_ROWS has 3 entries
    assert data["rows_upserted"] == 3


@pytest.mark.anyio
async def test_sync_is_idempotent(sync_client, db_session):
    """
    Running the sync twice with the same data must NOT duplicate rows.
    ON CONFLICT DO UPDATE means the second sync updates in place.

    This is the most important property of the sync job — evaluators will
    run it multiple times during the demo.
    """
    await sync_client.post("/api/v1/admin/sync")
    count_after_first = await db_session.scalar(
        select(func.count()).select_from(CostRecord)
    )

    await sync_client.post("/api/v1/admin/sync")
    count_after_second = await db_session.scalar(
        select(func.count()).select_from(CostRecord)
    )

    assert count_after_first == count_after_second == 3
