"""
Tests for the recommendations API (app/api/v1/recommendations.py).

DB-backed against cloudguard_test, driven through the FastAPI app via the
`client` fixture (which points get_db at the test session). We seed
recommendation rows directly, then exercise the three endpoints.

Seed set (one AWS account):
  ebs_volume       vol-a   open       $100.00
  ebs_volume       vol-b   open         $8.00
  elastic_ip       eip-a   open         $3.60
  ec2_instance_idle i-idle open         $0.00
  ebs_volume       vol-x   dismissed  $999.00   ← excluded from open views

Open totals: 4 rows, $111.60. ebs_volume(open) = 2 rows, $108.00.
"""

from decimal import Decimal

import pytest

from app.models.cost import AwsAccount
from app.models.recommendation import Recommendation

OPEN_TOTAL = pytest.approx(111.60)


async def _seed(db) -> AwsAccount:
    account = AwsAccount(account_id="123456789012")
    db.add(account)
    await db.flush()

    def rec(resource_type, resource_id, usd, status="open"):
        return Recommendation(
            aws_account_id=account.id,
            resource_type=resource_type,
            resource_id=resource_id,
            region="us-east-1",
            reason=f"{resource_type} {resource_id} wasteful",
            estimated_monthly_usd=Decimal(str(usd)),
            status=status,
        )

    db.add_all([
        rec("ebs_volume", "vol-a", "100.00"),
        rec("ebs_volume", "vol-b", "8.00"),
        rec("elastic_ip", "eip-a", "3.60"),
        rec("ec2_instance_idle", "i-idle", "0.00"),
        rec("ebs_volume", "vol-x", "999.00", status="dismissed"),
    ])
    await db.commit()
    return account


@pytest.mark.anyio
async def test_list_defaults_to_open_sorted_by_dollars_desc(client, db_session):
    await _seed(db_session)

    resp = await client.get("/api/v1/recommendations")
    assert resp.status_code == 200
    body = resp.json()

    # Default status='open' → the dismissed row is excluded.
    assert body["total"] == 4
    assert body["total_estimated_savings"] == OPEN_TOTAL

    ids = [item["resource_id"] for item in body["items"]]
    # Sorted by estimated_monthly_usd descending.
    assert ids == ["vol-a", "vol-b", "eip-a", "i-idle"]
    assert "vol-x" not in ids


@pytest.mark.anyio
async def test_list_filters_by_resource_type(client, db_session):
    await _seed(db_session)

    resp = await client.get(
        "/api/v1/recommendations", params={"resource_type": "ebs_volume"}
    )
    assert resp.status_code == 200
    body = resp.json()

    # Only the two OPEN ebs_volume rows (the dismissed vol-x is filtered out).
    assert body["total"] == 2
    assert body["total_estimated_savings"] == pytest.approx(108.00)
    assert [i["resource_id"] for i in body["items"]] == ["vol-a", "vol-b"]


@pytest.mark.anyio
async def test_list_can_filter_to_dismissed(client, db_session):
    await _seed(db_session)

    resp = await client.get("/api/v1/recommendations", params={"status": "dismissed"})
    assert resp.status_code == 200
    body = resp.json()

    assert body["total"] == 1
    assert [i["resource_id"] for i in body["items"]] == ["vol-x"]


@pytest.mark.anyio
async def test_summary_totals_and_breakdown(client, db_session):
    await _seed(db_session)

    resp = await client.get("/api/v1/recommendations/summary")
    assert resp.status_code == 200
    body = resp.json()

    assert body["total_monthly_savings"] == OPEN_TOTAL
    assert body["open_count"] == 4

    by_type = {b["resource_type"]: b for b in body["by_resource_type"]}
    assert by_type["ebs_volume"]["count"] == 2
    assert by_type["ebs_volume"]["monthly_savings"] == pytest.approx(108.00)
    assert by_type["elastic_ip"]["monthly_savings"] == pytest.approx(3.60)
    assert by_type["ec2_instance_idle"]["monthly_savings"] == pytest.approx(0.0)
    # Dismissed rows never appear in the summary.
    assert all(b["count"] >= 0 for b in body["by_resource_type"])
    assert sum(b["count"] for b in body["by_resource_type"]) == 4

    # Breakdown is sorted by savings descending.
    savings_order = [b["monthly_savings"] for b in body["by_resource_type"]]
    assert savings_order == sorted(savings_order, reverse=True)


@pytest.mark.anyio
async def test_patch_dismiss_and_resolve(client, db_session):
    await _seed(db_session)

    # Grab an open recommendation's id.
    listing = (await client.get("/api/v1/recommendations")).json()
    target_id = listing["items"][0]["id"]

    dismiss = await client.patch(
        f"/api/v1/recommendations/{target_id}", json={"status": "dismissed"}
    )
    assert dismiss.status_code == 200
    assert dismiss.json()["status"] == "dismissed"

    # A different row → resolved.
    other_id = listing["items"][1]["id"]
    resolve = await client.patch(
        f"/api/v1/recommendations/{other_id}", json={"status": "resolved"}
    )
    assert resolve.status_code == 200
    assert resolve.json()["status"] == "resolved"

    # Both are now gone from the default (open) list → open total dropped by 2.
    after = (await client.get("/api/v1/recommendations")).json()
    assert after["total"] == 2


@pytest.mark.anyio
async def test_patch_rejects_invalid_status(client, db_session):
    await _seed(db_session)
    target_id = (await client.get("/api/v1/recommendations")).json()["items"][0]["id"]

    resp = await client.patch(
        f"/api/v1/recommendations/{target_id}", json={"status": "open"}
    )
    # 'open' is not an allowed transition target — Pydantic Literal rejects it.
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_patch_404_for_unknown_id(client, db_session):
    await _seed(db_session)

    resp = await client.patch(
        "/api/v1/recommendations/999999", json={"status": "resolved"}
    )
    assert resp.status_code == 404
