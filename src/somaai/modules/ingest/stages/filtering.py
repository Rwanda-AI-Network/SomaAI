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
        max_filter_ratio: float = 0.9,
    ):
        """Initialize filter parameters.

        Args:
            min_length: Minimum chunk length in characters
            min_quality: Minimum quality score (0-1)
            remove_boilerplate: Whether to remove boilerplate text
            max_filter_ratio: Maximum ratio of chunks that can be filtered (0-1).
                If more than this fraction is dropped, the stage FAILS to
                prevent silent data loss from overly aggressive filtering.
        """
        self.min_length = min_length
        self.min_quality = min_quality
        self.remove_boilerplate = remove_boilerplate
        self.max_filter_ratio = max_filter_ratio

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

        # FAIL if ALL chunks were filtered — this is always data loss
        if final_count == 0 and original_count > 0:
            return StageResult(
                success=False,
                data={
                    "original": original_count,
                    "remaining": 0,
                    "filtered": original_count,
                },
                errors=[
                    f"All {original_count} chunks were filtered out. "
                    "Consider lowering min_quality or min_length thresholds."
                ],
            )

        # FAIL if filter ratio exceeds the safety threshold
        filter_ratio = filtered_count / original_count if original_count > 0 else 0
        if filter_ratio > self.max_filter_ratio:
            logger.error(
                "Filter ratio %.1f%% exceeds max_filter_ratio %.1f%%. "
                "Failing to prevent silent data loss.",
                filter_ratio * 100,
                self.max_filter_ratio * 100,
            )
            return StageResult(
                success=False,
                data={
                    "original": original_count,
                    "remaining": final_count,
                    "filtered": filtered_count,
                },
                errors=[
                    f"Excessive filtering: {filter_ratio:.0%} of chunks removed "
                    f"(threshold: {self.max_filter_ratio:.0%}). "
                    "This may indicate a document quality issue or "
                    "overly strict filters."
                ],
            )

        return StageResult(
            success=True,
            data={
                "original": original_count,
                "remaining": final_count,
                "filtered": filtered_count,
            },
        )
