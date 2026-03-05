"""Tests for ConversationService.

Unit-like tests exercising conversation CRUD via the API layer,
verifying ownership isolation, listing, and title management.
"""

from fastapi.testclient import TestClient


def _create_conversation(
    client: TestClient,
    grade: str = "S1",
    subject: str = "social_studies",
    title: str | None = None,
) -> dict:
    """Helper: create a conversation and return the response dict."""
    payload = {"grade": grade, "subject": subject}
    if title:
        payload["title"] = title
    resp = client.post(
        "/api/v1/chat/conversations",
        json=payload,
    )
    if resp.status_code != 201:
        print(f"DEBUG REQ: {grade} {subject}")
        print(f"DEBUG RESP: {resp.status_code} - {resp.text}")
    assert resp.status_code == 201
    return resp.json()


def _ask_in_conversation(
    client: TestClient,
    conversation_id: str,
    question: str = "What is photosynthesis?",
    grade: str = "S2",
    subject: str = "science",
) -> dict:
    """Helper: ask a question in a conversation."""
    resp = client.post(
        f"/api/v1/chat/conversations/{conversation_id}/ask",
        json={
            "question": question,
            "user_role": "student",
        },
    )
    assert resp.status_code == 201
    return resp.json()


class TestConversationCRUD:
    """Test conversation create/list via API."""

    def test_create_sets_defaults(self, client: TestClient):
        data = _create_conversation(client)
        assert data["title"] == "New Chat"
        assert data["grade"] == "S1"
        assert data["subject"] == "social_studies"

    def test_create_with_explicit_title(self, client: TestClient):
        resp = client.post(
            "/api/v1/chat/conversations",
            json={
                "grade": "S1",
                "subject": "social_studies",
                "title": "Custom Title",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["title"] == "Custom Title"

    def test_create_rejects_whitespace_title(self, client: TestClient):
        resp = client.post(
            "/api/v1/chat/conversations",
            json={"grade": "S1", "title": "   "},
        )
        assert resp.status_code == 422

    def test_list_empty_for_new_actor(self, client: TestClient):
        resp = client.get("/api/v1/chat/conversations")
        assert resp.status_code == 200
        assert resp.json()["conversations"] == []

    def test_list_returns_own_conversations(
        self, client: TestClient
    ):
        c1 = _create_conversation(
            client, grade="S1", subject="science"
        )
        c2 = _create_conversation(
            client, grade="S2", subject="mathematics"
        )

        resp = client.get("/api/v1/chat/conversations")
        ids = [
            c["id"] for c in resp.json()["conversations"]
        ]
        assert c1["id"] in ids
        assert c2["id"] in ids

    def test_list_ordered_by_most_recent(
        self, client: TestClient
    ):
        """Most recently active conversations should come first."""
        c1 = _create_conversation(client)
        c2 = _create_conversation(client, subject="mathematics")

        # Ask in c1 to make it more recently active
        _ask_in_conversation(client, c1["id"])

        resp = client.get("/api/v1/chat/conversations")
        convos = resp.json()["conversations"]

        # c1 should be first (most recently active)
        assert convos[0]["id"] == c1["id"]


class TestConversationOwnership:
    """Test ownership checks on ask endpoint."""

    def test_ask_in_own_conversation_succeeds(
        self, client: TestClient
    ):
        convo = _create_conversation(client)
        data = _ask_in_conversation(client, convo["id"])
        assert data["conversation_id"] == convo["id"]

    def test_ask_in_nonexistent_returns_404(
        self, client: TestClient
    ):
        resp = client.post(
            "/api/v1/chat/conversations/fake-id-12345/ask",
            json={
                "question": "Hello?",
                "user_role": "student",
            },
        )
        assert resp.status_code == 404


class TestAutoTitle:
    """Test that first message auto-titles the conversation."""

    def test_first_message_updates_title(
        self, client: TestClient
    ):
        convo = _create_conversation(client)
        assert convo["title"] == "New Chat"

        _ask_in_conversation(
            client,
            convo["id"],
            question="How does gravity work?",
        )

        resp = client.get("/api/v1/chat/conversations")
        updated = next(
            c
            for c in resp.json()["conversations"]
            if c["id"] == convo["id"]
        )
        assert updated["title"] == "How does gravity work?"

    def test_second_message_does_not_change_title(
        self, client: TestClient
    ):
        convo = _create_conversation(client)

        _ask_in_conversation(
            client, convo["id"], question="First question"
        )
        _ask_in_conversation(
            client, convo["id"], question="Second question"
        )

        resp = client.get("/api/v1/chat/conversations")
        updated = next(
            c
            for c in resp.json()["conversations"]
            if c["id"] == convo["id"]
        )
        assert updated["title"] == "First question"
class TestOptionalSubject:
    """Test creating conversations and asking questions without a subject."""

    def test_create_without_subject_succeeds(self, client: TestClient):
        resp = client.post(
            "/api/v1/chat/conversations",
            json={"grade": "S1"},  # subject omitted
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["subject"] == "general"

    def test_ask_without_subject_succeeds(self, client: TestClient):
        # Create without subject
        convo = client.post(
            "/api/v1/chat/conversations",
            json={"grade": "S1"},
        ).json()

        # Ask without subject
        resp = client.post(
            f"/api/v1/chat/conversations/{convo['id']}/ask",
            json={
                "question": "What is the capital of Rwanda?",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        # grade/subject are NOT echoed on ChatResponse
        assert "grade" not in data
        assert "subject" not in data
        # Since no docs are found in test, check fallback answer contains subject
        # Since no docs are found in test, check fallback answer contains subject
        assert "general" in data["answer"].lower()


class TestConversationDetailUpdateDelete:
    """Test detailed GET, PATCH, and DELETE operations."""

    def test_get_conversation_detail(self, client: TestClient):
        convo = _create_conversation(client, title="Detail Check")
        resp = client.get(f"/api/v1/chat/conversations/{convo['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == convo["id"]
        assert resp.json()["title"] == "Detail Check"

    def test_update_conversation_title(self, client: TestClient):
        convo = _create_conversation(client)
        resp = client.patch(
            f"/api/v1/chat/conversations/{convo['id']}",
            json={"title": "Updated Title"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Title"

        # Verify persistence
        detail = client.get(f"/api/v1/chat/conversations/{convo['id']}").json()
        assert detail["title"] == "Updated Title"

    def test_update_rejects_whitespace(self, client: TestClient):
        convo = _create_conversation(client)
        resp = client.patch(
            f"/api/v1/chat/conversations/{convo['id']}",
            json={"title": "   "},
        )
        assert resp.status_code == 422

    def test_delete_conversation(self, client: TestClient):
        convo = _create_conversation(client)
        resp = client.delete(f"/api/v1/chat/conversations/{convo['id']}")
        assert resp.status_code == 204

        # Verify 404 on follow-up detail
        assert (
            client.get(f"/api/v1/chat/conversations/{convo['id']}").status_code
            == 404
        )

        # Verify it's gone from the LIST
        list_resp = client.get("/api/v1/chat/conversations")
        assert list_resp.status_code == 200
        ids = [c["id"] for c in list_resp.json()["conversations"]]
        assert convo["id"] not in ids

    def test_ownership_isolation(self, client: TestClient):
        # Create convo as actor 1 (default)
        c1 = _create_conversation(client)

        from somaai.deps import get_actor_id

        # Override to other-actor
        client.app.dependency_overrides[get_actor_id] = lambda: "other-actor"

        try:
            # Try to GET c1 as other-actor
            assert (
                client.get(f"/api/v1/chat/conversations/{c1['id']}").status_code
                == 404
            )
            # Try to PATCH c1 as other-actor
            assert (
                client.patch(
                    f"/api/v1/chat/conversations/{c1['id']}",
                    json={"title": "Hacked"},
                ).status_code
                == 404
            )
            # Try to DELETE c1 as other-actor
            assert (
                client.delete(
                    f"/api/v1/chat/conversations/{c1['id']}"
                ).status_code
                == 404
            )
        finally:
            # Clean up override
            del client.app.dependency_overrides[get_actor_id]
