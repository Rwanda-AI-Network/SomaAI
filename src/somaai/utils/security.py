"""Security utilities for input sanitization and validation.

Protects against prompt injection and other input-based attacks.
"""

from __future__ import annotations

import re
from re import Pattern

# Patterns that may indicate prompt injection attempts
INJECTION_PATTERNS: list[Pattern] = [
    re.compile(
        r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?)", re.I
    ),
    re.compile(r"disregard\s+(the\s+)?(above|previous|system)", re.I),
    re.compile(r"forget\s+(everything|all|your)\s+(instructions?|rules?)", re.I),
    re.compile(r"you\s+are\s+now\s+(a|an|the)", re.I),
    re.compile(r"new\s+instructions?:", re.I),
    re.compile(r"system\s*prompt", re.I),
    re.compile(r"<\s*(system|assistant|user)\s*>", re.I),
    re.compile(r"\[\s*INST\s*\]", re.I),
    re.compile(r"```\s*(system|instruction)", re.I),
]

# Maximum query lengths
MAX_QUERY_LENGTH = 2000
MAX_CONTEXT_LENGTH = 50000


class InputSanitizer:
    """Sanitizes user input to prevent prompt injection attacks."""

    def __init__(
        self,
        max_query_length: int = MAX_QUERY_LENGTH,
        block_injections: bool = True,
        log_blocked: bool = True,
    ):
        """Initialize sanitizer.

        Args:
            max_query_length: Maximum allowed query length
            block_injections: If True, raise error on injection attempts
            log_blocked: If True, log blocked attempts
        """
        self.max_query_length = max_query_length
        self.block_injections = block_injections
        self.log_blocked = log_blocked

    def sanitize_query(self, query: str) -> str:
        """Sanitize a user query.

        Args:
            query: Raw user input

        Returns:
            Sanitized query

        Raises:
            ValueError: If injection attempt detected and blocking enabled
        """
        if not query:
            return ""

        # Truncate to max length
        query = query[:self.max_query_length]

        # Check for injection patterns
        for pattern in INJECTION_PATTERNS:
            if pattern.search(query):
                if self.log_blocked:
                    import logging
                    logging.warning(
                        f"Potential prompt injection blocked: {query[:100]}..."
                    )

                if self.block_injections:
                    raise ValueError("Query contains potentially harmful content")

                # Replace instead of blocking
                query = pattern.sub("[FILTERED]", query)

        # Remove excessive whitespace
        query = " ".join(query.split())

        return query

    def sanitize_metadata(self, metadata: dict) -> dict:
        """Sanitize metadata values.

        Args:
            metadata: Metadata dictionary

        Returns:
            Sanitized metadata
        """
        sanitized = {}
        for key, value in metadata.items():
            if isinstance(value, str):
                # Truncate long strings
                sanitized[key] = value[:500]
            else:
                sanitized[key] = value
        return sanitized


def sanitize_query(query: str) -> str:
    """Convenience function for query sanitization.

    Args:
        query: Raw user input

    Returns:
        Sanitized query
    """
    sanitizer = InputSanitizer(block_injections=False)
    return sanitizer.sanitize_query(query)


def validate_query(query: str) -> str:
    """Validate and sanitize query, raising on injection attempts.

    Args:
        query: Raw user input

    Returns:
        Validated query

    Raises:
        ValueError: If query is invalid or contains injection
    """
    if not query or not query.strip():
        raise ValueError("Query cannot be empty")

    sanitizer = InputSanitizer(block_injections=True)
    return sanitizer.sanitize_query(query)
