"""Tests for chat endpoints.

Since tests use llm_backend="mock" with RAGPipeline (not MockRAGPipeline),
and there is no Qdrant instance in tests, retrieval returns 0 docs.
The pipeline correctly returns "insufficient" when no documents are found.
"""

from fastapi.testclient import TestClient


class TestChatEndpoints:
    """Test cases for /api/v1/chat endpoints.

    Uses RAGPipeline with MockLLMProvider. Without a real Qdrant
    instance, retrieval returns empty results, so responses will have
    sufficiency="insufficient".
    """

    def test_ask_returns_required_fields(self, client: TestClient):
        """POST /chat/ask should return message_id, answer, sufficiency, citations."""
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

        # Without Qdrant, pipeline returns insufficient context
        assert data["sufficiency"] == "insufficient"
        assert isinstance(data["citations"], list)

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
