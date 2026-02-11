"""Factory for creating RAG pipeline instances."""

from __future__ import annotations

import os

from somaai.modules.rag.pipelines import RAGPipeline
from somaai.providers.llm import LLMClient
from somaai.settings import Settings


def get_rag_pipeline(settings: Settings, llm: LLMClient) -> RAGPipeline:
    """Create RAG pipeline based on settings.

    Args:
        settings: Application settings
        llm: Initialized LLM client

    Returns:
        Configured RAG pipeline instance

    Raises:
        RuntimeError: If llm_backend is "mock" outside of tests
    """
    _backend = (settings.llm_backend or "groq").lower()

    if _backend == "mock":
        # Fail fast: mock backend is only for tests.
        # In production, this would silently return fake data.
        _is_testing = os.environ.get("TESTING", "").lower() in (
            "1",
            "true",
        )
        if not _is_testing:
            raise RuntimeError(
                "LLM_BACKEND='mock' is not allowed outside of tests. "
                "Set LLM_BACKEND to 'groq', 'openai', or another real "
                "provider, or set TESTING=1 for test mode."
            )

    return RAGPipeline(settings=settings)
