"""Tests for meta mutation endpoints.

Tests for creating, updating, and deleting curriculum metadata:
grades, subjects, and topics.
"""

import asyncio

from fastapi.testclient import TestClient

from somaai.db.models import Grade, Subject, Topic
from somaai.db.session import async_session_maker
from somaai.modules.meta.service import invalidate_meta_cache


def _run(coro):
    """Run async code from sync test."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


async def _cleanup_all():
    """Remove all seeded data."""
    from sqlalchemy import delete

    async with async_session_maker() as db:
        await db.execute(delete(Topic))
        await db.execute(delete(Subject))
        await db.execute(delete(Grade))
        await db.commit()


class TestMetaMutations:
    """POST, PATCH, DELETE /api/v1/meta/* — metadata mutations."""

    def setup_method(self):
        invalidate_meta_cache()
        _run(_cleanup_all())

    def teardown_method(self):
        invalidate_meta_cache()
        _run(_cleanup_all())

    # --- Grades ---

    def test_create_grade(self, client: TestClient):
        """POST /meta/grades — create a new grade."""
        payload = {
            "id": "T1",
            "name": "Test Grade",
            "level": "secondary",
            "display_order": 100,
        }
        response = client.post("/api/v1/meta/grades", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "T1"
        assert data["name"] == "Test Grade"

        # Verify it exists
        get_resp = client.get("/api/v1/meta/grades")
        assert any(g["id"] == "T1" for g in get_resp.json())

    def test_update_grade(self, client: TestClient):
        """PATCH /meta/grades/{id} — update a grade."""
        # Setup
        _run(_cleanup_all())
        client.post(
            "/api/v1/meta/grades",
            json={
                "id": "T1",
                "name": "Old Name",
                "level": "primary",
                "display_order": 1,
            },
        )

        # Update
        response = client.patch("/api/v1/meta/grades/T1", json={"name": "New Name"})
        assert response.status_code == 200
        assert response.json()["name"] == "New Name"

        # Verify cache invalidation
        get_resp = client.get("/api/v1/meta/grades")
        assert any(g["name"] == "New Name" for g in get_resp.json())

    def test_delete_grade(self, client: TestClient):
        """DELETE /meta/grades/{id} — delete a grade."""
        # Setup
        client.post(
            "/api/v1/meta/grades",
            json={"id": "T1", "name": "Test", "level": "primary", "display_order": 1},
        )

        # Delete
        response = client.delete("/api/v1/meta/grades/T1")
        assert response.status_code == 204

        # Verify it's gone
        get_resp = client.get("/api/v1/meta/grades")
        assert not any(g["id"] == "T1" for g in get_resp.json())

    # --- Subjects ---

    def test_create_subject(self, client: TestClient):
        """POST /meta/subjects — create a new subject."""
        payload = {
            "id": "test_subj",
            "name": "Test Subject",
            "icon": "test-icon",
            "display_order": 50,
        }
        response = client.post("/api/v1/meta/subjects", json=payload)
        assert response.status_code == 201
        assert response.json()["id"] == "test_subj"

    def test_update_subject(self, client: TestClient):
        """PATCH /meta/subjects/{id} — update a subject."""
        client.post(
            "/api/v1/meta/subjects",
            json={"id": "ts", "name": "Old", "display_order": 1},
        )
        response = client.patch("/api/v1/meta/subjects/ts", json={"name": "New"})
        assert response.status_code == 200
        assert response.json()["name"] == "New"

    def test_delete_subject(self, client: TestClient):
        """DELETE /meta/subjects/{id} — delete a subject."""
        client.post(
            "/api/v1/meta/subjects",
            json={"id": "ts", "name": "Old", "display_order": 1},
        )
        assert client.delete("/api/v1/meta/subjects/ts").status_code == 204
        assert client.get("/api/v1/meta/subjects").json() == []

    # --- Topics ---

    def test_create_topic(self, client: TestClient):
        """POST /meta/topics — create a new topic."""
        # Need a grade and subject for topic FKs / logic
        client.post(
            "/api/v1/meta/grades",
            json={"id": "S1", "name": "S1", "level": "secondary", "display_order": 1},
        )
        client.post(
            "/api/v1/meta/subjects",
            json={"id": "math", "name": "Math", "display_order": 1},
        )

        payload = {
            "title": "Algebra Basics",
            "grade": "S1",
            "subject": "math",
            "page_start": 10,
            "page_end": 20,
            "path": ["Unit 1", "Algebra Basics"],
        }
        response = client.post("/api/v1/meta/topics", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Algebra Basics"
        assert "topic_id" in data

    def test_update_topic(self, client: TestClient):
        """PATCH /meta/topics/{id} — update a topic."""
        # Setup
        client.post(
            "/api/v1/meta/grades",
            json={"id": "S1", "name": "S1", "level": "sec", "display_order": 1},
        )
        client.post(
            "/api/v1/meta/subjects",
            json={"id": "math", "name": "Math", "display_order": 1},
        )
        t_data = client.post(
            "/api/v1/meta/topics",
            json={
                "title": "Old",
                "grade": "S1",
                "subject": "math",
                "page_start": 1,
                "page_end": 2,
            },
        ).json()
        tid = t_data["topic_id"]

        # Update
        response = client.patch(f"/api/v1/meta/topics/{tid}", json={"title": "New"})
        assert response.status_code == 200
        assert response.json()["title"] == "New"

    def test_delete_topic(self, client: TestClient):
        """DELETE /meta/topics/{id} — delete a topic."""
        client.post(
            "/api/v1/meta/grades",
            json={"id": "S1", "name": "S1", "level": "sec", "display_order": 1},
        )
        client.post(
            "/api/v1/meta/subjects",
            json={"id": "math", "name": "Math", "display_order": 1},
        )
        t_data = client.post(
            "/api/v1/meta/topics",
            json={
                "title": "Old",
                "grade": "S1",
                "subject": "math",
                "page_start": 1,
                "page_end": 2,
            },
        ).json()
        tid = t_data["topic_id"]

        assert client.delete(f"/api/v1/meta/topics/{tid}").status_code == 204
        assert client.get("/api/v1/meta/topics?grade=S1&subject=math").json() == []
