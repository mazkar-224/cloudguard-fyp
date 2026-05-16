import pytest


@pytest.mark.anyio
async def test_health_returns_200(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_health_response_shape(client):
    """Response must always include status, version, and environment."""
    data = (await client.get("/api/v1/health")).json()

    assert data["status"] == "ok"
    assert "version" in data
    assert "environment" in data
