"""Chat module service."""

import logging
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from somaai.contracts.chat import (
    ChatRequest,
    ChatResponse,
    CitationResponse,
    Enhancement,
    MessageResponse,
    Preferences,
    ResponseEnhancements,
)
from somaai.contracts.common import Sufficiency, UserRole
from somaai.db.models import (
    Chunk,
    Conversation,
    Message,
    MessageCitation,
    TeacherProfile,
)
from somaai.modules.chat.citations import get_citation_extractor
from somaai.modules.chat.context import ContextBuilder
from somaai.modules.chat.conversation import ConversationService
from somaai.modules.rag.pipelines import BaseRAGPipeline
from somaai.utils.ids import generate_id
from somaai.utils.time import utc_now

logger = logging.getLogger(__name__)


class ChatService:
    """Chat service."""

    def __init__(
        self,
        db: AsyncSession,
        rag_pipeline: BaseRAGPipeline,
        actor_id: str,
    ) -> None:
        """Initialize ChatService.

        Args:
            db: Async database session for persistence
            rag_pipeline: RAG pipeline instance for answer generation
            actor_id: Resolved actor ID for this request — embedded once
                so downstream helpers don't need it threaded through their
                signatures.
        """
        self.db = db
        self.rag_pipeline = rag_pipeline
        self.actor_id = actor_id
        self.citation_manager = get_citation_extractor()
        self.context_builder = ContextBuilder(db)
        self.conversation_service = ConversationService(db)

    async def ask(
        self,
        data: ChatRequest,
        conversation: Conversation,  # Injected already-loaded conversation
    ) -> ChatResponse:
        """Process a chat message and generate AI response.

        Flow:
        1. Load conversation — resolve grade/subject (source of truth)
        2. Determine effective preferences
        3. Build token-aware history
        4. Run RAG pipeline
        5. Save message
        6. Save citations
        7. Auto-title on first message
        8. Return ChatResponse
        """
        conversation_id = conversation.id
        grade = str(conversation.grade)
        subject = str(conversation.subject)

        # 2. Normalize question
        question = data.question.strip()

        # 3. Determine effective preferences
        effective_enhancements = await self._resolve_enhancements(
            user_role=data.user_role,
            requested=data.preferences,
        )

        pipeline_preferences = {
            "enable_analogy": Enhancement.ANALOGY in effective_enhancements,
            "enable_realworld": Enhancement.REAL_WORLD in effective_enhancements,
        }

        # 4. Build token-aware history
        history_text = await self.context_builder.build_history(
            conversation_id=conversation_id,
            actor_id=self.actor_id,
        )

        # 5. Run RAG pipeline (graceful degradation on failure)
        try:
            rag_result = await self.rag_pipeline.run(
                query=question,
                grade=grade,
                subject=subject,
                user_role=data.user_role.value,
                preferences=pipeline_preferences,
                history=history_text,
            )
        except Exception as exc:
            logger.error(
                "RAG pipeline failed, returning graceful fallback",
                extra={
                    "conversation_id": conversation_id,
                    "actor_id": self.actor_id,
                    "error": str(exc),
                },
                exc_info=True,
            )
            rag_result = {
                "answer": ("I'm unable to answer right now. Please try again shortly."),
                "sufficiency": "insufficient",
                "confidence": 0.0,
                "citations": [],
                "chunks_map": {},
            }

        # 6. Generate message ID and timestamp
        message_id = generate_id()
        created_at = utc_now()

        # 7. Save message to DB
        raw_analogy = rag_result.get("analogy")
        raw_realworld = rag_result.get("realworld_context")

        # Use a more conservative ratio for safety
        # (avg 3.2 chars per token for English/Code)
        conf_val = float(
            Decimal(str(rag_result.get("confidence", 0.0))).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
        )

        message = Message(
            id=message_id,
            conversation_id=conversation_id,
            actor_id=self.actor_id,
            user_role=data.user_role.value,
            question=question,
            answer=rag_result["answer"],
            sufficiency=rag_result.get("sufficiency", "sufficient"),
            confidence=conf_val,
            grade=grade,
            subject=subject,
            analogy=raw_analogy,
            realworld_context=raw_realworld,
            created_at=created_at,
        )
        self.db.add(message)

        # 8. Handle Citations
        citations_dicts = rag_result.get("citations", [])
        citations_objects = [CitationResponse(**c) for c in citations_dicts]
        chunks_map = rag_result.get("chunks_map", {})

        # Validate citation data before saving
        if citations_objects and not chunks_map:
            logger.warning(
                "Citations generated but chunks_map is empty - "
                "citations will not be saved",
                extra={
                    "message_id": message_id,
                    "citation_count": len(citations_objects),
                    "conversation_id": conversation_id,
                },
            )

        await self.citation_manager.save_citations(
            db=self.db,
            message_id=message_id,
            citations=citations_objects,
            chunks_map=chunks_map,
        )

        await self.db.flush()

        # 9. Auto-title: use first question as title
        msg_count_stmt = (
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conversation_id)
        )
        msg_count_result = await self.db.execute(msg_count_stmt)
        if msg_count_result.scalar() == 1:
            await self.conversation_service.update_title(conversation_id, question[:80])

        # Touch conversation updated_at
        await self.conversation_service.touch(conversation_id)

        # 10. Build ResponseEnhancements if any were generated
        enhancements = None
        if raw_analogy or raw_realworld:
            enhancements = ResponseEnhancements(
                analogy=raw_analogy,
                real_world_context=raw_realworld,
            )

        # 11. Return ChatResponse
        return ChatResponse(
            message_id=message_id,
            conversation_id=conversation_id,
            answer=rag_result["answer"],
            sufficiency=Sufficiency(rag_result.get("sufficiency", "sufficient")),
            confidence=float(
                Decimal(str(rag_result.get("confidence", 0.0))).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )
            ),
            citations=citations_objects,
            enhancements=enhancements,
            created_at=created_at,
        )

    async def _resolve_enhancements(
        self,
        user_role: UserRole,
        requested: Preferences,
    ) -> set[Enhancement]:
        """Resolve which enhancements to enable for this request.

        Priority: explicit request > teacher profile defaults > role defaults.

        Returns a set of enabled Enhancement values.
        """
        if requested.enabled_enhancements is not None:
            # Caller explicitly chose — honour it exactly.
            return set(requested.enabled_enhancements)

        if user_role == UserRole.TEACHER:
            profile = await self._get_teacher_profile(self.actor_id)
            if profile:
                enabled: set[Enhancement] = set()
                if cast(bool, profile.analogy_enabled):
                    enabled.add(Enhancement.ANALOGY)
                if cast(bool, profile.realworld_enabled):
                    enabled.add(Enhancement.REAL_WORLD)
                return enabled

        # Default: all enhancements on
        return {Enhancement.ANALOGY, Enhancement.REAL_WORLD}

    async def _get_teacher_profile(self, actor_id: str) -> TeacherProfile | None:
        """Get teacher profile from database."""
        result = await self.db.execute(
            select(TeacherProfile).where(TeacherProfile.teacher_id == actor_id)
        )
        return result.scalar_one_or_none()

    async def get_message(
        self,
        conversation_id: str,
        message_id: str,
    ) -> MessageResponse | None:
        """Get a specific message by ID in a conversation."""
        from sqlalchemy.orm import joinedload

        result = await self.db.execute(
            select(Message)
            .options(
                joinedload(Message.citations)
                .joinedload(MessageCitation.chunk)
                .joinedload(Chunk.document)
            )
            .where(
                Message.id == message_id,
                Message.conversation_id == conversation_id,
                Message.actor_id == self.actor_id,
            )
        )
        message = result.unique().scalar_one_or_none()

        if not message:
            return None

        # Citations are already loaded via nested joinedload
        citations = [
            CitationResponse(
                doc_id=c.chunk.document_id,
                doc_title=c.chunk.document.title,
                section_title=None,
                page_start=c.chunk.page_start,
                page_end=c.chunk.page_end,
                chunk_preview=c.snippet or "",
                view_url="",  # To be generated in a mapping layer if needed
                relevance_score=c.relevance_score or 0.0,
            )
            for c in message.citations
        ]

        # Build enhancements block from stored columns
        raw_analogy = cast(str, message.analogy) if message.analogy else None
        raw_realworld = (
            cast(str, message.realworld_context) if message.realworld_context else None
        )
        enhancements = None
        if raw_analogy or raw_realworld:
            enhancements = ResponseEnhancements(
                analogy=raw_analogy,
                real_world_context=raw_realworld,
            )

        return MessageResponse(
            message_id=cast(str, message.id),
            conversation_id=cast(str, message.conversation_id),
            grade=cast(str, message.grade),
            subject=cast(str, message.subject),
            user_role=UserRole(cast(str, message.user_role)),
            question=cast(str, message.question),
            answer=cast(str, message.answer),
            sufficiency=Sufficiency(cast(str, message.sufficiency)),
            confidence=float(message.confidence or 0.0),
            citations=citations,
            enhancements=enhancements,
            created_at=cast(datetime, message.created_at),
        )

    async def get_message_citations(
        self,
        conversation_id: str,
        message_id: str,
    ) -> list[CitationResponse] | None:
        """Get citations for a message in a conversation."""
        # First verify message and conversation ownership
        result = await self.db.execute(
            select(Message).where(
                Message.id == message_id,
                Message.conversation_id == conversation_id,
                Message.actor_id == self.actor_id,
            )
        )
        if not result.scalar_one_or_none():
            return None

        return await self.citation_manager.get_message_citations(self.db, message_id)

    async def list_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[MessageResponse], str | None]:
        """List messages in a conversation with pagination and joined citations.

        Args:
            conversation_id: Conversation ID
            limit: Page size
            cursor: Pagination cursor (ISO timestamp)

        Returns:
            Tuple of (MessageResponses, next_cursor)
        """
        import base64

        from sqlalchemy.orm import joinedload

        limit = min(limit, 100)

        # Base query
        stmt = (
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.actor_id == self.actor_id,
            )
            .options(
                joinedload(Message.citations)
                .joinedload(MessageCitation.chunk)
                .joinedload(Chunk.document)
            )
        )

        if cursor:
            try:
                decoded = base64.b64decode(cursor).decode()
                ref_ts = datetime.fromisoformat(decoded)
                stmt = stmt.where(Message.created_at < ref_ts)
            except Exception as e:
                logger.warning(
                    "Invalid pagination cursor, returning first page",
                    extra={
                        "cursor": cursor[:20] + "..." if len(cursor) > 20 else cursor,
                        "error": str(e),
                        "conversation_id": conversation_id,
                    },
                )
                # Continue without cursor filter (returns first page)

        # Order by created_at DESC (recent first) for pagination
        stmt = stmt.order_by(Message.created_at.desc()).limit(limit + 1)

        result = await self.db.execute(stmt)
        rows = list(result.unique().scalars().all())

        has_next = len(rows) > limit
        page_messages = rows[:limit]

        # Batch load citations for all messages in one query (performance optimization)
        message_ids = [msg.id for msg in page_messages]
        citations_by_message = await self.citation_manager.get_citations_batch(
            self.db, message_ids
        )

        responses = []
        for msg in page_messages:
            # Get pre-loaded citations from batch
            citations = citations_by_message.get(msg.id, [])

            # Map enhancements
            enhancements = None
            if msg.analogy or msg.realworld_context:
                enhancements = ResponseEnhancements(
                    analogy=msg.analogy,
                    real_world_context=msg.realworld_context,
                )

            responses.append(
                MessageResponse(
                    message_id=msg.id,
                    conversation_id=msg.conversation_id,
                    grade=msg.grade,
                    subject=msg.subject,
                    user_role=UserRole(msg.user_role),
                    question=msg.question,
                    answer=msg.answer,
                    sufficiency=Sufficiency(msg.sufficiency),
                    confidence=float(msg.confidence or 0.0),
                    citations=citations,
                    enhancements=enhancements,
                    created_at=msg.created_at,
                )
            )

        next_cursor: str | None = None
        if has_next and page_messages:
            last_ts = page_messages[-1].created_at.isoformat()
            next_cursor = base64.b64encode(last_ts.encode()).decode()

        return responses, next_cursor

    async def stream_ask(
        self,
        data: ChatRequest,
        conversation: Message,
    ):
        """Streaming version of ask (v2).

        This is a placeholder for future Server-Sent Events (SSE) support.
        Yields chunks of the response.
        """
        # In the future, this will yield partial JSON tokens or tokens.
        yield {"answer_chunk": "Streaming support is coming in v2."}
