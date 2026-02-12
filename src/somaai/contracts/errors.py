"""Error response schemas."""

from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error response format.

    Returned for all API errors (4xx, 5xx).
    """

    error: str = Field(..., description="Error type identifier")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] | None = Field(None, description="Additional error context")
    request_id: str | None = Field(None, description="Request ID for debugging")


class ValidationErrorDetail(BaseModel):
    """Single field validation error."""

    field: str = Field(..., description="Field path that failed validation")
    message: str = Field(..., description="Validation error message")
    type: str = Field(..., description="Error type (e.g., 'value_error', 'type_error')")


class ValidationErrorResponse(BaseModel):
    """Validation error response (422).

    Returned when request body or query params fail validation.
    """

    error: str = Field(default="validation_error", description="Error type")
    message: str = Field(
        default="Request validation failed", description="Error message"
    )
    errors: list[ValidationErrorDetail] = Field(
        ..., description="List of validation errors"
    )
