"""Job decorators for background task execution.

Provides decorators for job status tracking, error handling,
and database integration.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from somaai.contracts.jobs import JobStatus

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def with_job_tracking(task_name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator for job status tracking.
    
    Automatically updates job status to RUNNING on start,
    COMPLETED on success, or FAILED on exception.
    
    Usage:
        @with_job_tracking("ingest_document")
        async def ingest_document_task(job_id: str, **kwargs):
            ...
    
    Args:
        task_name: Name of the task for logging
        
    Returns:
        Decorated function with job tracking
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            job_id = kwargs.get("job_id")
            if not job_id:
                # No job_id, just execute
                return await func(*args, **kwargs)

            from somaai.db import crud
            from somaai.db.session import async_session_maker

            # Mark job as running
            async with async_session_maker() as db:
                await crud.update_job_status(
                    db, job_id, JobStatus.RUNNING.value, progress_pct=0
                )

            logger.info(f"[{task_name}] Job {job_id} started")

            try:
                result = await func(*args, **kwargs)

                # Mark job as completed
                async with async_session_maker() as db:
                    await crud.update_job_status(
                        db, job_id, JobStatus.COMPLETED.value, progress_pct=100
                    )

                logger.info(f"[{task_name}] Job {job_id} completed")
                return result

            except Exception as e:
                # Mark job as failed
                async with async_session_maker() as db:
                    await crud.update_job_status(
                        db, job_id, JobStatus.FAILED.value, error=str(e)
                    )

                logger.exception(f"[{task_name}] Job {job_id} failed: {e}")
                raise

        return wrapper
    return decorator


def with_progress_callback(
    job_id_kwarg: str = "job_id",
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator that injects a database-backed progress callback.
    
    Creates a sync-compatible progress callback that updates the database.
    The callback is passed as 'progress_callback' kwarg to the decorated function.
    
    Usage:
        @with_progress_callback()
        async def some_task(job_id: str, progress_callback=None, **kwargs):
            # progress_callback(50) updates database
            ...
    
    Args:
        job_id_kwarg: Name of the job_id keyword argument
        
    Returns:
        Decorated function with progress callback
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            job_id = kwargs.get(job_id_kwarg)

            if not job_id:
                return await func(*args, **kwargs)

            def progress_callback(pct: int, stage: str = "") -> None:
                """Sync progress callback that schedules DB update."""
                import asyncio

                from somaai.db import crud
                from somaai.db.session import async_session_maker

                async def _update():
                    async with async_session_maker() as db:
                        await crud.update_job_progress(db, job_id, pct)

                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(_update())
                except RuntimeError:
                    # No running loop, skip update
                    pass

            kwargs["progress_callback"] = progress_callback
            return await func(*args, **kwargs)

        return wrapper
    return decorator


def register_task(name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to register a task in the global registry.
    
    Usage:
        @register_task("ingest_document")
        async def ingest_document_task(job_id: str, **kwargs):
            ...
    
    Args:
        name: Task name for registration
        
    Returns:
        Decorated function (registered in TASK_REGISTRY)
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        from somaai.jobs.tasks import TASK_REGISTRY
        TASK_REGISTRY[name] = func
        return func
    return decorator
