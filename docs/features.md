# SomaAI Features & Usage

This document provides a technical reference for the core features of SomaAI: RAG pipeline, Ingestion system, Background Jobs, and Optimizations.

## 1. Document Ingestion Pipeline

### Overview
The ingestion pipeline converts raw curriculum documents (PDF, DOCX) into searchable vector embeddings.

### Architecture
- **Load:** Detects file type (`.pdf`, `.docx`, `.txt`) and extracts text.
- **Split:** Semantically chunks text using `RecursiveCharacterTextSplitter`.
- **Filter:** Removes low-quality chunks (<30% alphanumeric characters).
- **Enrich:** Adds metadata (grade, subject, page number, chunk ID).
- **Store:** Generates embeddings and saves to Qdrant vector database.

### Performance Optimizations
- **Batch Processing:** Processing chunks in batches of 50 using `aioitertools`.
- **Deduplication:** SHA-256 file hashes prevent duplicate work.
- **Chunked Uploads:** Redis-backed session state for files >50MB via `/api/v1/upload/*`.

---

## 2. RAG Pipeline (Question Answering)

### Pipeline Stages
1. **Cache Check:** Returns cached response if available (TTL: 24h).
2. **Safety:** Sanitizes input to prevent injection.
3. **Retrieve:** Fetches top-20 documents from Qdrant.
4. **Rerank:** Re-scores top documents using a Cross-Encoder to select top 5.
5. **Generate:** Calls LLM to generate answer, analogy, and citations.

### Caching Strategy
- **Layer 1 (Embeddings):** Query embeddings cached for 1 hour (Redis db/2).
- **Layer 2 (Responses):** High-confidence answers (>0.7) cached for 24 hours.

---

## 3. Background Job System

### Overview
Long-running tasks (ingestion, quiz generation) are handled asynchronously using **ARQ**.

### Architecture
- **Queue:** Redis (db/1) persists jobs.
- **Worker:** Standalone process (`python -m somaai.jobs.worker`).
- **State:** PostgreSQL tracks job status (pending, running, completed, failed).

---

## 4. Database & Storage Optimizations

### PostgreSQL
- **Indexing:** B-Tree indexes on `grade`, `subject`, `session_id`, `chunk_id`.
- **Cascade Deletes:** Enforced at DB level.

### Redis Strategy
- **db/0 (General):** Sessions, rate limits.
- **db/1 (Jobs):** ARQ tasks.
- **db/2 (Cache):** RAG embeddings/responses.

---

## 5. Observability & Security

- **Metrics:** `/metrics` exposes Prometheus counters and bounded histograms.
- **Rate Limiting:** Redis-backed sliding window (default 10-60 req/min).
- **Security:** API Key authentication and input sanitization.
