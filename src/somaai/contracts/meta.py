"""Metadata endpoint schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class MetadataCreate(BaseModel):
    """Schema for creating a new curriculum metadata entry."""

    type: str = Field(
        ..., description="Metadata type: 'grade' or 'subject'", pattern="^(grade|subject)$"
    )
    key: str = Field(
        ..., description="Unique key (e.g., 'P6', 'computer_science')", min_length=1, max_length=50
    )
    name: str = Field(
        ..., description="Display name (e.g., 'Primary 6', 'Computer Science')", min_length=1
    )
    display_order: int = Field(0, description="Sort order for UI")
    is_active: bool = Field(True, description="Whether this entry is active")


class MetadataUpdate(BaseModel):
    """Schema for updating an existing metadata entry."""

    name: str | None = Field(None, description="Display name")
    display_order: int | None = Field(None, description="Sort order for UI")
    is_active: bool | None = Field(None, description="Whether this entry is active")


class MetadataResponse(BaseModel):
    """Curriculum metadata response.

    Returned by GET /api/v1/meta/metadata.
    """

    id: str = Field(..., description="Unique ID")
    type: str = Field(..., description="'grade' or 'subject'")
    key: str = Field(..., description="Unique key")
    name: str = Field(..., description="Display name")
    display_order: int = Field(0, description="Sort order")
    is_active: bool = Field(True, description="Active flag")
    created_at: datetime | None = Field(None, description="Creation timestamp")
    updated_at: datetime | None = Field(None, description="Last update timestamp")



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
