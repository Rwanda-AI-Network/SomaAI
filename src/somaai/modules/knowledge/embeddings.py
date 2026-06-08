from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.embeddings import Embeddings
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import OpenAIEmbeddings

if TYPE_CHECKING:
    from somaai.settings import Settings

logger = logging.getLogger(__name__)


class ThreadSafeEmbeddings(Embeddings):
    """LangChain-compatible wrapper that offloads sync inference to a thread.

    HuggingFace ``embed_query`` / ``embed_documents`` are CPU-bound.
    When LangChain's ``QdrantVectorStore.asimilarity_search_with_score``
    calls the embedding model, it first tries the async methods.  This
    wrapper ensures those async methods use ``asyncio.to_thread`` so the
    Uvicorn event loop is never blocked.

    OpenAI embeddings are already network-bound, but the thread hop adds
    negligible overhead and keeps the interface uniform.
    """

    def __init__(self, inner: HuggingFaceEmbeddings | OpenAIEmbeddings) -> None:
        self._inner = inner

    # -- Sync interface (used by LangChain when no event loop) -----------

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._inner.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._inner.embed_query(text)

    # -- Async interface (used by LangChain's a* methods) ----------------

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._inner.embed_documents, texts)

    async def aembed_query(self, text: str) -> list[float]:
        return await asyncio.to_thread(self._inner.embed_query, text)


# Singleton embeddings model (wrapped for thread safety)
_EMBEDDINGS_MODEL: ThreadSafeEmbeddings | Embeddings | None = None


class MockEmbeddings(Embeddings):
    """Zero-overhead embeddings for tests (prevents model downloads in CI)."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 384 for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.0] * 384

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        return self.embed_query(text)


def get_embeddings(settings: Settings) -> ThreadSafeEmbeddings:
    """Get singleton thread-safe embeddings model.

    Returns a ``ThreadSafeEmbeddings`` wrapper so that both sync and
    async callers get correct behaviour without blocking the event loop.

    Args:
        settings: Application settings

    Returns:
        Shared ThreadSafeEmbeddings instance
    """
    global _EMBEDDINGS_MODEL
    if _EMBEDDINGS_MODEL is None:
        if settings.is_testing:
            logger.info("Using MockEmbeddings (CI/CD optimized)")
            _EMBEDDINGS_MODEL = MockEmbeddings()
            return _EMBEDDINGS_MODEL

        logger.info("Creating HuggingFace embeddings model (local)")
        inner = HuggingFaceEmbeddings(
            model_name="all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        _EMBEDDINGS_MODEL = ThreadSafeEmbeddings(inner)
    return _EMBEDDINGS_MODEL


async def aembed_query(settings: Settings, text: str) -> list[float]:
    """Embed a single query string without blocking the event loop.

    HuggingFace inference is CPU-bound; running it inline inside an async
    context starves the event loop.  This wrapper offloads to a thread pool
    so other coroutines can make progress while embeddings are computed.

    OpenAI embeddings are already network-bound so the thread hop adds
    negligible overhead and keeps the interface uniform.

    Args:
        settings: Application settings (used to initialise singleton once)
        text: Text to embed

    Returns:
        Embedding vector as a list of floats
    """
    model = get_embeddings(settings)
    return await model.aembed_query(text)


async def aembed_documents(settings: Settings, texts: list[str]) -> list[list[float]]:
    """Embed a batch of documents without blocking the event loop.

    Same rationale as ``aembed_query`` — CPU work goes to the thread pool.

    Args:
        settings: Application settings
        texts: List of texts to embed

    Returns:
        List of embedding vectors
    """
    model = get_embeddings(settings)
    return await model.aembed_documents(texts)
