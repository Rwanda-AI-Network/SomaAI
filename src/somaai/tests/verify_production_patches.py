"""Portable verification script for SomaAI production hardening.

Uses standard library unittest and asyncio (no pytest dependency).
"""

import asyncio
import logging
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from somaai.cache.rag import ResponseCache
from somaai.modules.knowledge.stores.qdrant import QdrantStore
from somaai.modules.rag.pipelines import RAGPipeline
from somaai.providers.llm import GroqLLMProvider
from somaai.settings import settings

# Configure logging to see retry messages
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestProductionHardening(unittest.IsolatedAsyncioTestCase):
    async def test_groq_llm_retries(self):
        """Verify GroqLLMProvider retries 3 times on failure."""
        mock_client = AsyncMock()
        # Fail twice, succeed on 3rd
        mock_client.chat.completions.create.side_effect = [
            Exception("Transient 1"),
            Exception("Transient 2"),
            MagicMock(
                choices=[MagicMock(message=MagicMock(content='{"answer": "success"}'))]
            ),
        ]

        provider = GroqLLMProvider(api_key="test", model="test")
        provider.client = mock_client

        result = await provider.generate("test prompt")

        self.assertEqual(result, '{"answer": "success"}')
        self.assertEqual(mock_client.chat.completions.create.call_count, 3)

    async def test_qdrant_search_retries(self):
        """Verify QdrantStore.search retries on ConnectionError."""
        store = QdrantStore(settings)
        store._store = AsyncMock()

        # Fail once, then succeed
        store._store.asimilarity_search_with_score.side_effect = [
            ConnectionError("Pool timeout"),
            [],
        ]

        with patch.object(QdrantStore, "_ensure_store", return_value=store._store):
            result = await store.search("test query")
            self.assertEqual(result, [])
            self.assertEqual(store._store.asimilarity_search_with_score.call_count, 2)

    async def test_redis_cache_timeout(self):
        """Verify ResponseCache enforces 2s timeout."""
        cache = ResponseCache(ttl=3600)
        mock_redis = AsyncMock()

        async def slow_get(*args, **kwargs):
            await asyncio.sleep(3)
            return '{"answer": "cached"}'

        mock_redis.get.side_effect = slow_get
        cache._redis = mock_redis

        result = await cache.get("q", "S1", "bio")
        self.assertIsNone(result)

    async def test_rag_pipeline_retrieval_timeout_fallback(self):
        """Verify RAG pipeline falls back to insufficient_context on timeout."""
        pipeline = RAGPipeline(settings)
        pipeline.retriever = MagicMock()

        async def slow_retrieve(*args, **kwargs):
            await asyncio.sleep(
                5
            )  # Shorter but still enough to trigger if we lower timeout for test
            return [], ""

        pipeline.retriever.retrieve_for_context = slow_retrieve

        # Override the timeout for testing purposes if possible,
        # but the current code has 10.0 hardcoded.
        # Let's mock asyncio.timeout to be shorter for the test.

        original_timeout = asyncio.timeout

        def mock_timeout(delay):
            if delay == 10.0:
                return original_timeout(0.1)  # Trigger fast
            return original_timeout(delay)

        # Mock cache to return an AsyncMock
        mock_cache = AsyncMock()
        mock_cache.get.return_value = None

        with (
            patch("somaai.modules.rag.pipelines.sanitize_query", return_value="test"),
            patch(
                "somaai.modules.rag.pipelines.classify_query",
                return_value=("curriculum", None),
            ),
            patch("somaai.cache.rag.get_response_cache", return_value=mock_cache),
            patch("asyncio.timeout", side_effect=mock_timeout),
        ):
            result = await pipeline.run("test query")
            self.assertTrue(
                "couldn't find relevant curriculum content" in result["answer"].lower()
            )
            self.assertEqual(result["sufficiency"], "insufficient")

    async def test_rag_pipeline_generation_timeout_fallback(self):
        """Verify RAG pipeline falls back to safe response on generation timeout."""
        pipeline = RAGPipeline(settings)

        pipeline.retriever = AsyncMock()
        pipeline.retriever.retrieve_for_context.return_value = ([{"id": 1}], "context")

        pipeline.generator = AsyncMock()

        async def slow_generate(*args, **kwargs):
            await asyncio.sleep(5)
            return {"answer": "too slow"}

        pipeline.generator.generate.side_effect = slow_generate

        original_timeout = asyncio.timeout

        def mock_timeout(delay):
            if delay == 20.0:
                return original_timeout(0.1)  # Trigger fast
            return original_timeout(delay)

        # Mock cache to return an AsyncMock
        mock_cache = AsyncMock()
        mock_cache.get.return_value = None

        with (
            patch("somaai.modules.rag.pipelines.sanitize_query", return_value="test"),
            patch(
                "somaai.modules.rag.pipelines.classify_query",
                return_value=("curriculum", None),
            ),
            patch("somaai.cache.rag.get_response_cache", return_value=mock_cache),
            patch("asyncio.timeout", side_effect=mock_timeout),
        ):
            result = await pipeline.run("test query")
            self.assertTrue(
                "unable to provide a detailed answer" in result["answer"].lower()
            )
            self.assertEqual(result["confidence"], 0.0)


if __name__ == "__main__":
    unittest.main()
