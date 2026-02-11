"""Chunk quality utilities for filtering low-quality content.

Provides filtering for:
- Minimum length requirements
- Boilerplate removal
- Quality scoring
"""

from __future__ import annotations

import re

# Minimum chunk length (characters)
MIN_CHUNK_LENGTH = 50


def is_garbage_text(text: str) -> bool:
    """Check if text appears to be garbage/corrupted.

    Detects:
    - Fragmented text (C h a r)
    - Missing spaces (LongStringOfGarbage)
    """
    if not text:
        return True

    words = text.split()
    if not words:
        return True

    avg_len = sum(len(w) for w in words) / len(words)

    # Heuristics
    if avg_len < 1.5:
        return True  # Fragmented
    if avg_len > 25:
        return True  # Missing spaces/Garbage

    # Check vowel ratio (English is typically ~40%, garbage is often low)
    vowels = set("aeiouAEIOU")
    vowel_count = sum(1 for c in text if c in vowels)
    if len(text) > 0:
        vowel_ratio = vowel_count / len(text)
        if vowel_ratio < 0.2:
            return True

    return False


# Maximum whitespace ratio
MAX_WHITESPACE_RATIO = 0.5

# Boilerplate patterns to remove
BOILERPLATE_PATTERNS = [
    re.compile(r"^page\s*\d+\s*$", re.I | re.M),  # Page numbers
    re.compile(r"^table\s+of\s+contents?\s*$", re.I | re.M),
    re.compile(r"^\s*©.*copyright.*$", re.I | re.M),
    re.compile(r"^all\s+rights\s+reserved\.?\s*$", re.I | re.M),
    re.compile(r"^\s*\d+\s*$"),  # Just numbers
    re.compile(r"^chapter\s+\d+\s*$", re.I | re.M),  # Chapter headers only
    re.compile(r"^\s*\.{3,}\s*$"),  # Ellipsis lines
    re.compile(r"^_{3,}$|^-{3,}$|^={3,}$", re.M),  # Separator lines
]


def is_boilerplate(text: str) -> bool:
    """Check if text is boilerplate content.

    Args:
        text: Text to check

    Returns:
        True if text appears to be boilerplate
    """
    cleaned = text.strip()
    if not cleaned:
        return True

    for pattern in BOILERPLATE_PATTERNS:
        if pattern.fullmatch(cleaned):
            return True

    return False


def calculate_quality_score(text: str) -> float:
    """Calculate quality score for a chunk (0-1).

    Higher score = better quality.

    Args:
        text: Chunk text

    Returns:
        Quality score between 0.0 and 1.0
    """
    if not text or not text.strip():
        return 0.0

    score = 1.0

    # Length penalty
    length = len(text.strip())
    if length < MIN_CHUNK_LENGTH:
        score *= length / MIN_CHUNK_LENGTH

    # Whitespace ratio penalty
    whitespace_count = sum(1 for c in text if c.isspace())
    whitespace_ratio = whitespace_count / len(text) if text else 1.0
    if whitespace_ratio > MAX_WHITESPACE_RATIO:
        score *= (1.0 - whitespace_ratio) / (1.0 - MAX_WHITESPACE_RATIO)

    # Alphanumeric ratio bonus
    alnum_count = sum(1 for c in text if c.isalnum())
    alnum_ratio = alnum_count / len(text) if text else 0.0
    if alnum_ratio < 0.3:
        score *= alnum_ratio / 0.3

    # Boilerplate penalty
    if is_boilerplate(text):
        score *= 0.1

    # Avg word length penalty (detects "C h a r a c t e r" spacing artifacts)
    words = text.split()
    if words:
        avg_word_len = sum(len(w) for w in words) / len(words)
        if avg_word_len < 1.5:
            score *= 0.1

    return max(0.0, min(1.0, score))


def filter_chunks(
    chunks: list,
    min_length: int = MIN_CHUNK_LENGTH,
    min_quality: float = 0.3,
    remove_boilerplate: bool = True,
) -> list:
    """Filter chunks by quality criteria.

    Args:
        chunks: List of LangChain Document objects
        min_length: Minimum character length
        min_quality: Minimum quality score (0-1)
        remove_boilerplate: Remove boilerplate content

    Returns:
        Filtered list of chunks
    """
    filtered = []

    for chunk in chunks:
        raw_content = (
            chunk.page_content if hasattr(chunk, "page_content") else str(chunk)
        )

        # Clean content (removes null bytes etc)
        content = clean_chunk_text(raw_content)

        # Update chunk content
        if hasattr(chunk, "page_content"):
            chunk.page_content = content

        # Skip short chunks
        if len(content.strip()) < min_length:
            continue

        # Skip boilerplate
        if remove_boilerplate and is_boilerplate(content):
            continue

        # Skip low quality
        quality = calculate_quality_score(content)
        if quality < min_quality:
            continue

        # Add quality score to metadata
        if hasattr(chunk, "metadata"):
            chunk.metadata["quality_score"] = round(quality, 3)

        filtered.append(chunk)

    return filtered


def clean_chunk_text(text: str) -> str:
    """Clean chunk text by removing common artifacts.

    Args:
        text: Raw chunk text

    Returns:
        Cleaned text
    """
    if not text:
        return ""

    # Remove null bytes (Critical for Postgres)
    text = text.replace("\x00", "")

    # Remove multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Remove leading/trailing whitespace per line
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    # Remove multiple spaces
    text = re.sub(r" {2,}", " ", text)

    return text.strip()


