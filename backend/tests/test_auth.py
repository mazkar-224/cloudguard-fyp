"""
Auth tests — the Phase 6.1 definition of done, in code.

These use `unauth_client`, which (unlike `client`) leaves the real
get_current_user dependency in place, so protected routes genuinely require a
valid token. We drive the full flow through HTTP: register a user, log in to
get a token, then prove a protected endpoint rejects anonymous callers and
accepts an authenticated one.

GET /api/v1/recommendations is used as the "protected endpoint" because it
returns 200 with an empty list when the DB has no data — no AWS call, no
seeding needed — so the only thing under test is the auth gate itself.
"""

import pytest

PROTECTED_URL = "/api/v1/recommendations"
REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"

CREDENTIALS = {"email": "azkar@cloudguard.dev", "password": "supersecret123"}


async def _register(client, **overrides):
    body = {**CREDENTIALS, **overrides}
    return await client.post(REGISTER_URL, json=body)


async def _login(client, **overrides):
    body = {**CREDENTIALS, **overrides}
    return await client.post(LOGIN_URL, json=body)


@pytest.mark.anyio
async def test_register_creates_user(unauth_client):
    """Registration returns 201 with the new user — and never the password."""
    resp = await _register(unauth_client)

    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == CREDENTIALS["email"]
    assert "id" in data and "created_at" in data
    assert "password" not in data
    assert "hashed_password" not in data


@pytest.mark.anyio
async def test_register_duplicate_email_rejected(unauth_client):
    """The same email can't register twice."""
    first = await _register(unauth_client)
    assert first.status_code == 201

    second = await _register(unauth_client)
    assert second.status_code == 409


@pytest.mark.anyio
async def test_login_returns_token(unauth_client):
    """Correct credentials yield a bearer access token."""
    await _register(unauth_client)

    resp = await _login(unauth_client)

    assert resp.status_code == 200
    data = resp.json()
    assert data["token_type"] == "bearer"
    assert isinstance(data["access_token"], str) and data["access_token"]


@pytest.mark.anyio
async def test_login_wrong_password_rejected(unauth_client):
    """A bad password is a 401, not a token."""
    await _register(unauth_client)

    resp = await _login(unauth_client, password="wrong-password")

    assert resp.status_code == 401
    assert "access_token" not in resp.json()


@pytest.mark.anyio
async def test_protected_endpoint_rejects_without_token(unauth_client):
    """No Authorization header → 401 from the protected route."""
    resp = await unauth_client.get(PROTECTED_URL)
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_protected_endpoint_rejects_garbage_token(unauth_client):
    """A malformed/forged token is rejected, not silently trusted."""
    resp = await unauth_client.get(
        PROTECTED_URL, headers={"Authorization": "Bearer not.a.real.jwt"}
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_protected_endpoint_accepts_with_token(unauth_client):
    """Register → login → call protected route with the token → 200."""
    await _register(unauth_client)
    token = (await _login(unauth_client)).json()["access_token"]

    resp = await unauth_client.get(
        PROTECTED_URL, headers={"Authorization": f"Bearer {token}"}
    )

    assert resp.status_code == 200
    # The recommendations list shape, proving we reached the real handler.
    assert "items" in resp.json()


@pytest.mark.anyio
async def test_me_returns_current_user(unauth_client):
    """GET /auth/me echoes back the logged-in user when given a valid token."""
    await _register(unauth_client)
    token = (await _login(unauth_client)).json()["access_token"]

    resp = await unauth_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert resp.status_code == 200
    assert resp.json()["email"] == CREDENTIALS["email"]
