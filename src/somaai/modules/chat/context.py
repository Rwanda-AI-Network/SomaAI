"""Token-aware context builder.

Replaces the old MemoryLoader with a budget-aware approach that fits
as many recent turns as possible within a token limit.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from somaai.db.models import Message

logger = logging.getLogger(__name__)


def estimate_tokens(text: str) -> int:
    """Estimate token count using the 4-chars-per-token heuristic.

    Good enough for MVP — within ~20% of tiktoken for English text.

    Args:
        text: Input text

    Returns:
        Estimated token count
    """
    return len(text) // 4


class ContextBuilder:
    """Build token-aware conversation context from DB history."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def build_history(
        self,
        conversation_id: str,
        actor_id: str,
        max_tokens: int = 1500,
    ) -> str:
        """Build conversation history string within a token budget.

        Loads messages newest-first, then assembles the result in
        chronological order. Stops adding turns when the budget is
        exhausted.

        Args:
            conversation_id: Conversation to load history for
            actor_id: Actor who must own the conversation (security)
            max_tokens: Maximum estimated tokens for the history block

        Returns:
            Formatted history string, or empty string if no history
        """
        if not conversation_id:
            return ""

        # Fetch messages newest-first
        stmt = (
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.actor_id == actor_id,
            )
            .order_by(Message.created_at.desc())
        )
        result = await self.db.execute(stmt)
        messages = list(result.scalars().all())

        if not messages:
            return ""

        # Greedily add turns from newest to oldest within budget
        selected: list[Message] = []
        tokens_used = 0

        for msg in messages:
            role_label = self._get_role_label(msg)
            turn_text = f"{role_label}: {msg.question}\nAssistant: {msg.answer}\n"
            turn_tokens = estimate_tokens(turn_text)

            if tokens_used + turn_tokens > max_tokens:
                break

            selected.append((msg, role_label))
            tokens_used += turn_tokens

        if not selected:
            return ""

        # Reverse to chronological order for the prompt
        selected.reverse()

        lines: list[str] = []
        for msg, role_label in selected:
            lines.append(f"{role_label}: {msg.question}")
            lines.append(f"Assistant: {msg.answer}")

        history = "\n".join(lines)

        logger.debug(
            "Built history: %d turns, ~%d tokens",
            len(selected),
            tokens_used,
            extra={
                "conversation_id": conversation_id,
                "turns": len(selected),
                "tokens_estimated": tokens_used,
            },
        )

        return history

    def _get_role_label(self, msg: Message) -> str:
        """Get the title-cased role label for a message."""
        if not msg.user_role:
            return "Student"
        # Support both Enum and raw string
        val = msg.user_role.value if hasattr(msg.user_role, "value") else msg.user_role
        return str(val).title()
