"""Test configuration.

Provides fixtures for integration tests using TestClient with mocked
external dependencies (LLM, Qdrant, Redis).
"""

import os

import pytest
from fastapi.testclient import TestClient

# Defer imports that trigger DB initialization until after environment is set.
# from somaai.app import create_app  <-- DO NOT IMPORT HERE


def pytest_configure(config):
    """Set environment variables before any test imports happen."""
    os.environ["SOMAAI_ENV"] = "test"
    os.environ["SOMAAI_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    os.environ["SOMAAI_LLM_BACKEND"] = "mock"


@pytest.fixture(scope="session", autouse=True)
async def cleanup_system_resources():
    """Dispose of global resources (DB engine, Qdrant client) after all tests."""
    yield

    # 1. Dispose of SQLAlchemy engine
    try:
        from somaai.db.session import engine
        await engine.dispose()
    except Exception:
        pass

    # 2. Close Qdrant client if it exists
    try:
        import somaai.modules.knowledge.stores.qdrant as qdrant_module
        if qdrant_module._QDRANT_CLIENT:
            qdrant_module._QDRANT_CLIENT.close()
            qdrant_module._QDRANT_CLIENT = None
    except Exception:
        pass


@pytest.fixture(scope="function", autouse=True)
def _seed_test_metadata(request):
    """Seed baseline metadata for all tests except meta tests."""
    # Exclude all meta-related tests from auto-seeding to ensure isolation
    if "test_meta" in str(request.node.fspath):
        yield
        return

    import asyncio

    from sqlalchemy.exc import IntegrityError

    from somaai.db.models import CurriculumMetadata
    from somaai.db.session import async_session_maker

    async def _seed():
        from somaai.db.session import init_db

        await init_db()
        async with async_session_maker() as db:
            # Comprehensive grades for all tests
            for g_id in [
                "P1",
                "P2",
                "P3",
                "P4",
                "P5",
                "P6",
                "S1",
                "S2",
                "S3",
                "S4",
                "S5",
                "S6",
            ]:
                try:
                    await db.merge(
                        CurriculumMetadata(
                            id=g_id,
                            type="grade",
                            key=g_id,
                            name=f"Grade {g_id}",
                            display_order=1,
                            is_active=True,
                        )
                    )
                    await db.commit()
                except IntegrityError:
                    await db.rollback()

            # Comprehensive subjects for all tests
            for s_id in [
                "general",
                "science",
                "math",
                "mathematics",
                "biology",
                "chemistry",
                "physics",
                "english",
                "social_studies",
                "geography",
                "history",
                "economics",
                "computer_science",
            ]:
                try:
                    await db.merge(
                        CurriculumMetadata(
                            id=s_id,
                            type="subject",
                            key=s_id,
                            name=s_id.replace("_", " ").title(),
                            display_order=1,
                            is_active=True,
                        )
                    )
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


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_env():
    """Clean up test environment variables after session."""
    yield
    os.environ.pop("SOMAAI_ENV", None)
    os.environ.pop("SOMAAI_LLM__BACKEND", None)


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

    Uses llm_backend="mock" which is allowed in tests due to SOMAAI_ENV=test.
    The RAGPipeline will be created (not MockRAGPipeline) but will use
    MockLLMProvider for generation.

    Session middleware runs in-memory mode (no Redis) automatically.
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    from somaai.app import create_app
    from somaai.deps import get_settings
    from somaai.settings import Settings

    app = create_app()

    def get_test_settings():

        return Settings(llm_backend="mock")

    app.dependency_overrides[get_settings] = get_test_settings

    # Patch where it is defined, not where it is imported locally
    with (
        patch("somaai.modules.knowledge.stores.qdrant.QdrantStore") as mock_store_cls,
        patch(
            "somaai.modules.rag.retriever.Retriever.retrieve",
            new_callable=AsyncMock,
        ) as mock_retrieve,
        patch(
            "somaai.utils.redis.get_cache_redis", new_callable=AsyncMock
        ) as mock_redis_cache,
        patch(
            "somaai.utils.redis.get_general_redis", new_callable=AsyncMock
        ) as mock_redis_gen,
        patch(
            "somaai.utils.redis.get_jobs_redis", new_callable=AsyncMock
        ) as mock_redis_jobs,
        patch("somaai.health.get_qdrant_client") as mock_qdrant_client_func,
    ):
        # Setup Redis mock behavior (mimic empty/down Redis for most tests)
        async def _async_iter_empty():
            """Empty async iterator for scan_iter mock."""
            if False:  # Never execute, just make it an async generator
                yield

        for m in [mock_redis_cache, mock_redis_gen, mock_redis_jobs]:
            redis_inst = AsyncMock()
            redis_inst.get.return_value = None
            redis_inst.setex.return_value = True
            redis_inst.delete.return_value = True
            # scan_iter should return an async iterator
            redis_inst.scan_iter.return_value = _async_iter_empty()
            # Make the mock return the redis_inst directly
            m.return_value = redis_inst

        mock_store = MagicMock()
        mock_store.add.return_value = True
        mock_store_cls.return_value = mock_store

        mock_retrieve.return_value = []

        mock_qdrant_client = MagicMock()
        mock_qdrant_client_func.return_value = mock_qdrant_client

        with TestClient(app) as c:
            yield c


@pytest.fixture
async def async_client():
    """Create async test client for tests that need httpx.AsyncClient.

    Uses the same mock strategy as the sync `client` fixture.
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    from httpx import ASGITransport, AsyncClient

    from somaai.app import create_app
    from somaai.deps import get_settings
    from somaai.settings import Settings

    app = create_app()

    def get_test_settings():
        return Settings(llm_backend="mock")

    app.dependency_overrides[get_settings] = get_test_settings

    with (
        patch("somaai.modules.knowledge.stores.qdrant.QdrantStore") as mock_store_cls,
        patch(
            "somaai.modules.rag.retriever.Retriever.retrieve",
            new_callable=AsyncMock,
        ) as mock_retrieve,
        patch(
            "somaai.utils.redis.get_cache_redis", new_callable=AsyncMock
        ) as mock_redis_cache,
        patch(
            "somaai.utils.redis.get_general_redis", new_callable=AsyncMock
        ) as mock_redis_gen,
        patch(
            "somaai.utils.redis.get_jobs_redis", new_callable=AsyncMock
        ) as mock_redis_jobs,
        patch("somaai.health.get_qdrant_client") as mock_qdrant_client_func,
    ):
        for m in [mock_redis_cache, mock_redis_gen, mock_redis_jobs]:
            redis_inst = AsyncMock()
            redis_inst.get.return_value = None
            redis_inst.setex.return_value = True
            redis_inst.delete.return_value = True
            m.return_value = redis_inst

        mock_store = MagicMock()
        mock_store.add.return_value = True
        mock_store_cls.return_value = mock_store
        mock_retrieve.return_value = []
        mock_qdrant_client_func.return_value = MagicMock()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac
