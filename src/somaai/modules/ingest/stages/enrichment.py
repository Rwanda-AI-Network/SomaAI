"""Enrichment stage - add document metadata to chunks."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from somaai.modules.ingest.stages.base import PipelineStage, StageResult
from somaai.utils.ids import generate_id

if TYPE_CHECKING:
    from somaai.modules.ingest.context import PipelineContext

logger = logging.getLogger(__name__)


class MetadataEnrichmentStage(PipelineStage):
    """Enrich chunks with document metadata.

    Adds to each chunk:
    - doc_id, title, grade, subject
    - chunk_id, chunk_index
    - Page information
    """

    name = "enrichment"
    start_pct = 40
    end_pct = 50

    async def execute(self, ctx: PipelineContext) -> StageResult:
        """Add metadata to all chunks."""

        self._report_progress(ctx, "Enriching metadata", 0.3)

        for i, chunk in enumerate(ctx.chunks):
            page_num = chunk.metadata.get("page", 1)

            # Normalize grade/subject to canonical casing.
            # Grade: UPPERCASE (matches DB convention: P6, S1, S6)
            # Subject: lowercase (matches Subject enum: computer_science)
            grade = (ctx.grade or "").strip().upper()
            subject = (ctx.subject or "").strip().lower()

            chunk.metadata.update(
                {
                    # Document identifiers
                    "doc_id": ctx.doc_id,
                    "title": ctx.title,
                    "grade": grade,
                    "subject": subject,
                    # Chunk identifiers
                    "chunk_index": i,
                    "chunk_id": chunk.metadata.get("chunk_id") or generate_id(),
                    # Page information
                    "page_start": page_num,
                    "page_end": page_num,
                    # Note: section_title, section_level, chunk_type
                    # are already set by SemanticChunker
                }
            )

        logger.info(f"Enriched {len(ctx.chunks)} chunks with metadata")

        return StageResult(success=True, data={"enriched_count": len(ctx.chunks)})
