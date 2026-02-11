import asyncio
import logging
import sys
from unittest.mock import AsyncMock, patch

# Add src to path
sys.path.append("src")

from somaai.modules.ingest.orchestrator import IngestionOrchestrator
from somaai.settings import Settings

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(name)s | %(message)s')

async def test_ingestion_flow():
    print("\n--- Testing Ingestion Orchestrator ---")

    # Mock settings
    settings = Settings(llm_backend="mock")

    # Mock QdrantStore to avoid real DB connection
    # Patch where it is defined, not where it is imported locally
    with patch(
        "somaai.modules.knowledge.stores.qdrant.QdrantStore"
    ) as mock_store_cls:
        mock_store = AsyncMock()
        mock_store.exists_by_doc_id.return_value = False  # Not a duplicate
        mock_store.add.return_value = True  # Successful storage
        mock_store_cls.return_value = mock_store

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
                skip_if_exists=False
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
