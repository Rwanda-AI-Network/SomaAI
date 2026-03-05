import pytest
import asyncio
import base64
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from somaai.deps import get_actor_id
from somaai.modules.rag.pipelines import BaseRAGPipeline

def _create_conversation(client: TestClient, grade="S1", subject="science", title=None):
    payload = {"grade": grade, "subject": subject}
    if title:
        payload["title"] = title
    resp = client.post("/api/v1/chat/conversations", json=payload)
    if resp.status_code != 201:
        print(f"DEBUG: {resp.status_code} - {resp.text}")
    assert resp.status_code == 201
    return resp.json()

def _ask(client: TestClient, convo_id: str, question="Test?"):
    resp = client.post(
        f"/api/v1/chat/conversations/{convo_id}/ask", 
        json={"question": question, "user_role": "student"}
    )
    assert resp.status_code == 201
    return resp.json()

class TestSecurityHardening:
    """Rigorous ownership and isolation tests."""

    def test_actor_isolation_messages(self, client: TestClient):
        """CRITICAL: Actor B must not be able to access Actor A's messages or citations."""
        # 1. Actor A creates and asks
        convo_a = _create_conversation(client)
        msg_a = _ask(client, convo_a["id"])
        
        # 2. Switch to Actor B
        client.app.dependency_overrides[get_actor_id] = lambda: "actor-b"
        try:
            # Try to get Actor A's message details
            resp = client.get(f"/api/v1/chat/conversations/{convo_a['id']}/messages/{msg_a['message_id']}")
            assert resp.status_code == 404
            
            # Try to get Actor A's citations
            resp = client.get(f"/api/v1/chat/conversations/{convo_a['id']}/messages/{msg_a['message_id']}/citations")
            assert resp.status_code == 404
            
            # Try to list messages of Actor A's conversation
            resp = client.get(f"/api/v1/chat/conversations/{convo_a['id']}/messages")
            assert resp.status_code == 404
        finally:
            del client.app.dependency_overrides[get_actor_id]

    def test_cross_conversation_leakage(self, client: TestClient):
        """CRITICAL: Message ID from convo_1 must not be accessible via convo_2 path, even for same actor."""
        convo1 = _create_conversation(client)
        convo2 = _create_conversation(client)
        msg1 = _ask(client, convo1["id"])
        
        # Try to access msg1 via convo2 route
        # This confirms that conversation_id in path is validated against the message
        resp = client.get(f"/api/v1/chat/conversations/{convo2['id']}/messages/{msg1['message_id']}")
        assert resp.status_code == 404

class TestPaginationHardening:
    """Deep verification of cursor-based pagination."""

    def test_conversation_list_pagination(self, client: TestClient):
        """Verify multi-page conversation traversal."""
        # Create 5 conversations with unique titles to check order
        for i in range(5):
            _create_conversation(client, title=f"Convo {i}")
            
        # Page 1
        resp = client.get("/api/v1/chat/conversations?limit=2")
        data = resp.json()
        assert len(data["conversations"]) == 2
        assert data["conversations"][0]["title"] == "Convo 4" # Most recent first
        cursor = data.get("next_cursor")
        assert cursor is not None
        
        # Page 2
        resp = client.get(f"/api/v1/chat/conversations?limit=2&cursor={cursor}")
        data = resp.json()
        assert len(data["conversations"]) == 2
        assert data["conversations"][0]["title"] == "Convo 2"
        cursor = data.get("next_cursor")
        assert cursor is not None
        
        # Page 3 (final)
        resp = client.get(f"/api/v1/chat/conversations?limit=2&cursor={cursor}")
        data = resp.json()
        assert len(data["conversations"]) == 1
        assert data["conversations"][0]["title"] == "Convo 0"
        assert data.get("next_cursor") is None

    def test_message_history_pagination(self, client: TestClient):
        """Verify multi-page message history traversal."""
        convo = _create_conversation(client)
        for i in range(5):
            _ask(client, convo["id"], f"Question {i}")
            
        # Page 1
        resp = client.get(f"/api/v1/chat/conversations/{convo['id']}/messages?limit=2")
        data = resp.json()
        assert len(data["messages"]) == 2
        assert data["messages"][0]["question"] == "Question 4"
        cursor = data.get("next_cursor")
        assert cursor is not None
        
        # Page 2
        resp = client.get(f"/api/v1/chat/conversations/{convo['id']}/messages?limit=2&cursor={cursor}")
        data = resp.json()
        assert len(data["messages"]) == 2
        assert data["messages"][0]["question"] == "Question 2"

class TestResilienceHardening:
    """Graceful degradation and timeout scenarios."""

    @patch("somaai.modules.rag.pipelines.RAGPipeline.run", new_callable=AsyncMock)
    def test_rag_exception_fallback_behavior(self, mock_run, client: TestClient):
        """Verify that a pipeline crash results in a 201 with fallback text, not a 500."""
        mock_run.side_effect = Exception("Vector DB Connection Refused")
        convo = _create_conversation(client)
        
        # Use a question that would normally trigger RAG (not chitchat)
        resp = client.post(f"/api/v1/chat/conversations/{convo['id']}/ask", json={"question": "What is biology?"})
        assert resp.status_code == 201
        data = resp.json()
        assert "unable to answer" in data["answer"].lower()
        assert data["sufficiency"] == "insufficient"

    @patch("somaai.modules.chat.service.ChatService.ask", new_callable=AsyncMock)
    def test_rag_api_timeout_504(self, mock_ask, client: TestClient):
        """Verify that a timeout in the service layer triggers a 504 in the API layer."""
        mock_ask.side_effect = asyncio.TimeoutError()
        convo = _create_conversation(client)
        
        resp = client.post(f"/api/v1/chat/conversations/{convo['id']}/ask", json={"question": "Slow?"})
        assert resp.status_code == 504
        assert "timeout" in resp.json()["detail"].lower()

    def test_ask_stream_returns_501(self, client: TestClient):
        """Verify that the streaming endpoint returns 501 Not Implemented."""
        convo = _create_conversation(client)
        resp = client.post(
            f"/api/v1/chat/conversations/{convo['id']}/ask/stream",
            json={"question": "Can you stream?"}
        )
        assert resp.status_code == 501
        assert "not yet implemented" in resp.json()["detail"].lower()

    def test_invalid_cursor_encoding_fails_gracefully(self, client: TestClient):
        """Robustness: Invalid base64 or junk cursors should not crash (fall back to beginning)."""
        convo = _create_conversation(client)
        _ask(client, convo["id"])
        
        resp = client.get(f"/api/v1/chat/conversations/{convo['id']}/messages?cursor=not-base64-junk")
        assert resp.status_code == 200 # Service should ignore bad cursor
        assert len(resp.json()["messages"]) > 0
