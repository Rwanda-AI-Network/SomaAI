"""SomaAI API Contracts (Pydantic schemas).

This module contains all request/response schemas used by the API.
Centralizing contracts ensures consistency across endpoints.
"""

from somaai.contracts.chat import (
    ChatRequest,
    ChatResponse,
    CitationResponse,
    MessageResponse,
)
from somaai.contracts.common import (
    GradeLevel,
    PaginatedResponse,
    Subject,
    UserRole,
)
from somaai.contracts.docs import (
    DocumentResponse,
    IngestJobResponse,
    # IngestRequest,
)
from somaai.contracts.errors import (
    ErrorResponse,
    ValidationErrorResponse,
)
from somaai.contracts.feedback import (
    FeedbackRequest,
    FeedbackResponse,
)
from somaai.contracts.jobs import (
    JobResponse,
    JobStatus,
)
from somaai.contracts.meta import (
    GradeResponse,
    SubjectResponse,
    TopicResponse,
)
from somaai.contracts.quiz import (
    QuizDownloadParams,
    QuizGenerateRequest,
    QuizItemResponse,
    QuizResponse,
)
from somaai.contracts.teacher import (
    TeacherProfileRequest,
    TeacherProfileResponse,
)

__all__ = [
    # Common
    "PaginatedResponse",
    "UserRole",
    "GradeLevel",
    "Subject",
    # Errors
    "ErrorResponse",
    "ValidationErrorResponse",
    # Chat
    "ChatRequest",
    "ChatResponse",
    "MessageResponse",
    "CitationResponse",
    # Docs
    "DocumentResponse",
    # "IngestRequest",
    "IngestJobResponse",
    # Quiz
    "QuizGenerateRequest",
    "QuizResponse",
    "QuizItemResponse",
    "QuizDownloadParams",
    # Teacher
    "TeacherProfileRequest",
    "TeacherProfileResponse",
    # Feedback
    "FeedbackRequest",
    "FeedbackResponse",
    # Meta
    "GradeResponse",
    "SubjectResponse",
    "TopicResponse",
    # Jobs
    "JobStatus",
    "JobResponse",
]
