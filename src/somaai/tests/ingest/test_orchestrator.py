from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

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
    # Always write fresh content to ensure validation passes
    content = (
        "Section 1: Introduction\n\n"
        "Biology is the natural science that studies life and living organisms, "
        "including their physical structure, chemical processes, molecular "
        "interactions, physiological mechanisms, development and evolution. Despite "
        "the complexity "
        "of the science, certain unifying concepts consolidate it into a single, "
        "coherent field. Biology recognizes the cell as the basic unit of life, "
        "genes as the basic unit of heredity, and evolution as the engine that "
        "propels the creation and extinction of species."
    )
    test_file.write_text(content)

    try:
        # Patch the QdrantStore where it is defined
        with patch(
            "somaai.modules.knowledge.stores.qdrant.QdrantStore"
        ) as mock_store_cls:
            # Configure Mock Store
            mock_store = AsyncMock()
            mock_store.exists_by_doc_id.return_value = False  # Not a duplicate
            mock_store.add.return_value = True  # Successful storage
            mock_store_cls.return_value = mock_store

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
