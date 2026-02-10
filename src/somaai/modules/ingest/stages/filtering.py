"""Filtering stage - quality and hallucination risk filtering."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from somaai.modules.ingest.stages.base import PipelineStage, StageResult

if TYPE_CHECKING:
    from somaai.modules.ingest.context import PipelineContext

logger = logging.getLogger(__name__)


class QualityFilterStage(PipelineStage):
    """Filter low-quality and high-risk chunks.
    
    Applies:
    - Minimum length filter
    - Quality score filter
    - Boilerplate removal
    - Hallucination risk filter
    """
    
    name = "filtering"
    start_pct = 30
    end_pct = 40
    
    def __init__(
        self,
        min_length: int = 50,
        min_quality: float = 0.3,
        max_hallucination_risk: float = 0.7,
        remove_boilerplate: bool = True
    ):
        """Initialize filter parameters.
        
        Args:
            min_length: Minimum chunk length in characters
            min_quality: Minimum quality score (0-1)
            max_hallucination_risk: Maximum allowed risk (0-1)
            remove_boilerplate: Whether to remove boilerplate text
        """
        self.min_length = min_length
        self.min_quality = min_quality
        self.max_hallucination_risk = max_hallucination_risk
        self.remove_boilerplate = remove_boilerplate
    
    def validate_input(self, ctx: PipelineContext) -> bool:
        """Ensure chunks exist."""
        return len(ctx.chunks) > 0
    
    async def execute(self, ctx: PipelineContext) -> StageResult:
        """Apply quality filters to chunks."""
        from somaai.modules.ingest.quality import (
            filter_chunks,
            filter_by_hallucination_risk
        )
        
        original_count = len(ctx.chunks)
        
        # Standard quality filtering
        self._report_progress(ctx, "Quality filtering", 0.3)
        # Regex-heavy: Run in thread pool
        ctx.chunks = await asyncio.to_thread(
            filter_chunks,
            ctx.chunks,
            min_length=self.min_length,
            min_quality=self.min_quality,
            remove_boilerplate=self.remove_boilerplate,
        )
        
        after_quality = len(ctx.chunks)
        
        # Hallucination risk filtering
        self._report_progress(ctx, "Risk filtering", 0.7)
        ctx.chunks = await asyncio.to_thread(
            filter_by_hallucination_risk,
            ctx.chunks,
            max_risk=self.max_hallucination_risk
        )
        
        final_count = len(ctx.chunks)
        filtered_quality = original_count - after_quality
        filtered_risk = after_quality - final_count
        
        logger.info(
            f"Filtered: {filtered_quality} low-quality, "
            f"{filtered_risk} high-risk, {final_count} remaining"
        )
        
        # Warn if all chunks filtered (edge case)
        if final_count == 0 and original_count > 0:
            logger.warning(
                f"All {original_count} chunks were filtered! "
                "Consider adjusting min_quality or max_hallucination_risk thresholds."
            )
        
        return StageResult(
            success=True,
            data={
                "original": original_count,
                "remaining": final_count,
                "filtered_quality": filtered_quality,
                "filtered_risk": filtered_risk,
            }
        )
