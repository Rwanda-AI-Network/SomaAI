"""Document endpoint schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from somaai.contracts.common import GradeLevel, JobStatus, Subject

### This is not used yet ###
# class IngestRequest(BaseModel):
#     """Metadata for document ingestion.

#     File is uploaded separately as multipart form data.
#     """

#     grade: GradeLevel = Field(..., description="Grade level this document covers")
#     subject: Subject = Field(..., description="Subject this document covers")
#     title: str | None = Field(None, description="Document title")
#     metadata: dict[str, Any] | None = Field(None, description="Additional metadata")


class IngestJobResponse(BaseModel):
    """Response for POST /api/v1/ingest.

    Contains job ID for tracking ingestion progress.
    """

    job_id: str = Field(..., description="Background job ID")
    doc_id: str = Field(..., description="Document ID (available immediately)")
    status: JobStatus = Field(..., description="Initial job status (pending)")
    message: str = Field(..., description="Status message")


class DocumentResponse(BaseModel):
    """Document details for GET /api/v1/docs/{doc_id}.

    Contains document metadata without content.
    """

    doc_id: str = Field(..., description="Unique document ID")
    filename: str = Field(..., description="Original filename")
    title: str = Field(..., description="Document title")
    grade: GradeLevel = Field(..., description="Grade level")
    subject: Subject = Field(..., description="Subject")
    page_count: int = Field(..., description="Total number of pages")
    chunk_count: int = Field(..., description="Number of indexed chunks")
    storage_backend: str = Field(..., description="Storage backend (local/gdrive)")
    uploaded_at: datetime = Field(..., description="Upload timestamp")
    processed_at: datetime | None = Field(
        None, description="Processing completion timestamp"
    )
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata")


class DocumentViewLinkResponse(BaseModel):
    """Response for GET /api/v1/docs/{doc_id}/view."""

    url: str = Field(..., description="URL to view the document")


### This is not used yet ###

# class DocumentViewResponse(BaseModel):
#     """Page view for GET /api/v1/docs/{doc_id}/view.

#     Returns content or image URL for a specific page.
#     """

#     doc_id: str = Field(..., description="Document ID")
#     page_number: int = Field(..., description="Page number (1-indexed)")
#     total_pages: int = Field(..., description="Total pages in document")
#     content: str | None = Field(None, description="Page text content")
#     image_url: str | None = Field(
#         None, description="Page image URL (for PDF rendering)"
#     )
#     chunks: list = Field(
#         default_factory=list, description="Chunks extracted from this page"
#     )
