"""Factory for creating RAG pipeline instances."""

from somaai.modules.rag.pipelines import BaseRAGPipeline, MockRAGPipeline, RAGPipeline
from somaai.providers.llm import LLMClient
from somaai.settings import Settings


def get_rag_pipeline(settings: Settings, llm: LLMClient) -> BaseRAGPipeline:
    """Create RAG pipeline based on settings.
    
    Args:
        settings: Application settings
        llm: Initialized LLM client
        
    Returns:
        Configured RAG pipeline instance
    """
    _backend = (settings.llm_backend or "mock").lower()

    if _backend == "mock":
        return MockRAGPipeline(llm=llm, settings=settings)

    # Return real pipeline for all other backends (groq, openai, etc.)
    # The real pipeline initializes its own components (Retriever, Generator)
    # using the global settings, but we pass settings explicitly if supported.
    return RAGPipeline(settings=settings)
