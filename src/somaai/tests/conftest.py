"""Test configuration."""

import os

import pytest
from fastapi.testclient import TestClient

from somaai.app import create_app


@pytest.fixture(autouse=True)
def _set_testing_env():
    """Set TESTING=1 so factory allows mock backend."""
    os.environ["TESTING"] = "1"
    yield
    os.environ.pop("TESTING", None)


@pytest.fixture
def client():
    """Create test client with mock LLM backend.

    Uses llm_backend="mock" which is allowed in tests due to TESTING=1.
    The RAGPipeline will be created (not MockRAGPipeline) but will use
    MockLLMProvider for generation.
    """
    from somaai.deps import get_settings
    from somaai.settings import Settings

    app = create_app()

    def get_test_settings():
        return Settings(llm_backend="mock")

    app.dependency_overrides[get_settings] = get_test_settings

    from unittest.mock import AsyncMock, MagicMock, patch

    # Patch where it is defined, not where it is imported locally
    with patch(
        "somaai.modules.knowledge.stores.qdrant.QdrantStore"
    ) as mock_store_cls:
        mock_store = MagicMock()
        mock_store.add.return_value = True  # Successful storage
        mock_store_cls.return_value = mock_store

        # Mock retrieval to avoid Qdrant connection attempts in tests
        with patch(
            "somaai.modules.rag.retriever.Retriever.retrieve", new_callable=AsyncMock
        ) as mock_retrieve:
            mock_retrieve.return_value = []
            with TestClient(app) as c:
                yield c
