"""Validation module for ingestion pipeline.

Provides three-layer validation:
1. Extraction validation (post-extraction)
2. Chunk validation (post-chunking)
3. Storage validation (post-storage)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.documents import Document

    from somaai.utils.text_extractor import ExtractionResult

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    """Represents a validation issue."""

    severity: str  # "critical", "warning", "info"
    message: str
    suggestion: str


@dataclass
class ValidationReport:
    """Container for validation results."""

    passed: bool
    issues: list[ValidationIssue]
    confidence_score: float

    def log_issues(self) -> None:
        """Log all validation issues."""
        for issue in self.issues:
            if issue.severity == "critical":
                logger.error(f"[CRITICAL] {issue.message} - {issue.suggestion}")
            elif issue.severity == "warning":
                logger.warning(f"[WARNING] {issue.message} - {issue.suggestion}")
            else:
                logger.info(f"[INFO] {issue.message}")


class ExtractionValidator:
    """Validates extraction quality to prevent hallucination-prone inputs."""

    MIN_CONTENT_LENGTH = 100
    MIN_UNIQUE_CHARS = 20
    CURRICULUM_MARKERS = [
        "chapter",
        "section",
        "lesson",
        "exercise",
        "question",
        "answer",
    ]

    def validate(self, extraction: ExtractionResult) -> ValidationReport:
        """
        Validate extraction result quality.

        Args:
            extraction: ExtractionResult from text_extractor

        Returns:
            ValidationReport with issues and confidence score
        """
        issues = []

        # Check 1: Minimum content length
        content_length = len(extraction.full_text.strip())
        if content_length < self.MIN_CONTENT_LENGTH:
            issues.append(
                ValidationIssue(
                    severity="critical",
                    message=f"Extracted text too short ({content_length} chars)",
                    suggestion="Retry with OCR or verify document is not corrupted",
                )
            )

        # Check 2: Structure detection
        has_structure = bool(extraction.hierarchy or extraction.tables)
        if not has_structure:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    message="No structure detected (no sections or tables)",
                    suggestion="Document may be plain text or unstructured",
                )
            )

        # Check 3: Character diversity (OCR quality indicator)
        unique_chars = len(set(extraction.full_text))
        if unique_chars < self.MIN_UNIQUE_CHARS:
            issues.append(
                ValidationIssue(
                    severity="critical",
                    message=(
                        f"Low character diversity ({unique_chars} unique characters)"
                    ),
                    suggestion="Possible OCR failure or corrupted document",
                )
            )

        # Check 4: Curriculum pattern detection
        text_lower = extraction.full_text.lower()
        has_curriculum_markers = any(
            marker in text_lower for marker in self.CURRICULUM_MARKERS
        )
        if not has_curriculum_markers:
            issues.append(
                ValidationIssue(
                    severity="info",
                    message="No curriculum marker words detected",
                    suggestion="Verify this is a curriculum/educational document",
                )
            )

        # Check 5: Table quality (if tables present)
        if extraction.tables:
            for i, table in enumerate(extraction.tables):
                if not table.markdown or len(table.markdown) < 10:
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            message=f"Table {i} appears empty or malformed",
                            suggestion="Review table extraction settings",
                        )
                    )

        # Calculate confidence
        confidence = self._calculate_confidence(extraction, issues)

        # Determine pass/fail
        passed = not any(issue.severity == "critical" for issue in issues)

        return ValidationReport(
            passed=passed, issues=issues, confidence_score=confidence
        )

    def _calculate_confidence(
        self, extraction: ExtractionResult, issues: list[ValidationIssue]
    ) -> float:
        """Calculate extraction confidence score (0.0-1.0)."""
        score = 1.0

        # Penalties for issues
        for issue in issues:
            if issue.severity == "critical":
                score -= 0.3
            elif issue.severity == "warning":
                score -= 0.1
            # info severity: no penalty

        # Bonuses for structure
        if extraction.hierarchy:
            score += 0.1
        if extraction.tables:
            score += 0.1

        # Clamp to [0.0, 1.0]
        return max(0.0, min(1.0, score))


class ChunkValidator:
    """Validates chunk quality and integrity."""

    MIN_CHUNK_LENGTH = 50

    def validate(self, chunks: list[Document]) -> ValidationReport:
        """
        Validate chunks for quality issues.

        Args:
            chunks: List of LangChain Document chunks

        Returns:
            ValidationReport
        """
        issues = []

        for i, chunk in enumerate(chunks):
            chunk_id = chunk.metadata.get("chunk_id", f"chunk_{i}")

            # Check 1: Empty or very short chunks
            content_length = len(chunk.page_content.strip())
            if content_length == 0:
                issues.append(
                    ValidationIssue(
                        severity="critical",
                        message=f"Empty chunk: {chunk_id}",
                        suggestion="Remove empty chunks from pipeline",
                    )
                )
            elif content_length < self.MIN_CHUNK_LENGTH:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        message=(
                            f"Very short chunk ({content_length} chars): {chunk_id}"
                        ),
                        suggestion="Review chunking strategy for minimum size",
                    )
                )

            # Check 2: Table integrity
            if chunk.metadata.get("chunk_type") == "table":
                pipe_count = chunk.page_content.count("|")
                if pipe_count < 4:  # Minimum for valid Markdown table
                    issues.append(
                        ValidationIssue(
                            severity="critical",
                            message=f"Truncated or malformed table: {chunk_id}",
                            suggestion="Check table chunking logic",
                        )
                    )

            # Check 3: Metadata completeness
            required_fields = ["chunk_type", "page"]
            missing_fields = [f for f in required_fields if f not in chunk.metadata]
            if missing_fields:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        message=f"Missing metadata in {chunk_id}: {missing_fields}",
                        suggestion="Ensure all required metadata fields are populated",
                    )
                )

            # Check 4: Orphaned headers (suggests improper chunking)
            if chunk.metadata.get("chunk_type") in ["section", "section_fragment"]:
                content = chunk.page_content.strip()
                # Check if chunk ends with a header-like pattern
                lines = content.split("\n")
                if lines and any(
                    lines[-1].lower().startswith(marker)
                    for marker in ["chapter", "section", "##", "###"]
                ):
                    issues.append(
                        ValidationIssue(
                            severity="info",
                            message=f"Chunk may end with orphaned header: {chunk_id}",
                            suggestion="Review section splitting logic",
                        )
                    )

        # Calculate confidence
        confidence = 1.0 - min(len(issues) * 0.05, 0.5)  # Max 50% penalty

        # Pass if no critical issues
        passed = not any(issue.severity == "critical" for issue in issues)

        return ValidationReport(
            passed=passed, issues=issues, confidence_score=confidence
        )


class StorageValidator:
    """Validates post-storage integrity with smoke tests."""

    async def validate(self, doc_id: str) -> ValidationReport:
        """
        Run smoke tests after storage.

        Args:
            doc_id: Document ID to validate

        Returns:
            ValidationReport
        """
        issues = []

        try:
            # Import here to avoid circular dependencies
            from somaai.modules.rag.retriever import Retriever
            from somaai.settings import settings

            retriever = Retriever(settings)

            # Test 1: Can we retrieve anything from this document?
            results = await retriever.retrieve(query="test", top_k=1)

            if not results:
                issues.append(
                    ValidationIssue(
                        severity="critical",
                        message=f"Cannot retrieve any chunks for doc_id={doc_id}",
                        suggestion="Check Qdrant storage and embedding generation",
                    )
                )
            else:
                # Test 2: Metadata integrity
                chunk = results[0]
                if not chunk.metadata.get("chunk_id"):
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            message="Retrieved chunk missing chunk_id metadata",
                            suggestion="Verify metadata pipeline",
                        )
                    )

                if chunk.metadata.get("doc_id") != doc_id:
                    issues.append(
                        ValidationIssue(
                            severity="critical",
                            message=(
                                f"doc_id mismatch: expected {doc_id}, "
                                f"got {chunk.metadata.get('doc_id')}"
                            ),
                            suggestion="Check metadata assignment in pipeline",
                        )
                    )

        except Exception as e:
            issues.append(
                ValidationIssue(
                    severity="critical",
                    message=f"Storage validation error: {str(e)}",
                    suggestion="Check Qdrant connection and retriever configuration",
                )
            )

        passed = not any(issue.severity == "critical" for issue in issues)
        confidence = 1.0 if passed else 0.0

        return ValidationReport(
            passed=passed, issues=issues, confidence_score=confidence
        )
