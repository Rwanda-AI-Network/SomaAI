# Architecture

System design of SomaAI — a Retrieval-Augmented Generation (RAG) platform for educational content built on FastAPI, Qdrant, PostgreSQL, and Redis.

---

## System Overview

```mermaid
graph TB
    Client["Client<br/>(Web / Mobile)"]
    
    subgraph Gateway["FastAPI Gateway"]
        Router["API v1 Router"]
    end

    subgraph Modules["Core Modules"]
        Chat["Chat Module<br/>(RAG Q&A)"]
        Ingest["Ingestion<br/>Pipeline"]
        Quiz["Quiz<br/>Generator"]
        Teacher["Teacher<br/>Module"]
        Feedback["Feedback<br/>Module"]
    end

    subgraph Data["Data Stores"]
        Qdrant["Qdrant<br/>(384d vectors)"]
        Redis["Redis<br/>(cache + jobs)"]
        PG["PostgreSQL 16<br/>(metadata, history)"]
        Storage["Local / S3<br/>(file storage)"]
    end

    Client -->|HTTP/REST| Router
    Router --> Chat
    Router --> Ingest
    Router --> Quiz
    Router --> Teacher
    Router --> Feedback
    
    Chat --> Qdrant
    Chat --> Redis
    Chat --> PG
    Ingest --> Qdrant
    Ingest --> PG
    Ingest --> Storage
    Quiz --> Chat
```

**Data flow:** Documents are ingested through a 7-stage pipeline (extract → chunk → embed → store), then queried via the RAG pipeline (classify → sanitize → retrieve → generate) with citation tracking.

---

## Core Modules

### 1. Ingestion Pipeline (`modules/ingest/`)

Transforms raw PDFs into searchable vector embeddings. Orchestrated by `IngestionOrchestrator` which runs 7 sequential stages:

```mermaid
graph LR
    PDF["PDF Upload"]
    D["1. Dedup<br/>(SHA-256)"]
    E["2. Extract<br/>(text + OCR)"]
    C["3. Chunk<br/>(semantic, 1500 char)"]
    F["4. Filter<br/>(quality ≥ 0.3)"]
    EN["5. Enrich<br/>(metadata)"]
    V["6. Vector<br/>(Qdrant)"]
    DB["7. DB Sync<br/>(PostgreSQL)"]
    
    PDF --> D --> E --> C --> F --> EN --> V --> DB
```

- **Chunking**: `SemanticChunker` with 1500-char max, section-aware splitting
- **Filtering**: Discards chunks < 50 characters or quality score < 0.3
- **Vector Storage**: Batch upsert to Qdrant (batch size 50, 3 retries)

See [INGESTION_PIPELINE.md](INGESTION_PIPELINE.md) for the full technical deep dive.

### 2. RAG Pipeline (`modules/rag/`)

The core intelligence module. Orchestrated by `RAGPipeline` in `pipelines.py`.

```mermaid
graph TD
    Q["User Query"]
    Cache{"Response<br/>Cache Hit?"}
    Sanitize["Sanitize Input"]
    Classify{"Query<br/>Classifier"}
    Condense["Condense with History<br/>(if multi-turn)"]
    Retrieve["Dense Retrieval<br/>(Qdrant, cosine sim)"]
    Fallback{"≥ 3 results?"}
    NoFilter["Retry: No Filters"]
    Context["Build Context<br/>(truncate to 4000 tokens)"]
    Generate["LLM Generation<br/>(structured JSON)"]
    Citations["Citation Validation"]
    CacheStore["Cache Response"]
    Response["Return Response"]
    Chitchat["Direct Response<br/>(greeting/farewell)"]

    Q --> Cache
    Cache -->|Hit| Response
    Cache -->|Miss| Sanitize
    Sanitize --> Classify
    Classify -->|chitchat| Chitchat
    Classify -->|curriculum| Condense
    Condense --> Retrieve
    Retrieve --> Fallback
    Fallback -->|Yes| Context
    Fallback -->|No| NoFilter --> Context
    Context --> Generate
    Generate --> Citations
    Citations --> CacheStore --> Response
```

Key components:

| Component | File | Purpose |
|-----------|------|---------|
| `RAGPipeline` | `pipelines.py` | Orchestrates the full pipeline with caching and observability |
| `Retriever` | `retriever.py` | Dense semantic search with grade filtering and 2-level fallback |
| `LLMGenerator` | `generator.py` | Structured JSON response generation with citation validation |
| `QueryClassifier` | `query_classifier.py` | Regex-based classifier: routes greetings/chitchat away from RAG |
| `Reranker` | `reranker.py` | Cross-encoder relevance scoring (**implemented, not active**) |
| Prompts | `prompts.py` | Student/teacher prompt templates with few-shot examples |
| Schemas | `schemas.py` | `GroundedResponse` Pydantic model for structured LLM output |

See [RETRIEVAL.md](RETRIEVAL.md) for design decisions and limitations.

### 3. Knowledge Layer (`modules/knowledge/`)

Manages embeddings and vector/sparse indices.

| Component | File | Status |
|-----------|------|--------|
| Embeddings | `embeddings.py` | **Active** — `all-MiniLM-L6-v2` (384d, local) or `text-embedding-3-small` (OpenAI) |
| Qdrant Store | `stores/qdrant.py` | **Active** — collection `somaai_documents`, cosine distance |
| BM25 Index | `bm25_index.py` | **Implemented, not integrated** — persistent index with deferred rebuild, but never called from `Retriever` |

### 4. API Layer (`api/v1/`)

FastAPI with Pydantic contracts. Active endpoints:

| Endpoint Group | Prefix | Key Routes |
|---------------|--------|------------|
| Chat | `/chat` | `POST /ask` (201), `GET /messages/{id}`, `GET /messages/{id}/citations` |
| Ingest | `/ingest` | `POST /` (upload + background job), `GET /jobs/{id}` |
| Quiz | `/quiz` | Quiz generation and download |
| Meta | `/meta` | Grades, subjects, topics (in-process TTL cache) |
| Teacher | `/teacher` | Profile management |
| Feedback | `/feedback` | Response ratings |
| Actors | `/actors` | Anonymous user management |
| Docs | `/docs` | Document viewing |
| Chunked Upload | `/chunked-upload` | Large file support |

> **Note**: The `/retrieval` endpoint exists in code but is **commented out** in the router.

### 5. Background Jobs (`jobs/`)

- **Queue**: Redis db/1 via ARQ
- **Worker**: Standalone process (`python -m somaai.jobs.worker`)
- **State**: PostgreSQL tracks job status (pending → running → completed → failed)
- Used for: document ingestion, quiz generation

### 6. Providers (`providers/`)

Adapter layer for swappable backends:

| Provider | File | Options | Status |
|----------|------|---------|--------|
| LLM | `llm.py` | `mock`, `groq`, `openai`, `huggingface` | **Groq**: fully implemented (uses JSON mode). **Mock**: works but blocked outside tests by `factory.py`. **OpenAI/HuggingFace**: `NotImplementedError` stubs. |
| Storage | `storage.py`, `storage_local.py` | `local` (filesystem) or `gdrive` | **Local**: implemented. **GDrive**: planned, not implemented. |

> **Important**: The `factory.py` guard raises `RuntimeError` if `LLM_BACKEND=mock` is used outside tests (requires `TESTING=1` env var). For local dev without API keys, set `TESTING=1` alongside `LLM_BACKEND=mock`.

---

## Data Storage Strategy

| Store | Technology | Purpose | Config |
|-------|------------|---------|--------|
| **Vector Store** | Qdrant | 384-dimensional embeddings + metadata. Cosine similarity search. | `QDRANT_URL`, `QDRANT_COLLECTION_NAME` |
| **Relational DB** | PostgreSQL 16 | Users, chat history, document metadata, job state, citations (3-way join: Message → Chunk → Document). | `DATABASE_URL` |
| **Cache** | Redis 7 | db/0: sessions & rate limits. db/1: ARQ job queue. db/2: response cache (24h TTL, strips citations before caching) + embedding cache (1h TTL). | `REDIS_URL`, `REDIS_JOBS_URL`, `REDIS_CACHE_URL` |
| **File Storage** | Local / S3 | Raw uploaded PDFs. Max 100MB per file. | `STORAGE_BACKEND`, `STORAGE_LOCAL_PATH` |

---

## Request Lifecycle

### Chat Request (`POST /api/v1/chat/ask`)

```mermaid
sequenceDiagram
    participant C as Client
    participant F as FastAPI
    participant CS as ChatService
    participant P as RAGPipeline
    participant R as Retriever
    participant Q as Qdrant
    participant L as LLMGenerator
    participant DB as PostgreSQL
    participant RC as Redis Cache

    C->>F: POST /chat/ask (201)
    F->>F: Sanitize input, 30s timeout
    F->>CS: ask(data, actor_id)
    CS->>CS: Resolve preferences (student/teacher)
    CS->>CS: Load history (last 6 turns)
    CS->>P: run(query, grade, subject, ...)
    P->>RC: Check response cache
    alt Cache hit
        RC-->>P: Cached response
    else Cache miss
        P->>P: Sanitize query
        P->>P: Classify (chitchat vs curriculum)
        P->>P: Condense with history (if exists)
        P->>R: retrieve_for_context()
        R->>Q: Search with grade filter
        alt < 3 results
            R->>Q: Retry without filters
        end
        R-->>P: docs + context string
        P->>L: generate(query, context, role)
        L-->>P: GroundedResponse JSON
        P->>P: Validate citations
        P->>RC: Cache response (if confidence ≥ 0.7)
    end
    P-->>CS: response dict
    CS->>DB: Save Message + Citations
    CS-->>F: ChatResponse
    F-->>C: 201 Created
```

### Ingestion Request (`POST /api/v1/ingest`)

```mermaid
sequenceDiagram
    participant C as Client
    participant F as FastAPI
    participant S as Storage
    participant DB as PostgreSQL
    participant ARQ as Redis/ARQ
    participant W as Worker
    participant O as Orchestrator
    participant Q as Qdrant

    C->>F: POST /ingest (multipart)
    F->>F: Validate file (≤100MB, allowed extensions)
    F->>S: Save file to local storage
    F->>DB: Create document record
    F->>ARQ: Enqueue ingestion job
    F-->>C: {job_id, doc_id, status: "pending"}
    
    ARQ->>W: Pick up job
    W->>O: run(doc_id, file_path, grade, subject)
    O->>O: 7 stages: dedup → extract → chunk → filter → enrich → store → sync
    O->>Q: Batch upsert vectors
    O->>DB: Update document record
```

---

## Observability

```mermaid
graph LR
    subgraph Metrics["Prometheus Metrics"]
        rag_requests["rag_requests_total<br/>(grade, subject, role, status)"]
        rag_latency["rag_latency_seconds<br/>(stage: retrieval, generation, total)"]
        rag_confidence["rag_confidence_score<br/>(histogram)"]
        rag_fallback["rag_fallback_level_total<br/>(level: 0, 1, 2)"]
        cache_ops["cache_operations_total<br/>(type, operation, status)"]
        feature_flags["rag_feature_flags<br/>(feature: hyde, reranking, ...)"]
    end
    
    subgraph Endpoints["Health Endpoints"]
        health["/health"]
        metrics["/metrics"]
    end
```

Prometheus metrics are optional — if `prometheus_client` is not installed, no-op stubs are used so the app still runs.

---

## Design Principles

1. **Modularity** — Each domain (ingest, RAG, auth, quiz) is isolated in its own module
2. **Async-First** — Heavy operations use async IO or are backgrounded via ARQ
3. **Type Safety** — Pydantic contracts for all API boundaries
4. **Contracts as Source of Truth** — `contracts/` defines the API surface; implementations conform to it
5. **Graceful Degradation** — Mock LLM, fallback retrieval, optional Prometheus, optional rate limiting
6. **Lazy Initialization** — All heavy objects (Qdrant store, LLM client, embedding model) are created on first use via `@property` patterns

---

## Known Limitations

| Limitation | Details |
|------------|---------|
| **BM25 not integrated** | `BM25Index` exists with full persistence and deferred rebuild, but is never called from `Retriever`. Config flags (`RAG_ENABLE_HYBRID_SEARCH`, `RAG_HYBRID_ALPHA`) exist in `.env.example` but are **not defined in `settings.py`** and not checked by any pipeline code. |
| **Reranker not active** | Cross-encoder reranker is implemented but `RAG_ENABLE_RERANKING` is not a defined setting — only accessed via `getattr` in monitoring. The pipeline never calls the reranker. |
| **HyDE not implemented** | `RAG_ENABLE_HYDE` appears in `.env.example` and monitoring but there is no HyDE implementation in the RAG pipeline code. |
| **Subject filter disabled** | `Retriever.retrieve()` hardcodes `subject=None` (line 110 of `retriever.py`). Only grade filtering is active. |
| **OpenAI/HuggingFace LLM stubs** | Both providers raise `NotImplementedError`. Only `groq` and `mock` backends are functional. |
| **No evaluation metrics** | No Recall@K, MRR, or ground-truth dataset exists. |
| **Mock LLM restricted** | `factory.py` blocks `LLM_BACKEND=mock` unless `TESTING=1` is set. |
| **Response cache strips citations** | `ResponseCache.set()` removes the `citations` key before caching, so cached responses have no citations. |
