"""Tests for SessionMiddleware.

Verifies cookie-based session management: creation, reuse, and
actor_id assignment via the in-memory store.
"""

from fastapi.testclient import TestClient


class TestSessionMiddleware:
    """Test the cookie-based session middleware."""

    def test_first_request_creates_session_cookie(self, client: TestClient):
        """First API request should set a session cookie."""
        resp = client.get("/api/v1/chat/conversations")
        assert resp.status_code == 200

        cookie = resp.cookies.get("somaai_session")
        assert cookie, "Session cookie should be set"

        from somaai.middleware.session import _memory_store

        assert cookie in _memory_store
        session_data = _memory_store[cookie]
        assert "actor_id" in session_data
        assert session_data["actor_id"].startswith("anon_")
        assert session_data["is_authenticated"] is False

    def test_subsequent_requests_reuse_session(self, client: TestClient):
        """Subsequent requests with cookie reuse the session."""
        from somaai.middleware.session import _memory_store

        resp1 = client.get("/api/v1/chat/conversations")
        cookie1 = resp1.cookies.get("somaai_session")
        actor_1 = _memory_store[cookie1]["actor_id"]

        # Second request with same client reuses cookie
        client.get("/api/v1/chat/conversations")
        assert _memory_store[cookie1]["actor_id"] == actor_1

    def test_health_endpoint_skips_session(self, client: TestClient):
        """Health check should not create a session."""
        from somaai.middleware.session import _memory_store

        initial_count = len(_memory_store)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert len(_memory_store) == initial_count
        assert "somaai_session" not in resp.cookies

    def test_session_provides_actor_id_to_endpoints(self, client: TestClient):
        """Endpoints should see actor_id from session middleware."""
        resp = client.post(
            "/api/v1/chat/conversations",
            json={"grade": "S1", "subject": "science"},
        )
        assert resp.status_code == 201

        # List should find the conversation
        list_resp = client.get("/api/v1/chat/conversations")
        convos = list_resp.json()["conversations"]
        assert len(convos) >= 1

    def test_clear_memory_store(self):
        """clear_memory_store should empty the store."""
        from somaai.middleware.session import (
            _memory_store,
            clear_memory_store,
        )

        _memory_store["test_token"] = {"actor_id": "anon_test"}
        assert len(_memory_store) > 0
        clear_memory_store()
        assert len(_memory_store) == 0
