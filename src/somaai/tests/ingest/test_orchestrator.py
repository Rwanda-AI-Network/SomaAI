import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path

from somaai.modules.ingest.orchestrator import IngestionOrchestrator
from somaai.settings import Settings

@pytest.mark.asyncio
async def test_ingestion_orchestrator_flow():
    """Verify end-to-end ingestion orchestration using mocks."""
    
    # 1. Setup Environment
    settings = Settings(llm_backend="mock")
    
    # Create a temporary test file if not exists, or use existing one
    # Assuming test_document.txt is at project root from previous context
    # But better to create a temp one for isolation if possible. 
    # For now, let's look for "test_document.txt" or create a dummy one.
    
    test_file = Path("test_document_pytest.txt")
    if not test_file.exists():
        test_file.write_text("Test content for pytest ingestion.\nNew Line.")
    
    try:
        # Patch the QdrantStore where it is defined
        with patch("somaai.modules.knowledge.stores.qdrant.QdrantStore") as MockStoreClass:
            # Configure Mock Store
            mock_store = AsyncMock()
            mock_store.exists_by_doc_id.return_value = False # Not a duplicate
            mock_store.add.return_value = True # Successful storage
            MockStoreClass.return_value = mock_store
            
            # Instantiate orchestrator
            orchestrator = IngestionOrchestrator(settings)
            
            # 2. Execute
            result = await orchestrator.run(
                doc_id="test-pytest-001",
                file_path=str(test_file),
                grade="S1",
                subject="testing",
                title="Pytest Document",
                skip_if_exists=False 
            )
            
            # 3. Assertions
            assert result["status"] == "completed"
            assert result["doc_id"] == "test-pytest-001"
            assert result["chunks"] > 0
            assert result["pages"] > 0
            
    finally:
        # Cleanup temp file if created
        if test_file.exists() and test_file.name == "test_document_pytest.txt":
            test_file.unlink()
