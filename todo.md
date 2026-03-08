Phase 0: Foundation (Day 1)

Step 2: Docker Compose
Two compose files:

docker-compose.yml — dev (SQLite, no MinIO, no monitoring)
docker-compose.prod.yml — production (PostgreSQL, MinIO, Redis, Qdrant, Prometheus, Grafana)
Why? Because right now your single docker-compose.yml spins up 7 containers just to run in dev. That's slow and overkill. In dev, you should be able to run make dev and have the app start with just SQLite and a local Qdrant. No Redis, no MinIO, no Prometheus.

Step 3: Database Models
I'd create exactly 3 tables to start:

documents       — id, filename, title, grade, subject, status, content_hash, storage_path, page_count, chunk_count, uploaded_at, processed_at
conversations   — id, actor_id, grade, subject, title, created_at, updated_at
messages        — id, conversation_id, role, content, citations_json, created_at
Why no 

grades
 or 

subjects
 table? Because you told me — and you're 100% right — that only your team uploads documents. The valid grades/subjects are whatever you've uploaded. A Python dict handles display names. No seed scripts, no CRUD overhead.

Why no 

chunks
 table? This is controversial but hear me out. The chunks live in Qdrant (the vector store). Duplicating them in PostgreSQL means you have two sources of truth that can go out of sync. For MVP, Qdrant is the authority on chunks. PostgreSQL just tracks the document and its metadata.

Phase 1: Ingestion Pipeline (Day 2-4)
Step 4: Storage Abstraction
python
class StorageBackend(ABC):
    async def save(file, path) -> str
    async def get(path) -> bytes
    async def open(path) -> StorageStream
    async def exists(path) -> bool
    async def delete(path) -> bool
Two implementations:

LocalStorage — for dev (saves to ./uploads/)
MinioStorage — for prod
Why build the abstraction? Because the ingestion pipeline, the document viewer, and the chunked upload all need to read/write files. If they all call MinIO directly, switching backends becomes a nightmare.

What I'd keep from the current code: The 

StorageStream
 RAII wrapper is excellent. It guarantees 

close()
 and release_conn(). Keep it.

What I'd drop: 

save_deduplicated()
. It's a nice optimization, but for MVP, just save files with a UUID key. Dedup adds complexity and edge cases. You can add it when you have 10,000 documents, not 50.

Step 5: Text Extraction
PDF → pdfplumber (text + tables) → raw text
One extractor. One library. Don't over-engineer this. pdfplumber handles 95% of Rwandan curriculum PDFs. If a PDF is scanned (no extractable text), log a warning and skip it. Don't add OCR for MVP.

Step 6: Chunking
raw text → RecursiveCharacterTextSplitter → chunks with metadata
The current SemanticChunker in the codebase is good but has some issues (duplicate **base_metadata on line 158 of semantic_chunker.py which I noticed in the diff). For MVP, LangChain's RecursiveCharacterTextSplitter with chunk_size=1500, overlap=200 is battle-tested and sufficient.

Each chunk gets this metadata:

python
{
    "doc_id": "abc123",
    "grade": "S2",
    "subject": "biology",
    "title": "Biology Senior 2",
    "page_start": 15,        
    "chunk_index": 3,
    "content_hash": "sha256..."
}
Step 7: Embedding + Vector Storage
chunks → sentence-transformers (all-MiniLM-L6-v2) → Qdrant
Why this model? It's 80MB, loads in 2 seconds, embeds in milliseconds, and has 384 dimensions. For a curriculum chatbot, it's more than enough. You don't need OpenAI embeddings for MVP.

Step 8: Ingestion Orchestrator
Upload → Extract → Chunk → Enrich Metadata → Embed → Store in Qdrant → Update DB status
The current pipeline has 7 stages. I'd simplify to 5:

Extract — PDF → text
Chunk — text → chunks
Enrich — add grade/subject/title to each chunk's metadata
Embed + Store — embed chunks and upsert to Qdrant
Update DB — set status=completed, chunk_count=N
What I'd drop for MVP:

DeduplicationStage — your team uploads knowingly, duplicates are rare
QualityFilterStage — the 90% threshold safety is good engineering but adds complexity. For MVP, if chunks look bad, you re-upload the document.
Step 9: The Ingest API
Just one endpoint:

POST /api/v1/ingest
  - file: UploadFile
  - grade: str
  - subject: str  
  - title: str (optional)
What I'd drop for MVP:

POST /ingest/storage — nice to have, not essential
Chunked upload (/upload/*) — unless you're uploading 500MB textbooks, the standard endpoint with a 100MB limit is fine
Rate limiting — your team is the only uploader
Phase 2: RAG Pipeline (Day 5-7)
Step 10: Retriever
python
async def retrieve(query, grade, subject, top_k=5) -> list[dict]:
    # 1. Embed the query
    # 2. Search Qdrant with metadata filters (grade + subject)
    # 3. Return top_k results
Key decision: Always filter by grade AND subject. If a student is in S2 Biology, they should ONLY see S2 Biology content. This prevents the LLM from mixing up curricula.

What I'd skip for MVP:

HyDE (Hypothetical Document Embedding) — adds latency, marginal quality gain
Hybrid search (BM25 + dense) — requires maintaining a separate sparse index
Reranking — adds another model to load and 200-500ms latency
You can add all three later if retrieval quality isn't good enough. But start simple.

Step 11: LLM Generator
python
async def generate(query, context_docs, conversation_history) -> dict:
    # 1. Build prompt with system instructions + context + history
    # 2. Call Groq API (llama3)
    # 3. Parse response (answer, confidence, sufficiency)
    # 4. Return structured response
The prompt is the most important thing in your entire app. This is where 80% of answer quality comes from. I'd spend time on:

Clear system instruction: "You are a Rwandan curriculum tutor..."
Explicit "if information is not in the context, say so" instruction
Few-shot examples of good answers
Dev mode: Use MockLLMProvider that returns canned responses. This lets you develop the full pipeline without burning API credits.

Step 12: Response Cache
query + grade + subject → SHA256 key → Redis cache (24h TTL)
If a student in S2 Biology asks "What is photosynthesis?" and another student asks the exact same question, serve the cached answer. This saves LLM API costs.

For dev: Skip Redis entirely. Use an in-memory dict with TTL.

Phase 3: Chat API (Day 8-10)
Step 13: Conversation Management
POST   /chat/conversations              — create
GET    /chat/conversations              — list (paginated)
GET    /chat/conversations/{id}         — get one
PATCH  /chat/conversations/{id}         — update title
DELETE /chat/conversations/{id}         — delete
Step 14: Ask Endpoint
POST /chat/conversations/{id}/ask
  - question: str
  - user_role: "student" | "teacher"
Flow:

sanitize input → load conversation history → retrieve relevant docs → 
generate LLM response → save user message + AI message to DB → 
return response with citations
The current code does this well. The 30s timeout, rollback on error, and structured logging are all good patterns.

Step 15: Message History
GET /chat/conversations/{id}/messages?cursor=xxx&limit=50
Cursor-based pagination. This is already implemented well in the current code.

Phase 4: Supporting APIs (Day 11-12)
Step 16: Meta API (Your Dynamic Approach)
GET /meta/grades     → SELECT DISTINCT grade FROM documents  
GET /meta/subjects   → SELECT DISTINCT subject FROM documents
Two read-only endpoints. Display names from a Python dict. No CRUD. No tables. No seed scripts.

Step 17: Document Viewer
GET /docs/{id}       → metadata (grade, subject, status, chunk_count)
GET /docs/{id}/view  → stream the PDF from storage
Fix the existence check before streaming. This is the one critical bug I identified.

Step 18: Feedback
POST /feedback       → save thumbs up/down for a message
GET  /feedback/{id}  → check if feedback exists
Simple. Keep as-is.

Step 19: Health Check
GET /health → ping PostgreSQL + Qdrant, return 200 or 503
Keep as-is. This is well implemented.

Phase 5: Production Hardening (Day 13-15)
Step 20: Monitoring (only for prod)
Prometheus for metrics
Grafana for dashboards
Alert rules for: service down, high latency, high error rate
Don't load any of this in dev. Gate it behind SOMAAI_ENABLE_METRICS=true.

Step 21: Logging
Request ID on every request (already implemented)
Structured JSON logging for production
Human-readable logging for dev
Step 22: Security
SOMAAI_REQUIRE_API_KEY=true in production
Rate limiting on chat endpoint
Input sanitization on all user input (already implemented)
SecretStr for all API keys (already implemented)
The Order Matters — Here's Why
1. Settings        → everything imports this
2. DB Models       → storage depends on this  
3. Storage         → ingestion depends on this
4. Ingestion       → RAG depends on having documents
5. Retriever       → chat depends on retrieval
6. LLM Generator   → chat depends on generation
7. Chat API        → the actual user-facing product
8. Meta/Docs/Feedback → supporting features
9. Monitoring      → production polish
Each layer depends on the one above it. If you try to build the chat before the ingestion works, you have nothing to chat about. If you build ingestion before storage, you don't know where files go.

What I'd Intentionally Leave Out of MVP
Feature	Why Skip It
Chunked upload	Your docs are <50MB
/ingest/storage endpoint	Nice to have, not essential
Grade/Subject CRUD tables	Your team controls uploads
Streaming chat (/ask/stream)	Standard request-response is fine for v1
HyDE / Reranking / Hybrid Search	Add when quality isn't good enough
Quiz generation	Separate feature, not core RAG
Deduplication stage	Your team won't upload duplicates
Quality filter stage	Re-upload if something looks bad
The goal of MVP is: upload a PDF, ask a question, get a good answer with citations. Everything else is polish.