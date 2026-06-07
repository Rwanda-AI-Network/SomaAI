"""Verification script for Hybrid Search integration.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from somaai.modules.knowledge.stores.qdrant import QdrantStore
from somaai.settings import Settings


class TestHybridSearch(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = Settings(
            qdrant_url="http://localhost:6333",
            qdrant_collection="test_collection",
            rag_enable_hybrid_search=True
        )
        self.store = QdrantStore(self.settings)

    @patch("qdrant_client.QdrantClient")
    @patch("langchain_qdrant.FastEmbedSparseEncoder")
    @patch("langchain_qdrant.QdrantVectorStore")
    async def test_hybrid_initialization(self, mock_vector_store, mock_sparse_encoder, mock_client):
        """Verify that sparse encoder is initialized when hybrid search is enabled."""
        mock_client_instance = mock_client.return_value
        mock_client_instance.collection_exists.return_value = True
        
        # Mock embeddings
        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1] * 768
        
        with patch.object(self.store, "embeddings", mock_embeddings):
            await self.store._ensure_store()
            
            # Check sparse encoder was created
            mock_sparse_encoder.assert_called_once_with(model_name="Qdrant/bm25")
            
            # Check QdrantVectorStore was initialized with sparse_encoder
            _, kwargs = mock_vector_store.call_args
            self.assertIsNotNone(kwargs.get("sparse_encoder"))

    @patch("qdrant_client.QdrantClient")
    async def test_collection_creation_with_sparse(self, mock_client):
        """Verify that collection creation includes sparse vectors config."""
        mock_client_instance = mock_client.return_value
        mock_client_instance.collection_exists.return_value = False
        
        # Mock embeddings
        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1] * 384
        
        with patch.object(self.store, "embeddings", mock_embeddings), \
             patch("langchain_qdrant.FastEmbedSparseEncoder"), \
             patch("langchain_qdrant.QdrantVectorStore"):
            
            await self.store._ensure_store()
            
            # Check create_collection was called with sparse_vectors_config
            mock_client_instance.create_collection.assert_called_once()
            _, kwargs = mock_client_instance.create_collection.call_args
            self.assertIn("sparse_vectors_config", kwargs)
            self.assertEqual(kwargs["sparse_vectors_config"], {"sparse_vector": {}})

if __name__ == "__main__":
    unittest.main()
