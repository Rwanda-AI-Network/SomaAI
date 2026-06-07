"""Metadata utilities for normalization and consistency."""


def normalize_grade(grade: str) -> str:
    """Normalize grade to canonical uppercase form (e.g., 's1' -> 'S1')."""
    if not grade:
        return ""
    return grade.strip().upper()


def normalize_subject(subject: str) -> str:
    """Normalize subject to canonical lowercase form (e.g., 'MATH' -> 'math')."""
    if not subject:
        return "general"
    return subject.strip().lower()


def normalize_metadata(grade: str, subject: str | None = None) -> tuple[str, str]:
    """Normalize both grade and subject.

    Returns:
        Tuple of (normalized_grade, normalized_subject)
    """
    return normalize_grade(grade), normalize_subject(subject)
