"""Tests for chat endpoints."""

from fastapi.testclient import TestClient

# Remove pytest.mark.asyncio and make functions sync


class TestChatEndpoints:
    """Test cases for /api/v1/chat endpoints.

    Uses the MockRAGPipeline by default due to settings configuration in tests.
    """

    def test_ask_returns_required_fields(self, client: TestClient):
        """POST /chat/ask should return message_id, response, sufficiency, citations."""
        response = client.post(
            "/api/v1/chat/ask",
            json={
                "question": "What is photosynthesis?",
                "grade": "S2",
                "subject": "science",
                "user_role": "student",
            },
            headers={"X-Actor-Id": "test_student_1"},
        )

        assert response.status_code == 201
        data = response.json()

        # Check top-level fields
        assert "message_id" in data
        assert "answer" in data
        assert "sufficiency" in data
        assert "citations" in data
        assert "created_at" in data

        # Mock LLM should return a specific format answer
        assert data["answer"].startswith("MOCK_ANSWER:")

        # Citations should be present because "photosynthesis" is in MOCK_CHUNKS
        assert len(data["citations"]) > 0
        citation = data["citations"][0]
        assert "doc_id" in citation
        assert citation["doc_title"] == "REB Biology S2 - Cell Biology"

    def test_get_message_returns_details(self, client: TestClient):
        """GET /chat/messages/{id} returns full message details."""
        # 1. Create a message first
        ask_response = client.post(
            "/api/v1/chat/ask",
            json={
                "question": "What is photosynthesis?",
                "grade": "S2",
                "subject": "science",
            },
            headers={"X-Actor-Id": "test_student_2"},
        )
        assert ask_response.status_code == 201
        message_id = ask_response.json()["message_id"]

        # 2. Retrieve the message
        get_response = client.get(
            f"/api/v1/chat/messages/{message_id}",
            headers={"X-Actor-Id": "test_student_2"},
        )

        assert get_response.status_code == 200
        data = get_response.json()
        assert data["message_id"] == message_id
        assert data["question"] == "What is photosynthesis?"
        assert data["user_role"] == "student"  # default

        # Note: Citations won't be persisted in Mock mode because chunk_id is None,
        # so we expect empty citations here unless we seeded chunks in DB.
        assert isinstance(data["citations"], list)

    def test_get_message_citations_returns_list(self, client: TestClient):
        """GET /chat/messages/{id}/citations returns citation list."""
        # 1. Create a message
        ask_response = client.post(
            "/api/v1/chat/ask",
            json={
                "question": "What is cell respiration?",
                "grade": "S2",
                "subject": "science",
            },
            headers={"X-Actor-Id": "test_student_3"},
        )
        message_id = ask_response.json()["message_id"]

        # 2. Get citations
        cit_response = client.get(
            f"/api/v1/chat/messages/{message_id}/citations",
            headers={"X-Actor-Id": "test_student_3"},
        )

        assert cit_response.status_code == 200
        citations = cit_response.json()
        assert isinstance(citations, list)
        # Expected empty for mock mode without DB seeding
