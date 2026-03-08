

Phase 1: Ingestion Pipeline (Day 2-4)

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



Step 17: Document Viewer
GET /docs/{id}       → metadata (grade, subject, status, chunk_count)
GET /docs/{id}/view  → stream the PDF from storage
Fix the existence check before streaming. This is the one critical bug I identified.


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