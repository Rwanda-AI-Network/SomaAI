# Teacher Chat Request Flow Documentation

**Author**: CTO Technical Review  
**Date**: March 6, 2026  
**System**: SomaAI RAG Educational Platform (FastAPI)

---

## Executive Summary

This document provides a comprehensive technical analysis of how teacher chat requests are created, processed, and responded to in the SomaAI RAG system. The architecture supports role-based pedagogical enhancements (analogies, real-world context) with teacher profile defaults and per-request overrides.

---

## Architecture Overview

```mermaid
graph TB
    Teacher["Teacher Client"] -->|1. Create Conversation| API["FastAPI Gateway"]
    Teacher -->|2. Ask Question| API
    API -->|Validate & Route| ChatEndpoint["Chat Endpoint"]
    ChatEndpoint -->|Resolve Preferences| ChatService["Chat Service"]
    ChatService -->|Load Profile| TeacherProfile["Teacher Profile DB"]
    ChatService -->|Build History| ContextBuilder["Context Builder"]
    ChatService -->|Execute RAG| RAGPipeline["RAG Pipeline"]
    RAGPipeline -->|Retrieve| Qdrant["Qdrant Vector Store"]
    RAGPipeline -->|Generate| LLM["Groq LLM (Llama 3.2)"]
    ChatService -->|Save| PostgreSQL["PostgreSQL"]
    ChatService -->|Return| Teacher
```

---

## Request Flow: Step-by-Step

### Phase 1: Conversation Creation

**Endpoint**: `POST /api/v1/chat/conversations`


**Request Schema** (`CreateConversationRequest`):
```json
{
  "grade": "S1",
  "subject": "mathematics",
  "title": "Algebra Questions"
}
```

**Response Schema** (`ConversationResponse`):
```json
{
  "id": "conv_abc123xyz",
  "title": "Algebra Questions",
  "grade": "S1",
  "subject": "mathematics",
  "message_count": 0,
  "created_at": "2026-03-06T10:30:00Z",
  "updated_at": "2026-03-06T10:30:00Z"
}
```

**Key Points**:
- Grade and subject are locked at conversation creation (source of truth)
- Title is optional; auto-generated from first question if omitted
- Conversation ID is used for all subsequent chat requests
- Rate limited: 60 requests/minute (configurable via `RATE_LIMIT_CREATE_CONVERSATION`)

---

### Phase 2: Teacher Chat Request

**Endpoint**: `POST /api/v1/chat/conversations/{conversation_id}/ask`

**Request Schema** (`ChatRequest`):
```json
{
  "question": "How do I explain quadratic equations to students who struggle with algebra?",
  "user_role": "teacher",
  "preferences": {
    "enabled_enhancements": ["analogy", "real_world"]
  }
}
```

**Field Specifications**:

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `question` | string | Yes | 1-2000 chars, non-whitespace | Teacher's question |
| `user_role` | enum | No | `student` or `teacher` | Defaults to `student` |
| `preferences` | object | No | See below | Pedagogical preferences |


**Preferences Object** (`Preferences`):
```json
{
  "enabled_enhancements": ["analogy", "real_world"]
}
```

- `enabled_enhancements`: `null` | `[]` | `["analogy"]` | `["real_world"]` | `["analogy", "real_world"]`
  - `null` = Use server defaults (teacher profile or role-based)
  - `[]` = Disable all enhancements
  - Explicit array = Enable only specified enhancements

**Enhancement Types**:
- `analogy`: Generate analogies to explain concepts
- `real_world`: Provide real-world applications and context

---

### Phase 3: Request Processing Pipeline

#### 3.1 Authentication & Validation
```python
# File: src/somaai/api/v1/endpoints/chat.py:ask_question()

1. Extract actor_id from session middleware (X-API-Key or session token)
2. Verify conversation ownership (404 if not owned by actor)
3. Sanitize question input (strip XSS, SQL injection patterns)
4. Apply rate limiting (default: 60/min per actor)
5. Set 30-second timeout for entire request
```

#### 3.2 Preference Resolution
```python
# File: src/somaai/modules/chat/service.py:_resolve_enhancements()

Priority cascade:
1. Explicit request preferences (if provided)
2. Teacher profile defaults (if user_role=teacher and profile exists)
3. Role-based defaults (all enhancements enabled)

Example:
- Request: preferences.enabled_enhancements = null
- User: teacher with profile {analogy_enabled: true, realworld_enabled: false}
- Result: Only analogy enhancement enabled
```


#### 3.3 Context Building
```python
# File: src/somaai/modules/chat/context.py:ContextBuilder.build_history()

1. Load previous messages from conversation (ordered by created_at DESC)
2. Format as "Q: {question}\nA: {answer}\n\n"
3. Truncate to token limit (default: 2000 tokens for history)
4. Return formatted history string for RAG pipeline
```

#### 3.4 RAG Pipeline Execution
```python
# File: src/somaai/modules/rag/pipelines.py:RAGPipeline.run()

Stage 1: Cache Check
- Query response cache (Redis db/2, 24h TTL)
- Cache key: hash(query + grade + subject)
- If hit: return cached response (citations stripped)

Stage 2: Query Classification
- Regex-based classifier checks for greetings/chitchat
- If chitchat: return direct response, skip RAG
- If curriculum: proceed to retrieval

Stage 3: Query Condensation (if history exists)
- Use LLM to rewrite follow-up questions as standalone queries
- Prompt: CONDENSE_QUESTION_PROMPT with history context
- Fallback: use original query if rewriting fails

Stage 4: Retrieval
- Dense semantic search in Qdrant (384d embeddings)
- Filters: grade AND subject (mandatory)
- Fallback strategy:
  - Level 0: grade + subject filters
  - Level 1: Remove filters if < 3 results
- Top-K: 5 chunks by cosine similarity
- Context truncation: 4000 tokens max

Stage 5: Generation
- LLM: Groq Llama 3.2 (JSON mode)
- Prompt template: Teacher-specific or student-specific
- Structured output: GroundedResponse schema
- Includes: answer, sufficiency, confidence, citations, analogy, realworld_context

Stage 6: Citation Validation
- Cross-reference LLM's cited page numbers with retrieved chunks
- Build CitationResponse objects with doc metadata
- Create chunks_map for frontend rendering
```


#### 3.5 Persistence
```python
# File: src/somaai/modules/chat/service.py:ask()

1. Generate message_id (UUID-like)
2. Save Message record to PostgreSQL:
   - conversation_id, actor_id, user_role
   - question, answer, sufficiency, confidence
   - grade, subject (snapshot from conversation)
   - analogy, realworld_context (if generated)
   - created_at timestamp

3. Save MessageCitation records (3-way join):
   - message_id → chunk_id → document_id
   - relevance_score, snippet (preview text)

4. Auto-title conversation (if first message):
   - Use first 80 chars of question as title

5. Touch conversation.updated_at timestamp
```

---

## Response Structure

### Complete Response Schema (`ChatResponse`)

```json
{
  "message_id": "msg_xyz789abc",
  "conversation_id": "conv_abc123xyz",
  "answer": "Quadratic equations can be challenging for students who struggle with algebra. Here's a structured approach:\n\n1. Start with visual representations using parabola graphs\n2. Connect to the factoring skills they already know\n3. Use the quadratic formula as a reliable fallback method\n\nThe curriculum recommends beginning with simple factorable equations before introducing the formula.",
  "sufficiency": "sufficient",
  "confidence": 0.87,
  "citations": [
    {
      "doc_id": "doc_math_s1_001",
      "doc_title": "Mathematics S1 Teacher Guide",
      "section_title": "Algebra Unit 3: Quadratic Equations",
      "page_start": 45,
      "page_end": 47,
      "chunk_preview": "Teaching quadratic equations requires scaffolding from linear equations. Begin with visual representations...",
      "view_url": "/api/v1/docs/doc_math_s1_001/view?page=45",
      "relevance_score": 0.92
    }
  ],
  "enhancements": {
    "analogy": "Think of quadratic equations like throwing a ball: the path it takes (parabola) can be described by the equation. The vertex is the highest point, and the roots are where it hits the ground.",
    "real_world_context": "Quadratic equations are used in physics to calculate projectile motion, in business to optimize profit functions, and in engineering to design parabolic structures like satellite dishes."
  },
  "created_at": "2026-03-06T10:35:42Z"
}
```


### Response Field Specifications

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| `message_id` | string | Unique message identifier | UUID format |
| `conversation_id` | string | Parent conversation ID | UUID format |
| `answer` | string | AI-generated response | 1-10000 chars |
| `sufficiency` | enum | Context adequacy | `sufficient`, `insufficient`, `partial` |
| `confidence` | float | Model confidence score | 0.0-1.0, rounded to 4 decimals |
| `citations` | array | Source references | 0-5 citations (top-K) |
| `enhancements` | object | Pedagogical enrichments | `null` if not requested/generated |
| `created_at` | datetime | Response timestamp | ISO 8601 UTC |

**Sufficiency Levels**:
- `sufficient`: Retrieved context fully answers the question
- `partial`: Context provides some information but incomplete
- `insufficient`: No relevant context found in curriculum

**Confidence Scoring**:
- 0.9-1.0: High confidence, well-grounded in curriculum
- 0.7-0.89: Moderate confidence, some inference required
- 0.5-0.69: Low confidence, limited context
- 0.0-0.49: Very low confidence, fallback response

---

## Teacher-Specific Features

### 1. Teacher Profile Management

**Endpoint**: `GET /api/v1/teacher/profile`

**Response**:
```json
{
  "profile_id": "prof_teacher123",
  "teacher_id": "actor_teacher123",
  "classes_taught": [
    {"grade": "S1", "subject": "mathematics"},
    {"grade": "S2", "subject": "mathematics"}
  ],
  "analogy_enabled": true,
  "realworld_enabled": true,
  "created_at": "2026-01-15T08:00:00Z",
  "updated_at": "2026-03-01T14:30:00Z"
}
```

**Endpoint**: `POST /api/v1/teacher/profile`

**Request**:
```json
{
  "classes_taught": [
    {"grade": "S1", "subject": "mathematics"},
    {"grade": "S2", "subject": "mathematics"}
  ],
  "analogy_enabled": true,
  "realworld_enabled": false
}
```


### 2. Teacher vs Student Prompt Differences

**Teacher Prompt Template** (from `src/somaai/modules/rag/prompts.py`):
- Focuses on pedagogical strategies and teaching methods
- Includes curriculum alignment guidance
- Provides scaffolding suggestions for different student levels
- Emphasizes classroom management and differentiation

**Student Prompt Template**:
- Direct explanations with step-by-step breakdowns
- Age-appropriate language and examples
- Encourages active learning and practice
- Focuses on understanding concepts, not just memorization

---

## Error Handling & Edge Cases

### Timeout Handling
```python
# 30-second timeout for entire request
try:
    async with asyncio.timeout(30):
        response = await chat_service.ask(data, conversation)
except asyncio.TimeoutError:
    return HTTPException(504, "Request timeout — try a simpler question")
```

### Insufficient Context Response
```json
{
  "message_id": "msg_fallback123",
  "conversation_id": "conv_abc123xyz",
  "answer": "I couldn't find relevant curriculum content for your question about mathematics at the S1 level. Please try:\n1. Rephrasing your question\n2. Checking if this topic is covered in the curriculum\n3. Asking a more specific question",
  "sufficiency": "insufficient",
  "confidence": 0.0,
  "citations": [],
  "enhancements": null,
  "created_at": "2026-03-06T10:35:42Z"
}
```

### Graceful Degradation
- RAG pipeline failure → Fallback response with error message
- LLM unavailable → Mock LLM (if `TESTING=1` and `LLM_BACKEND=mock`)
- Cache unavailable → Skip caching, continue processing
- Prometheus unavailable → No-op metrics, continue processing


---

## Performance & Observability

### Caching Strategy

**Response Cache** (Redis db/2):
- Key: `hash(query + grade + subject)`
- TTL: 24 hours
- Strips citations before caching (citations regenerated on cache hit)
- Only caches responses with confidence ≥ 0.7

**Embedding Cache** (Redis db/2):
- Key: `hash(text)`
- TTL: 1 hour
- Caches embedding vectors to reduce model inference

### Prometheus Metrics

```python
# Tracked metrics (src/somaai/monitoring.py)
rag_requests_total{grade, subject, role, status}
rag_latency_seconds{stage}  # retrieval, generation, total
rag_confidence_score (histogram)
rag_fallback_level_total{level}  # 0, 1, 2
cache_operations_total{type, operation, status}
```

### Logging

**Structured Logs** (JSON format):
```json
{
  "timestamp": "2026-03-06T10:35:42Z",
  "level": "INFO",
  "logger": "somaai.modules.chat.service",
  "message": "Chat request processed",
  "conversation_id": "conv_abc123xyz",
  "actor_id": "actor_teacher123",
  "user_role": "teacher",
  "grade": "S1",
  "subject": "mathematics",
  "docs_retrieved": 5,
  "confidence": 0.87,
  "latency_ms": 1247
}
```

---

## Database Schema

### Conversation Table
```sql
CREATE TABLE conversations (
    id VARCHAR PRIMARY KEY,
    actor_id VARCHAR NOT NULL,
    grade VARCHAR NOT NULL,
    subject VARCHAR NOT NULL,
    title VARCHAR(255),
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    INDEX idx_actor_updated (actor_id, updated_at DESC)
);
```


### Message Table
```sql
CREATE TABLE messages (
    id VARCHAR PRIMARY KEY,
    conversation_id VARCHAR NOT NULL REFERENCES conversations(id),
    actor_id VARCHAR NOT NULL,
    user_role VARCHAR NOT NULL,  -- 'student' or 'teacher'
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    sufficiency VARCHAR NOT NULL,
    confidence DECIMAL(5,4),
    grade VARCHAR NOT NULL,
    subject VARCHAR NOT NULL,
    analogy TEXT,
    realworld_context TEXT,
    created_at TIMESTAMP NOT NULL,
    INDEX idx_conversation_created (conversation_id, created_at DESC)
);
```

### MessageCitation Table
```sql
CREATE TABLE message_citations (
    id VARCHAR PRIMARY KEY,
    message_id VARCHAR NOT NULL REFERENCES messages(id),
    chunk_id VARCHAR NOT NULL REFERENCES chunks(id),
    relevance_score DECIMAL(5,4),
    snippet TEXT,
    created_at TIMESTAMP NOT NULL,
    INDEX idx_message (message_id)
);
```

### TeacherProfile Table
```sql
CREATE TABLE teacher_profiles (
    id VARCHAR PRIMARY KEY,
    teacher_id VARCHAR NOT NULL UNIQUE,
    analogy_enabled BOOLEAN DEFAULT TRUE,
    realworld_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE teacher_classes (
    id VARCHAR PRIMARY KEY,
    profile_id VARCHAR NOT NULL REFERENCES teacher_profiles(id),
    grade VARCHAR NOT NULL,
    subject VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL
);
```

---

## Security Considerations

### Input Sanitization
```python
# File: src/somaai/utils/security.py:sanitize_query()

1. Strip leading/trailing whitespace
2. Remove SQL injection patterns ('; DROP TABLE, etc.)
3. Remove XSS patterns (<script>, javascript:, etc.)
4. Limit length to 2000 characters
5. Reject empty or whitespace-only queries
```


### Rate Limiting
- Default: 60 requests/minute per actor
- Configurable via `RATE_LIMIT_ASK` environment variable
- Graceful degradation if `slowapi` not installed
- Response headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`

### Authentication
- Session-based via `SessionMiddleware`
- API key via `X-API-Key` header
- Actor ID resolution: session token → actor_id
- Conversation ownership validation (404 to prevent enumeration)

---

## Complete Request/Response Examples

### Example 1: Teacher Asking About Teaching Strategy

**Request**:
```http
POST /api/v1/chat/conversations/conv_abc123/ask HTTP/1.1
Host: api.somaai.rw
Content-Type: application/json
X-API-Key: teacher_key_xyz789

{
  "question": "What are effective strategies for teaching photosynthesis to S2 students?",
  "user_role": "teacher",
  "preferences": {
    "enabled_enhancements": ["analogy", "real_world"]
  }
}
```

**Response**:
```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "message_id": "msg_photo123",
  "conversation_id": "conv_abc123",
  "answer": "Effective strategies for teaching photosynthesis to S2 students include:\n\n1. **Visual Models**: Use diagrams showing chloroplasts and the light-dependent/independent reactions\n2. **Hands-on Experiments**: Conduct leaf disk assays to demonstrate oxygen production\n3. **Scaffolding**: Start with the overall equation (6CO₂ + 6H₂O → C₆H₁₂O₆ + 6O₂) before diving into detailed mechanisms\n4. **Differentiation**: Provide simplified versions for struggling students and extension activities for advanced learners\n\nThe curriculum recommends spending 3-4 lessons on this topic with practical demonstrations.",
  "sufficiency": "sufficient",
  "confidence": 0.91,
  "citations": [
    {
      "doc_id": "doc_bio_s2_003",
      "doc_title": "Biology S2 Teacher Guide - Unit 4",
      "section_title": "Photosynthesis Teaching Strategies",
      "page_start": 78,
      "page_end": 82,
      "chunk_preview": "Teaching photosynthesis requires a multi-modal approach. Begin with the overall process before introducing cellular details...",
      "view_url": "/api/v1/docs/doc_bio_s2_003/view?page=78",
      "relevance_score": 0.94
    }
  ],
  "enhancements": {
    "analogy": "Photosynthesis is like a solar-powered factory: the chloroplasts are the factory buildings, sunlight is the electricity, water and CO₂ are the raw materials, and glucose is the manufactured product. The oxygen is the waste product released into the air.",
    "real_world_context": "Understanding photosynthesis is crucial for addressing climate change, as plants absorb CO₂ from the atmosphere. It's also the foundation of agriculture and food production, making it relevant to Rwanda's economy and food security goals."
  },
  "created_at": "2026-03-06T10:45:23Z"
}
```


### Example 2: Teacher Disabling Enhancements

**Request**:
```http
POST /api/v1/chat/conversations/conv_xyz789/ask HTTP/1.1
Host: api.somaai.rw
Content-Type: application/json
X-API-Key: teacher_key_xyz789

{
  "question": "What is the curriculum sequence for teaching fractions in P4?",
  "user_role": "teacher",
  "preferences": {
    "enabled_enhancements": []
  }
}
```

**Response**:
```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "message_id": "msg_frac456",
  "conversation_id": "conv_xyz789",
  "answer": "The P4 mathematics curriculum teaches fractions in the following sequence:\n\n1. **Term 1**: Introduction to fractions (halves, quarters, thirds)\n2. **Term 2**: Equivalent fractions and simplification\n3. **Term 3**: Adding and subtracting fractions with like denominators\n\nEach unit includes 5-6 lessons with formative assessments. The curriculum emphasizes visual representations (fraction bars, circles) before abstract notation.",
  "sufficiency": "sufficient",
  "confidence": 0.88,
  "citations": [
    {
      "doc_id": "doc_math_p4_001",
      "doc_title": "Mathematics P4 Curriculum Guide",
      "section_title": "Fractions Unit Overview",
      "page_start": 34,
      "page_end": 36,
      "chunk_preview": "The fractions unit is taught across three terms with progressive complexity. Begin with concrete manipulatives...",
      "view_url": "/api/v1/docs/doc_math_p4_001/view?page=34",
      "relevance_score": 0.89
    }
  ],
  "enhancements": null,
  "created_at": "2026-03-06T11:02:15Z"
}
```

---

## Configuration Reference

### Environment Variables

```bash
# LLM Configuration
LLM_BACKEND=groq                    # groq, openai, huggingface, mock
GROQ_API_KEY=gsk_...               # Required for Groq
GROQ_MODEL=llama-3.2-90b-text-preview

# Rate Limiting
RATE_LIMIT_ASK=60/minute           # Chat requests per actor
RATE_LIMIT_CREATE_CONVERSATION=60/minute

# RAG Pipeline
RAG_TOP_K=5                        # Number of chunks to retrieve
RAG_CONTEXT_MAX_TOKENS=4000        # Max context length for LLM
RAG_HISTORY_MAX_TOKENS=2000        # Max history length

# Caching
REDIS_CACHE_URL=redis://localhost:6379/2
RESPONSE_CACHE_TTL=86400           # 24 hours
EMBEDDING_CACHE_TTL=3600           # 1 hour

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/somaai

# Vector Store
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION_NAME=somaai_documents

# Observability
DEBUG=false                        # Enable pipeline debugging
PROMETHEUS_ENABLED=true            # Enable metrics collection
```


---

## API Client Implementation Examples

### Python Client

```python
import httpx
from typing import Optional

class SomaAIClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.headers = {"X-API-Key": api_key}
    
    async def create_conversation(
        self, 
        grade: str, 
        subject: str, 
        title: Optional[str] = None
    ) -> dict:
        """Create a new conversation."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/chat/conversations",
                json={"grade": grade, "subject": subject, "title": title},
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
    
    async def ask_question(
        self,
        conversation_id: str,
        question: str,
        user_role: str = "teacher",
        enable_analogy: bool = True,
        enable_realworld: bool = True
    ) -> dict:
        """Ask a question in a conversation."""
        enhancements = []
        if enable_analogy:
            enhancements.append("analogy")
        if enable_realworld:
            enhancements.append("real_world")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/chat/conversations/{conversation_id}/ask",
                json={
                    "question": question,
                    "user_role": user_role,
                    "preferences": {"enabled_enhancements": enhancements}
                },
                headers=self.headers,
                timeout=35.0  # Slightly longer than server timeout
            )
            response.raise_for_status()
            return response.json()

# Usage
client = SomaAIClient("https://api.somaai.rw", "teacher_key_xyz")
conversation = await client.create_conversation("S2", "biology")
response = await client.ask_question(
    conversation["id"],
    "How do I teach photosynthesis effectively?",
    user_role="teacher"
)
print(response["answer"])
```


### JavaScript/TypeScript Client

```typescript
interface ChatRequest {
  question: string;
  user_role: 'student' | 'teacher';
  preferences?: {
    enabled_enhancements?: ('analogy' | 'real_world')[] | null;
  };
}

interface ChatResponse {
  message_id: string;
  conversation_id: string;
  answer: string;
  sufficiency: 'sufficient' | 'insufficient' | 'partial';
  confidence: number;
  citations: Citation[];
  enhancements?: {
    analogy?: string;
    real_world_context?: string;
  };
  created_at: string;
}

class SomaAIClient {
  constructor(
    private baseUrl: string,
    private apiKey: string
  ) {}

  async createConversation(
    grade: string,
    subject: string,
    title?: string
  ): Promise<any> {
    const response = await fetch(`${this.baseUrl}/api/v1/chat/conversations`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': this.apiKey,
      },
      body: JSON.stringify({ grade, subject, title }),
    });
    
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async askQuestion(
    conversationId: string,
    request: ChatRequest
  ): Promise<ChatResponse> {
    const response = await fetch(
      `${this.baseUrl}/api/v1/chat/conversations/${conversationId}/ask`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': this.apiKey,
        },
        body: JSON.stringify(request),
      }
    );
    
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }
}

// Usage
const client = new SomaAIClient('https://api.somaai.rw', 'teacher_key_xyz');
const conversation = await client.createConversation('S2', 'biology');
const response = await client.askQuestion(conversation.id, {
  question: 'How do I teach photosynthesis effectively?',
  user_role: 'teacher',
  preferences: {
    enabled_enhancements: ['analogy', 'real_world']
  }
});
console.log(response.answer);
```

---

## Testing & Quality Assurance

### Unit Tests
```python
# tests/modules/chat/test_service.py

async def test_teacher_chat_with_enhancements():
    """Test teacher chat request with enhancements enabled."""
    service = ChatService(db, rag_pipeline, actor_id="teacher_123")
    
    request = ChatRequest(
        question="How do I teach quadratic equations?",
        user_role=UserRole.TEACHER,
        preferences=Preferences(
            enabled_enhancements=[Enhancement.ANALOGY, Enhancement.REAL_WORLD]
        )
    )
    
    response = await service.ask(request, conversation)
    
    assert response.enhancements is not None
    assert response.enhancements.analogy is not None
    assert response.enhancements.real_world_context is not None
    assert response.confidence >= 0.7
```


### Integration Tests
```python
# tests/api/test_chat_endpoints.py

async def test_teacher_chat_flow(client: AsyncClient):
    """Test complete teacher chat flow."""
    # 1. Create conversation
    conv_response = await client.post(
        "/api/v1/chat/conversations",
        json={"grade": "S1", "subject": "mathematics"},
        headers={"X-API-Key": "teacher_key"}
    )
    assert conv_response.status_code == 201
    conversation_id = conv_response.json()["id"]
    
    # 2. Ask question
    chat_response = await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/ask",
        json={
            "question": "How do I teach algebra to struggling students?",
            "user_role": "teacher",
            "preferences": {"enabled_enhancements": ["analogy"]}
        },
        headers={"X-API-Key": "teacher_key"}
    )
    assert chat_response.status_code == 201
    data = chat_response.json()
    assert data["answer"]
    assert data["enhancements"]["analogy"]
    assert data["enhancements"]["real_world_context"] is None
```

---

## Known Limitations & Future Enhancements

### Current Limitations

1. **No Streaming Support**: The `/ask/stream` endpoint returns 501 Not Implemented
2. **Citation Stripping in Cache**: Cached responses have citations removed, requiring regeneration
3. **BM25 Not Integrated**: Hybrid search (dense + sparse) is implemented but not active
4. **Reranker Not Active**: Cross-encoder reranking exists but is not called in the pipeline
5. **Teacher Profile Endpoints Stubbed**: GET/POST `/teacher/profile` return empty responses
6. **No Multi-Turn Context Compression**: Long conversations may exceed token limits

### Planned Enhancements

1. **Server-Sent Events (SSE)**: Streaming responses for real-time feedback
2. **Conversation Summarization**: Compress long histories to fit token limits
3. **Teacher Dashboard**: Analytics on student questions and curriculum coverage
4. **Collaborative Features**: Share conversations between teachers
5. **Feedback Loop**: Teacher ratings to improve RAG quality
6. **Multi-Modal Support**: Image uploads for diagrams and worksheets

---

## Troubleshooting Guide

### Common Issues

**Issue**: 504 Timeout Error
- **Cause**: RAG pipeline exceeds 30-second limit
- **Solution**: Simplify question, check Qdrant/LLM latency, increase timeout

**Issue**: Empty Citations Array
- **Cause**: No relevant documents found or confidence < 0.7
- **Solution**: Verify curriculum documents are ingested, check grade/subject filters

**Issue**: Enhancements Not Generated
- **Cause**: Preferences set to `[]` or LLM failed to generate
- **Solution**: Check preferences object, verify LLM is responding correctly

**Issue**: 404 Conversation Not Found
- **Cause**: Conversation doesn't exist or not owned by actor
- **Solution**: Verify conversation_id, check actor_id matches creator


---

## Appendix A: Complete Sequence Diagram

```mermaid
sequenceDiagram
    participant T as Teacher Client
    participant API as FastAPI Gateway
    participant Auth as SessionMiddleware
    participant Chat as ChatService
    participant Profile as TeacherProfile DB
    participant Context as ContextBuilder
    participant RAG as RAGPipeline
    participant Cache as Redis Cache
    participant Retriever as Retriever
    participant Qdrant as Qdrant
    participant LLM as Groq LLM
    participant DB as PostgreSQL

    T->>API: POST /conversations/{id}/ask
    API->>Auth: Resolve actor_id
    Auth-->>API: actor_id
    API->>Chat: ask(request, conversation)
    
    Chat->>Chat: Validate ownership
    Chat->>Profile: Load teacher profile
    Profile-->>Chat: Profile settings
    Chat->>Chat: Resolve enhancements
    
    Chat->>Context: build_history(conversation_id)
    Context->>DB: Load previous messages
    DB-->>Context: Message history
    Context-->>Chat: Formatted history
    
    Chat->>RAG: run(query, grade, subject, role, prefs, history)
    
    RAG->>Cache: Check response cache
    alt Cache Hit
        Cache-->>RAG: Cached response
    else Cache Miss
        RAG->>RAG: Sanitize & classify query
        RAG->>RAG: Condense query (if history)
        
        RAG->>Retriever: retrieve_for_context()
        Retriever->>Qdrant: Search (grade + subject filters)
        Qdrant-->>Retriever: Top-K chunks
        alt < 3 results
            Retriever->>Qdrant: Retry without filters
            Qdrant-->>Retriever: Fallback chunks
        end
        Retriever-->>RAG: Documents + context
        
        RAG->>LLM: generate(query, context, role, prefs)
        LLM-->>RAG: GroundedResponse JSON
        
        RAG->>RAG: Validate citations
        RAG->>Cache: Cache response
    end
    
    RAG-->>Chat: Response dict
    
    Chat->>DB: Save Message
    Chat->>DB: Save Citations
    Chat->>DB: Update conversation
    DB-->>Chat: Success
    
    Chat-->>API: ChatResponse
    API-->>T: 201 Created + JSON
```

---

## Appendix B: Data Flow Diagram

```mermaid
graph TD
    A[Teacher Question] --> B[Input Sanitization]
    B --> C{Query Classification}
    C -->|Chitchat| D[Direct Response]
    C -->|Curriculum| E[Load Teacher Profile]
    E --> F[Resolve Enhancements]
    F --> G[Build Conversation History]
    G --> H{History Exists?}
    H -->|Yes| I[Condense Query with LLM]
    H -->|No| J[Use Original Query]
    I --> K[Dense Retrieval]
    J --> K
    K --> L[Qdrant Vector Search]
    L --> M{≥ 3 Results?}
    M -->|Yes| N[Build Context]
    M -->|No| O[Retry Without Filters]
    O --> N
    N --> P[LLM Generation]
    P --> Q[Validate Citations]
    Q --> R[Save to PostgreSQL]
    R --> S[Return ChatResponse]
    D --> S
```

---

## Appendix C: Contract Definitions

### Enhancement Enum
```python
class Enhancement(str, Enum):
    ANALOGY = "analogy"
    REAL_WORLD = "real_world"
```

### UserRole Enum
```python
class UserRole(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"
```

### Sufficiency Enum
```python
class Sufficiency(str, Enum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    PARTIAL = "partial"
```

---

## Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-06 | CTO Review | Initial comprehensive documentation |

---

## References

- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture overview
- [FRONTEND_INTEGRATION.md](./FRONTEND_INTEGRATION.md) - Frontend integration guide
- [api.md](./api.md) - Complete API reference
- [RETRIEVAL.md](./RETRIEVAL.md) - Retrieval strategy details
- FastAPI Documentation: https://fastapi.tiangolo.com
- Pydantic Documentation: https://docs.pydantic.dev

---

**End of Document**
