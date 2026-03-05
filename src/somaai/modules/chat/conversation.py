"""Conversation CRUD service.

Manages conversation lifecycle: creation, listing, ownership validation,
and title updates.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from somaai.db.models import Conversation
from somaai.utils.ids import generate_id
from somaai.utils.time import kigali_now

logger = logging.getLogger(__name__)


class ConversationService:
    """Service for managing conversations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        from somaai.modules.meta.service import MetaService

        self.meta_service = MetaService(db)

    async def create(
        self,
        actor_id: str,
        grade: str,
        subject: str = "general",
        title: str | None = None,
    ) -> Conversation:
        from somaai.utils.meta import normalize_metadata

        # Canonical normalization
        grade, subject = normalize_metadata(grade, subject)

        # Existence validation (CTO Hardening)
        if not await self.meta_service.check_exists_grade(grade):
            raise ValueError(f"Invalid grade: {grade}")
        if subject != "general" and not await self.meta_service.check_exists_subject(
            subject
        ):
            raise ValueError(f"Invalid subject: {subject}")

        convo = Conversation(
            id=generate_id(),
            actor_id=actor_id,
            title=title or "New Chat",
            grade=grade,
            subject=subject,
            created_at=kigali_now(),
            updated_at=kigali_now(),
        )
        self.db.add(convo)
        await self.db.flush()

        # Add message_count to the object for the response (non-persistent attribute)
        convo.message_count = 0

        logger.info(
            "Conversation created",
            extra={
                "conversation_id": convo.id,
                "actor_id": actor_id,
                "grade": grade,
                "subject": subject,
            },
        )
        return convo

    async def list_for_actor(
        self,
        actor_id: str,
        limit: int = 20,
        cursor: str | None = None,
        grade: str | None = None,
        subject: str | None = None,
    ) -> tuple[list[Conversation], str | None]:
        """List conversations for an actor, most recent first."""
        import base64
        from somaai.db.models import Message
        from sqlalchemy import func

        limit = min(limit, 100)

        from somaai.utils.meta import normalize_grade, normalize_subject

        # Base query with message count JOIN
        stmt = (
            select(Conversation, func.count(Message.id))
            .outerjoin(Message)
            .where(
                Conversation.actor_id == actor_id,
                Conversation.deleted_at.is_(None),
            )
            .group_by(Conversation.id)
        )

        # Filters with normalization
        if grade:
            grade = normalize_grade(grade)
            stmt = stmt.where(Conversation.grade == grade)
        if subject:
            subject = normalize_subject(subject)
            stmt = stmt.where(Conversation.subject == subject)

        if cursor:
            try:
                decoded = base64.b64decode(cursor).decode()
                ts_str, ref_id = decoded.split("|", 1)
                from datetime import datetime

                ref_ts = datetime.fromisoformat(ts_str)
                from sqlalchemy import and_, or_

                stmt = stmt.where(
                    or_(
                        Conversation.updated_at < ref_ts,
                        and_(
                            Conversation.updated_at == ref_ts,
                            Conversation.id < ref_id,
                        ),
                    )
                )
            except Exception:
                pass

        stmt = (
            stmt.order_by(
                Conversation.updated_at.desc(),
                Conversation.id.desc(),
            )
            .limit(limit + 1)
        )

        result = await self.db.execute(stmt)
        # rows is list of tuples (Conversation, count)
        rows = list(result.all())

        has_next = len(rows) > limit
        page_tuples = rows[:limit]

        page: list[Conversation] = []
        for convo, count in page_tuples:
            convo.message_count = count
            page.append(convo)

        next_cursor: str | None = None
        if has_next and page:
            last = page[-1]
            raw = f"{last.updated_at.isoformat()}|{last.id}"
            next_cursor = base64.b64encode(raw.encode()).decode()

        return page, next_cursor

    async def get_owned(
        self,
        conversation_id: str,
        actor_id: str,
    ) -> Conversation | None:
        """Get a conversation if owned by the actor.

        Returns None (not 403) to prevent enumeration attacks.

        Args:
            conversation_id: Conversation to retrieve
            actor_id: Actor who must own it

        Returns:
            Conversation if owned, None otherwise
        """
        stmt = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.actor_id == actor_id,
            Conversation.deleted_at.is_(None),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_title(
        self,
        conversation_id: str,
        title: str,
    ) -> None:
        """Update conversation title.

        Args:
            conversation_id: Conversation to update
            title: New title (truncated to 255 chars)
        """
        convo = await self.db.get(Conversation, conversation_id)
        if convo:
            convo.title = title[:255]
            convo.updated_at = kigali_now()

    async def touch(self, conversation_id: str) -> None:
        """Update the updated_at timestamp.

        Args:
            conversation_id: Conversation to touch
        """
        convo = await self.db.get(Conversation, conversation_id)
        if convo:
            convo.updated_at = kigali_now()

    async def delete(self, conversation_id: str) -> bool:
        """Soft-delete a conversation.

        Args:
            conversation_id: Conversation to delete

        Returns:
            True if deleted, False if not found
        """
        convo = await self.db.get(Conversation, conversation_id)
        if not convo or convo.deleted_at:
            return False

        convo.deleted_at = kigali_now()
        await self.db.flush()
        logger.info("Conversation soft-deleted", extra={"conversation_id": conversation_id})
        return True
