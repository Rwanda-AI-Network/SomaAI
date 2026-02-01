"""Dependency injection."""

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from somaai.db.session import get_session
from somaai.modules.chat.service import ChatService
from somaai.modules.rag.factory import get_rag_pipeline
from somaai.modules.rag.pipelines import BaseRAGPipeline
from somaai.providers.llm import LLMClient, get_llm
from somaai.settings import Settings, settings
from somaai.utils.ids import generate_short_id


def get_settings() -> Settings:
    """Get settings."""
    return settings


def get_llm_dep(request: Request) -> LLMClient:
    """Get LLM dependency from app state."""
    return request.app.state.llm


def get_llm_instance(settings: Settings = Depends(get_settings)) -> LLMClient:
    """Get LLM client instance."""
    return get_llm(settings)


def get_rag_pipeline_dep(
    settings: Settings = Depends(get_settings),
    llm: LLMClient = Depends(get_llm_instance),
) -> BaseRAGPipeline:
    """Get RAG pipeline instance."""
    return get_rag_pipeline(settings, llm)


def get_actor_id(x_actor_id: str | None = Header(None, alias="X-Actor-Id")) -> str:
    """Get actor ID from request header.

    If no actor ID is provided, generate a temporary one.
    Frontend should persist and send the actor ID.

    Args:
        x_actor_id: Actor ID from X-Actor-Id header

    Returns:
        Actor ID (provided or generated)
    """
    if x_actor_id and x_actor_id.strip():
        return x_actor_id.strip()

    # Generate temporary ID if not provided
    # This allows API testing without frontend
    return f"anon_{generate_short_id()}"


def get_chat_service(
    db: AsyncSession = Depends(get_session),
    rag_pipeline: BaseRAGPipeline = Depends(get_rag_pipeline_dep),
) -> ChatService:
    """Get chat service instance."""
    return ChatService(db, rag_pipeline)
