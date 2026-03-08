from fastapi.testclient import TestClient


def _create_conversation(
    client: TestClient,
    grade: str = "S1",
    subject: str = "social_studies",
) -> dict:
    resp = client.post(
        "/api/v1/chat/conversations",
        json={"grade": grade, "subject": subject},
    )
    assert resp.status_code == 201
    return resp.json()


def _ask_in_conversation(
    client: TestClient,
    conversation_id: str,
    question: str = "What is photosynthesis?",
) -> dict:
    resp = client.post(
        f"/api/v1/chat/conversations/{conversation_id}/ask",
        json={
            "question": question,
            "user_role": "student",
        },
    )
    assert resp.status_code == 201
    return resp.json()


class TestSubmitFeedback:
    """Tests for POST /api/v1/feedback"""

    def test_submit_feedback_success(self, client: TestClient):
        """Happy path: submit valid feedback returns 201."""
        convo = _create_conversation(client)
        msg = _ask_in_conversation(client, convo["id"])
        message_id = msg["message_id"]

        resp = client.post(
            "/api/v1/feedback",
            json={
                "message_id": message_id,
                "useful": True,
                "text": "Great answer!",
                "tags": ["accurate", "helpful"],
                "user_role": "teacher",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["message_id"] == message_id
        assert data["useful"] is True
        assert data["text"] == "Great answer!"
        assert data["tags"] == ["accurate", "helpful"]
        assert "feedback_id" in data

    def test_submit_feedback_minimal(self, client: TestClient):
        """Minimal valid request: only required fields."""
        convo = _create_conversation(client)
        msg = _ask_in_conversation(client, convo["id"])
        message_id = msg["message_id"]

        resp = client.post(
            "/api/v1/feedback",
            json={
                "message_id": message_id,
                "useful": False,
                "user_role": "teacher",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["useful"] is False
        assert data["text"] is None
        assert data["tags"] is None

    def test_submit_feedback_message_not_found(self, client: TestClient):
        """404 when message_id doesn't exist."""
        resp = client.post(
            "/api/v1/feedback",
            json={
                "message_id": "non_existent_msg",
                "useful": True,
                "user_role": "teacher",
            },
        )
        assert resp.status_code == 404

    def test_submit_feedback_duplicate_conflict(self, client: TestClient):
        """409 when feedback already exists for message."""
        convo = _create_conversation(client)
        msg = _ask_in_conversation(client, convo["id"])
        message_id = msg["message_id"]

        # First submission
        client.post(
            "/api/v1/feedback",
            json={
                "message_id": message_id,
                "useful": True,
                "user_role": "teacher",
            },
        )

        # Second submission
        resp = client.post(
            "/api/v1/feedback",
            json={
                "message_id": message_id,
                "useful": False,
                "user_role": "teacher",
            },
        )
        assert resp.status_code == 409

    def test_submit_feedback_tags_normalized(self, client: TestClient):
        """Tags should be lowercased, trimmed, and deduplicated."""
        convo = _create_conversation(client)
        msg = _ask_in_conversation(client, convo["id"])
        message_id = msg["message_id"]

        resp = client.post(
            "/api/v1/feedback",
            json={
                "message_id": message_id,
                "useful": True,
                "tags": [" Accurate ", "helpful", "ACCURATE", ""],
                "user_role": "teacher",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        # Normalized result: ["accurate", "helpful"]
        assert data["tags"] == ["accurate", "helpful"]

    def test_submit_feedback_missing_required_fields(self, client: TestClient):
        """422 when required fields are missing."""
        resp = client.post(
            "/api/v1/feedback",
            json={
                "useful": True,
                # message_id missing
            },
        )
        assert resp.status_code == 422

    def test_submit_feedback_tags_limit(self, client: TestClient):
        """Tags should be capped at 10."""
        convo = _create_conversation(client)
        msg = _ask_in_conversation(client, convo["id"])
        message_id = msg["message_id"]

        # 12 tags
        many_tags = [f"tag_{i}" for i in range(12)]

        resp = client.post(
            "/api/v1/feedback",
            json={
                "message_id": message_id,
                "useful": True,
                "tags": many_tags,
                "user_role": "teacher",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["tags"]) == 10
        assert data["tags"] == [f"tag_{i}" for i in range(10)]

    def test_submit_feedback_text_too_long(self, client: TestClient):
        """422 when feedback text exceeds 1000 characters."""
        convo = _create_conversation(client)
        msg = _ask_in_conversation(client, convo["id"])
        message_id = msg["message_id"]

        resp = client.post(
            "/api/v1/feedback",
            json={
                "message_id": message_id,
                "useful": True,
                "text": "A" * 1001,
                "user_role": "teacher",
            },
        )
        assert resp.status_code == 422


class TestGetFeedback:
    """Tests for GET /api/v1/feedback/{message_id}"""

    def test_get_feedback_success(self, client: TestClient):
        """Get existing feedback returns 200."""
        convo = _create_conversation(client)
        msg = _ask_in_conversation(client, convo["id"])
        message_id = msg["message_id"]

        # Submit first
        client.post(
            "/api/v1/feedback",
            json={
                "message_id": message_id,
                "useful": True,
                "text": "Correct!",
                "user_role": "teacher",
            },
        )

        # Then Get
        resp = client.get(f"/api/v1/feedback/{message_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["message_id"] == message_id
        assert data["useful"] is True
        assert data["text"] == "Correct!"

    def test_get_feedback_not_found(self, client: TestClient):
        """404 when no feedback exists for message."""
        convo = _create_conversation(client)
        msg = _ask_in_conversation(client, convo["id"])
        message_id = msg["message_id"]

        resp = client.get(f"/api/v1/feedback/{message_id}")
        assert resp.status_code == 404
