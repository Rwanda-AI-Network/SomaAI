"""Chat memory management."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from somaai.db.models import Message


class MemoryLoader:
    """Loads chat history from the database."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_recent_turns(
        self,
        session_id: str,
        actor_id: str,
        limit: int = 6,
    ) -> list[dict[str, str]]:
        """Fetch recent conversation turns for a session.

        Args:
            session_id: The session identifier
            actor_id: The user identifier (for security)
            limit: Number of recent turns to fetch

        Returns:
            List of dicts with 'role' (user/assistant) and 'content' keys,
            ordered chronologically (oldest to newest).
        """
        if not session_id:
            return []

        # query: select * from messages where session_id = ... AND actor_id = ...
        query = (
            select(Message)
            .where(
                Message.session_id == session_id,
                Message.actor_id == actor_id,
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
        )

        result = await self.db.execute(query)
        messages = result.scalars().all()

        if not messages:
            return []

        # DB returns newest first (due to desc limit), revert to chronological order
        history = []
        for msg in reversed(messages):
            # Add user question
            history.append({"role": "user", "content": str(msg.question)})
            # Add AI answer
            history.append({"role": "assistant", "content": str(msg.answer)})

        return history

    @staticmethod
    def format_history_for_prompt(history: list[dict[str, str]]) -> str:
        """Format history list into a string for the prompt."""
        if not history:
            return ""

        lines = []
        for turn in history:
            role = "Student" if turn["role"] == "user" else "SomaAI"
            # Truncate to avoid exploding context window (simple rule)
            content = turn["content"][:600] + (
                "..." if len(turn["content"]) > 600 else ""
            )
            lines.append(f"{role}: {content}")

        return "\n".join(lines)
