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
        super().__init__(f"Extraction validation failed with {len(issues)} issues")


class ChunkValidationError(IngestionError):
    """Raised when chunk validation fails."""

    def __init__(self, issues):
        self.issues = issues
        super().__init__(f"Chunk validation failed with {len(issues)} issues")


class StorageError(IngestionError):
    """Raised when storage operations fail."""

    pass


class EmbeddingError(IngestionError):
    """Raised when embedding generation fails."""

    pass


class DataIntegrityError(IngestionError):
    """Raised when data integrity checks fail."""

    pass
