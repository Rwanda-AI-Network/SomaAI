"""Observability utilities for structured logging and tracing.

Provides context managers and decorators for tracking operation latency
with structured logging. All Prometheus metric updates are delegated
to :mod:`somaai.monitoring` — this module handles the *logging* side.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextlib import contextmanager
from functools import wraps
from typing import Any


@contextmanager
def measure_latency(operation: str, tags: dict | None = None):
    """Context manager to measure and log operation latency.

    Args:
        operation: Operation name for the log record.
        tags: Optional tags included in the log.

    Yields:
        None
    """
    logger = logging.getLogger("somaai.perf")
    start = time.perf_counter()
    try:
        yield
    finally:
        latency_ms = (time.perf_counter() - start) * 1000
        logger.debug(
            "%s completed in %.2fms",
            operation,
            latency_ms,
            extra={
                "operation": operation,
                "latency_ms": round(latency_ms, 2),
                **(tags or {}),
            },
        )


def log_rag_request(
    query: str,
    grade: str,
    subject: str,
    docs_retrieved: int,
    docs_reranked: int,
    latency_ms: float,
    success: bool = True,
    error: str | None = None,
) -> None:
    """Log a RAG request for observability.

    This is the lightweight fallback used when ``somaai.monitoring`` is
    not available (e.g. in unit tests without prometheus_client).
    The full ``monitoring.log_rag_request`` should be preferred in prod.
    """
    logger = logging.getLogger("somaai.rag")

    log_data: dict[str, Any] = {
        "event": "rag_request",
        "query_length": len(query),
        "grade": grade,
        "subject": subject,
        "docs_retrieved": docs_retrieved,
        "docs_reranked": docs_reranked,
        "latency_ms": round(latency_ms, 2),
        "success": success,
    }
    if error:
        log_data["error"] = error

    if success:
        logger.info("RAG request completed", extra=log_data)
    else:
        logger.error("RAG request failed", extra=log_data)


def log_ingestion(
    doc_id: str,
    chunks_created: int,
    pages_processed: int,
    latency_ms: float,
    success: bool = True,
    error: str | None = None,
) -> None:
    """Log a document ingestion for observability.

    Lightweight log-only version. Prefer ``monitoring.log_ingestion``
    in production for Prometheus metric updates.
    """
    logger = logging.getLogger("somaai.ingest")

    log_data: dict[str, Any] = {
        "event": "ingestion",
        "doc_id": doc_id,
        "chunks_created": chunks_created,
        "pages_processed": pages_processed,
        "latency_ms": round(latency_ms, 2),
        "success": success,
    }
    if error:
        log_data["error"] = error

    if success:
        logger.info("Document ingested", extra=log_data)
    else:
        logger.error("Ingestion failed", extra=log_data)


def traced(operation: str):
    """Decorator to trace async function execution with structured logging.

    Args:
        operation: Operation name for tracing.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            logger = logging.getLogger(func.__module__)
            start = time.perf_counter()

            try:
                result = await func(*args, **kwargs)
                latency_ms = (time.perf_counter() - start) * 1000

                logger.debug(
                    "%s completed",
                    operation,
                    extra={
                        "operation": operation,
                        "latency_ms": round(latency_ms, 2),
                        "success": True,
                    },
                )
                return result

            except Exception as e:
                latency_ms = (time.perf_counter() - start) * 1000
                logger.error(
                    "%s failed: %s",
                    operation,
                    e,
                    extra={
                        "operation": operation,
                        "latency_ms": round(latency_ms, 2),
                        "success": False,
                        "error": str(e),
                    },
                )
                raise

        return wrapper

    return decorator
