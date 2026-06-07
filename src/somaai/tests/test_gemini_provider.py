"""Verification script for Gemini LLM Provider integration.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from somaai.providers.llm import GeminiLLMProvider


class TestGeminiProvider(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.api_key = "test-key"
        self.model = "gemini-1.5-flash"
        
        # Mock the entire google.generativeai module
        self.patcher = patch("google.generativeai.GenerativeModel")
        self.mock_model_class = self.patcher.start()
        self.mock_model_instance = self.mock_model_class.return_value
        
        with patch("google.generativeai.configure"):
            self.provider = GeminiLLMProvider(self.api_key, self.model)

    def tearDown(self):
        self.patcher.stop()

    async def test_generate_json_mode(self):
        """Verify generate uses applications/json response_mime_type."""
        mock_response = AsyncMock()
        mock_response.text = '{"answer": "success"}'
        self.mock_model_instance.generate_content_async.return_value = mock_response

        result = await self.provider.generate("test prompt")
        
        self.assertEqual(result, '{"answer": "success"}')
        # Check if generation_config was passed with json mime type
        self.mock_model_instance.generate_content_async.assert_called_once()
        args, kwargs = self.mock_model_instance.generate_content_async.call_args
        self.assertEqual(kwargs["generation_config"]["response_mime_type"], "application/json")

    async def test_generate_retries(self):
        """Verify Gemini provider retries on transient errors."""
        mock_response = AsyncMock()
        mock_response.text = '{"answer": "finally"}'
        
        self.mock_model_instance.generate_content_async.side_effect = [
            Exception("Overloaded"),
            Exception("Deadline Exceeded"),
            mock_response
        ]

        result = await self.provider.generate("test prompt")
        self.assertEqual(result, '{"answer": "finally"}')
        self.assertEqual(self.mock_model_instance.generate_content_async.call_count, 3)

    @patch("google.generativeai.embed_content")
    async def test_embed(self, mock_embed):
        """Verify embed calls genai.embed_content correctly."""
        mock_embed.return_value = {"embedding": [[0.1] * 768]}
        
        result = await self.provider.embed(["test text"])
        
        self.assertEqual(result, [[0.1] * 768])
        mock_embed.assert_called_once_with(
            model="models/text-embedding-004",
            content=["test text"],
            task_type="retrieval_document"
        )

if __name__ == "__main__":
    unittest.main()
