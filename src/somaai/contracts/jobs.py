"""Background job schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from somaai.contracts.common import JobStatus


class JobResponse(BaseModel):
    """Response for job status endpoints.

    Used by ingest jobs, quiz generation, etc.
    """

    job_id: str = Field(..., description="Unique job ID")
    status: JobStatus = Field(..., description="Current job status")
    progress_pct: int = Field(
        0, ge=0, le=100, description="Progress percentage (0-100)"
    )
    result_id: str | None = Field(
        None, description="Result ID when completed (e.g., doc_id, quiz_id)"
    )
    error: str | None = Field(None, description="Error message if failed")
    created_at: datetime = Field(..., description="Job creation timestamp")
    started_at: datetime | None = Field(None, description="Processing start timestamp")
    completed_at: datetime | None = Field(None, description="Completion timestamp")
    metadata: dict[str, Any] | None = Field(None, description="Additional job metadata")
