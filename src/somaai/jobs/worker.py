"""Background job worker using ARQ.

Simple Redis-backed polling worker for processing background jobs.
Run separately from the main application.

Usage:
    arq somaai.jobs.worker.WorkerSettings
    
    OR
    
    python -m somaai.jobs.worker
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Task functions must be top-level coroutines for arq
async def ingest_document(ctx: dict, job_id: str, **kwargs) -> dict:
    """Document ingestion task wrapper."""
    from somaai.jobs.tasks import ingest_document_task
    await ingest_document_task(job_id=job_id, **kwargs)
    return {"status": "completed"}


async def generate_quiz(ctx: dict, job_id: str, **kwargs) -> dict:
    """Quiz generation task wrapper."""
    from somaai.jobs.tasks import generate_quiz_task
    await generate_quiz_task(job_id=job_id, **kwargs)
    return {"status": "completed"}


def _get_redis_settings():
    """Get Redis settings for ARQ worker.
    
    Must be called at class definition time to set the class attribute.
    """
    from arq.connections import RedisSettings

    from somaai.settings import settings

    # Parse Redis URL for jobs database
    redis_url = settings.redis_jobs_url
    if "://" in redis_url:
        parts = redis_url.split("://")[1]
        host_port = parts.split("/")[0]
        host = host_port.split(":")[0]
        port = int(host_port.split(":")[1]) if ":" in host_port else 6379
        db = int(parts.split("/")[1]) if "/" in parts else 1
    else:
        host, port, db = "localhost", 6379, 1

    return RedisSettings(
        host=host,
        port=port,
        database=db,
        password=settings.redis_password or None,
    )


class WorkerSettings:
    """ARQ Worker configuration.

    This class is auto-discovered by arq CLI.
    Run with: arq somaai.jobs.worker.WorkerSettings
    """

    # Redis settings - must be a class attribute, not a method
    # ARQ accesses this directly as WorkerSettings.redis_settings.host
    redis_settings = _get_redis_settings()

    # Register task functions
    functions = [ingest_document, generate_quiz]

    # Retry configuration
    max_tries = 3
    job_timeout = 3600  # 1 hour max per job

    # Concurrency
    max_jobs = 10

    # Health check
    health_check_interval = 30


def run_worker() -> None:
    """Entry point for running the worker.
    
    This is a SYNCHRONOUS function that creates its own event loop.
    Do NOT call this from within an async context.

    Usage:
        python -m somaai.jobs.worker
    """
    from arq import run_worker as arq_run_worker

    logger.info("Starting ARQ worker...")

    # run_worker is synchronous and manages its own event loop
    arq_run_worker(WorkerSettings)


if __name__ == "__main__":
    run_worker()
