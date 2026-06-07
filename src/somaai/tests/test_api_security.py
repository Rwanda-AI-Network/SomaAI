import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_v1_endpoints_require_api_key(async_client: AsyncClient):
    """Verify that v1 endpoints return 401 without API key."""
    # Attempt to list conversations without X-API-Key header
    response = await async_client.get("/api/v1/chat/conversations")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_v1_endpoints_allow_valid_api_key(async_client: AsyncClient):
    """Verify that v1 endpoints allow access with a valid API key."""
    from somaai.api.security import get_api_key_auth

    auth = get_api_key_auth()
    test_key = "test-secret-key-security"
    await auth.add_key(test_key, {"user": "tester"})

    # Attempt with valid API key
    response = await async_client.get(
        "/api/v1/chat/conversations", headers={"X-API-Key": test_key}
    )
    # Should not be 401.
    assert response.status_code != 401
