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
        query = query[: self.max_query_length]

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


def sanitize_query(query: str, max_length: int = MAX_QUERY_LENGTH) -> str:
    """Convenience function for query sanitization.

    Args:
        query: Raw user input
        max_length: Maximum allowed query length

    Returns:
        Sanitized query
    """
    sanitizer = InputSanitizer(max_query_length=max_length, block_injections=False)
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


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal attacks.

    Args:
        filename: Original filename

    Returns:
        Safe filename
    """
    # Remove path components
    filename = filename.split("/")[-1].split("\\")[-1]

    # Remove dangerous characters (keep alphanumeric, spaces, dots, dashes, underscores)
    filename = re.sub(r"[^\w\s\-\.]", "", filename)

    # Remove leading dots (hidden files)
    filename = filename.lstrip(".")

    # Limit length
    if len(filename) > 255:
        name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
        filename = name[:250] + ("." + ext if ext else "")

    # Ensure not empty
    if not filename:
        filename = "unnamed_file"

    return filename


def validate_file_content(content: bytes, filename: str) -> None:
    """Validate file content for security issues.

    Checks file signatures and detects potentially malicious content.

    Args:
        content: File content bytes
        filename: Filename for extension check

    Raises:
        ValueError: If file is invalid or potentially malicious
    """
    # Check file size
    if len(content) == 0:
        raise ValueError("File is empty")

    if len(content) > 100 * 1024 * 1024:  # 100MB
        raise ValueError("File too large (max 100MB)")

    # Validate file signatures
    ext = filename.lower().split(".")[-1] if "." in filename else ""

    # if ext == 'pdf':
    #     # PDF should start with %PDF
    #     if not content.startswith(b'%PDF'):
    #         raise ValueError("Invalid PDF file signature")

    #     # Check for suspicious JavaScript (potential security risk)
    #     if b'/JavaScript' in content or b'/JS' in content:
    #         raise ValueError("PDF contains JavaScript (potential security risk)")

    #     # Check for suspicious actions
    #     if b'/Launch' in content or b'/SubmitForm' in content:
    #         raise ValueError("PDF contains potentially dangerous actions")

    if ext == "pdf":
        # PDF should start with %PDF
        if not content.startswith(b"%PDF"):
            raise ValueError("Invalid PDF file signature")

        # Check for suspicious JavaScript (potential security risk)
        # Note: /JS alone is too broad — matches font names, metadata, etc.
        # Look for actual JavaScript action patterns instead.
        js_patterns = [b"/JavaScript", b"/JS ", b"/JS\n", b"/JS\r"]
        if any(p in content for p in js_patterns):
            raise ValueError("PDF contains JavaScript (potential security risk)")

        # Check for suspicious actions
        if b"/Launch" in content or b"/SubmitForm" in content:
            raise ValueError("PDF contains potentially dangerous actions")

    elif ext == "docx":
        # DOCX is a ZIP file (PK signature)
        if not content.startswith(b"PK\x03\x04"):
            raise ValueError("Invalid DOCX file signature")

    elif ext == "doc":
        # DOC files start with specific signatures
        valid_signatures = [
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",  # OLE2
            b"\x0d\x44\x4f\x43",  # DOC
        ]
        if not any(content.startswith(sig) for sig in valid_signatures):
            raise ValueError("Invalid DOC file signature")

    elif ext in ["txt", "md"]:
        # Text files should be valid UTF-8
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("Invalid text encoding (must be UTF-8)")

        # Check for null bytes (binary data in text file)
        if b"\x00" in content:
            raise ValueError("Text file contains binary data")

    else:
        raise ValueError(f"Unsupported file extension: {ext}")
