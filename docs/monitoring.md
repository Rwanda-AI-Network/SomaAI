# Monitoring Stack Documentation

SomaAI uses a production-ready monitoring stack based on **Prometheus** for metrics collection and **Grafana** for visualization.

## Architecture

The monitoring implementation is centralized in `src/somaai/monitoring.py`. It uses a "graceful degradation" pattern:
1. If `prometheus_client` is installed, it registers custom metrics.
2. If not installed, it falls back to no-op stubs so the application remains functional.
3. Collection is gated by the `SOMAAI_ENABLE_METRICS` environment variable.

## Metrics Exposed

All custom metrics are namespaced with the `somaai_` prefix.

### RAG Pipeline
- `somaai_rag_requests_total`: Total RAG requests (labels: `grade`, `subject`, `user_role`, `status`).
- `somaai_rag_latency_seconds`: Histogram of RAG request latency (labels: `stage`).
- `somaai_rag_confidence_score`: Histogram of LLM confidence scores.
- `somaai_rag_sufficiency_total`: Counter for response sufficiency (`sufficient`, `insufficient`).
- `somaai_rag_empty_results_total`: Counter for queries returning zero documents.

### Infrastructure & System
- `somaai_service_up`: Binary gauge (1=UP, 0=DOWN) for `qdrant`, `redis`, and `postgres`.
- `somaai_cache_operations_total`: Counter for cache hits/misses.
- `somaai_ingestion_total`: Counter for document ingestion status.
- `somaai_llm_api_errors_total`: Counter for LLM provider errors.

## Configuration

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SOMAAI_ENABLE_METRICS` | `true` | Enables/disables the `/metrics` endpoint and background collection. |

### Dashboards & Alerts

- **Prometheus**: Accessible at `http://localhost:9090`. Configured in `monitoring/prometheus.yml`.
- **Alerts**: Defined in `monitoring/alerts.yml`. Includes alerts for high latency (>10s p95), high error rates (>5%), and service downtime.
- **Grafana**: Accessible at `http://localhost:3000`. Auto-provisions the "SomaAI - Production Dashboard" located at `monitoring/grafana/provisioning/dashboards/somaai-dashboard.json`.

## Usage in Code

### Decorators
Use `@monitor_rag_stage("stage_name")` to automatically time a specific part of the pipeline:

```python
from somaai.monitoring import monitor_rag_stage

@monitor_rag_stage("retrieval")
async def my_retrieval_func(...):
    ...
```

### Manual Logging
Use `log_rag_request` to record a full request lifecycle (handles both structured logging and Prometheus updates):

```python
from somaai.monitoring import log_rag_request

log_rag_request(
    query=query,
    grade=grade,
    ...,
    success=True
)
```
