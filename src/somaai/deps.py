"""Dependency injection."""

from fastapi import Depends, Request
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


def get_actor_id(request: Request) -> str:
    """Get the actor ID from the session middleware.

    The SessionMiddleware hydrates ``request.state.actor_id`` on every
    API request. This dependency reads that value.

    Args:
        request: FastAPI Request object (auto-injected)

    Returns:
        Server-controlled actor ID string
    """
    actor_id = getattr(request.state, "actor_id", None)
    if actor_id:
        return actor_id
    # Fallback for non-API routes where middleware may not run
    return f"anon_{generate_short_id()}"


def get_chat_service(
    db: AsyncSession = Depends(get_session),
    rag_pipeline: BaseRAGPipeline = Depends(get_rag_pipeline_dep),
    actor_id: str = Depends(get_actor_id),
) -> ChatService:
    """Get chat service instance."""
    return ChatService(db, rag_pipeline, actor_id)
