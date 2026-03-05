"""Global error handler — maps exceptions to HTTP status codes.

Provides structured error responses for all exception types:
- 400 for user/validation errors
- 404 for not-found
- 503 for service unavailability
- 500 for unexpected errors with generic message (no leak)
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from somaai.exceptions import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)

logger = logging.getLogger(__name__)


def _error_response(
    status_code: int,
    detail: str,
    error_type: str = "error",
) -> JSONResponse:
    """Build a structured error response."""
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": detail,
            "error_type": error_type,
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app."""

    @app.exception_handler(ValidationError)
    async def validation_error_handler(
        request: Request, exc: ValidationError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_400_BAD_REQUEST,
            str(exc),
            "validation_error",
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(
        request: Request, exc: ValueError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_400_BAD_REQUEST,
            str(exc),
            "validation_error",
        )

    @app.exception_handler(NotFoundError)
    async def not_found_handler(
        request: Request, exc: NotFoundError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            str(exc),
            "not_found",
        )

    @app.exception_handler(ConflictError)
    async def conflict_handler(
        request: Request, exc: ConflictError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_409_CONFLICT,
            str(exc),
            "conflict",
        )

    @app.exception_handler(ServiceUnavailableError)
    async def service_unavailable_handler(
        request: Request, exc: ServiceUnavailableError
    ) -> JSONResponse:
        logger.error(
            "Service unavailable: %s",
            exc,
            extra={"error_type": "service_unavailable"},
        )
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Service temporarily unavailable. Please try again later.",
            "service_unavailable",
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.error(
            "Unhandled exception: %s",
            exc,
            exc_info=True,
            extra={"error_type": "internal_error"},
        )
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "An internal error occurred. Please try again.",
            "internal_error",
        )
