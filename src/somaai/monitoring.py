"""Production monitoring metrics for Prometheus.

Single source of truth for all application metrics. Uses prometheus_client
when available, falls back to no-op stubs so the app runs without it.

Metrics are organized by domain:
- RAG pipeline (requests, latency, quality)
- Cache (hit rate, operations)
- Ingestion (documents, latency)
- System health (service connectivity, pool stats)
"""

import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

try:
    from prometheus_client import Counter, Gauge, Histogram, Info

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

    # ── No-op stubs when prometheus_client is not installed ──────────

    class _NoOpMetric:
        """Base no-op metric that silently discards all calls."""

        def __init__(self, *args, **kwargs):
            pass

        def labels(self, **kwargs):
            return self

        def inc(self, *args):
            pass

        def dec(self, *args):
            pass

        def set(self, *args):
            pass

        def observe(self, *args):
            pass

        def info(self, *args):
            pass

    Counter = _NoOpMetric
    Histogram = _NoOpMetric
    Gauge = _NoOpMetric
    Info = _NoOpMetric


logger = logging.getLogger(__name__)

# Metric prefix for namespacing
_PREFIX = "somaai"

# Runtime flag — set to True by setup_metrics() when the app opts in.
# This ensures no Prometheus writes happen if settings.enable_metrics is False.
_metrics_enabled = False

# ════════════════════════════════════════════════════════════════════
# Application Info
# ════════════════════════════════════════════════════════════════════

app_info = Info(
    f"{_PREFIX}_app",
    "Application build information",
)

# ════════════════════════════════════════════════════════════════════
# RAG Request Metrics
# ════════════════════════════════════════════════════════════════════

rag_requests_total = Counter(
    f"{_PREFIX}_rag_requests_total",
    "Total RAG requests processed",
    ["grade", "subject", "user_role", "status"],
)

rag_latency_seconds = Histogram(
    f"{_PREFIX}_rag_latency_seconds",
    "RAG request latency in seconds",
    ["stage"],  # retrieval, generation, total
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

# ════════════════════════════════════════════════════════════════════
# RAG Quality Metrics
# ════════════════════════════════════════════════════════════════════

rag_confidence_score = Histogram(
    f"{_PREFIX}_rag_confidence_score",
    "Distribution of RAG response confidence scores",
    buckets=[0.0, 0.1, 0.3, 0.5, 0.7, 0.85, 0.95, 1.0],
)

rag_empty_results_total = Counter(
    f"{_PREFIX}_rag_empty_results_total",
    "Queries that returned zero documents",
    ["grade", "subject"],
)

rag_sufficiency_total = Counter(
    f"{_PREFIX}_rag_sufficiency_total",
    "Response sufficiency distribution",
    ["sufficiency"],  # sufficient, partial, insufficient
)

rag_docs_retrieved = Histogram(
    f"{_PREFIX}_rag_docs_retrieved",
    "Number of documents retrieved per query",
    buckets=[0, 1, 3, 5, 10, 20, 50],
)

# ════════════════════════════════════════════════════════════════════
# Cache Metrics
# ════════════════════════════════════════════════════════════════════

cache_operations_total = Counter(
    f"{_PREFIX}_cache_operations_total",
    "Cache operations by type and result",
    ["cache_type", "operation", "status"],  # embedding/response, get/set, hit/miss
)

cache_hit_ratio = Gauge(
    f"{_PREFIX}_cache_hit_ratio",
    "Rolling cache hit ratio (0.0–1.0)",
    ["cache_type"],
)

# ════════════════════════════════════════════════════════════════════
# Ingestion Metrics
# ════════════════════════════════════════════════════════════════════

ingestion_total = Counter(
    f"{_PREFIX}_ingestion_total",
    "Total document ingestions",
    ["status"],  # success, error
)

ingestion_latency_seconds = Histogram(
    f"{_PREFIX}_ingestion_latency_seconds",
    "Document ingestion latency in seconds",
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

ingestion_chunks_created = Histogram(
    f"{_PREFIX}_ingestion_chunks_created",
    "Number of chunks created per ingestion",
    buckets=[1, 5, 10, 25, 50, 100, 250, 500],
)

# ════════════════════════════════════════════════════════════════════
# System Health Metrics
# ════════════════════════════════════════════════════════════════════

service_up = Gauge(
    f"{_PREFIX}_service_up",
    "Service connectivity (1=connected, 0=disconnected)",
    ["service"],  # qdrant, redis, postgres
)

llm_api_errors_total = Counter(
    f"{_PREFIX}_llm_api_errors_total",
    "LLM API errors by provider and error type",
    ["provider", "error_type"],
)

llm_api_latency_seconds = Histogram(
    f"{_PREFIX}_llm_api_latency_seconds",
    "LLM API call latency in seconds",
    ["provider"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

# ════════════════════════════════════════════════════════════════════
# Feature Flags
# ════════════════════════════════════════════════════════════════════

feature_flags = Gauge(
    f"{_PREFIX}_feature_flag",
    "Feature flag status (1=enabled, 0=disabled)",
    ["feature"],
)


# ════════════════════════════════════════════════════════════════════
# Decorators
# ════════════════════════════════════════════════════════════════════


def monitor_rag_stage(stage_name: str):
    """Decorator to time RAG pipeline stages.

    Usage::

        @monitor_rag_stage("retrieval")
        async def retrieve(self, ...):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                elapsed = time.perf_counter() - start
                rag_latency_seconds.labels(stage=stage_name).observe(elapsed)
                return result
            except Exception:
                elapsed = time.perf_counter() - start
                rag_latency_seconds.labels(stage=f"{stage_name}_error").observe(elapsed)
                raise

        return wrapper

    return decorator


def monitor_latency(metric: Any, **label_kwargs):
    """Generic decorator to observe latency on any Histogram.

    Usage::

        @monitor_latency(ingestion_latency_seconds)
        async def ingest(self, ...):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                elapsed = time.perf_counter() - start
                if label_kwargs:
                    metric.labels(**label_kwargs).observe(elapsed)
                else:
                    metric.observe(elapsed)
                return result
            except Exception:
                raise

        return wrapper

    return decorator


# ════════════════════════════════════════════════════════════════════
# Helper Functions
# ════════════════════════════════════════════════════════════════════


def setup_metrics(settings) -> None:
    """Initialize metrics on application startup.

    Sets app info and feature flags from current settings.
    Call this once during the FastAPI lifespan. This flips _metrics_enabled
    to True so that helper functions start writing to Prometheus.
    """
    global _metrics_enabled  # noqa: PLW0603

    if not PROMETHEUS_AVAILABLE:
        logger.info("Prometheus client not installed — metrics disabled")
        return

    try:
        # App info
        app_info.info(
            {
                "version": getattr(settings, "version", "unknown"),
                "app_name": getattr(settings, "app_name", "somaai"),
            }
        )

        # Feature flags — only report flags that actually exist in Settings
        feature_flags.labels(feature="input_validation").set(
            1 if getattr(settings, "rag_enable_input_validation", True) else 0
        )
        feature_flags.labels(feature="debug").set(
            1 if getattr(settings, "debug", False) else 0
        )
        feature_flags.labels(feature="require_api_key").set(
            1 if getattr(settings, "require_api_key", False) else 0
        )

        _metrics_enabled = True
        logger.info("Prometheus metrics initialized and enabled")
    except Exception as e:
        logger.warning("Failed to initialize metrics: %s", e)


def log_rag_request(
    query: str,
    grade: str,
    subject: str,
    user_role: str,
    docs_retrieved: int,
    docs_reranked: int,
    latency_ms: float,
    success: bool,
    confidence: float = 0.0,
    sufficiency: str = "unknown",
    error: str | None = None,
) -> None:
    """Log RAG request with structured data AND update Prometheus metrics.

    This is the single place where both structured logging and metric
    updates happen for a RAG request.
    """
    status = "success" if success else "error"

    # ── Prometheus counters (only when metrics are enabled) ──
    if _metrics_enabled:
        rag_requests_total.labels(
            grade=grade, subject=subject, user_role=user_role, status=status
        ).inc()

        rag_latency_seconds.labels(stage="total").observe(latency_ms / 1000)
        rag_docs_retrieved.observe(docs_retrieved)

        if success:
            rag_confidence_score.observe(confidence)
            rag_sufficiency_total.labels(sufficiency=sufficiency).inc()
            if docs_retrieved == 0:
                rag_empty_results_total.labels(grade=grade, subject=subject).inc()

    # ── Structured log ──
    log_data: dict[str, Any] = {
        "event": "rag_request",
        "query_length": len(query),
        "grade": grade,
        "subject": subject,
        "user_role": user_role,
        "docs_retrieved": docs_retrieved,
        "docs_reranked": docs_reranked,
        "latency_ms": round(latency_ms, 2),
        "success": success,
        "confidence": round(confidence, 3),
        "sufficiency": sufficiency,
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
    """Log a document ingestion with structured data AND Prometheus metrics."""
    status = "success" if success else "error"

    if _metrics_enabled:
        ingestion_total.labels(status=status).inc()
        ingestion_latency_seconds.observe(latency_ms / 1000)

        if success:
            ingestion_chunks_created.observe(chunks_created)

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


def record_service_status(service: str, is_up: bool) -> None:
    """Record service connectivity for health dashboards."""
    if _metrics_enabled:
        service_up.labels(service=service).set(1 if is_up else 0)


def record_cache_operation(cache_type: str, operation: str, hit: bool) -> None:
    """Record a cache get/set with hit/miss status."""
    if _metrics_enabled:
        status = "hit" if hit else "miss"
        cache_operations_total.labels(
            cache_type=cache_type, operation=operation, status=status
        ).inc()


# ════════════════════════════════════════════════════════════════════
# Module-level init log
# ════════════════════════════════════════════════════════════════════

if PROMETHEUS_AVAILABLE:
    logger.info("Prometheus client available — custom metrics registered")
else:
    logger.info("Prometheus client not installed — using no-op metric stubs")
