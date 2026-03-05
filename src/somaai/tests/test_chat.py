from fastapi.testclient import TestClient


def _create_conversation(
    client: TestClient,
    grade: str = "S1",
    subject: str = "social_studies",
) -> dict:
    """Helper: create a conversation and return the response dict."""
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
    """Helper: ask a question and return the response dict.

    grade/subject are now owned by the conversation — not sent on ask.
    """
    resp = client.post(
        f"/api/v1/chat/conversations/{conversation_id}/ask",
        json={
            "question": question,
            "user_role": "student",
        },
    )
    assert resp.status_code == 201
    return resp.json()


class TestConversationCreation:
    """Test POST /api/v1/chat/conversations."""

    def test_create_conversation_returns_201(
        self, client: TestClient
    ):
        data = _create_conversation(client)
        assert "id" in data
        assert data["title"] == "New Chat"
        assert data["grade"] == "S1"
        assert data["subject"] == "social_studies"
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_multiple_conversations(
        self, client: TestClient
    ):
        c1 = _create_conversation(
            client, grade="S1", subject="science"
        )
        c2 = _create_conversation(
            client, grade="S2", subject="mathematics"
        )
        assert c1["id"] != c2["id"]

    def test_list_conversations(self, client: TestClient):
        _create_conversation(client, subject="mathematics")
        _create_conversation(client, subject="science")

        resp = client.get("/api/v1/chat/conversations")
        assert resp.status_code == 200
        data = resp.json()
        assert "conversations" in data
        # next_cursor is absent (stripped as None) when results fit on one page
        assert data.get("next_cursor") is None
        assert len(data["conversations"]) >= 2

    def test_list_conversations_pagination_defaults(
        self, client: TestClient
    ):
        resp = client.get("/api/v1/chat/conversations?limit=1")
        assert resp.status_code == 200
        data = resp.json()
        assert "conversations" in data


class TestAskQuestion:
    """Test POST /api/v1/chat/conversations/{id}/ask."""

    def test_ask_returns_required_fields(
        self, client: TestClient
    ):
        convo = _create_conversation(client)
        data = _ask_in_conversation(client, convo["id"])

        assert "message_id" in data
        assert "conversation_id" in data
        assert data["conversation_id"] == convo["id"]
        assert "answer" in data
        assert "sufficiency" in data
        assert "citations" in data
        assert "created_at" in data

        # grade/subject are NOT echoed on the response
        assert "grade" not in data
        assert "subject" not in data

        # Without Qdrant, pipeline returns insufficient context
        assert data["sufficiency"] == "insufficient"
        assert isinstance(data["citations"], list)

    def test_ask_enhancements_field_present(
        self, client: TestClient
    ):
        convo = _create_conversation(client)
        data = _ask_in_conversation(client, convo["id"])
        # enhancements may be absent (None stripped) or present as an object
        assert data.get("enhancements") is None or isinstance(data["enhancements"], dict)

    def test_ask_in_nonexistent_conversation_returns_404(
        self, client: TestClient
    ):
        resp = client.post(
            "/api/v1/chat/conversations/nonexistent-id/ask",
            json={
                "question": "Hello?",
                "user_role": "student",
            },
        )
        assert resp.status_code == 404

    def test_ask_auto_titles_on_first_message(
        self, client: TestClient
    ):
        convo = _create_conversation(client)
        _ask_in_conversation(
            client,
            convo["id"],
            question="What is photosynthesis?",
        )

        # List conversations and check title was updated
        resp = client.get("/api/v1/chat/conversations")
        convos = resp.json()["conversations"]
        updated = next(
            c for c in convos if c["id"] == convo["id"]
        )
        assert updated["title"] == "What is photosynthesis?"

    def test_ask_empty_question_returns_422(
        self, client: TestClient
    ):
        convo = _create_conversation(client)
        resp = client.post(
            f"/api/v1/chat/conversations/{convo['id']}/ask",
            json={
                "question": "",
                "user_role": "student",
            },
        )
        # Pydantic validation rejects empty string (min_length=1)
        assert resp.status_code == 422


class TestMessageRetrieval:
    """Test GET endpoints for messages and citations."""

    def test_get_message_returns_details(
        self, client: TestClient
    ):
        convo = _create_conversation(client)
        ask_data = _ask_in_conversation(client, convo["id"])
        message_id = ask_data["message_id"]

        resp = client.get(
            f"/api/v1/chat/conversations/{convo['id']}/messages/{message_id}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message_id"] == message_id
        assert data["conversation_id"] == convo["id"]
        assert data["question"] == "What is photosynthesis?"
        assert data["user_role"] == "student"
        assert isinstance(data["citations"], list)
        # MessageResponse carries the enhancements block (absent when None)
        assert data.get("enhancements") is None or isinstance(data["enhancements"], dict)

    def test_get_nonexistent_message_returns_404(
        self, client: TestClient
    ):
        convo = _create_conversation(client)
        resp = client.get(
            f"/api/v1/chat/conversations/{convo['id']}/messages/nonexistent-id",
        )
        assert resp.status_code == 404

    def test_get_message_citations(self, client: TestClient):
        convo = _create_conversation(client)
        ask_data = _ask_in_conversation(client, convo["id"])
        message_id = ask_data["message_id"]

        resp = client.get(
            f"/api/v1/chat/conversations/{convo['id']}/messages/{message_id}/citations"
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_citations_nonexistent_message_returns_404(
        self, client: TestClient
    ):
        convo = _create_conversation(client)
        resp = client.get(
            f"/api/v1/chat/conversations/{convo['id']}/messages/nonexistent-id/citations",
        )
        assert resp.status_code == 404

    def test_list_messages_history(self, client: TestClient):
        convo = _create_conversation(client)
        # Ask two questions
        _ask_in_conversation(client, convo["id"], "Question 1")
        _ask_in_conversation(client, convo["id"], "Question 2")

        resp = client.get(f"/api/v1/chat/conversations/{convo['id']}/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert "messages" in data
        assert len(data["messages"]) == 2
        # Most recent first
        assert data["messages"][0]["question"] == "Question 2"
        assert data["messages"][1]["question"] == "Question 1"
        assert "next_cursor" in data


class TestOptionalSubject:
    """Test chat flow with optional subject."""

    def test_ask_without_subject_resolves_general(
        self, client: TestClient
    ):
        # Create without subject (defaults to "general" server-side)
        convo = client.post(
            "/api/v1/chat/conversations",
            json={"grade": "S1"},
        ).json()
        convo_id = convo["id"]

        # Ask — grade/subject no longer in request body
        resp = client.post(
            f"/api/v1/chat/conversations/{convo_id}/ask",
            json={"question": "Hello, how are you?"},
        )
        assert resp.status_code == 201
        data = resp.json()
        # grade/subject are NOT echoed on ChatResponse
        assert "grade" not in data
        assert "subject" not in data

        # Retrieve message and verify it saved correctly
        msg_id = data["message_id"]
        msg_resp = client.get(f"/api/v1/chat/conversations/{convo_id}/messages/{msg_id}")
        assert msg_resp.status_code == 200
        msg_data = msg_resp.json()
        assert "message_id" in msg_data


class TestPreferences:
    """Test the Enhancement enum and Preferences contract."""

    def test_ask_with_empty_enhancements_list(
        self, client: TestClient
    ):
        """Passing [] disables all enhancements."""
        convo = _create_conversation(client)
        resp = client.post(
            f"/api/v1/chat/conversations/{convo['id']}/ask",
            json={
                "question": "What is osmosis?",
                "preferences": {"enabled_enhancements": []},
            },
        )
        assert resp.status_code == 201

    def test_ask_with_analogy_only(
        self, client: TestClient
    ):
        """Passing a specific enhancement list is accepted."""
        convo = _create_conversation(client)
        resp = client.post(
            f"/api/v1/chat/conversations/{convo['id']}/ask",
            json={
                "question": "What is osmosis?",
                "preferences": {"enabled_enhancements": ["analogy"]},
            },
        )
        assert resp.status_code == 201
