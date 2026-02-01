"""Chat endpoints for student and teacher interactions."""

from fastapi import APIRouter, Depends

from somaai.contracts.chat import (
    ChatRequest,
    ChatResponse,
    CitationResponse,
    MessageResponse,
)
from somaai.deps import get_actor_id, get_chat_service
from somaai.exceptions import not_found_exception
from somaai.modules.chat.service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/ask", response_model=ChatResponse, status_code=201)
async def ask_question(
    data: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
    actor_id: str = Depends(get_actor_id),
) -> ChatResponse:
    """Ask a question and get an AI-generated answer.

    Works for both students and teachers:
    - Students: Basic RAG with optional analogy/realworld
    - Teachers: Defaults from profile, analogy/realworld enabled

    Request body:
    - query: The question to answer
    - grade: Grade level for context
    - subject: Subject for context
    - session_id: Optional conversation session
    - user_role: "student" or "teacher"
    - enable_analogy: Include analogy (optional for students)
    - enable_realworld: Include real-world context (optional)

    Response:
    - message_id: ID for reference/feedback
    - response: AI-generated answer
    - sufficiency: Whether enough context was found
    - citations: Source document references
    - analogy: Analogy explanation (if enabled)
    - realworld_context: Real-world application (if enabled)

    If insufficient context:
    - sufficiency = false
    - response contains fallback message
    """
    return await chat_service.ask(data=data, actor_id=actor_id)


@router.get("/messages/{message_id}", response_model=MessageResponse)
async def get_message(
    message_id: str,
    actor_id: str = Depends(get_actor_id),
    chat_service: ChatService = Depends(get_chat_service),
) -> MessageResponse:
    """Get a specific message by ID.

    Returns full message details including:
    - Original query and response
    - Grade and subject context
    - All citations

    Returns 404 if message not found.
    """
    message = await chat_service.get_message(message_id=message_id, actor_id=actor_id)
    if not message:
        raise not_found_exception(f"Message {message_id} not found")
    return message


@router.get("/messages/{message_id}/citations", response_model=list[CitationResponse])
async def get_message_citations(
    message_id: str,
    actor_id: str = Depends(get_actor_id),
    chat_service: ChatService = Depends(get_chat_service),
) -> list[CitationResponse]:
    """Get citations for a message.

    Returns list of source citations with:
    - doc_id: Source document ID
    - doc_title: Document title
    - page_number: Page number
    - chunk_content: Relevant excerpt
    - view_url: Link to view the page

    Used for "show sources" functionality.

    Returns 404 if message not found.
    """
    citations = await chat_service.get_message_citations(
        message_id=message_id, actor_id=actor_id
    )
    if citations is None:
        raise not_found_exception(f"Citations for message {message_id} not found")

    return citations


# @router.get("/documents/{doc_id}", response_model=DocumentResponse)
# async def get_view_document_url(doc_id: str):
#     """Get a document's view URL."""
#     return {"view_url": f"https://example.com/view/{doc_id}"}
