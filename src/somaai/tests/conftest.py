"""Test configuration.

Provides fixtures for integration tests using TestClient with mocked
external dependencies (LLM, Qdrant, Redis).
"""

import os

import pytest
from fastapi.testclient import TestClient

from somaai.app import create_app

@pytest.fixture(scope="function", autouse=True)
def _seed_test_metadata(request):
    """Seed baseline metadata for all tests except meta tests."""
    if "test_meta.py" in str(request.node.fspath):
        yield
        return

    import asyncio
    from somaai.db.models import Grade, Subject
    from somaai.db.session import async_session_maker
    from sqlalchemy.exc import IntegrityError

    async def _seed():
        from somaai.db.session import init_db
        await init_db()
        from sqlalchemy import select, func
        async with async_session_maker() as db:
            # Comprehensive grades for all tests
            for g_id in ["P1", "P2", "P3", "P4", "P5", "P6", "S1", "S2", "S3", "S4", "S5", "S6"]:
                try:
                    await db.merge(Grade(id=g_id, name=f"Grade {g_id}", level="primary" if g_id.startswith("P") else "secondary", display_order=1))
                    await db.commit()
                except IntegrityError:
                    await db.rollback()
            
            # Comprehensive subjects for all tests
            for s_id in ["general", "science", "math", "mathematics", "biology", "chemistry", "physics", "english", "social_studies", "geography", "history", "economics", "computer_science"]:
                try:
                    await db.merge(Subject(id=s_id, name=s_id.replace("_", " ").title(), display_order=1))
                    await db.commit()
                except IntegrityError:
                    await db.rollback()

    try:
        asyncio.run(_seed())
    except RuntimeError:
        # Fallback if loop already exists
        loop = asyncio.get_event_loop()
        loop.run_until_complete(_seed())

    yield


@pytest.fixture(autouse=True)
def _set_testing_env():
    """Set TESTING=1 so factory allows mock backend."""
    os.environ["TESTING"] = "1"
    yield
    os.environ.pop("TESTING", None)


@pytest.fixture(autouse=True)
def _clear_session_store():
    """Clear the in-memory session store between tests."""
    try:
        from somaai.middleware.session import clear_memory_store

        clear_memory_store()
        yield
        clear_memory_store()
    except ImportError:
        # middleware.session not available (old layout)
        yield


@pytest.fixture
def client():
    """Create test client with mock LLM backend.

    Uses llm_backend="mock" which is allowed in tests due to TESTING=1.
    The RAGPipeline will be created (not MockRAGPipeline) but will use
    MockLLMProvider for generation.

    Session middleware runs in-memory mode (no Redis) automatically.
    """
    from somaai.deps import get_settings
    from somaai.settings import Settings
    from unittest.mock import AsyncMock, MagicMock, patch

    app = create_app()

    def get_test_settings():
        return Settings(llm_backend="mock")

    app.dependency_overrides[get_settings] = get_test_settings

    # Patch where it is defined, not where it is imported locally
    with (
        patch(
            "somaai.modules.knowledge.stores.qdrant.QdrantStore"
        ) as mock_store_cls,
        patch(
            "somaai.modules.rag.retriever.Retriever.retrieve",
            new_callable=AsyncMock,
        ) as mock_retrieve,
        patch(
            "somaai.health.get_qdrant_client"
        ) as mock_qdrant_client_func,
    ):
        mock_store = MagicMock()
        mock_store.add.return_value = True
        mock_store_cls.return_value = mock_store

        mock_retrieve.return_value = []

        mock_qdrant_client = MagicMock()
        mock_qdrant_client_func.return_value = mock_qdrant_client

        with TestClient(app) as c:
            yield c
