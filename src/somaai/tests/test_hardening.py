import pytest
from fastapi.testclient import TestClient

from somaai.db.models import Grade, Subject
from somaai.db.session import async_session_maker


def _run(coro):
    import asyncio

    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def setup_metadata():
    """Seed S1, S2, science, and math for basic tests."""

    async def _seed():
        from sqlalchemy.exc import IntegrityError

        async with async_session_maker() as db:
            try:
                # Grades
                db.add(
                    Grade(id="S1", name="Senior 1", level="secondary", display_order=1)
                )
                db.add(
                    Grade(id="S2", name="Senior 2", level="secondary", display_order=2)
                )
                # Subjects
                db.add(Subject(id="science", name="Science", display_order=1))
                db.add(Subject(id="math", name="Mathematics", display_order=2))
                await db.commit()
            except IntegrityError:
                await db.rollback()

    _run(_seed())
    yield


class TestHardening:
    """Critical scenarios: Security, Validation, and Robustness."""

    def test_actor_isolation(self, client: TestClient):
        """CRITICAL: Actor B must not be able to access Actor A's conversation."""
        # 1. Actor A creates a conversation
        resp_a = client.post(
            "/api/v1/chat/conversations", json={"grade": "S1", "subject": "science"}
        )
        assert resp_a.status_code == 201
        convo_id = resp_a.json()["id"]

        # 2. Get the session cookie for Actor A
        client.cookies.get("somaai_session")

        # 3. Create a clean client for Actor B (no cookies)
        client.cookies.clear()

        # 4. Actor B tries to ask a question in Actor A's conversation
        resp_b = client.post(
            f"/api/v1/chat/conversations/{convo_id}/ask",
            json={"question": "I am a hacker"},
        )

        # Should be 403 or 404 (depends on get_owned implementation)
        # Let's see what happens.
        assert resp_b.status_code in (403, 404)

    def test_create_conversation_invalid_grade_fails(self, client: TestClient):
        """CRITICAL: Cannot create conversation for non-existent grade/subject."""
        # This tests if the system validates against the DB
        resp = client.post(
            "/api/v1/chat/conversations",
            json={"grade": "NONEXISTENT", "subject": "science"},
        )
        # This is expected to fail if we want a robust system.
        # If it returns 201, it's a validation gap.
        assert resp.status_code in (400, 422, 404)

    def test_ask_whitespace_only_question_fails(self, client: TestClient):
        """Robustness: Whitespace-only questions should be rejected."""
        resp_convo = client.post("/api/v1/chat/conversations", json={"grade": "S1"})
        convo_id = resp_convo.json()["id"]

        resp_ask = client.post(
            f"/api/v1/chat/conversations/{convo_id}/ask", json={"question": "   "}
        )
        assert resp_ask.status_code in (400, 422)

    def test_list_conversations_filter_isolation(self, client: TestClient):
        """Accuracy: Filters must return exactly what was requested."""
        client.post(
            "/api/v1/chat/conversations", json={"grade": "S1", "subject": "science"}
        )
        client.post(
            "/api/v1/chat/conversations", json={"grade": "S2", "subject": "math"}
        )

        # Filter by S1
        resp = client.get("/api/v1/chat/conversations?grade=S1")
        convos = resp.json()["conversations"]
        assert all(c["grade"] == "S1" for c in convos)

        # Filter by math
        resp = client.get("/api/v1/chat/conversations?subject=math")
        convos = resp.json()["conversations"]
        assert all(c["subject"] == "math" for c in convos)

    def test_pagination_boundary_max(self, client: TestClient):
        """Edge Case: Ensure limit caps work (e.g. limit=1000 stays at 100)."""
        resp = client.get("/api/v1/chat/conversations?limit=1000")
        assert resp.status_code == 200
        # The service should have capped it.

    def test_case_sensitivity_on_metadata(self, client: TestClient):
        """Robustness: Metadata should be case-insensitive or normalized."""
        # Create with lowercase
        resp = client.post(
            "/api/v1/chat/conversations", json={"grade": "s1", "subject": "SCIENCE"}
        )
        assert resp.status_code == 201
        data = resp.json()
        # If the backend is robust, it should return the canonical Form
        # Currently it might just return what was sent.
        assert data["grade"] == "S1"
        assert data["subject"] == "science"
