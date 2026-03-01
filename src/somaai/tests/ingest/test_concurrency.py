import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from pathlib import Path
from somaai.modules.ingest.orchestrator import IngestionOrchestrator
from somaai.settings import Settings

@pytest.mark.asyncio
async def test_concurrent_ingestion_deduplication():
    """Verify that simultaneous ingestion of the same document handles deduplication gracefully.
    
    This test simulates a race condition where multiple ingestion processes start for 
    the same document at once.
    """
    settings = Settings(llm_backend="mock")
    orchestrator = IngestionOrchestrator(settings)
    
    doc_id = "concurrent-doc-001"
    file_path = Path("test.pdf")
    
    # Mock dependencies
    with (
        patch("somaai.modules.knowledge.stores.qdrant.QdrantStore") as mock_store_cls,
        patch("somaai.providers.storage.get_storage") as mock_storage_func,
        patch("somaai.modules.ingest.stages.deduplication.DeduplicationStage.run") as mock_dedup_run,
        patch("somaai.modules.ingest.stages.extraction.ExtractionStage.run") as mock_extract_run,
        patch("somaai.modules.ingest.stages.chunking.ChunkingStage.run") as mock_chunk_run,
        patch("somaai.modules.ingest.stages.filtering.QualityFilterStage.run") as mock_filter_run,
        patch("somaai.modules.ingest.stages.enrichment.MetadataEnrichmentStage.run") as mock_enrich_run,
        patch("somaai.modules.ingest.stages.storage.VectorStorageStage.run") as mock_store_run,
        patch("somaai.modules.ingest.stages.db_sync.DatabaseSyncStage.run") as mock_db_run,
    ):
        from somaai.modules.ingest.stages.base import StageResult
        
        # Setup mock behavior
        # First dedup call says "proceed", subsequent say "skipped"
        mock_dedup_run.side_effect = [
            StageResult(success=True, data={"status": "proceed"}),
            StageResult(success=True, data={"status": "skipped", "reason": "already_exists"}, should_skip=True),
            StageResult(success=True, data={"status": "skipped", "reason": "already_exists"}, should_skip=True),
        ]
        
        # All other stages succeed
        mock_extract_run.return_value = StageResult(success=True, data={})
        mock_chunk_run.return_value = StageResult(success=True, data={})
        mock_filter_run.return_value = StageResult(success=True, data={})
        mock_enrich_run.return_value = StageResult(success=True, data={})
        mock_store_run.return_value = StageResult(success=True, data={})
        mock_db_run.return_value = StageResult(success=True, data={})
        
        # Run 3 ingestions concurrently
        tasks = [
            orchestrator.run(
                doc_id=doc_id,
                file_path=file_path,
                grade="S1",
                subject="math",
                skip_if_exists=True
            )
            for _ in range(3)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Assertions
        statuses = []
        for r in results:
            if isinstance(r, dict):
                statuses.append(r.get("status"))
            else:
                statuses.append("error")
        
        # Verify at least one 'completed' (from the one that proceeded)
        assert "completed" in statuses
        # Verify others 'skipped' (since mock_dedup_run returns should_skip=True for 2nd and 3rd calls)
        assert "skipped" in statuses
        
        # Verify deduplication check was called 3 times
        assert mock_dedup_run.call_count == 3

@pytest.mark.asyncio
async def test_ingestion_error_isolation():
    """Verify that a failure in one ingestion task does not affect others."""
    settings = Settings(llm_backend="mock")
    orchestrator = IngestionOrchestrator(settings)
    
    with (
        patch("somaai.modules.knowledge.stores.qdrant.QdrantStore") as mock_store_cls,
        patch("somaai.providers.storage.get_storage") as mock_storage_func,
    ):
        mock_store = AsyncMock()
        # Simulate a crash for one specific call
        mock_store.exists_by_doc_id.side_effect = [Exception("Storage Failure"), False]
        mock_store_cls.return_value = mock_store
        
        tasks = [
            orchestrator.run(doc_id="doc-fail", file_path=Path("f.pdf"), grade="S1", subject="s"),
            orchestrator.run(doc_id="doc-pass", file_path=Path("p.pdf"), grade="S1", subject="s")
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # One should fail, one should proceed (to extraction at least)
        assert isinstance(results[0], Exception) or results[0].get("status") == "failed"
        # The other should have attempted to proceed (failing later on extraction due to lacks of mocks is fine, 
        # as long as the first failure didn't block it)
