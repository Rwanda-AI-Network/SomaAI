"""LLM provider adapters + factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from somaai.settings import Settings

logger = logging.getLogger(__name__)


@runtime_checkable
class LLMClient(Protocol):
    async def generate(self, prompt: str) -> str: ...
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    def generate_stream(self, prompt: str) -> AsyncIterator[str]: ...


class MockLLMProvider:
    """Mock LLM provider for local dev/tests (no API keys needed)."""

    async def generate(self, prompt: str) -> str:
        import json

        # Check if analogy/realworld were requested in the prompt
        # LLMGenerator formats them into the prompt
        return json.dumps(
            {
                "answer": (
                    "MOCK_ANSWER: You are SomaAI, an educational assistant for Rwandan "
                    "students and teachers. You help with curriculum."
                ),
                "sufficiency": "sufficient",
                "is_grounded": True,
                "confidence": 1.0,
                "reasoning": "This is a mock response.",
                "citations": [
                    {"page_number": 1, "quote": "A cell is the basic unit of life."}
                ],
                "analogy": "A cell is like a small factory.",
                "realworld_context": "Cells are found in all living things.",
            }
        )

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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_random_exponential(multiplier=1, max=10),
        retry=retry_if_exception_type((Exception)),  # Narrower in production
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def generate(self, prompt: str) -> str:
        """Generate text using Groq API with retries.

        Strict Requirements:
        - 3 attempts
        - Exponential backoff + jitter
        - JSON mode enabled
        """
        try:
            response = await self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"Groq API call failed after retries: {e}")
            raise

    async def generate_stream(self, prompt: str) -> AsyncIterator[str]:
        raise NotImplementedError("Groq streaming not implemented yet")
        yield ""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("Groq embeddings not implemented (use local).")


class GeminiLLMProvider:
    """Google Gemini provider implementation."""

    def __init__(self, api_key: str, model: str):
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError(
                "google-generativeai package not found. "
                "Install with 'pip install google-generativeai'"
            )

        genai.configure(api_key=api_key)
        self.model_name = model.strip()
        # Ensure we don't have double models/ prefix
        if self.model_name.startswith("models/"):
            self.model_name = self.model_name.replace("models/", "", 1)
        
        self.client = genai.GenerativeModel(model_name=self.model_name)
        self.fallback_models = ["gemini-1.5-flash", "gemini-1.5-flash-latest", "gemini-1.0-pro"]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_random_exponential(multiplier=1, max=10),
        retry=retry_if_exception_type((Exception)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def generate(self, prompt: str) -> str:
        """Generate text using Gemini API with retries and fallback models."""
        try:
            return await self._generate_internal(self.model_name, prompt)
        except Exception as e:
            # If 404, try fallbacks
            if "404" in str(e) or "not found" in str(e).lower():
                logger.warning(f"Model {self.model_name} not found. Attempting model rotation...")
                for fallback in self.fallback_models:
                    if fallback == self.model_name:
                        continue
                    try:
                        logger.info(f"Gemini: Rotating to {fallback}")
                        return await self._generate_internal(fallback, prompt)
                    except Exception as fallback_e:
                        if "404" in str(fallback_e) or "not found" in str(fallback_e).lower():
                            continue
                        raise
            raise

    async def _generate_internal(self, model_name: str, prompt: str) -> str:
        """Internal helper to call Gemini with a specific model name."""
        try:
            import google.generativeai as genai
            client = genai.GenerativeModel(model_name=model_name)
            response = await client.generate_content_async(
                prompt,
                generation_config={"response_mime_type": "application/json"},
            )
            return response.text
        except Exception as e:
            logger.debug(f"Gemini error with {model_name}: {e}")
            raise

    async def generate_stream(self, prompt: str) -> AsyncIterator[str]:
        """Stream generation (simplified for now)."""
        response = await self.client.generate_content_async(prompt, stream=True)
        async for chunk in response:
            yield chunk.text

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using Gemini."""
        import google.generativeai as genai

        # Note: 'models/text-embedding-004' is the current standard
        # Use simple model name if provided in settings, 
        # but genai.embed_content usually needs the full path or defaults.
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=texts,
            task_type="retrieval_document",
        )
        return result["embedding"]


def get_llm(settings: Settings, fallback_to_mock: bool = False) -> LLMClient:
    """Return the configured LLM provider based on settings.llm_backend.

    Args:
        settings: Application settings.
        fallback_to_mock: If True, return MockLLMProvider if configuration is missing.
    """
    import logging

    logger = logging.getLogger("somaai.providers.llm")
    backend = (settings.llm_backend or "mock").lower()

    if backend == "mock":
        return MockLLMProvider()

    try:
        # if backend == "openai":
        #     if not settings.openai_api_key:
        #         raise ValueError(
        #             "SOMAAI_OPENAI_API_KEY is required for OpenAI backend"
        #         )
        #     if not settings.openai_model:
        #         raise ValueError(
        #             "SOMAAI_OPENAI_MODEL is required for OpenAI backend"
        #         )
        #     return OpenAILLMProvider(
        #         api_key=settings.openai_api_key.get_secret_value(),
        #         model=settings.openai_model,
        #     )

        if backend == "groq":
            if not settings.groq_api_key:
                raise ValueError(
                    "SOMAAI_GROQ_API_KEY is required for Groq backend"
                )
            if not settings.groq_model:
                raise ValueError("SOMAAI_GROQ_MODEL is required for Groq backend")
            return GroqLLMProvider(
                api_key=settings.groq_api_key.get_secret_value(),
                model=settings.groq_model,
            )

        if backend == "gemini":
            if not settings.gemini_api_key:
                raise ValueError("SOMAAI_GEMINI_API_KEY is required for Gemini backend")
            if not settings.gemini_model:
                raise ValueError("SOMAAI_GEMINI_MODEL is required for Gemini backend")
            return GeminiLLMProvider(
                api_key=settings.gemini_api_key.get_secret_value(),
                model=settings.gemini_model,
            )

        # if backend == "openai":
        ...
        raise ValueError(f"Unknown LLM_BACKEND: {backend}")

    except (ValueError, NotImplementedError) as e:
        if fallback_to_mock:
            logger.warning(
                f"⚠️  LLM configuration error for '{backend}': {e}. "
                "FALLING BACK TO MOCK PROVIDER for development."
            )
            return MockLLMProvider()
        raise
