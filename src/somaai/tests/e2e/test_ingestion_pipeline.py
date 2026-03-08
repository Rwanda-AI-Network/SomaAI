import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

# Add src to path
sys.path.append("src")

from somaai.modules.ingest.orchestrator import IngestionOrchestrator
from somaai.settings import Settings

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")


async def test_ingestion_flow():
    print("\n--- Testing Ingestion Orchestrator ---")

    # Mock settings
    from somaai.settings import LLMSettings

    settings = Settings(llm=LLMSettings(backend="mock"))

    # Mock QdrantStore to avoid real DB connection
    with (
        patch("somaai.modules.knowledge.stores.qdrant.QdrantStore") as mock_store_cls,
        patch("somaai.providers.storage.get_storage") as mock_storage_func,
    ):
        from unittest.mock import MagicMock

        mock_store = AsyncMock()
        mock_store.exists_by_doc_id.return_value = False
        mock_store.add.return_value = []
        mock_store_cls.return_value = mock_store

        # Mock storage (MagicMock for sync methods like open, read, hexdigest)
        mock_storage = MagicMock()
        mock_storage_func.return_value = mock_storage

        # Mock storage context manager
        mock_stream = MagicMock()
        mock_stream.hexdigest.return_value = "test-hash"

        @asynccontextmanager
        async def mock_open(*args, **kwargs):
            yield mock_stream

        mock_storage.open = mock_open

        # Mock database session to avoid real DB hits
        with (
            patch("somaai.db.session.async_session_maker") as mock_session_maker,
            patch("somaai.db.crud.create_chunks", new_callable=AsyncMock),
            patch("somaai.db.crud.update_document_processed", new_callable=AsyncMock),
            patch("somaai.db.crud.update_document_status", new_callable=AsyncMock),
        ):
            mock_session = AsyncMock()
            mock_session_maker.return_value.__aenter__.return_value = mock_session

            # Instantiate orchestrator
            orchestrator = IngestionOrchestrator(settings)

        # Define progress callback
        def on_progress(stage, pct):
            print(f"Progress: [{stage}] {pct}%")

        # Run ingestion
        try:
            result = await orchestrator.run(
                doc_id="test-doc-001",
                file_path="test_document.txt",
                grade="S1",
                subject="geography",
                title="Vision 2050 Test",
                on_progress=on_progress,
                skip_if_exists=False,
            )

            print("\n--- Result ---")
            print(f"Status: {result.get('status')}")
            print(f"Doc ID: {result.get('doc_id')}")
            print(f"Chunks: {result.get('chunks')}")
            print(f"Pages: {result.get('pages')}")

            if result.get("status") == "completed":
                print("\nSUCCESS: Ingestion pipeline verified!")
            else:
                print("\nFAILURE: Pipeline did not complete successfully.")

        except Exception as e:
            print(f"\nFAILURE: Exception during execution: {e}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_ingestion_flow())
