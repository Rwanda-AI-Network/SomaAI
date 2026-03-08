"""Database sync stage - sync chunks to PostgreSQL."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from somaai.modules.ingest.stages.base import PipelineStage, StageResult

if TYPE_CHECKING:
    from somaai.modules.ingest.context import PipelineContext

logger = logging.getLogger(__name__)


class DatabaseSyncStage(PipelineStage):
    """Sync chunk records to PostgreSQL for FK references.

    Creates chunk records in the database so that:
    - Citations can reference chunks by ID
    - Chunk metadata is queryable via SQL
    """

    name = "db_sync"
    start_pct = 95
    end_pct = 98

    async def execute(self, ctx: PipelineContext) -> StageResult:
        """Sync chunks to PostgreSQL."""
        from somaai.db.crud import create_chunks
        from somaai.db.session import async_session_maker

        self._report_progress(ctx, "Syncing to database", 0.3)

        try:
            async with async_session_maker() as session:
                chunk_records = []

                for chunk in ctx.chunks:
                    chunk_records.append(
                        {
                            "id": chunk.metadata["chunk_id"],
                            "document_id": ctx.doc_id,
                            "content": chunk.page_content,
                            "page_start": chunk.metadata.get("page_start", 1),
                            "page_end": chunk.metadata.get("page_end", 1),
                            "chunk_index": chunk.metadata.get("chunk_index", 0),
                            # Note: section_title/chunk_type stored in
                            # vector DB metadata, not currently in SQL
                            # schema based on crud.py
                        }
                    )

                await create_chunks(session, chunk_records)

                # Update document denormalized metadata (chunk_count + processed_at)
                from somaai.db.crud import update_document_processed

                await update_document_processed(
                    session,
                    doc_id=ctx.doc_id,
                    page_count=ctx.page_count,
                    chunk_count=len(chunk_records),
                )

            logger.info(
                f"Synced {len(chunk_records)} chunks to PostgreSQL for doc {ctx.doc_id}"
            )

            return StageResult(success=True, data={"synced_count": len(chunk_records)})

        except Exception as e:
            logger.error(f"Database sync failed: {e}")
            # CRITICAL: Do NOT report success when DB sync fails.
            # This ensures the orchestrator marks the doc as 'failed'
            # rather than 'completed' with missing chunk records.
            return StageResult(
                success=False,
                data={"synced_count": 0},
                errors=[f"DB sync failed: {e}"],
                metadata={"db_sync_failed": True},
            )
