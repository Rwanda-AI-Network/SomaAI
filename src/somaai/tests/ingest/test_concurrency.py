import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from somaai.modules.ingest.orchestrator import IngestionOrchestrator
from somaai.settings import Settings


@pytest.mark.asyncio
async def test_concurrent_ingestion_deduplication():
    """Verify that simultaneous ingestion handles deduplication.

    This test simulates a race condition where multiple processes start
    the same document at once.
    """
    from somaai.settings import LLMSettings

    settings = Settings(llm=LLMSettings(backend="mock"))
    orchestrator = IngestionOrchestrator(settings)

    doc_id = "concurrent-doc-001"
    file_path = Path("test.pdf")

    # Mock all stages to ensure sub-second execution and no side effects
    with (
        patch("somaai.modules.knowledge.stores.qdrant.QdrantStore"),
        patch("somaai.providers.storage.get_storage"),
        patch(
            "somaai.modules.ingest.stages.deduplication.DeduplicationStage.run"
        ) as mock_dedup_run,
        patch(
            "somaai.modules.ingest.stages.extraction.ExtractionStage.run"
        ) as mock_extract_run,
        patch(
            "somaai.modules.ingest.stages.chunking.ChunkingStage.run"
        ) as mock_chunk_run,
        patch(
            "somaai.modules.ingest.stages.filtering.QualityFilterStage.run"
        ) as mock_filter_run,
        patch(
            "somaai.modules.ingest.stages.enrichment.MetadataEnrichmentStage.run"
        ) as mock_enrich_run,
        patch(
            "somaai.modules.ingest.stages.storage.VectorStorageStage.run"
        ) as mock_store_run,
        patch(
            "somaai.modules.ingest.stages.db_sync.DatabaseSyncStage.run"
        ) as mock_db_run,
    ):
        from somaai.modules.ingest.stages.base import StageResult

        # Setup mock behavior
        # First dedup call says "proceed", subsequent say "skipped"
        skipped_res = StageResult(
            success=True,
            data={"status": "skipped", "reason": "already_exists"},
            should_skip=True,
        )
        mock_dedup_run.side_effect = [
            StageResult(success=True, data={"status": "proceed"}),
            skipped_res,
            skipped_res,
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
                subject="mathematics",
                skip_if_exists=True,
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
        # Verify others 'skipped' (since mock_dedup_run returns should_skip=True)
        assert "skipped" in statuses

        # Verify deduplication check was called 3 times
        assert mock_dedup_run.call_count == 3


@pytest.mark.asyncio
async def test_ingestion_error_isolation():
    """Verify that a failure in one ingestion task does not affect others."""
    from somaai.settings import LLMSettings

    settings = Settings(llm=LLMSettings(backend="mock"))
    orchestrator = IngestionOrchestrator(settings)

    with (
        patch("somaai.modules.knowledge.stores.qdrant.QdrantStore"),
        patch("somaai.providers.storage.get_storage"),
        patch("somaai.db.session.async_session_maker") as mock_session_maker,
        patch("somaai.db.crud.update_document_status", new_callable=AsyncMock),
        patch(
            "somaai.modules.ingest.stages.deduplication.DeduplicationStage.run"
        ) as mock_dedup_run,
        patch(
            "somaai.modules.ingest.stages.extraction.ExtractionStage.run"
        ) as mock_extract_run,
        patch(
            "somaai.modules.ingest.stages.chunking.ChunkingStage.run"
        ) as mock_chunk_run,
        patch(
            "somaai.modules.ingest.stages.filtering.QualityFilterStage.run"
        ) as mock_filter_run,
        patch(
            "somaai.modules.ingest.stages.enrichment.MetadataEnrichmentStage.run"
        ) as mock_enrich_run,
        patch(
            "somaai.modules.ingest.stages.storage.VectorStorageStage.run"
        ) as mock_store_run,
        patch(
            "somaai.modules.ingest.stages.db_sync.DatabaseSyncStage.run"
        ) as mock_db_run,
    ):
        from somaai.modules.ingest.stages.base import StageResult

        # Mock DB session
        mock_session = AsyncMock()
        mock_session_maker.return_value.__aenter__.return_value = mock_session

        # Simulate a crash for one specific call (first task)
        # and success for the other
        mock_dedup_run.side_effect = [
            Exception("Storage Failure"),
            StageResult(success=True, data={"status": "proceed"}),
        ]

        # All other stages succeed
        mock_extract_run.return_value = StageResult(success=True, data={})
        mock_chunk_run.return_value = StageResult(success=True, data={})
        mock_filter_run.return_value = StageResult(success=True, data={})
        mock_enrich_run.return_value = StageResult(success=True, data={})
        mock_store_run.return_value = StageResult(success=True, data={})
        mock_db_run.return_value = StageResult(success=True, data={})

        tasks = [
            orchestrator.run(
                doc_id="doc-fail", file_path=Path("f.pdf"), grade="S1", subject="s"
            ),
            orchestrator.run(
                doc_id="doc-pass", file_path=Path("p.pdf"), grade="S1", subject="s"
            ),
        ]

        # Use return_exceptions=True to capture the failure of the first task
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # First task should have failed
        assert isinstance(results[0], Exception)
        assert "Storage Failure" in str(results[0])

        # Second task should have completed successfully
        assert isinstance(results[1], dict)
        assert results[1].get("status") == "completed"

        # Verify error isolation: both tasks were attempted
        assert mock_dedup_run.call_count == 2
