"""Verification script for Gemini LLM Provider integration."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from somaai.providers.llm import GeminiLLMProvider


class TestGeminiProvider(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.api_key = "test-key"
        self.model = "gemini-1.5-flash"

        # Patch the Client class
        self.patcher = patch("google.genai.Client", autospec=True)
        self.mock_client_class = self.patcher.start()
        self.mock_client = self.mock_client_class.return_value
        
        # Setup nested mocks for aio and models
        self.mock_client.aio = MagicMock()
        self.mock_client.aio.models = MagicMock()
        self.mock_client.aio.models.generate_content = AsyncMock()
        
        self.mock_client.models = MagicMock()
        self.mock_client.models.embed_content = MagicMock()

        self.provider = GeminiLLMProvider(self.api_key, self.model)
        # Force the mock client onto the provider
        self.provider.client = self.mock_client

    def tearDown(self):
        self.patcher.stop()

    async def test_generate_json_mode(self):
        """Verify generate uses application/json response_mime_type."""
        mock_response = MagicMock()
        mock_response.text = '{"answer": "success"}'
        self.mock_client.aio.models.generate_content.return_value = mock_response

        result = await self.provider.generate("test prompt")

        self.assertEqual(result, '{"answer": "success"}')
        self.mock_client.aio.models.generate_content.assert_called_once()
        _, kwargs = self.mock_client.aio.models.generate_content.call_args
        # In v2 SDK, it's config.response_mime_type
        self.assertEqual(
            kwargs["config"].response_mime_type, "application/json"
        )

    async def test_generate_retries(self):
        """Verify Gemini provider retries on transient errors."""
        mock_response = MagicMock()
        mock_response.text = '{"answer": "finally"}'

        self.mock_client.aio.models.generate_content.side_effect = [
            Exception("Overloaded"),
            Exception("Deadline Exceeded"),
            mock_response,
        ]

        result = await self.provider.generate("test prompt")
        self.assertEqual(result, '{"answer": "finally"}')
        self.assertEqual(self.mock_client.aio.models.generate_content.call_count, 3)

    async def test_embed(self):
        """Verify embed calls client.models.embed_content correctly."""
        mock_embedding = MagicMock()
        mock_embedding.values = [0.1] * 768
        
        mock_response = MagicMock()
        mock_response.embeddings = [mock_embedding]
        self.mock_client.models.embed_content.return_value = mock_response

        result = await self.provider.embed(["test text"])

        self.assertEqual(result, [[0.1] * 768])
        self.mock_client.models.embed_content.assert_called_once()
        _, kwargs = self.mock_client.models.embed_content.call_args
        self.assertEqual(kwargs["model"], "text-embedding-004")
        self.assertEqual(kwargs["contents"], ["test text"])
        self.assertEqual(kwargs["config"]["task_type"], "RETRIEVAL_DOCUMENT")


if __name__ == "__main__":
    unittest.main()

