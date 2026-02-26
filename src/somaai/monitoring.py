"""Custom RAG monitoring metrics for Prometheus.

Extends the basic HTTP metrics with RAG-specific observability.
"""

import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

try:
    from prometheus_client import Counter, Gauge, Histogram

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

    # Create no-op classes if Prometheus not available
    class Counter:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, **kwargs):
            return self

        def inc(self, *args):
            pass

    class Histogram:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, **kwargs):
            return self

        def observe(self, *args):
            pass

    class Gauge:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            pass

        def set(self, *args):
            pass


logger = logging.getLogger(__name__)

# ============================================================================
# RAG Request Metrics
# ============================================================================

rag_requests_total = Counter(
    "rag_requests_total",
    "Total RAG requests",
    ["grade", "subject", "user_role", "status"],
)

rag_latency_seconds = Histogram(
    "rag_latency_seconds",
    "RAG request latency in seconds",
    ["stage"],  # retrieval, reranking, generation, total
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# ============================================================================
# Quality Metrics
# ============================================================================

rag_confidence_score = Histogram(
    "rag_confidence_score",
    "Confidence score distribution",
    buckets=[0.0, 0.3, 0.5, 0.7, 0.85, 0.95, 1.0],
)

rag_empty_results_total = Counter(
    "rag_empty_results_total", "Queries with no results", ["grade", "subject"]
)

rag_fallback_level_total = Counter(
    "rag_fallback_level_total",
    "Retrieval fallback level triggered",
    ["level"],  # 0=exact, 1=grade_only, 2=no_filters
)

rag_sufficiency_total = Counter(
    "rag_sufficiency_total",
    "Response sufficiency distribution",
    ["sufficiency"],  # sufficient, partial, insufficient
)

# ============================================================================
# Cache Metrics
# ============================================================================

cache_operations_total = Counter(
    "cache_operations_total",
    "Cache operations",
    ["cache_type", "operation", "status"],  # embedding/response, get/set, hit/miss
)

cache_hit_rate = Gauge("cache_hit_rate", "Cache hit rate percentage", ["cache_type"])

# ============================================================================
# System Health Metrics
# ============================================================================

qdrant_connection_status = Gauge(
    "qdrant_connection_status", "Qdrant connection status (1=connected, 0=disconnected)"
)

redis_connection_status = Gauge(
    "redis_connection_status", "Redis connection status (1=connected, 0=disconnected)"
)

llm_api_errors_total = Counter(
    "llm_api_errors_total", "LLM API errors", ["provider", "error_type"]
)

# ============================================================================
# Feature Flag Metrics
# ============================================================================

rag_feature_flags = Gauge(
    "rag_feature_flags", "RAG feature flag status (1=enabled, 0=disabled)", ["feature"]
)

# ============================================================================
# Decorators for Automatic Instrumentation
# ============================================================================


def monitor_rag_stage(stage_name: str):
    """Decorator to monitor RAG pipeline stages.

    Usage:
        @monitor_rag_stage("retrieval")
        async def retrieve(...):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                latency = time.time() - start_time
                rag_latency_seconds.labels(stage=stage_name).observe(latency)
                return result
            except Exception:
                latency = time.time() - start_time
                rag_latency_seconds.labels(stage=f"{stage_name}_error").observe(latency)
                raise

        return wrapper

    return decorator


# ============================================================================
# Helper Functions
# ============================================================================


def update_feature_flags(settings):
    """Update feature flag metrics from settings.

    Call this on application startup.
    """
    if not PROMETHEUS_AVAILABLE:
        return

    try:
        rag_feature_flags.labels(feature="hyde").set(
            1 if getattr(settings, "rag_enable_hyde", False) else 0
        )
        rag_feature_flags.labels(feature="reranking").set(
            1 if getattr(settings, "rag_enable_reranking", False) else 0
        )
        rag_feature_flags.labels(feature="input_validation").set(
            1 if getattr(settings, "rag_enable_input_validation", True) else 0
        )
        rag_feature_flags.labels(feature="simplified_retrieval").set(
            1 if getattr(settings, "rag_use_simplified_retrieval", True) else 0
        )
        logger.info("Feature flag metrics updated")
    except Exception as e:
        logger.warning(f"Failed to update feature flag metrics: {e}")


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
):
    """Log RAG request with structured data and metrics.

    This function both logs to the application logger and updates Prometheus metrics.
    """
    # Update Prometheus metrics
    status = "success" if success else "error"
    rag_requests_total.labels(
        grade=grade, subject=subject, user_role=user_role, status=status
    ).inc()

    if success:
        rag_confidence_score.observe(confidence)
        rag_sufficiency_total.labels(sufficiency=sufficiency).inc()

        if docs_retrieved == 0:
            rag_empty_results_total.labels(grade=grade, subject=subject).inc()

    # Structured logging
    log_data = {
        "event": "rag_request",
        "query_length": len(query),
        "grade": grade,
        "subject": subject,
        "user_role": user_role,
        "docs_retrieved": docs_retrieved,
        "docs_reranked": docs_reranked,
        "latency_ms": latency_ms,
        "success": success,
        "confidence": confidence,
        "sufficiency": sufficiency,
    }

    if error:
        log_data["error"] = error

    if success:
        logger.info("RAG request completed", extra=log_data)
    else:
        logger.error("RAG request failed", extra=log_data)


# ============================================================================
# Initialization
# ============================================================================

if PROMETHEUS_AVAILABLE:
    logger.info("Custom RAG metrics initialized")
else:
    logger.warning("Prometheus not available, metrics disabled")
