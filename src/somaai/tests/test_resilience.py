"""Hardened resilience and security tests.

Tests extreme scenarios:
- Large payloads (denial of service / memory limits)
- session hijacking / cross-actor isolation
- Database and external service resilience (mocked)
"""

from fastapi.testclient import TestClient

from somaai.deps import get_actor_id


def _create_convo(client: TestClient):
    resp = client.post(
        "/api/v1/chat/conversations", json={"grade": "S1", "subject": "science"}
    )
    assert resp.status_code == 201
    return resp.json()["id"]


class TestResilience:
    """Stress and robustness tests."""

    def test_large_question_stress(self, client: TestClient):
        """Robustness: Send a very large question (50KB) to ensure no crash."""
        convo_id = _create_convo(client)
        # 50k 'a's
        large_question = "a" * 50000

        resp = client.post(
            f"/api/v1/chat/conversations/{convo_id}/ask",
            json={"question": large_question, "user_role": "student"},
        )
        # Pydantic validation should catch this with 422
        assert resp.status_code == 422

    def test_malformed_json_resilience(self, client: TestClient):
        """Robustness: Invalid JSON should return 400/422, not 500."""
        resp = client.post(
            "/api/v1/chat/conversations",
            content="{invalid json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code in (400, 422)

    def test_sql_injection_attempt_in_search(self, client: TestClient):
        """Security: Attempt SQL injection in metadata filters."""
        # Using a payload that tries to break out of SQL strings
        injection_payload = "S1' OR '1'='1"
        resp = client.get(f"/api/v1/chat/conversations?grade={injection_payload}")
        assert resp.status_code == 200  # Should just return 0 results, not crash
        assert len(resp.json()["conversations"]) == 0


class TestSecurityIsolation:
    """Deep security tests for actor isolation."""

    def test_session_hijacking_prevention(self, client: TestClient):
        """CRITICAL: One actor's session cannot access another's data."""
        # 1. Actor A creates data
        resp_a = client.post(
            "/api/v1/chat/conversations", json={"grade": "S1", "subject": "science"}
        )
        convo_id = resp_a.json()["id"]
        cookie_a = client.cookies.get("somaai_session")

        # 2. Get Actor B's session
        client.cookies.clear()
        client.app.dependency_overrides[get_actor_id] = lambda: "actor-b"
        try:
            # Actor B tries to access Actor A's data without cookie
            # Now Actor B TRYS to use Actor A's cookie (if they stole it)
            # If session is tied to internal actor_id, it might still work
            # But here, dependency_override is forcing actor_id to "actor-b".
            # The backend SHOULD check convo.actor_id == current_actor_id ("actor-b").

            client.cookies.set("somaai_session", cookie_a)
            resp = client.get(f"/api/v1/chat/conversations/{convo_id}")
            assert resp.status_code == 404
        finally:
            del client.app.dependency_overrides[get_actor_id]

    def test_delete_other_actor_conversation(self, client: TestClient):
        """Security: Actor B cannot delete Actor A's conversation."""
        convo_a = _create_convo(client)

        client.app.dependency_overrides[get_actor_id] = lambda: "actor-b"
        try:
            resp = client.delete(f"/api/v1/chat/conversations/{convo_a}")
            assert resp.status_code == 404
        finally:
            del client.app.dependency_overrides[get_actor_id]
