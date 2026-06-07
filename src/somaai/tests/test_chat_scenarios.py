"""Comprehensive chat scenarios testing.

Validates "each possible response" and scenario:
- Student vs Teacher roles
- Pedagogical enhancements (analogies, realworld)
- Citation accuracy and view_url generation
- Context sufficiency (SUFFICIENT vs INSUFFICIENT)
- History handling
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from somaai.contracts.common import Sufficiency


@pytest.fixture
def mock_convo(client: TestClient):
    resp = client.post(
        "/api/v1/chat/conversations", json={"grade": "S1", "subject": "science"}
    )
    return resp.json()["id"]


class TestChatScenarios:
    """End-to-end chat scenario validation."""

    def test_student_basic_ask(self, client: TestClient, mock_convo):
        """Scenario: Student asks a simple question with default settings."""
        # Use patch to ensure retrieval returns something, making it "sufficient"
        with patch(
            "somaai.modules.rag.retriever.Retriever.retrieve_for_context",
            new_callable=AsyncMock,
        ) as m:
            m.return_value = (
                [{"content": "A cell is the unit of life.", "score": 0.9}],
                "A cell is the unit of life.",
            )
            resp = client.post(
                f"/api/v1/chat/conversations/{mock_convo}/ask",
                json={"question": "What is a cell?", "user_role": "student"},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["conversation_id"] == mock_convo
        assert "answer" in data
        assert data["sufficiency"] == Sufficiency.SUFFICIENT

    def test_teacher_with_enhancements(self, client: TestClient, mock_convo):
        """Scenario: Teacher asks with explicit enhancements (analogy + realworld)."""
        with patch(
            "somaai.modules.rag.retriever.Retriever.retrieve_for_context",
            new_callable=AsyncMock,
        ) as m:
            m.return_value = (
                [{"content": "Mitosis is cell division.", "score": 0.9}],
                "Mitosis is cell division.",
            )
            resp = client.post(
                f"/api/v1/chat/conversations/{mock_convo}/ask",
                json={
                    "question": "Explain cell division.",
                    "user_role": "teacher",
                    "preferences": {"enabled_enhancements": ["analogy", "real_world"]},
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["enhancements"] is not None
        assert data["enhancements"]["analogy"] is not None
        assert data["enhancements"]["real_world_context"] is not None

    def test_insufficient_context_fallback(self, client: TestClient, mock_convo):
        """Scenario: LLM determines context is insufficient for a query."""
        # Here we DON'T patch, so default conftest [] retrieval is used
        resp = client.post(
            f"/api/v1/chat/conversations/{mock_convo}/ask",
            json={"question": "How do I build a rocket ship?", "user_role": "student"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["sufficiency"] == Sufficiency.INSUFFICIENT

    def test_citation_integrity(self, client: TestClient, mock_convo):
        """Scenario: Verify citations lead to valid view URLs."""
        with patch(
            "somaai.modules.rag.retriever.Retriever.retrieve_for_context",
            new_callable=AsyncMock,
        ) as m:
            m.return_value = (
                [
                    {
                        "content": "Photosynthesis turns light into energy.",
                        "score": 0.9,
                        "metadata": {
                            "doc_id": "test-doc-123",
                            "title": "Science Book",
                            "page_start": 1,
                        },
                    }
                ],
                "Photosynthesis turns light into energy.",
            )

            resp = client.post(
                f"/api/v1/chat/conversations/{mock_convo}/ask",
                json={"question": "What is photosynthesis?", "user_role": "student"},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["citations"]) > 0
        cit = data["citations"][0]
        assert cit["doc_id"] == "test-doc-123"
        assert "view_url" in cit
        assert "/api/v1/docs/test-doc-123/view" in cit["view_url"]

    def test_chat_history_pagination(self, client: TestClient, mock_convo):
        """Scenario: Post multiple questions and verify history retrieval."""
        # Patching to ensure each 'ask' succeeds and saves a message
        with patch(
            "somaai.modules.rag.retriever.Retriever.retrieve_for_context",
            new_callable=AsyncMock,
        ) as m:
            m.return_value = ([{"content": "data", "score": 0.5}], "data")
            for i in range(3):
                client.post(
                    f"/api/v1/chat/conversations/{mock_convo}/ask",
                    json={"question": f"Question {i}", "user_role": "student"},
                )

        resp = client.get(f"/api/v1/chat/conversations/{mock_convo}/messages")
        assert resp.status_code == 200
        data = resp.json()
        # Should have 3 Message pairs (each containing question + answer)
        assert len(data["messages"]) == 3
        assert data["messages"][0]["question"] == "Question 2"  # Newest first

    def test_message_history_integrity(self, client: TestClient, mock_convo):
        """Scenario: Verify history retrieval contains full data."""
        # 1. Ask with enhancements to ensure they are saved
        # Note: Citations require actual chunks in DB, so we skip citation validation
        # and focus on enhancements which are stored directly in the message
        with patch(
            "somaai.modules.rag.retriever.Retriever.retrieve_for_context",
            new_callable=AsyncMock,
        ) as m:
            m.return_value = (
                [
                    {
                        "content": "A cell is a factory.",
                        "score": 0.9,
                        "metadata": {
                            "doc_id": "cell-doc-1",
                            "title": "Biology 101",
                            "page_start": 5,
                            # No chunk_id - citations won't be saved (OK for test)
                        },
                    }
                ],
                "A cell is a factory.",
            )

            resp = client.post(
                f"/api/v1/chat/conversations/{mock_convo}/ask",
                json={
                    "question": "Tell me about cells with an analogy.",
                    "user_role": "teacher",
                    "preferences": {"enabled_enhancements": ["analogy"]},
                },
            )
            assert resp.status_code == 201

        # 2. Retrieve history
        resp = client.get(f"/api/v1/chat/conversations/{mock_convo}/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["messages"]) > 0
        msg = data["messages"][0]

        # 3. Verify Enhancements are present in history
        assert msg["enhancements"] is not None
        assert msg["enhancements"]["analogy"] is not None

        # 4. Verify message structure is complete
        assert "question" in msg
        assert "answer" in msg
        assert "confidence" in msg
        assert "sufficiency" in msg

    def test_history_pagination_cursor(self, client: TestClient, mock_convo):
        """Scenario: Verify next_cursor correctly paginates history."""
        # Create 3 messages
        with patch(
            "somaai.modules.rag.retriever.Retriever.retrieve_for_context",
            new_callable=AsyncMock,
        ) as m:
            m.return_value = ([{"content": "data", "score": 0.5}], "data")
            for i in range(3):
                client.post(
                    f"/api/v1/chat/conversations/{mock_convo}/ask",
                    json={"question": f"Q{i}", "user_role": "student"},
                )

        # Get first page (limit 1)
        resp = client.get(f"/api/v1/chat/conversations/{mock_convo}/messages?limit=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["messages"]) == 1
        assert data["messages"][0]["question"] == "Q2"  # Newest
        assert data["next_cursor"] is not None

        # Get second page using cursor
        cursor = data["next_cursor"]
        resp2 = client.get(
            f"/api/v1/chat/conversations/{mock_convo}/messages?limit=1&cursor={cursor}"
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert len(data2["messages"]) == 1
        assert data2["messages"][0]["question"] == "Q1"
        assert data2["next_cursor"] is not None
