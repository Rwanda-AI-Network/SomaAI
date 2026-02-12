"""Custom exceptions."""

from fastapi import HTTPException, status


class SomaAIError(Exception):
    """Base exception for SomaAI."""

    pass


class NotFoundError(SomaAIError):
    """Resource not found error."""

    pass


class ValidationError(SomaAIError):
    """Validation error."""

    pass


class ConflictError(SomaAIError):
    """Conflict error (e.g. duplicate)."""

    pass


def not_found_exception(detail: str = "Resource not found") -> HTTPException:
    """Create a not found HTTP exception."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def bad_request_exception(detail: str = "Bad request") -> HTTPException:
    """Create a bad request HTTP exception."""
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def conflict_exception(detail: str = "Resource already exists") -> HTTPException:
    """Create a conflict HTTP exception."""
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
