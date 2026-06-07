"""Custom exceptions for ingestion pipeline.

Provides clear error types for better debugging and error handling.
"""


class IngestionError(Exception):
    """Base exception for ingestion pipeline errors."""

    pass


class ExtractionValidationError(IngestionError):
    """Raised when extraction validation fails."""

    def __init__(self, issues):
        self.issues = issues
        # Build detailed message
        critical_count = sum(
            1 for i in issues if isinstance(i, dict) and i.get("severity") == "critical"
        )
        warning_count = sum(
            1 for i in issues if isinstance(i, dict) and i.get("severity") == "warning"
        )

        message_parts = []
        if critical_count > 0:
            message_parts.append(f"{critical_count} critical issue(s)")
        if warning_count > 0:
            message_parts.append(f"{warning_count} warning(s)")

        summary = f"Extraction validation failed: {', '.join(message_parts)}"

        # Add details
        details = []
        for issue in issues:
            if isinstance(issue, dict):
                severity = issue.get("severity", "error")
                message = issue.get("message", str(issue))
                suggestion = issue.get("suggestion", "")
                detail = f"[{severity.upper()}] {message}"
                if suggestion:
                    detail += f" → {suggestion}"
                details.append(detail)
            else:
                details.append(str(issue))

        if details:
            summary += "\n" + "\n".join(details)

        super().__init__(summary)


class ChunkValidationError(IngestionError):
    """Raised when chunk validation fails."""

    def __init__(self, issues):
        self.issues = issues
        # Build detailed message
        critical_count = sum(
            1 for i in issues if isinstance(i, dict) and i.get("severity") == "critical"
        )
        warning_count = sum(
            1 for i in issues if isinstance(i, dict) and i.get("severity") == "warning"
        )

        message_parts = []
        if critical_count > 0:
            message_parts.append(f"{critical_count} critical issue(s)")
        if warning_count > 0:
            message_parts.append(f"{warning_count} warning(s)")

        summary = f"Chunk validation failed: {', '.join(message_parts)}"

        # Add details
        details = []
        for issue in issues:
            if isinstance(issue, dict):
                severity = issue.get("severity", "error")
                message = issue.get("message", str(issue))
                detail = f"[{severity.upper()}] {message}"
                details.append(detail)
            else:
                details.append(str(issue))

        if details:
            summary += "\n" + "\n".join(details[:5])  # Limit to first 5 for brevity
            if len(details) > 5:
                summary += f"\n... and {len(details) - 5} more issue(s)"

        super().__init__(summary)


class StorageError(IngestionError):
    """Raised when storage operations fail."""

    pass


class EmbeddingError(IngestionError):
    """Raised when embedding generation fails."""

    pass


class DataIntegrityError(IngestionError):
    """Raised when data integrity checks fail."""

    pass
