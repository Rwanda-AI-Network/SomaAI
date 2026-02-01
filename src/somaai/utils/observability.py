"""Observability utilities for logging and metrics.

Provides structured logging for RAG pipeline monitoring.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextlib import contextmanager
from functools import wraps

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


class MetricsCollector:
    """Collects and tracks metrics for observability.

    In production, this would push to Prometheus/Datadog/etc.
    For now, logs metrics for debugging.
    Memory-bounded: limits histogram samples to prevent unbounded growth.
    """

    MAX_HISTOGRAM_SAMPLES = 1000  # Prevent unbounded memory growth

    def __init__(self):
        """Initialize collector."""
        self._counters: dict[str, int] = {}
        self._histograms: dict[str, list[float]] = {}

    def increment(self, name: str, value: int = 1, tags: dict | None = None) -> None:
        """Increment a counter metric.

        Args:
            name: Metric name
            value: Value to add
            tags: Optional tags
        """
        key = f"{name}:{tags}" if tags else name
        self._counters[key] = self._counters.get(key, 0) + value

    def record_latency(
        self, name: str, latency_ms: float, tags: dict | None = None
    ) -> None:
        """Record a latency measurement.

        Args:
            name: Metric name
            latency_ms: Latency in milliseconds
            tags: Optional tags
        """
        key = f"{name}:{tags}" if tags else name
        if key not in self._histograms:
            self._histograms[key] = []

        # Bounded: keep only recent samples to prevent memory growth
        if len(self._histograms[key]) >= self.MAX_HISTOGRAM_SAMPLES:
            # Remove oldest 10% to make room
            trim_count = self.MAX_HISTOGRAM_SAMPLES // 10
            self._histograms[key] = self._histograms[key][trim_count:]

        self._histograms[key].append(latency_ms)

        # Log for observability
        logging.debug(f"metric.{name}: {latency_ms:.2f}ms")

    def get_stats(self, name: str) -> dict:
        """Get statistics for a metric.

        Args:
            name: Metric name

        Returns:
            Statistics dict
        """
        values = self._histograms.get(name, [])
        if not values:
            return {}

        return {
            "count": len(values),
            "avg": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "p50": sorted(values)[len(values) // 2],
            "p95": (
                sorted(values)[int(len(values) * 0.95)]
                if len(values) > 20
                else max(values)
            ),
        }


# Global metrics collector
_metrics = MetricsCollector()


def get_metrics() -> MetricsCollector:
    """Get the global metrics collector."""
    return _metrics


@contextmanager
def measure_latency(operation: str, tags: dict | None = None):
    """Context manager to measure operation latency.

    Args:
        operation: Operation name
        tags: Optional tags

    Yields:
        None
    """
    start = time.time()
    try:
        yield
    finally:
        latency_ms = (time.time() - start) * 1000
        _metrics.record_latency(operation, latency_ms, tags)


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
    """Log a complete RAG request for observability.

    Args:
        query: User query
        grade: Grade level
        subject: Subject
        docs_retrieved: Number of docs retrieved
        docs_reranked: Number of docs after reranking
        latency_ms: Total latency
        success: Whether request succeeded
        error: Error message if failed
    """
    logger = logging.getLogger("somaai.rag")

    log_data = {
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

    # Track metrics
    _metrics.increment("rag_requests", tags={"success": str(success)})
    _metrics.record_latency("rag_latency", latency_ms)


def log_ingestion(
    doc_id: str,
    chunks_created: int,
    pages_processed: int,
    latency_ms: float,
    success: bool = True,
    error: str | None = None,
) -> None:
    """Log a document ingestion for observability.

    Args:
        doc_id: Document ID
        chunks_created: Number of chunks created
        pages_processed: Number of pages processed
        latency_ms: Total latency
        success: Whether ingestion succeeded
        error: Error message if failed
    """
    logger = logging.getLogger("somaai.ingest")

    log_data = {
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

    # Track metrics
    _metrics.increment("ingestions", tags={"success": str(success)})
    _metrics.record_latency("ingestion_latency", latency_ms)


def traced(operation: str):
    """Decorator to trace function execution.

    Args:
        operation: Operation name for tracing

    Returns:
        Decorator function
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            logger = logging.getLogger(func.__module__)
            start = time.time()

            try:
                result = await func(*args, **kwargs)
                latency_ms = (time.time() - start) * 1000

                logger.debug(
                    f"{operation} completed",
                    extra={
                        "operation": operation,
                        "latency_ms": round(latency_ms, 2),
                        "success": True,
                    },
                )
                _metrics.record_latency(f"{operation}_latency", latency_ms)

                return result

            except Exception as e:
                latency_ms = (time.time() - start) * 1000

                logger.error(
                    f"{operation} failed: {e}",
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
