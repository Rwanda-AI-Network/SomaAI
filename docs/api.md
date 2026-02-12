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

### Chat
- `POST /chat/ask` - Send a RAG-enhanced question (Student/Teacher)
- `GET /chat/messages/{id}` - Get full message details with citations
- `GET /chat/history` - Get conversation history

### Ingest
- `POST /ingest` - Ingest document (PDF/DOCX < 50MB) - Rate Limited: 10/min
- `GET /ingest/jobs/{id}` - Get ingestion job status

### Documents & Meta
- `GET /docs/{id}/view` - View processed document content
- `GET /meta/grades` - List available grades
- `GET /meta/subjects` - List available subjects

### Quiz & Teacher
- `POST /quiz/generate` - Generate a quiz from topics
- `GET /quiz/{id}` - Download generated quiz
- `GET /teacher/profile` - Get teacher settings

### Chunked Upload (Files > 50MB)
- `POST /upload/init` - Initialize upload session
- `POST /upload/chunk/{id}/{idx}` - Upload file chunk
- `POST /upload/complete/{id}` - Reassemble and start ingestion
- `DELETE /upload/cancel/{id}` - Cancel upload session

### Search
- `POST /retrieval/search` - Debug/Admin search of vector store

### Feedback
- `POST /feedback` - Submit helpfulness feedback on AI responses


