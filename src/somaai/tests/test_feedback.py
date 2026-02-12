"""Tests for feedback endpoint."""

import pytest
from httpx import AsyncClient


class TestSubmitFeedback:
    """Tests for POST /api/v1/feedback"""

    @pytest.mark.asyncio
    async def test_submit_feedback_success(self, client: AsyncClient):
        """Happy path: submit valid feedback returns 201."""
        # TODO: Implement when database fixtures are available
        pass

    @pytest.mark.asyncio
    async def test_submit_feedback_minimal(self, client: AsyncClient):
        """Minimal valid request: only required fields."""
        # TODO: Implement when database fixtures are available
        pass

    @pytest.mark.asyncio
    async def test_submit_feedback_message_not_found(self, client: AsyncClient):
        """404 when message_id doesn't exist."""
        # TODO: Implement when database fixtures are available
        pass

    @pytest.mark.asyncio
    async def test_submit_feedback_duplicate_conflict(self, client: AsyncClient):
        """409 when feedback already exists for message."""
        # TODO: Implement when database fixtures are available
        pass

    @pytest.mark.asyncio
    async def test_submit_feedback_tags_normalized(self, client: AsyncClient):
        """Tags should be lowercased, trimmed, and deduplicated."""
        # TODO: Implement when database fixtures are available
        pass

    @pytest.mark.asyncio
    async def test_submit_feedback_missing_required_fields(self, client: AsyncClient):
        """422 when required fields are missing."""
        # TODO: Implement when database fixtures are available
        pass


class TestGetFeedback:
    """Tests for GET /api/v1/feedback/{message_id}"""

    @pytest.mark.asyncio
    async def test_get_feedback_success(self, client: AsyncClient):
        """Get existing feedback returns 200."""
        # TODO: Implement when database fixtures are available
        pass

    @pytest.mark.asyncio
    async def test_get_feedback_not_found(self, client: AsyncClient):
        """404 when no feedback exists for message."""
        # TODO: Implement when database fixtures are available
        pass
