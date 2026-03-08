"""Extraction stage - text_extractor integration with sanitization.

Design Decisions (Principal AI Engineer):
1. DEPENDENCY INJECTION: text_extractor passed as interface, not imported inline
2. SANITIZATION LAYER: All extraction results cleaned before pipeline continues
3. NO DUPLICATE FALLBACK: Fallback logic lives in text_extractor, not here
4. SINGLE RESPONSIBILITY: This stage only extracts and sanitizes
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from somaai.modules.ingest.exceptions import ExtractionValidationError
from somaai.modules.ingest.stages.base import PipelineStage, StageResult

if TYPE_CHECKING:
    from somaai.modules.ingest.context import PipelineContext
    from somaai.modules.ingest.validation import ExtractionValidator
    from somaai.utils.text_extractor import ExtractionResult

logger = logging.getLogger(__name__)


# ============================================================================
# EXTRACTORS: Protocol-based dependency injection
# ============================================================================


class TextExtractorProtocol(Protocol):
    """Protocol for text extraction - enables dependency injection.

    Why Protocol (vs ABC):
    - Structural typing: Any object with matching signature works
    - No inheritance required: Easy to mock for testing
    - Duck typing: Pythonic approach
    """

    def __call__(
        self, input_data: Path | bytes, ocr_mode: str, language: str
    ) -> ExtractionResult: ...


def get_default_extractor() -> TextExtractorProtocol:
    """Get the default text_extractor implementation.

    Lazy import: Only loads when needed, reducing startup time.
    """
    from somaai.utils.text_extractor import extract

    return extract


# ============================================================================
# SANITIZER: Clean extraction results for accurate downstream usage
# ============================================================================


@dataclass
class SanitizationConfig:
    """Configuration for text sanitization.

    These thresholds are tuned for curriculum documents:
    - Kinyarwanda/English bilingual content
    - Tables with numeric data
    - Mathematical notation
    """

    # Character cleaning
    normalize_unicode: bool = True  # NFKC normalization
    fix_encoding_errors: bool = True  # Replace common mojibake
    remove_control_chars: bool = True  # Remove \x00-\x1f except newlines

    # Whitespace handling
    collapse_whitespace: bool = True  # Multiple spaces → single
    normalize_newlines: bool = True  # \r\n, \r → \n
    max_consecutive_newlines: int = 3  # Collapse excessive blank lines

    # Content cleaning
    remove_page_artifacts: bool = True  # "Page X of Y", etc.
    fix_hyphenation: bool = True  # "docu-\nment" → "document"
    min_content_length: int = 10  # Pages with less are flagged


class TextSanitizer:
    """Sanitizes extracted text for accurate RAG usage.

    Why sanitize?
    1. ACCURACY: OCR introduces errors (mojibake, control chars)
    2. CONSISTENCY: Different extractors produce different whitespace
    3. EFFICIENCY: Smaller embeddings from cleaner text
    4. QUALITY: LLM performs better on clean input
    """

    def __init__(self, config: SanitizationConfig | None = None):
        self.config = config or SanitizationConfig()

        # Pre-compile patterns for efficiency
        self._whitespace_re = re.compile(r"[ \t]+")
        self._newline_re = re.compile(r"\n{4,}")
        self._page_artifact_re = re.compile(
            r"^\s*(page\s*\d+\s*(of\s*\d+)?|^\d+\s*$)", re.IGNORECASE | re.MULTILINE
        )
        self._hyphenation_re = re.compile(r"(\w+)-\n(\w+)")

        # Common encoding errors (mojibake) mappings
        self._mojibake_map = {
            "â€™": "'",  # Smart quote
            'â€"': "—",  # Em dash
            "â€œ": '"',  # Opening quote
            "â€": '"',  # Closing quote
            "Â ": " ",  # NBSP artifact
            "Ã©": "é",  # French e-acute
            "Ã¨": "è",  # French e-grave
        }

    def sanitize(self, text: str) -> str:
        """Apply all sanitization steps.

        Order matters - each step assumes previous steps ran.
        """
        if not text:
            return ""

        result = text

        # 1. Fix encoding issues FIRST (before any text manipulation)
        if self.config.fix_encoding_errors:
            result = self._fix_encoding(result)

        # 2. Unicode normalization (NFKC: compatible decomposition + composition)
        if self.config.normalize_unicode:
            result = unicodedata.normalize("NFKC", result)

        # 3. Remove control characters (keep \n, \t, \r for now)
        if self.config.remove_control_chars:
            result = self._remove_control_chars(result)

        # 4. Normalize newlines (\r\n, \r → \n)
        if self.config.normalize_newlines:
            result = result.replace("\r\n", "\n").replace("\r", "\n")

        # 5. Fix hyphenation BEFORE collapsing whitespace
        if self.config.fix_hyphenation:
            result = self._fix_hyphenation(result)

        # 6. Collapse whitespace
        if self.config.collapse_whitespace:
            result = self._whitespace_re.sub(" ", result)

        # 7. Limit consecutive newlines
        if self.config.max_consecutive_newlines:
            max_nl = "\n" * self.config.max_consecutive_newlines
            result = self._newline_re.sub(max_nl, result)

        # 8. Remove page artifacts
        if self.config.remove_page_artifacts:
            result = self._page_artifact_re.sub("", result)

        return result.strip()

    def _fix_encoding(self, text: str) -> str:
        """Fix common encoding errors (mojibake)."""
        for bad, good in self._mojibake_map.items():
            text = text.replace(bad, good)
        return text

    def _remove_control_chars(self, text: str) -> str:
        """Remove control characters except newline/tab."""
        return "".join(c for c in text if c >= " " or c in "\n\t\r")

    def _fix_hyphenation(self, text: str) -> str:
        """Rejoin hyphenated words split across lines."""
        return self._hyphenation_re.sub(r"\1\2", text)

    def sanitize_extraction_result(self, result: ExtractionResult) -> ExtractionResult:
        """Sanitize an entire ExtractionResult.

        Mutates the result in-place for efficiency.
        Also validates content quality.
        """

        # Sanitize full text
        result.full_text = self.sanitize(result.full_text)

        # Sanitize pages
        empty_pages = []
        for i, page in enumerate(result.pages):
            page.content = self.sanitize(page.content)
            if len(page.content) < self.config.min_content_length:
                empty_pages.append(i + 1)

        if empty_pages:
            logger.warning(f"Low content pages detected: {empty_pages[:5]}...")

        # Sanitize sections
        for section in result.hierarchy:
            section.title = self.sanitize(section.title)
            section.content = self.sanitize(section.content)

        # Sanitize tables (preserve markdown structure)
        for table in result.tables:
            # Light sanitization - don't break markdown
            if table.caption:
                table.caption = self.sanitize(table.caption)
            # Markdown needs minimal sanitization
            table.markdown = table.markdown.strip()

        return result


# ============================================================================
# EXTRACTION STAGE
# ============================================================================


class ExtractionStage(PipelineStage):
    """Extract and sanitize document content.

    Design Principles (Principal AI Engineer):

    1. DEPENDENCY INVERSION: Takes extractor as parameter, not hardcoded.
       - Enables testing with mock extractors
       - Allows swapping implementations without code change

    2. SANITIZATION BY DEFAULT: All results cleaned before continuing.
       - Prevents garbage-in-garbage-out in embeddings
       - Ensures consistent text format across all sources

    3. FAIL-FAST WITH FALLBACK: Validate early, but allow recovery.
       - Structured extraction validated strictly
       - Fallback allowed with lower confidence

    4. NO DUPLICATE LOGIC: text_extractor handles OCR fallback.
       - This stage doesn't re-implement what text_extractor does
       - Only adds sanitization and validation layers
    """

    name = "extraction"
    start_pct = 5
    end_pct = 20

    def __init__(
        self,
        validator: ExtractionValidator,
        extractor: TextExtractorProtocol | None = None,
        sanitizer: TextSanitizer | None = None,
    ):
        """Initialize extraction stage.

        Args:
            validator: Validates extraction quality
            extractor: Text extraction function (defaults to text_extractor.extract)
            sanitizer: Text sanitization (defaults to TextSanitizer)
        """
        self.validator = validator
        self._extractor = extractor
        self._sanitizer = sanitizer or TextSanitizer()

    @property
    def extractor(self) -> TextExtractorProtocol:
        """Lazy-load default extractor if not provided."""
        if self._extractor is None:
            self._extractor = get_default_extractor()
        return self._extractor

    async def execute(self, ctx: PipelineContext) -> StageResult:
        """Extract and sanitize document with production-grade streaming.

        Flow:
        1. Create managed stream using factory (auto-detects source)
        2. Ensure seekable (smart adapter selection)
        3. Extract with text_extractor
        4. Sanitize result
        5. Validate quality
        6. Store in context
        7. Automatic cleanup via context manager
        """
        self._report_progress(ctx, "Extracting document", 0.1)

        try:
            from somaai.utils.text_extractor.streaming import StreamFactory

            # STEP 1: Create managed stream from any source
            # Factory auto-detects: S3, local file, bytes, HTTP
            if ctx.storage_key:
                # S3/MinIO file - use factory with storage backend
                from somaai.settings import settings

                managed_stream = await StreamFactory.create_from_storage(
                    storage_key=ctx.storage_key,
                    backend=settings.storage.backend,
                    bucket=(
                        settings.storage.minio_bucket
                        if settings.storage.backend == "minio"
                        else settings.storage.s3_bucket
                    ),
                    endpoint=(
                        f"{'https' if settings.storage.minio_secure else 'http'}://{settings.storage.minio_endpoint}"
                        if settings.storage.backend == "minio"
                        else None
                    ),
                    access_key=(
                        settings.storage.minio_access_key
                        if settings.storage.backend == "minio"
                        else settings.storage.s3_access_key
                    ),
                    secret_key=(
                        settings.storage.minio_secret_key.get_secret_value()
                        if settings.storage.backend == "minio"
                        else (
                            settings.storage.s3_secret_key.get_secret_value()
                            if settings.storage.s3_secret_key
                            else None
                        )
                    ),
                    doc_id=ctx.doc_id,
                    ensure_seekable=True,  # Auto-adapt if needed
                )

            elif ctx.file_content:
                # Bytes in memory
                managed_stream = await StreamFactory.create(
                    source=ctx.file_content,
                    doc_id=ctx.doc_id,
                    ensure_seekable=True,
                )

            elif ctx.file_stream:
                # Existing stream - wrap it (less common path)
                # For now, read into bytes and use factory
                logger.debug("Converting existing stream to managed stream")
                data = await asyncio.to_thread(ctx.file_stream.read)
                managed_stream = await StreamFactory.create(
                    source=data,
                    doc_id=ctx.doc_id,
                    ensure_seekable=True,
                )

            else:
                # Local file
                managed_stream = await StreamFactory.create(
                    source=ctx.file_path,
                    doc_id=ctx.doc_id,
                    ensure_seekable=True,
                )

            # STEP 2: Use context manager for guaranteed cleanup
            async with managed_stream as stream:
                # STEP 3: Extract using text_extractor
                raw_result = await asyncio.to_thread(
                    self.extractor,
                    input_data=stream.stream,  # Pass the managed stream
                    ocr_mode=ctx.ocr_mode,
                    language=ctx.language,
                )

            # Stream automatically cleaned up here (even on exceptions)

            self._report_progress(ctx, "Sanitizing extracted content", 0.5)

            # STEP 2: Sanitize for accurate downstream usage
            sanitized_result = await asyncio.to_thread(
                self._sanitizer.sanitize_extraction_result, raw_result
            )

            # STEP 3: Validate extraction quality
            self._report_progress(ctx, "Validating extraction", 0.7)
            validation = await asyncio.to_thread(
                self.validator.validate, sanitized_result
            )

            # Always log issues (warnings and errors)
            validation.log_issues()

            if not validation.passed:
                # Convert ValidationIssue objects to dicts for better error messages
                issue_dicts = []
                for issue in validation.issues:
                    if hasattr(issue, "to_dict"):
                        issue_dicts.append(issue.to_dict())
                    else:
                        issue_dicts.append(
                            {
                                "severity": getattr(issue, "severity", "error"),
                                "message": getattr(issue, "message", str(issue)),
                                "suggestion": getattr(issue, "suggestion", ""),
                            }
                        )

                raise ExtractionValidationError(issue_dicts)

            validation.log_issues()  # Log warnings

            # STEP 4: Data integrity check
            if not sanitized_result.pages or len(sanitized_result.pages) == 0:
                raise ExtractionValidationError(
                    [{"severity": "critical", "message": "Zero pages extracted"}]
                )

            # STEP 5: Store in context
            ctx.extraction_result = sanitized_result
            ctx.extraction_confidence = validation.confidence_score

            # Log extraction summary
            self._log_extraction_summary(ctx)

            return StageResult(
                success=True, data=self._build_result_data(ctx, sanitized_result)
            )

        except ExtractionValidationError:
            raise

        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            raise ExtractionValidationError(
                [{"severity": "critical", "message": f"Extraction failed: {e}"}]
            )

    def _log_extraction_summary(self, ctx: PipelineContext) -> None:
        """Log extraction results for monitoring."""
        result = ctx.extraction_result
        logger.info(
            f"Extraction complete "
            f"(confidence={ctx.extraction_confidence:.2f}): "
            f"{len(result.pages)} pages, "
            f"{len(result.hierarchy)} sections, "
            f"{len(result.tables)} tables, "
            f"{len(result.full_text)} chars"
        )

    def _build_result_data(
        self, ctx: PipelineContext, result: ExtractionResult
    ) -> dict:
        """Build stage result data."""
        return {
            "method": result.metadata.get("method", "structured"),
            "pages": len(result.pages),
            "sections": len(result.hierarchy),
            "tables": len(result.tables),
            "confidence": ctx.extraction_confidence,
            "total_chars": len(result.full_text),
        }
