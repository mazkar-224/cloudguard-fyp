"""
Tests for the per-user AWS credential endpoints under /api/v1/settings.

What we prove:
  - POST validates the credentials against AWS (healthcheck) before saving, and
    stores them ENCRYPTED — the plaintext secret never lands in the DB column.
  - GET returns only a masked last-4 + region, never the secret or full key.
  - Credentials AWS rejects are not saved (400, no row written).
  - DELETE removes the saved credential.

The `client` fixture authenticates as a fixed fake user (id=1). The credentials
table has a FK to users, so we seed that user first. AWS is never really called:
we patch the settings router's `_healthcheck` to simulate success/failure.
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from app.models.aws_credential import AwsCredential
from app.models.user import User
from app.services import crypto_service

GOOD_BODY = {
    "access_key_id": "AKIAEXAMPLE1234567890",
    "secret_access_key": "wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY",
    "region": "us-east-1",
}

_OK = {"ok": True, "detail": "EC2 reachable in us-east-1 — permissions OK"}
_BAD = {"ok": False, "detail": "Access denied — credentials are invalid"}


def _patch_healthcheck(result: dict):
    """Patch the settings router's healthcheck to return *result* without AWS."""
    return patch("app.api.v1.settings._healthcheck", AsyncMock(return_value=result))


@pytest.fixture
async def seeded_user(db_session):
    """Insert the fake user (id=1) the `client` fixture authenticates as, so the
    aws_credentials FK to users.id is satisfiable."""
    user = User(id=1, email="tester@cloudguard.dev", hashed_password="x")
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.anyio
async def test_save_validates_and_encrypts(client, db_session, seeded_user):
    """POST stores credentials encrypted; the DB never holds the plaintext."""
    with _patch_healthcheck(_OK):
        resp = await client.post("/api/v1/settings/aws-credentials", json=GOOD_BODY)

    assert resp.status_code == 201

    cred = (await db_session.execute(select(AwsCredential))).scalar_one()

    # Stored values are ciphertext, not the plaintext we sent.
    assert cred.access_key_id_encrypted != GOOD_BODY["access_key_id"]
    assert cred.secret_access_key_encrypted != GOOD_BODY["secret_access_key"]

    # ...but they decrypt back to exactly what we sent.
    assert crypto_service.decrypt(cred.access_key_id_encrypted) == GOOD_BODY["access_key_id"]
    assert crypto_service.decrypt(cred.secret_access_key_encrypted) == GOOD_BODY["secret_access_key"]

    # The masked hint matches the last 4 chars of the access key id.
    assert cred.access_key_last4 == GOOD_BODY["access_key_id"][-4:]
    assert cred.region == "us-east-1"


@pytest.mark.anyio
async def test_get_never_leaks_secret(client, db_session, seeded_user):
    """GET returns only masked last-4 + region — never the secret or full key."""
    with _patch_healthcheck(_OK):
        await client.post("/api/v1/settings/aws-credentials", json=GOOD_BODY)

    resp = await client.get("/api/v1/settings/aws-credentials")
    assert resp.status_code == 200
    body = resp.json()

    assert body["access_key_last4"] == GOOD_BODY["access_key_id"][-4:]
    assert body["region"] == "us-east-1"

    # The secret and full access key id must NOT appear anywhere in the response.
    serialized = resp.text
    assert GOOD_BODY["secret_access_key"] not in serialized
    assert GOOD_BODY["access_key_id"] not in serialized
    assert "secret_access_key" not in body
    assert "access_key_id_encrypted" not in body
    assert "secret_access_key_encrypted" not in body


@pytest.mark.anyio
async def test_get_returns_null_when_none_saved(client, seeded_user):
    """GET returns null (not an error) when the user has saved nothing."""
    resp = await client.get("/api/v1/settings/aws-credentials")
    assert resp.status_code == 200
    assert resp.json() is None


@pytest.mark.anyio
async def test_bad_credentials_rejected(client, db_session, seeded_user):
    """Credentials AWS rejects are not stored — 400 and no row written."""
    with _patch_healthcheck(_BAD):
        resp = await client.post("/api/v1/settings/aws-credentials", json=GOOD_BODY)

    assert resp.status_code == 400

    count = (await db_session.execute(select(func.count()).select_from(AwsCredential))).scalar_one()
    assert count == 0


@pytest.mark.anyio
async def test_save_overwrites_existing(client, db_session, seeded_user):
    """Re-saving replaces in place — one credential set per user, no duplicates."""
    with _patch_healthcheck(_OK):
        await client.post("/api/v1/settings/aws-credentials", json=GOOD_BODY)
        new_body = {**GOOD_BODY, "access_key_id": "AKIANEWKEY0987654321", "region": "eu-west-1"}
        resp = await client.post("/api/v1/settings/aws-credentials", json=new_body)

    assert resp.status_code == 201

    rows = (await db_session.execute(select(AwsCredential))).scalars().all()
    assert len(rows) == 1
    assert rows[0].access_key_last4 == "4321"
    assert rows[0].region == "eu-west-1"


@pytest.mark.anyio
async def test_delete_removes_credential(client, db_session, seeded_user):
    """DELETE removes the saved credential; GET then returns null."""
    with _patch_healthcheck(_OK):
        await client.post("/api/v1/settings/aws-credentials", json=GOOD_BODY)

    resp = await client.delete("/api/v1/settings/aws-credentials")
    assert resp.status_code == 204

    count = (await db_session.execute(select(func.count()).select_from(AwsCredential))).scalar_one()
    assert count == 0


@pytest.mark.anyio
async def test_test_connection_reports_failure_without_saving(client, db_session, seeded_user):
    """POST /test-connection returns the healthcheck result and saves nothing."""
    with _patch_healthcheck(_BAD):
        resp = await client.post("/api/v1/settings/test-connection", json=GOOD_BODY)

    assert resp.status_code == 200
    assert resp.json()["ok"] is False

    count = (await db_session.execute(select(func.count()).select_from(AwsCredential))).scalar_one()
    assert count == 0
