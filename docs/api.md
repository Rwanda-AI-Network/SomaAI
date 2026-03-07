# SomaAI API Documentation

## Base URL
`/api/v1`

## Authentication & Rate Limiting
- **Auth:** `X-API-Key` header required for protected endpoints.
- **Rate Limit:** 60/min default. 10/min for Ingest. response headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`.

## Endpoints

### Health & Metrics
- `GET /health` - Health check (Redis, DB, VectorStore status)
- `GET /metrics` - Prometheus metrics (latency, counters)

### Chat & Conversations
- `POST /api/v1/chat/conversations` - Create a new conversation. Returns `ConversationResponse`.
- `GET /api/v1/chat/conversations` - List actor's conversations (most recent first).
- `POST /api/v1/chat/conversations/{id}/ask` - Ask a question within a conversation.
  - **Payload:** Requires `question`, `grade` (e.g., "S1"), and `subject` (defaults to `"general"`).
- `GET /api/v1/chat/messages/{id}` - Get full message details with citations and RAG metadata.
- `GET /api/v1/chat/messages/{id}/citations` - Get granular source citations for a specific message.

### Ingest
- `POST /ingest` - Ingest document (PDF/DOCX). Rate Limited: 10/min.
- `GET /ingest/jobs/{id}` - Get ingestion job status.
- *See [Upload & Ingestion Guide](./UPLOAD_AND_INGESTION.md) for streaming details.*

### Documents & Meta
- `GET /docs/{id}/view` - View processed document content
- `GET /meta/grades` - List available grades
- `GET /meta/subjects` - List available subjects

### Quiz & Teacher
- `POST /quiz/generate` - Generate a quiz from topics
- `GET /quiz/{id}` - Download generated quiz
- `GET /teacher/profile` - Get teacher settings

### Chunked Upload (Files > 50MB)
*Recommended for large student books to avoid timeouts.*
- `POST /upload/init` - Initialize upload session.
- `POST /upload/chunk/{id}/{idx}` - Upload file chunk.
- `POST /upload/complete/{id}` - Reassemble and start ingestion.
- `DELETE /upload/cancel/{id}` - Cancel upload session.
- *See [Upload & Ingestion Guide](./UPLOAD_AND_INGESTION.md) for mechanics.*

### Search
- `POST /retrieval/search` - Debug/Admin search of vector store

### Feedback


