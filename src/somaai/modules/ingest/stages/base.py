"""Base classes for pipeline stages."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from somaai.modules.ingest.context import PipelineContext

logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    """Result from a pipeline stage execution.

    Attributes:
        success: Whether the stage completed successfully
        data: Stage-specific result data
        metadata: Additional metadata about execution
        errors: List of errors if any
        should_skip: If True, remaining stages should be skipped
    """

    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    should_skip: bool = False


class PipelineStage(ABC):
    """Abstract base class for all pipeline stages.

    Each stage:
    - Has a unique name for logging/progress
    - Has defined progress range (start_pct to end_pct)
    - Implements execute() with its core logic
    - Can validate inputs before execution

    Example:
        class ExtractionStage(PipelineStage):
            name = "extraction"
            start_pct = 5
            end_pct = 20

            async def execute(self, ctx: PipelineContext) -> StageResult:
                result = extract(ctx.file_path)
                ctx.extraction_result = result
                return StageResult(success=True)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Stage name for logging and progress tracking."""
        pass

    @property
    def start_pct(self) -> int:
        """Progress percentage when stage starts."""
        return 0

    @property
    def end_pct(self) -> int:
        """Progress percentage when stage ends."""
        return 100

    @abstractmethod
    async def execute(self, context: PipelineContext) -> StageResult:
        """Execute the stage logic.

        Args:
            context: Shared pipeline context

        Returns:
            StageResult with success status and data
        """
        pass

    def validate_input(self, context: PipelineContext) -> bool:
        """Validate inputs before execution.

        Override in subclasses for specific validation.

        Args:
            context: Pipeline context to validate

        Returns:
            True if valid, False otherwise
        """
        return True

    def _report_progress(
        self, context: PipelineContext, message: str, stage_progress: float = 0.0
    ) -> None:
        """Report progress within this stage's range.

        Args:
            context: Pipeline context
            message: Progress message
            stage_progress: Progress within stage (0.0 to 1.0)
        """
        pct = int(self.start_pct + (self.end_pct - self.start_pct) * stage_progress)
        context.report_progress(message, pct)

    async def run(self, context: PipelineContext) -> StageResult:
        """Run the stage with logging and error handling.

        This wraps execute() with:
        - Input validation
        - Logging
        - Progress reporting
        - Error handling

        Args:
            context: Pipeline context

        Returns:
            StageResult from execute()
        """
        logger.info(f"[{self.name}] Starting stage")
        self._report_progress(context, f"Starting {self.name}", 0.0)

        if not self.validate_input(context):
            logger.error(f"[{self.name}] Input validation failed")
            return StageResult(
                success=False, errors=[f"Input validation failed for {self.name}"]
            )

        try:
            result = await self.execute(context)

            if result.success:
                logger.info(f"[{self.name}] Completed successfully")
                context.record_stage_result(self.name, result.data)
            else:
                logger.warning(f"[{self.name}] Completed with errors: {result.errors}")

            self._report_progress(context, f"Completed {self.name}", 1.0)
            return result

        except Exception as e:
            logger.error(f"[{self.name}] Failed with exception: {e}")
            return StageResult(success=False, errors=[str(e)])
