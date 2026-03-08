"""Chat endpoints for student and teacher interactions."""

import asyncio
import logging
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from somaai.contracts.chat import (
    ChatRequest,
    ChatResponse,
    CitationResponse,
    ConversationListResponse,
    ConversationResponse,
    CreateConversationRequest,
    MessageListResponse,
    MessageResponse,
    UpdateConversationRequest,
)
from somaai.db.session import get_session
from somaai.deps import get_actor_id, get_chat_service
from somaai.exceptions import not_found_exception
from somaai.modules.chat.conversation import ConversationService
from somaai.modules.chat.service import ChatService
from somaai.settings import settings
from somaai.utils.security import sanitize_query

logger = logging.getLogger(__name__)

# ── Rate limiter (graceful: no-op if slowapi not installed) ──────

try:
    from slowapi import Limiter

    from somaai.middleware import _get_actor_id_or_ip

    _limiter = Limiter(key_func=_get_actor_id_or_ip)

    def _rate_limit(rule: str) -> Callable:
        """Apply slowapi rate limit decorator."""
        return _limiter.limit(rule)

except ImportError:
    _limiter = None  # type: ignore[assignment]

    def _rate_limit(rule: str) -> Callable:  # type: ignore[misc]
        """No-op rate limit decorator when slowapi is not installed."""
        return lambda f: f


router = APIRouter(prefix="/chat/conversations", tags=["chat"])


# ── Conversation CRUD ────────────────────────────────────────────


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=201,
)
@_rate_limit(settings.security.rate_limit_create_conversation)
async def create_conversation(
    request: Request,
    data: CreateConversationRequest,
    actor_id: str = Depends(get_actor_id),
    db: AsyncSession = Depends(get_session),
) -> ConversationResponse:
    """Create a new conversation."""
    service = ConversationService(db)
    try:
        convo = await service.create(
            actor_id=actor_id,
            grade=data.grade,
            subject=data.subject,
            title=data.title,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()

    return ConversationResponse(
        id=convo.id,
        title=convo.title,
        grade=convo.grade,
        subject=convo.subject,
        message_count=getattr(convo, "message_count", 0),  # Use getattr with default
        created_at=convo.created_at,
        updated_at=convo.updated_at,
    )


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    cursor: str | None = Query(default=None, description="Pagination cursor"),
    limit: int = Query(default=20, ge=1, description="Page size (capped internally)"),
    grade: str | None = Query(default=None, description="Filter by grade"),
    subject: str | None = Query(default=None, description="Filter by subject"),
    actor_id: str = Depends(get_actor_id),
    db: AsyncSession = Depends(get_session),
) -> ConversationListResponse:
    """List conversations for the current actor, most recent first."""
    service = ConversationService(db)
    convos, next_cursor = await service.list_for_actor(
        actor_id, limit=limit, cursor=cursor, grade=grade, subject=subject
    )

    return ConversationListResponse(
        conversations=[
            ConversationResponse(
                id=c.id,
                title=c.title,
                grade=c.grade,
                subject=c.subject,
                message_count=c.message_count,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in convos
        ],
        next_cursor=next_cursor,
    )


@router.get("/{id}", response_model=ConversationResponse)
async def get_conversation(
    id: str,
    actor_id: str = Depends(get_actor_id),
    db: AsyncSession = Depends(get_session),
) -> ConversationResponse:
    """Retrieve a single conversation."""
    service = ConversationService(db)
    convo = await service.get_detail_for_actor(id, actor_id)
    if not convo:
        raise HTTPException(
            status_code=404, detail="Conversation not found or not owned"
        )

    return ConversationResponse(
        id=convo.id,
        title=convo.title,
        grade=convo.grade,
        subject=convo.subject,
        message_count=convo.message_count,
        created_at=convo.created_at,
        updated_at=convo.updated_at,
    )


@router.patch("/{id}", response_model=ConversationResponse)
async def update_conversation(
    id: str,
    data: UpdateConversationRequest,
    actor_id: str = Depends(get_actor_id),
    db: AsyncSession = Depends(get_session),
) -> ConversationResponse:
    """Update conversation title."""
    service = ConversationService(db)
    # Check ownership first using get_owned (we only need detailed
    # response at the end)
    convo = await service.get_owned(id, actor_id)
    if not convo:
        raise HTTPException(
            status_code=404, detail="Conversation not found or not owned"
        )

    await service.update_title(id, data.title)
    await db.commit()

    # Get updated detail with count
    updated = await service.get_detail_for_actor(id, actor_id)
    if not updated:
        # Should theoretically not happen if refresh succeeds
        raise HTTPException(
            status_code=404, detail="Conversation not found after update"
        )

    return ConversationResponse(
        id=updated.id,
        title=updated.title,
        grade=updated.grade,
        subject=updated.subject,
        message_count=updated.message_count,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
    )


@router.delete("/{id}", status_code=204)
async def delete_conversation(
    id: str,
    actor_id: str = Depends(get_actor_id),
    db: AsyncSession = Depends(get_session),
) -> None:
    """Delete a conversation."""
    service = ConversationService(db)
    convo = await service.get_owned(id, actor_id)
    if not convo:
        raise HTTPException(
            status_code=404, detail="Conversation not found or not owned"
        )

    await service.delete(id)
    await db.commit()


@router.get(
    "/{conversation_id}/messages",
    response_model=MessageListResponse,
)
async def list_messages(
    conversation_id: str,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1),
    chat_service: ChatService = Depends(get_chat_service),
    actor_id: str = Depends(get_actor_id),
    db: AsyncSession = Depends(get_session),
) -> MessageListResponse:
    """List messages in a conversation (paginated history)."""
    convo_service = ConversationService(db)
    convo = await convo_service.get_owned(conversation_id, actor_id)
    if not convo:
        raise not_found_exception("Conversation not found")

    messages, next_cursor = await chat_service.list_messages(
        conversation_id=conversation_id,
        limit=limit,
        cursor=cursor,
    )
    return MessageListResponse(messages=messages, next_cursor=next_cursor)


# ── Chat within conversation ─────────────────────────────────────


@router.post(
    "/{conversation_id}/ask",
    response_model=ChatResponse,
    status_code=201,
)
@_rate_limit(settings.security.rate_limit_ask)
async def ask_question(
    conversation_id: str,
    data: ChatRequest,
    request: Request,
    chat_service: ChatService = Depends(get_chat_service),
    actor_id: str = Depends(get_actor_id),
    db: AsyncSession = Depends(get_session),
) -> ChatResponse:
    """Ask a question within a conversation."""
    from somaai.utils.logging_ext import (
        conversation_id_ctx,
        set_conversation_id,
    )

    # Validate conversation ownership (404 to prevent enumeration)
    convo_service = ConversationService(db)
    convo = await convo_service.get_owned(conversation_id, actor_id)
    if not convo:
        raise not_found_exception(f"Conversation {conversation_id} not found")

    conv_token = set_conversation_id(conversation_id)

    try:
        # Sanitize input
        try:
            data.question = sanitize_query(data.question)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Execute with timeout
        try:
            async with asyncio.timeout(30):
                response = await chat_service.ask(
                    data=data,
                    conversation=convo,
                )
                # Basic validation before committing
                if not response.message_id:
                    await db.rollback()
                    logger.error(
                        "Response missing message_id",
                        extra={"conversation_id": conversation_id},
                    )
                    raise ValueError("Invalid response: missing message_id")

                await db.commit()
                return response
        except asyncio.TimeoutError:
            await db.rollback()  # Explicit rollback
            logger.error(
                "Chat request timeout",
                extra={
                    "actor_id": actor_id,
                    "conversation_id": conversation_id,
                },
            )
            raise HTTPException(
                status_code=504,
                detail=("Request timeout — please try again with a simpler question"),
            )
        except ConnectionError as e:
            await db.rollback()  # Explicit rollback
            # Qdrant or external service connection failure
            error_str = str(e).lower()
            if "qdrant" in error_str:
                detail = "Vector search service temporarily unavailable. Please try again shortly."
            elif "redis" in error_str:
                detail = "Cache service temporarily unavailable. Please try again shortly."
            else:
                detail = "AI service temporarily unavailable. Please try again shortly."
            
            logger.error(
                "External service connection failed",
                extra={
                    "actor_id": actor_id,
                    "conversation_id": conversation_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise HTTPException(status_code=503, detail=detail)
        except ValueError as e:
            # Response validation failed or invalid input
            await db.rollback()
            logger.warning(
                "Validation error in chat request",
                extra={
                    "actor_id": actor_id,
                    "conversation_id": conversation_id,
                    "error": str(e),
                },
            )
            raise HTTPException(
                status_code=400,
                detail=str(e),
            )
        except Exception as e:
            await db.rollback()  # Explicit rollback
            # Catch-all for unexpected errors
            logger.error(
                "Unexpected error in chat request",
                extra={
                    "actor_id": actor_id,
                    "conversation_id": conversation_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            # Re-raise as 500 with generic message (don't leak internals)
            raise HTTPException(
                status_code=500,
                detail="An unexpected error occurred. Please try again.",
            )
    finally:
        conversation_id_ctx.reset(conv_token)


@router.post(
    "/{conversation_id}/ask/stream",
    tags=["chat"],
    status_code=501,
)
async def ask_question_stream(
    conversation_id: str,
    data: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
    actor_id: str = Depends(get_actor_id),
    db: AsyncSession = Depends(get_session),
):
    """Ask a question with streaming response (v2 Placeholder).

    Currently returns 501 Not Implemented.
    """
    # Verify ownership before returning 501
    convo_service = ConversationService(db)
    convo = await convo_service.get_owned(conversation_id, actor_id)
    if not convo:
        raise not_found_exception("Conversation not found")

    raise HTTPException(
        status_code=501,
        detail="Streaming chat (v2) is not yet implemented in this version.",
    )


# ── Message retrieval ─────────────────────────────────────────────


@router.get("/{conversation_id}/messages/{message_id}")
async def get_message(
    conversation_id: str,
    message_id: str,
    chat_service: ChatService = Depends(get_chat_service),
    actor_id: str = Depends(get_actor_id),
    db: AsyncSession = Depends(get_session),
) -> MessageResponse:
    """Get a specific message by ID within a conversation.

    Returns 404 if message not found, doesn't belong to conversation,
    or not owned by actor.
    """
    convo_service = ConversationService(db)
    convo = await convo_service.get_owned(conversation_id, actor_id)
    if not convo:
        raise not_found_exception("Conversation not found")

    message = await chat_service.get_message(
        conversation_id=conversation_id, message_id=message_id
    )
    if not message:
        raise not_found_exception("Message not found")
    return message


@router.get(
    "/{conversation_id}/messages/{message_id}/citations",
    response_model=list[CitationResponse],
)
async def get_message_citations(
    conversation_id: str,
    message_id: str,
    chat_service: ChatService = Depends(get_chat_service),
    actor_id: str = Depends(get_actor_id),
    db: AsyncSession = Depends(get_session),
) -> list[CitationResponse]:
    """Get citations for a message within a conversation.

    Returns 404 if message not found, doesn't belong to conversation,
    or not owned by actor.
    """
    convo_service = ConversationService(db)
    convo = await convo_service.get_owned(conversation_id, actor_id)
    if not convo:
        raise not_found_exception("Conversation not found")

    citations = await chat_service.get_message_citations(
        conversation_id=conversation_id, message_id=message_id
    )
    if citations is None:
        raise not_found_exception("Message not found")

    return citations
