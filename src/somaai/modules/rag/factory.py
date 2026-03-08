"""Factory for creating RAG pipeline instances."""

from __future__ import annotations

from somaai.modules.rag.pipelines import RAGPipeline
from somaai.providers.llm import LLMClient
from somaai.settings import Settings

# Module-level singleton — RAGPipeline is stateless; its Retriever
# and LLMGenerator already lazy-init their own singletons, so
# re-creating the pipeline per request is pure waste.
_RAG_PIPELINE: RAGPipeline | None = None


def get_rag_pipeline(settings: Settings, llm: LLMClient) -> RAGPipeline:
    """Get or create singleton RAG pipeline.

    Args:
        settings: Application settings
        llm: Initialized LLM client

    Returns:
        Cached RAG pipeline instance

    Raises:
        RuntimeError: If llm_backend is "mock" outside of tests
    """
    global _RAG_PIPELINE

    _backend = (settings.llm.backend or "groq").lower()

    if _backend == "mock":
        # Fail fast: mock backend is only for tests.
        # In production, this would silently return fake data.
        from somaai.settings import AppEnv

        if settings.env != AppEnv.TESTING:
            raise RuntimeError(
                "LLM_BACKEND='mock' is not allowed outside of tests. "
                "Set LLM_BACKEND to 'groq', 'openai', or another real "
                "provider, or set SOMAAI_ENV=test for test mode."
            )

    if _RAG_PIPELINE is None:
        _RAG_PIPELINE = RAGPipeline(settings=settings)

    return _RAG_PIPELINE
