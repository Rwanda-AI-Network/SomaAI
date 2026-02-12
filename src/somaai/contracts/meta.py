"""Metadata endpoint schemas."""

from pydantic import BaseModel, Field


class GradeResponse(BaseModel):
    """Grade level metadata.

    Returned by GET /api/v1/meta/grades.
    """

    id: str = Field(..., description="Grade ID (e.g., 'P1', 'S3')")
    name: str = Field(..., description="Display name (e.g., 'Primary 1', 'Senior 3')")
    display_order: int = Field(..., description="Sort order for UI")
    level: str = Field(..., description="Level category (primary/secondary)")


class SubjectResponse(BaseModel):
    """Subject metadata.

    Returned by GET /api/v1/meta/subjects.
    """

    id: str = Field(..., description="Subject ID")
    name: str = Field(..., description="Display name")
    display_order: int = Field(..., description="Sort order for UI")
    icon: str | None = Field(None, description="Icon identifier for UI")


class TopicResponse(BaseModel):
    """Topic metadata.

    Returned by GET /api/v1/meta/topics.
    Topics are hierarchical and tied to grade+subject.
    """

    topic_id: str = Field(..., description="Topic ID")
    title: str = Field(..., description="Topic name")
    grade: str = Field(..., description="Grade ID")
    subject: str = Field(..., description="Subject ID")
    doc_id: str = Field(..., description="Document ID")
    page_start: int = Field(..., ge=1, description="Page start")
    page_end: int = Field(..., ge=1, description="Page end")
    path: list[str] = Field(default_factory=list, description="Path to topic")
    document_count: int = Field(
        0, description="Number of documents covering this topic"
    )
