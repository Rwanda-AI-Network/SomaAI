"""Ingestion orchestrator - coordinates pipeline stages."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from somaai.modules.ingest.context import PipelineContext
from somaai.modules.ingest.stages.base import PipelineStage, StageResult
from somaai.modules.ingest.exceptions import IngestionError

if TYPE_CHECKING:
    from somaai.settings import Settings

logger = logging.getLogger(__name__)


class IngestionOrchestrator:
    """Orchestrates the document ingestion pipeline.
    
    Coordinates stages:
    1. Deduplication - Check if document exists
    2. Extraction - Extract text with structure
    3. Chunking - Create semantic chunks
    4. Filtering - Quality and risk filtering
    5. Enrichment - Add document metadata
    6. Storage - Store in Qdrant
    7. DB Sync - Sync to PostgreSQL
    
    Features:
    - Modular stages (easy to add/remove)
    - Unified progress tracking
    - Error isolation per stage
    - Skip-on-duplicate
    
    Example:
        orchestrator = IngestionOrchestrator(settings)
        result = await orchestrator.run(
            doc_id="doc-123",
            file_path="/path/to/file.pdf",
            grade="S2",
            subject="biology"
        )
    """
    
    def __init__(self, settings: Settings | None = None):
        """Initialize orchestrator with settings.
        
        Args:
            settings: Application settings (lazy loaded if None)
        """
        self._settings = settings
        self._stages: list[PipelineStage] | None = None
    
    @property
    def settings(self) -> Settings:
        """Get or lazy-load settings."""
        if self._settings is None:
            from somaai.settings import settings
            self._settings = settings
        return self._settings
    
    @property
    def stages(self) -> list[PipelineStage]:
        """Get or build pipeline stages."""
        if self._stages is None:
            self._stages = self._build_pipeline()
        return self._stages
    
    def _build_pipeline(self) -> list[PipelineStage]:
        """Build the stage pipeline with dependencies.
        
        Creates all stages with their required dependencies.
        Order matters - stages execute sequentially.
        """
        # Lazy imports to avoid circular dependencies
        from somaai.modules.knowledge.stores.qdrant import QdrantStore
        from somaai.modules.ingest.validation import (
            ExtractionValidator,
            ChunkValidator
        )
        from somaai.modules.ingest.semantic_chunker import SemanticChunker
        
        # Stage imports
        from somaai.modules.ingest.stages.deduplication import DeduplicationStage
        from somaai.modules.ingest.stages.extraction import ExtractionStage
        from somaai.modules.ingest.stages.chunking import ChunkingStage
        from somaai.modules.ingest.stages.filtering import QualityFilterStage
        from somaai.modules.ingest.stages.enrichment import MetadataEnrichmentStage
        from somaai.modules.ingest.stages.storage import VectorStorageStage
        from somaai.modules.ingest.stages.db_sync import DatabaseSyncStage
        
        # Shared dependencies
        store = QdrantStore(self.settings)
        chunker = SemanticChunker(max_chunk_size=1500)
        
        # Build ordered pipeline
        return [
            DeduplicationStage(store=store),
            ExtractionStage(validator=ExtractionValidator()),
            ChunkingStage(chunker=chunker, validator=ChunkValidator()),
            QualityFilterStage(
                min_length=50,
                min_quality=0.3,
            ),
            MetadataEnrichmentStage(),
            VectorStorageStage(store=store, batch_size=50, max_retries=3),
            DatabaseSyncStage(),
        ]
    
    async def run(
        self,
        doc_id: str,
        file_path: str,
        grade: str,
        subject: str,
        title: str | None = None,
        on_progress: Callable[[str, int], None] | None = None,
        skip_if_exists: bool = True,
        ocr_mode: str = "auto",
        language: str = "eng",
    ) -> dict:
        """Execute the ingestion pipeline.
        
        Args:
            doc_id: Unique document identifier
            file_path: Path to document file
            grade: Grade level (e.g., "S2")
            subject: Subject (e.g., "biology")
            title: Optional document title
            on_progress: Progress callback (stage, percentage)
            skip_if_exists: Skip if document already ingested
            ocr_mode: OCR mode ('auto', 'force', 'skip')
            language: Language for OCR (default: 'eng')
            
        Returns:
            Dict with status, doc_id, chunks count, pages count
        """
        # Create pipeline context
        ctx = PipelineContext(
            doc_id=doc_id,
            file_path=Path(file_path),
            grade=grade,
            subject=subject,
            title=title or Path(file_path).stem,
            skip_if_exists=skip_if_exists,
            ocr_mode=ocr_mode,
            language=language,
            on_progress=on_progress,
            settings=self.settings,
        )
        
        logger.info(f"Starting ingestion pipeline for {doc_id}")
        
        try:
            # Execute stages sequentially
            for stage in self.stages:
                result = await stage.run(ctx)
                
                if not result.success:
                    raise IngestionError(
                        f"Stage '{stage.name}' failed: {result.errors}"
                    )
                
                # Check for skip signal (e.g., duplicate detected)
                if result.should_skip:
                    logger.info(f"Pipeline skipped at stage '{stage.name}'")
                    return result.data
            
            # Complete
            ctx.report_progress("Complete", 100)
            
            logger.info(
                f"Ingestion complete: {doc_id}, "
                f"{len(ctx.chunks)} chunks, {ctx.page_count} pages"
            )
            
            return {
                "status": "completed",
                "doc_id": doc_id,
                "chunks": len(ctx.chunks),
                "pages": ctx.page_count,
                "sections": ctx.section_count,
                "tables": ctx.table_count,
                "file_hash": ctx.file_hash,
                "stage_results": ctx.stage_results,
            }
            
        except IngestionError:
            raise
            
        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
            ctx.report_progress(f"Failed: {e}", -1)
            raise IngestionError(f"Ingestion failed: {e}")
