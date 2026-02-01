"""LLM provider adapters + factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from somaai.settings import Settings


@runtime_checkable
class LLMClient(Protocol):
    async def generate(self, prompt: str) -> str: ...
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    def generate_stream(self, prompt: str) -> AsyncIterator[str]: ...


class MockLLMProvider:
    """Mock LLM provider for local dev/tests (no API keys needed)."""

    async def generate(self, prompt: str) -> str:
        import json
        return json.dumps({
            "answer": (
                "MOCK_ANSWER: You are SomaAI, an educational assistant for Rwandan "
                "students and teachers. You help with curriculum."
            ),
            "sufficiency": "sufficient",
            "is_grounded": True,
            "confidence": 1.0,
            "analogy": None,
            "realworld_context": None
        })

    async def generate_stream(self, prompt: str) -> AsyncIterator[str]:
        text = await self.generate(prompt)
        yield text

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Deterministic dummy embeddings
        return [[0.0] * 768 for _ in texts]


class OpenAILLMProvider:
    """OpenAI provider (skeleton)."""

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    async def generate(self, prompt: str) -> str:
        raise NotImplementedError("OpenAI provider not implemented yet")

    async def generate_stream(self, prompt: str) -> AsyncIterator[str]:
        raise NotImplementedError("OpenAI streaming not implemented yet")
        # unreachable but makes this an async generator for type checking
        yield ""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("OpenAI embeddings not implemented yet")


class GroqLLMProvider:
    """Groq provider implementation."""

    def __init__(self, api_key: str, model: str):
        try:
            from groq import AsyncGroq
        except ImportError:
            raise ImportError("groq package not found. Install with 'pip install groq'")

        self.client = AsyncGroq(api_key=api_key)
        self.model = model

    async def generate(self, prompt: str) -> str:
        """Generate text using Groq API."""
        response = await self.client.chat.completions.create(
            messages=[
                {"role": "user", "content": prompt}
            ],
            model=self.model,
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        return response.choices[0].message.content or ""

    async def generate_stream(self, prompt: str) -> AsyncIterator[str]:
        raise NotImplementedError("Groq streaming not implemented yet")
        yield ""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("Groq embeddings not implemented (use local).")


def get_llm(settings: Settings) -> LLMClient:
    """Return the configured LLM provider based on settings.llm_backend."""
    backend = (settings.llm_backend or "mock").lower()

    if backend == "mock":
        return MockLLMProvider()

    if backend == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_BACKEND=openai")
        if not settings.openai_model:
            raise ValueError("OPENAI_MODEL is required when LLM_BACKEND=openai")
        return OpenAILLMProvider(
            api_key=settings.openai_api_key, model=settings.openai_model
        )

    if backend == "groq":
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is required when LLM_BACKEND=groq")
        if not settings.groq_model:
            raise ValueError("GROQ_MODEL is required when LLM_BACKEND=groq")
        return GroqLLMProvider(api_key=settings.groq_api_key, model=settings.groq_model)

    if backend == "huggingface":
        raise NotImplementedError("HuggingFace backend not implemented yet")

    raise ValueError(f"Unknown LLM_BACKEND: {backend}")
