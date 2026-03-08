"""Tests for ContextBuilder.

Unit tests for the token-aware context builder that loads
conversation history within a token budget.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestEstimateTokens:
    """Test the lightweight token estimator."""

    def _estimate_tokens(self, text: str) -> int:
        from somaai.modules.chat.context import estimate_tokens

        return estimate_tokens(text)

    def test_empty_string(self):
        assert self._estimate_tokens("") == 0

    def test_short_string(self):
        # "Hello" = 5 chars => 5 // 4 = 1 token
        assert self._estimate_tokens("Hello") == 1

    def test_longer_string(self):
        text = "a" * 100
        assert self._estimate_tokens(text) == 25  # 100 / 4

    def test_realistic_sentence(self):
        text = "What are the three pillars of Rwanda Vision 2050?"
        tokens = self._estimate_tokens(text)
        # ~50 chars => ~12 tokens (reasonable for English)
        assert 10 <= tokens <= 15


class TestContextBuilder:
    """Test ContextBuilder.build_history using mocked DB."""

    def _make_builder(self, mock_db):
        from somaai.modules.chat.context import ContextBuilder

        return ContextBuilder(mock_db)

    @pytest.fixture
    def mock_db(self):
        """Create a mock async DB session."""
        return AsyncMock()

    @pytest.fixture
    def builder(self, mock_db):
        return self._make_builder(mock_db)

    @pytest.mark.asyncio
    async def test_empty_conversation_returns_empty(self, builder, mock_db):
        """No messages should return empty string."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        history = await builder.build_history(
            conversation_id="conv-1",
            actor_id="actor-1",
        )
        assert history == ""

    @pytest.mark.asyncio
    async def test_none_conversation_returns_empty(self, builder):
        """Empty conversation_id should return empty string."""
        history = await builder.build_history(
            conversation_id="",
            actor_id="actor-1",
        )
        assert history == ""

    @pytest.mark.asyncio
    async def test_builds_chronological_history(self, builder, mock_db):
        """Messages should be returned in chronological order."""
        # Simulate 2 messages (returned newest-first by query)
        msg1 = MagicMock()
        msg1.question = "First question"
        msg1.answer = "First answer"
        msg1.user_role = "student"

        msg2 = MagicMock()
        msg2.question = "Second question"
        msg2.answer = "Second answer"
        msg2.user_role = "student"

        mock_result = MagicMock()
        # DB returns newest-first
        mock_result.scalars.return_value.all.return_value = [
            msg2,
            msg1,
        ]
        mock_db.execute.return_value = mock_result

        history = await builder.build_history(
            conversation_id="conv-1",
            actor_id="actor-1",
        )

        # Output should be chronological (oldest first)
        lines = history.split("\n")
        assert lines[0] == "Student: First question"
        assert lines[1] == "Assistant: First answer"
        assert lines[2] == "Student: Second question"
        assert lines[3] == "Assistant: Second answer"

    @pytest.mark.asyncio
    async def test_respects_token_budget(self, builder, mock_db):
        """Should stop adding turns when budget is exhausted."""
        # Create messages with ~200 chars each turn
        messages = []
        for i in range(10):
            msg = MagicMock()
            msg.question = f"Question {i} " + "x" * 80
            msg.answer = f"Answer {i} " + "y" * 80
            msg.user_role = "student"
            messages.append(msg)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = list(reversed(messages))
        mock_db.execute.return_value = mock_result

        # Small budget: should only fit 1-2 turns
        history = await builder.build_history(
            conversation_id="conv-1",
            actor_id="actor-1",
            max_tokens=50,
        )

        # Should have some content but not all 10 turns
        turn_count = history.count("Student:")
        assert 0 < turn_count < 10
