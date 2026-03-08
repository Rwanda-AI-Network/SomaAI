"""Pipeline context - shared state across all stages."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langchain_core.documents import Document

    from somaai.settings import Settings
    from somaai.utils.text_extractor import ExtractionResult


@dataclass
class PipelineContext:
    """Shared context passed through all pipeline stages.

    This dataclass carries:
    - Input parameters (doc_id, file_path, etc.)
    - Intermediate results from each stage
    - Progress tracking callbacks
    - Settings reference

    Each stage reads from and writes to this context,
    enabling loose coupling between stages.
    """

    # === Input Parameters ===
    doc_id: str
    file_path: Path  # kept for text_extractor compat (may be a temp path)
    grade: str
    subject: str
    title: str | None = None

    # === Object Storage ===
    file_content: bytes | None = None  # Raw bytes (buffered)
    file_stream: Any | None = None  # File-like object (streaming)
    storage_key: str | None = None  # Object key in MinIO/S3

    # === Processing Options ===
    skip_if_exists: bool = True
    ocr_mode: str = "auto"  # 'auto', 'force', 'skip'
    language: str = "eng"

    # === Intermediate Results (filled by stages) ===
    file_hash: str | None = None
    extraction_result: ExtractionResult | None = None
    extraction_confidence: float = 0.0
    chunks: list[Document] = field(default_factory=list)
    stored_chunk_ids: list[str] = field(default_factory=list)

    # === Progress Tracking ===
    on_progress: Callable[[str, int], None] | None = None

    # === Settings ===
    settings: Settings | None = None

    # === Stage Metadata ===
    stage_results: dict[str, Any] = field(default_factory=dict)

    def report_progress(self, stage: str, pct: int) -> None:
        """Report progress to callback if available.

        Args:
            stage: Description of current stage
            pct: Percentage complete (0-100, or -1 for error)
        """
        if self.on_progress:
            self.on_progress(stage, pct)

    def record_stage_result(self, stage_name: str, result: Any) -> None:
        """Record result from a stage for traceability.

        Args:
            stage_name: Name of the completed stage
            result: Stage result data
        """
        self.stage_results[stage_name] = result

    @property
    def has_structure(self) -> bool:
        """Check if extraction has structure (hierarchy/tables)."""
        if not self.extraction_result:
            return False
        return bool(self.extraction_result.hierarchy or self.extraction_result.tables)

    @property
    def page_count(self) -> int:
        """Get number of pages extracted."""
        if not self.extraction_result:
            return 0
        return len(self.extraction_result.pages)

    @property
    def table_count(self) -> int:
        """Get number of tables extracted."""
        if not self.extraction_result:
            return 0
        return len(self.extraction_result.tables)

    @property
    def section_count(self) -> int:
        """Get number of sections in hierarchy."""
        if not self.extraction_result:
            return 0
        return len(self.extraction_result.hierarchy)
