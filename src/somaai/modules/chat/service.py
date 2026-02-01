"""Chat module service."""

from datetime import datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from somaai.contracts.chat import (
    ChatRequest,
    ChatResponse,
    CitationResponse,
    MessageResponse,
    Preferences,
)
from somaai.contracts.common import GradeLevel, Subject, Sufficiency, UserRole
from somaai.db.models import Message, TeacherProfile
from somaai.modules.chat.citations import get_citation_extractor
from somaai.modules.chat.memory import MemoryLoader
from somaai.modules.rag.pipelines import BaseRAGPipeline
from somaai.utils.ids import generate_id
from somaai.utils.time import utc_now


class ChatService:
    """Chat service."""

    def __init__(self, db: AsyncSession, rag_pipeline: BaseRAGPipeline) -> None:
        """Initialize ChatService with database session and RAG pipeline.

        Args:
            db: Async database session for persistence
            rag_pipeline: RAG pipeline instance for answer generation
        """
        self.db = db
        self.rag_pipeline = rag_pipeline
        self.citation_manager = get_citation_extractor()
        self.memory_loader = MemoryLoader(db)

    async def ask(
        self,
        data: ChatRequest,
        actor_id: str,
    ) -> ChatResponse:
        """Process a chat message and generate AI response.
        Flow:
        1. Normalize question
        2. Determine preferences
        3. Fetch History
        4. Run RAG pipeline
        5. Save message
        6. Save citations
        7. Return ChatResponse
        """
        # 1. Normalize question
        question = data.question.strip()

        # 2. Determine effective preferences
        effective_preferences = await self._resolve_preferences(
            user_role=data.user_role,
            request_preferences=data.preferences,
            actor_id=actor_id,
        )

        # 3. Preparation: Fetch History
        history_turns: list[dict[str, str]] = []
        if data.session_id:
            history_turns = await self.memory_loader.get_recent_turns(
                session_id=data.session_id,
                actor_id=actor_id,
                limit=6,
            )
        history_text = self.memory_loader.format_history_for_prompt(history_turns)

        # 4. Run RAG pipeline (using new signature)
        pipeline_preferences = {
            "enable_analogy": effective_preferences.enable_analogy,
            "enable_realworld": effective_preferences.enable_realworld,
        }

        rag_result = await self.rag_pipeline.run(
            query=question,
            grade=data.grade.value,
            subject=data.subject.value,
            user_role=data.user_role.value,
            preferences=pipeline_preferences,
            session_id=data.session_id,
            history=history_text,
        )

        # 5. Generate message ID and timestamp
        message_id = generate_id()
        created_at = utc_now()

        # 6. Save message to DB
        message = Message(
            id=message_id,
            session_id=data.session_id,
            actor_id=actor_id,
            user_role=data.user_role.value,
            question=question,
            answer=rag_result["answer"],
            sufficiency=rag_result.get("sufficiency", "sufficient"),
            grade=data.grade.value,
            subject=data.subject.value,
            analogy=rag_result.get("analogy"),
            realworld_context=rag_result.get("realworld_context"),
            created_at=created_at,
        )
        self.db.add(message)

        # 7. Handle Citations
        # Reconstruct CitationResponse objects from dicts for the manager
        citations_dicts = rag_result.get("citations", [])
        citations_objects = [CitationResponse(**c) for c in citations_dicts]
        chunks_map = rag_result.get("chunks_map", {})

        await self.citation_manager.save_citations(
            db=self.db,
            message_id=message_id,
            citations=citations_objects,
            chunks_map=chunks_map
        )

        await self.db.flush()

        # 8. Return ChatResponse
        return ChatResponse(
            message_id=message_id,
            answer=rag_result["answer"],
            sufficiency=Sufficiency(rag_result.get("sufficiency", "sufficient")),
            citations=citations_objects,
            analogy=rag_result.get("analogy"),
            realworld_context=rag_result.get("realworld_context"),
            created_at=created_at,
        )

    async def _resolve_preferences(
        self,
        user_role: UserRole,
        request_preferences: Preferences,
        actor_id: str,
    ) -> Preferences:
        """Resolve effective preferences based on user role and profile."""
        if user_role == UserRole.STUDENT:
            return request_preferences

        profile = await self._get_teacher_profile(actor_id)
        if profile:
            enable_analogy = (
                request_preferences.enable_analogy
                if request_preferences.enable_analogy is not None
                else cast(bool, profile.analogy_enabled)
            )
            enable_realworld = (
                request_preferences.enable_realworld
                if request_preferences.enable_realworld is not None
                else cast(bool, profile.realworld_enabled)
            )
        else:
            enable_analogy = (
                request_preferences.enable_analogy
                if request_preferences.enable_analogy is not None
                else True
            )
            enable_realworld = (
                request_preferences.enable_realworld
                if request_preferences.enable_realworld is not None
                else True
            )
        return Preferences(
            enable_analogy=enable_analogy,
            enable_realworld=enable_realworld,
        )

    async def _get_teacher_profile(self, actor_id: str) -> TeacherProfile | None:
        """Get teacher profile from database."""
        result = await self.db.execute(
            select(TeacherProfile).where(TeacherProfile.teacher_id == actor_id)
        )
        return result.scalar_one_or_none()

    async def get_message(
        self,
        message_id: str,
        actor_id: str,
    ) -> MessageResponse | None:
        """Get a specific message by ID."""
        result = await self.db.execute(
            select(Message).where(
                Message.id == message_id, Message.actor_id == actor_id
            )
        )
        message = result.scalar_one_or_none()

        if not message:
            return None

        # Delegate citation retrieval to manager
        citations = await self.citation_manager.get_message_citations(self.db, message_id)

        return MessageResponse(
            message_id=cast(str, message.id),
            session_id=cast(str | None, message.session_id),
            user_role=UserRole(cast(str, message.user_role)),
            question=cast(str, message.question),
            answer=cast(str, message.answer),
            sufficiency=Sufficiency(cast(str, message.sufficiency)),
            grade=GradeLevel(cast(str, message.grade)),
            subject=Subject(cast(str, message.subject)),
            citations=citations,
            created_at=cast(datetime, message.created_at),
        )

    async def get_message_citations(
        self,
        message_id: str,
        actor_id: str,
    ) -> list[CitationResponse] | None:
        """Get citations for a message."""
        # First verify message ownership
        result = await self.db.execute(
            select(Message).where(
                Message.id == message_id, Message.actor_id == actor_id
            )
        )
        if not result.scalar_one_or_none():
            return None

        return await self.citation_manager.get_message_citations(self.db, message_id)
