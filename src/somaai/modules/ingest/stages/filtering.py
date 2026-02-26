"""Filtering stage - quality filtering for ingestion chunks."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from somaai.modules.ingest.stages.base import PipelineStage, StageResult

if TYPE_CHECKING:
    from somaai.modules.ingest.context import PipelineContext

logger = logging.getLogger(__name__)


class QualityFilterStage(PipelineStage):
    """Filter low-quality chunks during ingestion.

    Applies:
    - Minimum length filter
    - Quality score filter
    - Boilerplate removal
    """

    name = "filtering"
    start_pct = 30
    end_pct = 40

    def __init__(
        self,
        min_length: int = 50,
        min_quality: float = 0.3,
        remove_boilerplate: bool = True,
    ):
        """Initialize filter parameters.

        Args:
            min_length: Minimum chunk length in characters
            min_quality: Minimum quality score (0-1)
            remove_boilerplate: Whether to remove boilerplate text
        """
        self.min_length = min_length
        self.min_quality = min_quality
        self.remove_boilerplate = remove_boilerplate

    def validate_input(self, ctx: PipelineContext) -> bool:
        """Ensure chunks exist."""
        return len(ctx.chunks) > 0

    async def execute(self, ctx: PipelineContext) -> StageResult:
        """Apply quality filters to chunks."""
        from somaai.modules.ingest.quality import filter_chunks

        original_count = len(ctx.chunks)

        # Quality filtering (regex-heavy: run in thread pool)
        self._report_progress(ctx, "Quality filtering", 0.5)
        ctx.chunks = await asyncio.to_thread(
            filter_chunks,
            ctx.chunks,
            min_length=self.min_length,
            min_quality=self.min_quality,
            remove_boilerplate=self.remove_boilerplate,
        )

        final_count = len(ctx.chunks)
        filtered_count = original_count - final_count

        logger.info(
            "Filtered: %d low-quality, %d remaining",
            filtered_count,
            final_count,
        )

        # Warn if all chunks filtered (edge case)
        if final_count == 0 and original_count > 0:
            logger.warning(
                "All %d chunks were filtered! "
                "Consider adjusting min_quality threshold.",
                original_count,
            )

        return StageResult(
            success=True,
            data={
                "original": original_count,
                "remaining": final_count,
                "filtered": filtered_count,
            },
        )
