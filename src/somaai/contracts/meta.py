"""Metadata endpoint schemas."""

from pydantic import BaseModel, Field


# class GradeCreate(BaseModel):
#     """Schema for creating a new grade level."""

#     id: str = Field(..., description="Grade ID (e.g., 'P1', 'S3')")
#     name: str = Field(..., description="Display name (e.g., 'Primary 1', 'Senior 3')")
#     display_order: int = Field(0, description="Sort order for UI")
#     level: str = Field(..., description="Level category (primary/secondary)")


# class GradeUpdate(BaseModel):
#     """Schema for updating an existing grade level."""

#     name: str | None = Field(None, description="Display name")
#     display_order: int | None = Field(None, description="Sort order for UI")
#     level: str | None = Field(None, description="Level category")


class GradeResponse(BaseModel):
    """Grade level metadata.

    Returned by GET /api/v1/meta/grades.
    """

    id: str = Field(..., description="Grade ID (e.g., 'P1', 'S3')")
    name: str = Field(..., description="Display name (e.g., 'Primary 1', 'Senior 3')")
    display_order: int = Field(..., description="Sort order for UI")
    level: str = Field(..., description="Level category (primary/secondary)")


# class SubjectCreate(BaseModel):
#     """Schema for creating a new subject."""

#     id: str = Field(..., description="Subject ID")
#     name: str = Field(..., description="Display name")
#     display_order: int = Field(0, description="Sort order for UI")
#     icon: str | None = Field(None, description="Icon identifier for UI")


# class SubjectUpdate(BaseModel):
#     """Schema for updating an existing subject."""

#     name: str | None = Field(None, description="Display name")
#     display_order: int | None = Field(None, description="Sort order for UI")
#     icon: str | None = Field(None, description="Icon identifier for UI")


class SubjectResponse(BaseModel):
    """Subject metadata.

    Returned by GET /api/v1/meta/subjects.
    """

    id: str = Field(..., description="Subject ID")
    name: str = Field(..., description="Display name")
    display_order: int = Field(..., description="Sort order for UI")
    icon: str | None = Field(None, description="Icon identifier for UI")


class TopicCreate(BaseModel):
    """Schema for creating a new topic."""

    title: str = Field(..., description="Topic name")
    grade: str = Field(..., description="Grade ID")
    subject: str = Field(..., description="Subject ID")
    doc_id: str | None = Field(None, description="Document ID")
    page_start: int = Field(..., ge=1, description="Page start")
    page_end: int = Field(..., ge=1, description="Page end")
    path: list[str] = Field(default_factory=list, description="Path to topic")


class TopicUpdate(BaseModel):
    """Schema for updating an existing topic."""

    title: str | None = Field(None, description="Topic name")
    grade: str | None = Field(None, description="Grade ID")
    subject: str | None = Field(None, description="Subject ID")
    doc_id: str | None = Field(None, description="Document ID")
    page_start: int | None = Field(None, ge=1, description="Page start")
    page_end: int | None = Field(None, ge=1, description="Page end")
    path: list[str] | None = Field(None, description="Path to topic")


class TopicResponse(BaseModel):
    """Topic metadata.

    Returned by GET /api/v1/meta/topics.
    Topics are hierarchical and tied to grade+subject.
    """

    topic_id: str = Field(..., description="Topic ID")
    title: str = Field(..., description="Topic name")
    grade: str = Field(..., description="Grade ID")
    subject: str = Field(..., description="Subject ID")
    doc_id: str = Field("", description="Document ID")
    page_start: int = Field(..., ge=1, description="Page start")
    page_end: int = Field(..., ge=1, description="Page end")
    path: list[str] = Field(default_factory=list, description="Path to topic")
    document_count: int = Field(
        0, description="Number of documents covering this topic"
    )
