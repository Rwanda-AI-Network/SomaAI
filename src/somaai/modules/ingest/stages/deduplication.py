"""Deduplication stage - check if document already ingested."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from somaai.modules.ingest.stages.base import PipelineStage, StageResult

if TYPE_CHECKING:
    from somaai.modules.ingest.context import PipelineContext
    from somaai.modules.knowledge.stores.qdrant import QdrantStore

logger = logging.getLogger(__name__)


class DeduplicationStage(PipelineStage):
    """Check if document already exists in vector store.
    
    Uses file hash for content-based deduplication and
    doc_id for identity-based deduplication.
    
    If document exists, returns should_skip=True to abort pipeline.
    """
    
    name = "deduplication"
    start_pct = 0
    end_pct = 5
    
    def __init__(self, store: QdrantStore):
        """Initialize with vector store.
        
        Args:
            store: Qdrant vector store for existence checks
        """
        self.store = store
    
    async def execute(self, ctx: PipelineContext) -> StageResult:
        """Check for existing document.
        
        Steps:
        1. Compute file content hash
        2. Check if doc_id exists in store
        3. Return skip signal if found
        """
        from somaai.utils.files import async_read_file, compute_file_hash
        
        self._report_progress(ctx, "Computing file hash", 0.2)
        
        # Compute content hash for deduplication
        try:
            file_content = await async_read_file(ctx.file_path)
            ctx.file_hash = compute_file_hash(file_content)
        except Exception as e:
            logger.warning(f"Could not compute file hash: {e}")
            ctx.file_hash = None
        
        self._report_progress(ctx, "Checking for duplicates", 0.5)
        
        # Check if document already ingested
        if ctx.skip_if_exists:
            try:
                exists = await self.store.exists_by_doc_id(ctx.doc_id)
                
                if exists:
                    logger.info(f"Document {ctx.doc_id} already exists, skipping")
                    return StageResult(
                        success=True,
                        data={
                            "status": "skipped",
                            "reason": "already_exists",
                            "doc_id": ctx.doc_id,
                            "file_hash": ctx.file_hash,
                        },
                        should_skip=True  # Signal to abort pipeline
                    )
            except Exception as e:
                logger.warning(f"Deduplication check failed: {e}. Proceeding.")
        
        return StageResult(
            success=True,
            data={
                "status": "proceed",
                "file_hash": ctx.file_hash,
            }
        )
