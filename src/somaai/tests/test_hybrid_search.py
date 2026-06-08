"""Verification script for Hybrid Search integration."""

import unittest
from unittest.mock import MagicMock, patch

from somaai.modules.knowledge.stores.qdrant import QdrantStore
from somaai.settings import Settings


class TestHybridSearch(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = Settings(
            qdrant_url="http://localhost:6333",
            qdrant_collection="test_collection",
            rag_enable_hybrid_search=True,
        )
        self.store = QdrantStore(self.settings)
        # Reset the module-level singleton so our patches take effect
        import somaai.modules.knowledge.stores.qdrant as qdrant_module
        qdrant_module._QDRANT_CLIENT = None

    def tearDown(self):
        # Clean up singleton after each test
        import somaai.modules.knowledge.stores.qdrant as qdrant_module
        qdrant_module._QDRANT_CLIENT = None

    @patch("somaai.modules.knowledge.stores.qdrant.QdrantClient", autospec=True)
    @patch("langchain_qdrant.FastEmbedSparse", create=True, autospec=True)
    @patch("langchain_qdrant.QdrantVectorStore", autospec=True)
    async def test_hybrid_initialization(
        self, mock_vector_store, mock_sparse_encoder, mock_client
    ):
        """Verify that sparse encoder is initialized when hybrid search is enabled."""
        mock_client_instance = mock_client.return_value
        mock_client_instance.collection_exists.return_value = True

        # Mock embeddings
        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1] * 768

        # Mock inspect.signature to return a signature with sparse_embedding
        from inspect import Parameter, Signature
        mock_sig = Signature([
            Parameter("sparse_embedding", Parameter.KEYWORD_ONLY, default=None)
        ])

        with (
            patch(
                "somaai.modules.knowledge.stores.qdrant.get_embeddings",
                return_value=mock_embeddings,
            ),
            patch("inspect.signature", return_value=mock_sig)
        ):
            await self.store._ensure_store()

            # Check sparse encoder was created
            mock_sparse_encoder.assert_called_once_with(model_name="Qdrant/bm25")

            # Check QdrantVectorStore was initialized with sparse_embedding
            _, kwargs = mock_vector_store.call_args
            self.assertIn("sparse_embedding", kwargs)

    @patch("somaai.modules.knowledge.stores.qdrant.QdrantClient", autospec=True)
    @patch("langchain_qdrant.FastEmbedSparse", create=True, autospec=True)
    @patch("langchain_qdrant.QdrantVectorStore", autospec=True)
    async def test_collection_creation_with_sparse(
        self, mock_vector_store, mock_sparse_encoder, mock_client
    ):
        """Verify that collection creation includes sparse vectors config."""
        mock_client_instance = mock_client.return_value
        mock_client_instance.collection_exists.return_value = False

        # Mock embeddings
        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1] * 384

        # Mock inspect.signature to return a signature with sparse_embedding
        from inspect import Parameter, Signature
        mock_sig = Signature([
            Parameter("sparse_embedding", Parameter.KEYWORD_ONLY, default=None)
        ])

        with (
            patch(
                "somaai.modules.knowledge.stores.qdrant.get_embeddings",
                return_value=mock_embeddings,
            ),
            patch("inspect.signature", return_value=mock_sig)
        ):
            await self.store._ensure_store()

            # Check create_collection was called with sparse_vectors_config
            mock_client_instance.create_collection.assert_called_once()
            _, kwargs = mock_client_instance.create_collection.call_args
            self.assertIn("sparse_vectors_config", kwargs)
            self.assertEqual(kwargs["sparse_vectors_config"], {"sparse_vector": {}})


if __name__ == "__main__":
    unittest.main()

