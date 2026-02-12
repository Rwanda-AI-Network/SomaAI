"""Chunking stage - semantic chunking with structure preservation."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from somaai.modules.ingest.stages.base import PipelineStage, StageResult
from somaai.modules.ingest.exceptions import ChunkValidationError

if TYPE_CHECKING:
    from somaai.modules.ingest.context import PipelineContext
    from somaai.modules.ingest.semantic_chunker import SemanticChunker
    from somaai.modules.ingest.validation import ChunkValidator

logger = logging.getLogger(__name__)


class ChunkingStage(PipelineStage):
    """Create semantic chunks from extraction result.
    
    Uses SemanticChunker which:
    - Chunks by sections if hierarchy exists
    - Isolates tables as atomic chunks
    - Falls back to page-based chunking
    - Preserves structure metadata
    """
    
    name = "chunking"
    start_pct = 20
    end_pct = 30
    
    def __init__(self, chunker: SemanticChunker, validator: ChunkValidator):
        """Initialize with chunker and validator.
        
        Args:
            chunker: Semantic chunking implementation
            validator: Chunk quality validator
        """
        self.chunker = chunker
        self.validator = validator
    
    def validate_input(self, ctx: PipelineContext) -> bool:
        """Ensure extraction result exists."""
        return ctx.extraction_result is not None
    
    async def execute(self, ctx: PipelineContext) -> StageResult:
        """Create semantic chunks.
        
        Steps:
        1. Build base metadata from extraction
        2. Apply semantic chunking
        3. Validate chunks
        4. Check for data loss
        """
        self._report_progress(ctx, "Creating semantic chunks", 0.2)
        
        # Build metadata from extraction
        base_metadata = {
            "source": str(ctx.file_path),
            "extraction_confidence": ctx.extraction_confidence,
            "extraction_method": ctx.extraction_result.metadata.get("method", "structured"),
            "has_structure": ctx.has_structure,
        }
        
        # Apply semantic chunking
        self._report_progress(ctx, "Chunking by structure", 0.4)
        # CPU-bound: Run in thread pool
        ctx.chunks = await asyncio.to_thread(
            self.chunker.chunk,
            ctx.extraction_result,
            base_metadata
        )
        
        logger.info(f"Created {len(ctx.chunks)} chunks")
        
        # Validate chunks
        self._report_progress(ctx, "Validating chunks", 0.7)
        validation = await asyncio.to_thread(
            self.validator.validate,
            ctx.chunks
        )
        
        if not validation.passed:
            validation.log_issues()
            raise ChunkValidationError(validation.issues)
        
        validation.log_issues()  # Log warnings
        
        # Data integrity check: zero chunks
        if len(ctx.chunks) == 0:
            logger.error("Semantic chunking produced zero chunks - data loss")
            raise ChunkValidationError([
                {"severity": "critical", "message": "Zero chunks created"}
            ])
        
        # Data integrity check: suspiciously low count
        original_pages = ctx.page_count
        chunk_count = len(ctx.chunks)
        
        if chunk_count < original_pages * 0.5:
            logger.warning(
                f"Low chunk count: {chunk_count} chunks from {original_pages} pages. "
                f"Possible data loss during chunking."
            )
        
        return StageResult(
            success=True,
            data={
                "chunk_count": chunk_count,
                "from_pages": original_pages,
                "from_sections": ctx.section_count,
                "from_tables": ctx.table_count,
            }
        )
