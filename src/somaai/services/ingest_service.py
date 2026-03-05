"""In-house Ingestion Service for centralized document lifecycle logic."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from somaai.contracts.common import JobStatus
from somaai.contracts.docs import IngestJobResponse
from somaai.db import crud
from somaai.jobs.queue import enqueue_job
from somaai.providers.storage import get_storage

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class IngestionService:
    """Centralized service for triggering and tracking document ingestion."""

    @staticmethod
    async def trigger_ingestion(
        db: AsyncSession,
        doc_id: str,
        storage_key: str,
        grade: str,
        subject: str,
        title: str,
        filename: str,
        content_hash: str | None = None,
    ) -> IngestJobResponse:
        """Create document record and enqueue background ingestion job.

        Architecture Decision: Centralizes DB entry and worker handoff to ensure
        consistency between standard, storage-based, and chunked uploads.
        """
        storage = get_storage()
        storage_backend = storage.backend_type

        # 1. Create document record
        await crud.create_document(
            db=db,
            doc_id=doc_id,
            filename=filename,
            title=title,
            storage_path=storage_key,
            grade=grade,
            subject=subject,
            storage_backend=storage_backend,
            status="pending",
            content_hash=content_hash,
        )

        # 2. Enqueue background job
        job_id = await enqueue_job(
            task_name="ingest_document",
            payload={
                "doc_id": doc_id,
                "storage_key": storage_key,
                "content_hash": content_hash,
                "grade": grade,
                "subject": subject,
                "title": title,
            },
        )

        return IngestJobResponse(
            job_id=job_id,
            doc_id=doc_id,
            status=JobStatus.PENDING,
            message=f"Ingestion started for '{title}'.",
        )
