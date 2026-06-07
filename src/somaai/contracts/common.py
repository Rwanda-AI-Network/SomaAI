"""Common schemas shared across the API."""

from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class DifficultyLevel(str, Enum):
    """Quiz difficulty levels."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class UserRole(str, Enum):
    """User role in the system."""

    STUDENT = "student"
    TEACHER = "teacher"


# NOTE: GradeLevel and Subject enums have been removed.
# Grades and subjects are now DB-driven via the Grade/Subject tables,
# validated at runtime through utils/validators.py and cached via MetaService.
# This allows adding new curriculum data via DB insert instead of code deployment.


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper.

    Used for list endpoints that support pagination.
    """

    items: list[T] = Field(..., description="List of items in current page")
    total: int = Field(..., description="Total number of items")
    page_start: int = Field(..., ge=1, description="First item index (1-indexed)")
    page_end: int = Field(..., ge=1, description="Last item index (1-indexed)")
    has_next: bool = Field(..., description="Whether there are more pages")
    has_prev: bool = Field(..., description="Whether there are previous pages")


class Sufficiency(str, Enum):
    """Answer sufficiency levels."""

    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    PARTIAL = "partial"


class JobStatus(str, Enum):
    """Background job status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
