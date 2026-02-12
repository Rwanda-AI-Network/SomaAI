"""ARQ-based job queue for background tasks.

Provides async job enqueuing and status tracking.
Uses database for persistent job storage.
"""

from __future__ import annotations

from typing import Any

from somaai.contracts.jobs import JobResponse, JobStatus
from somaai.db import crud
from somaai.db.session import async_session_maker
from somaai.utils.ids import generate_id


async def get_redis_pool():
    """Get ARQ Redis connection pool.

    Returns:
        ARQ Redis pool
    """
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        from somaai.settings import settings

        # Parse Redis URL for jobs database
        redis_url = settings.redis_jobs_url
        if "://" in redis_url:
            # Format: redis://host:port/db
            parts = redis_url.split("://")[1]
            host_port = parts.split("/")[0]
            host = host_port.split(":")[0]
            port = int(host_port.split(":")[1]) if ":" in host_port else 6379
            db = int(parts.split("/")[1]) if "/" in parts else 1
        else:
            host, port, db = "localhost", 6379, 1

        return await create_pool(
            RedisSettings(
                host=host,
                port=port,
                database=db,
                password=settings.redis_password or None,
            )
        )
    except ImportError:
        raise ImportError("arq is required for job queue. Install with: uv add arq")


async def enqueue_job(
    task_name: str,
    payload: dict[str, Any],
) -> str:
    """Enqueue a background job.

    Creates a job record in database and adds it to the queue.

    Args:
        task_name: Name of the task to execute
            (e.g., 'ingest_document', 'generate_quiz')
        payload: Task-specific payload data

    Returns:
        job_id: Unique job identifier for tracking
    """
    from somaai.settings import settings

    job_id = generate_id()

    # Create job record in database
    async with async_session_maker() as db:
        await crud.create_job(db, job_id, task_name, payload)

    if settings.queue_backend == "sync":
        # Sync mode: Execute immediately
        from somaai.jobs.tasks import TASK_REGISTRY

        task_fn = TASK_REGISTRY.get(task_name)
        if task_fn:
            try:
                async with async_session_maker() as db:
                    await crud.update_job_status(
                        db, job_id, JobStatus.RUNNING.value, progress_pct=0
                    )
                await task_fn(job_id, **payload)
                async with async_session_maker() as db:
                    await crud.update_job_status(
                        db, job_id, JobStatus.COMPLETED.value, progress_pct=100
                    )
            except Exception as e:
                async with async_session_maker() as db:
                    await crud.update_job_status(
                        db, job_id, JobStatus.FAILED.value, error=str(e)
                    )
    else:
        # Redis mode: Enqueue with ARQ
        pool = await get_redis_pool()
        await pool.enqueue_job(
            task_name,
            job_id=job_id,
            **payload,
        )

    return job_id


async def get_job_status(job_id: str) -> JobResponse | None:
    """Get current status of a job.

    Args:
        job_id: Job identifier from enqueue_job

    Returns:
        JobResponse with current status, progress, and result
        None if job not found
    """
    async with async_session_maker() as db:
        job = await crud.get_job(db, job_id)

    if not job:
        return None

    return JobResponse(
        job_id=job.id,
        status=JobStatus(job.status),
        progress_pct=job.progress_pct or 0,
        result_id=job.result_id,
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        metadata=None,  # TODO: fix validation error for job.metadata
    )


async def update_job_status(
    job_id: str,
    status: JobStatus,
    progress_pct: int = 0,
    result_id: str | None = None,
    error: str | None = None,
) -> None:
    """Update job status (called by workers).

    Args:
        job_id: Job identifier
        status: New status
        progress_pct: Progress percentage (0-100)
        result_id: Result ID if completed (e.g., doc_id, quiz_id)
        error: Error message if failed
    """
    async with async_session_maker() as db:
        await crud.update_job_status(
            db, job_id, status.value, progress_pct, result_id, error
        )


async def update_job_progress(job_id: str, progress_pct: int, stage: str = "") -> None:
    """Update job progress (convenience function).

    Args:
        job_id: Job identifier
        progress_pct: Progress percentage (0-100)
        stage: Current stage description (not stored)
    """
    async with async_session_maker() as db:
        await crud.update_job_progress(db, job_id, progress_pct)


async def get_pending_jobs(limit: int = 10) -> list:
    """Get pending jobs for processing (used by worker).

    Args:
        limit: Maximum number of jobs to fetch

    Returns:
        List of job records ready for processing
    """
    async with async_session_maker() as db:
        jobs = await crud.get_pending_jobs(db, limit)
    return jobs
