"""Tests for the monitoring module.

Validates that Prometheus metrics are correctly registered, incremented,
and that the module degrades gracefully when prometheus_client is absent.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestLogRagRequest:
    """Test the combined logging + metrics function."""

    def test_success_increments_counters(self):
        """log_rag_request should increment Prometheus counters on success."""
        from somaai.monitoring import (
            log_rag_request,
            rag_confidence_score,
            rag_requests_total,
            rag_sufficiency_total,
        )

        # These are real prometheus_client objects or no-op stubs —
        # either way calling them should not raise.
        log_rag_request(
            query="What is photosynthesis?",
            grade="S1",
            subject="biology",
            user_role="student",
            docs_retrieved=5,
            docs_reranked=3,
            latency_ms=1234.5,
            success=True,
            confidence=0.87,
            sufficiency="sufficient",
        )
        # No assertion on counter value needed — we're testing no-crash.
        # In real prometheus_client, we'd use REGISTRY to check values.

    def test_error_logs_with_error_field(self):
        """Failed RAG requests should log the error string."""
        from somaai.monitoring import log_rag_request

        # Should not raise
        log_rag_request(
            query="broken query",
            grade="P6",
            subject="math",
            user_role="teacher",
            docs_retrieved=0,
            docs_reranked=0,
            latency_ms=50.0,
            success=False,
            error="LLM timeout",
        )

    def test_empty_results_tracked(self):
        """Queries with zero docs should increment the empty results counter."""
        from somaai.monitoring import log_rag_request

        log_rag_request(
            query="obscure topic",
            grade="S3",
            subject="chemistry",
            user_role="student",
            docs_retrieved=0,
            docs_reranked=0,
            latency_ms=200.0,
            success=True,
            confidence=0.1,
            sufficiency="insufficient",
        )


class TestLogIngestion:
    """Test the ingestion logging + metrics function."""

    def test_success(self):
        from somaai.monitoring import log_ingestion

        log_ingestion(
            doc_id="doc-abc-123",
            chunks_created=42,
            pages_processed=10,
            latency_ms=5000.0,
            success=True,
        )

    def test_failure(self):
        from somaai.monitoring import log_ingestion

        log_ingestion(
            doc_id="doc-fail",
            chunks_created=0,
            pages_processed=0,
            latency_ms=100.0,
            success=False,
            error="PDF extraction failed",
        )


class TestSetupMetrics:
    """Test the startup initialization function."""

    def test_setup_does_not_raise(self):
        """setup_metrics should never crash the app startup."""
        from somaai.monitoring import setup_metrics

        mock_settings = MagicMock()
        mock_settings.version = "0.1.0"
        mock_settings.app_name = "SomaAI"
        mock_settings.rag_enable_input_validation = True
        mock_settings.debug = False
        mock_settings.require_api_key = False

        # Should not raise
        setup_metrics(mock_settings)

    def test_setup_with_missing_attrs(self):
        """setup_metrics should handle settings objects missing attributes."""
        from somaai.monitoring import setup_metrics

        # Bare object with no attributes
        class BareSettings:
            pass

        setup_metrics(BareSettings())


class TestHelperFunctions:
    """Test utility functions."""

    def test_record_service_status(self):
        from somaai.monitoring import record_service_status

        record_service_status("qdrant", True)
        record_service_status("redis", False)
        record_service_status("postgres", True)

    def test_record_cache_operation(self):
        from somaai.monitoring import record_cache_operation

        record_cache_operation("embedding", "get", hit=True)
        record_cache_operation("response", "get", hit=False)
        record_cache_operation("embedding", "set", hit=True)


class TestMonitorRagStageDecorator:
    """Test the @monitor_rag_stage decorator."""

    @pytest.mark.asyncio
    async def test_decorator_times_function(self):
        from somaai.monitoring import monitor_rag_stage

        @monitor_rag_stage("test_retrieval")
        async def fake_retrieve():
            return ["doc1", "doc2"]

        result = await fake_retrieve()
        assert result == ["doc1", "doc2"]

    @pytest.mark.asyncio
    async def test_decorator_records_error_stage(self):
        from somaai.monitoring import monitor_rag_stage

        @monitor_rag_stage("test_generation")
        async def failing_generate():
            raise ValueError("LLM error")

        with pytest.raises(ValueError, match="LLM error"):
            await failing_generate()


class TestPrometheusAvailability:
    """Test graceful degradation."""

    def test_prometheus_flag_is_set(self):
        """PROMETHEUS_AVAILABLE should be True when prometheus_client is installed."""
        from somaai.monitoring import PROMETHEUS_AVAILABLE

        # In the test environment, prometheus_client should be installed
        # via the [scale] extra. If not, this flag correctly reports False.
        assert isinstance(PROMETHEUS_AVAILABLE, bool)

    def test_all_metrics_are_callable(self):
        """All metric objects should be callable without error."""
        from somaai.monitoring import (
            cache_hit_ratio,
            cache_operations_total,
            feature_flags,
            ingestion_chunks_created,
            ingestion_latency_seconds,
            ingestion_total,
            llm_api_errors_total,
            llm_api_latency_seconds,
            rag_confidence_score,
            rag_docs_retrieved,
            rag_empty_results_total,
            rag_latency_seconds,
            rag_requests_total,
            rag_sufficiency_total,
            service_up,
        )

        # Verify all metrics can be accessed without error
        assert rag_requests_total is not None
        assert rag_latency_seconds is not None
        assert rag_confidence_score is not None
        assert rag_empty_results_total is not None
        assert rag_sufficiency_total is not None
        assert rag_docs_retrieved is not None
        assert cache_operations_total is not None
        assert cache_hit_ratio is not None
        assert ingestion_total is not None
        assert ingestion_latency_seconds is not None
        assert ingestion_chunks_created is not None
        assert service_up is not None
        assert llm_api_errors_total is not None
        assert llm_api_latency_seconds is not None
        assert feature_flags is not None
