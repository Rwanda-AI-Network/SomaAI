"""Quiz generation endpoint schemas."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from somaai.contracts.common import DifficultyLevel, GradeLevel, Subject


class QuizStatus(str, Enum):
    """Quiz generation status."""

    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class DownloadVariant(str, Enum):
    """Quiz download variants."""

    QUESTIONS = "questions"
    QUESTIONS_ANSWERS = "questions_answers"


class DownloadFormat(str, Enum):
    """Quiz download formats."""

    PDF = "pdf"
    DOCX = "docx"


class QuizGenerateRequest(BaseModel):
    """Request body for POST /api/v1/quiz/generate.

    Teacher inputs for quiz generation.
    """

    topic_ids: list[str] = Field(
        ..., min_length=1, description="Topic IDs to generate questions from"
    )
    difficulty: DifficultyLevel = Field(..., description="Difficulty level")
    num_questions: int = Field(
        ..., ge=1, le=50, description="Number of questions to generate"
    )
    include_answer_key: bool = Field(
        True, description="Include detailed answers with citations"
    )
    include_citations: bool = Field(True, description="Include citations in answers")
    grade: GradeLevel = Field(..., description="Grade level")
    subject: Subject = Field(..., description="Subject")

    @model_validator(mode="after")
    def validate_flags(self):
        if not self.include_answer_key and self.include_citations:
            msg = "include_citations requires include_answer_key=true"
            raise ValueError(msg)
        return self


class QuizItemCitation(BaseModel):
    """Citation for a quiz item answer."""

    doc_id: str = Field(..., description="Source document ID")
    doc_title: str = Field(..., description="Document title")
    page_end: int = Field(..., ge=1, description="Last page (1-indexed)")
    has_next: bool = Field(..., description="Whether there are more pages")
    excerpt: str = Field(..., description="Relevant excerpt")


class QuizItemResponse(BaseModel):
    """Single quiz question with answer.

    Represents one question in a generated quiz.
    """

    item_id: str = Field(..., description="Quiz item ID")
    order: int = Field(..., description="Question order (1-indexed)")
    question: str = Field(..., description="Question text")
    options: list[str] | None = Field(None, description="MCQ Answer options")
    answer: str | None = Field(None, description="Answer text (if include_answer_key)")
    answer_citations: list[QuizItemCitation] | None = Field(
        None, description="Answer source citations"
    )


class QuizResponse(BaseModel):
    """Response for GET /api/v1/quiz/{quiz_id}.

    Full quiz details including all items.
    """

    quiz_id: str = Field(..., description="Unique quiz ID")
    status: QuizStatus = Field(..., description="Generation status")
    topic_names: list[str] = Field(
        default_factory=list, description="Topic names included"
    )
    difficulty: DifficultyLevel = Field(..., description="Difficulty level")
    num_questions: int = Field(..., description="Requested number of questions")
    items: list[QuizItemResponse] = Field(
        default_factory=list, description="Quiz items (if completed)"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    completed_at: datetime | None = Field(None, description="Completion timestamp")
    error: str | None = Field(None, description="Error message if failed")


class QuizDownloadParams(BaseModel):
    """Query params for GET /api/v1/quiz/{quiz_id}/download.

    Controls download format and content.
    """

    variant: DownloadVariant = Field(
        DownloadVariant.QUESTIONS, description="Content variant"
    )
    format: DownloadFormat = Field(DownloadFormat.PDF, description="File format")
