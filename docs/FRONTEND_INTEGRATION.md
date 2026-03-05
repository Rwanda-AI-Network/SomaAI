# SomaAI Chat API: Frontend Integration Guide (Production v1)

This document is the **Single Source of Truth** for frontend developers building user interfaces for SomaAI. It covers the complete lifecycle of chat sessions, pedagogical enhancements, feedback loops, and curriculum navigation.

---

## 📖 Table of Contents
1.  [API Standards & Base URL](#1-api-standards--base-url)
2.  [Curriculum Navigation (Metadata)](#2-curriculum-navigation-metadata)
3.  [Chat Session Lifecycle](#3-chat-session-lifecycle)
4.  [Interactions & RAG](#4-interactions--rag)
5.  [Thread History & Pagination](#5-thread-history--pagination)
6.  [Feedback & Quality Loops](#6-feedback--quality-loops)
7.  [Quiz Generation](#7-quiz-generation)
8.  [Document Uploads (Custom context)](#8-document-uploads-custom-context)
9.  [Error Handling & Rate Limits](#9-error-handling--rate-limits)
10. [UI/UX Recommendations](#10-uiux-recommendations)

---

## 1. API Standards & Base URL

- **Base URL**: `/api/v1`
- **Authentication**: Auth is managed via session cookies (`somaai_session`). Ensure your fetch/axios client includes `credentials: 'include'`.
- **Response Format**: All successful responses are JSON-wrapped.

---

## 2. Curriculum Navigation (Metadata)

Before starting a chat, the frontend usually needs to populate dropdowns for Grade and Subject.

### Get Grades
**Endpoint**: `GET /meta/grades`
**Description**: Fetches available Rwandan grade levels (P6, S1-S6).

**Example Response**:
```json
[
  { "id": "S1", "name": "Senior 1", "level": "secondary", "display_order": 1 },
  { "id": "S2", "name": "Senior 2", "level": "secondary", "display_order": 2 }
]
```

### Get Subjects
**Endpoint**: `GET /meta/subjects?grade=S1`
**Description**: Fetches subjects available for a specific grade.

**Example Response**:
```json
[
  { "id": "mathematics", "name": "Mathematics", "display_order": 1 },
  { "id": "biology", "name": "Biology", "display_order": 2 }
]
```

---

## 3. Chat Session Lifecycle

### Create Conversation
**Endpoint**: `POST /chat/conversations`
**Description**: Initializes a thread. `grade` and `subject` are mandatory anchors.

**Request Body**:
```json
{
  "grade": "S4",
  "subject": "biology",
  "title": "Photosynthesis Deep-Dive"
}
```

**Response Body (201 Created)**:
```json
{
  "id": "conv_9a2b1c",
  "title": "Photosynthesis Deep-Dive",
  "grade": "S4",
  "subject": "biology",
  "message_count": 0,
  "created_at": "2026-03-05T22:30:00Z",
  "updated_at": "2026-03-05T22:30:00Z"
}
```

---

## 4. Interactions & RAG

### Ask a Question
**Endpoint**: `POST /chat/conversations/{id}/ask`
**Description**: Sends a question to the RAG pipeline.

**Request Body**:
```json
{
  "question": "What are the stages of light-dependent reactions?",
  "user_role": "student",
  "preferences": {
    "enabled_enhancements": ["analogy", "real_world"]
  }
}
```

**Response Body (201 Created)**:
```json
{
  "message_id": "msg_f3e4d5",
  "conversation_id": "conv_9a2b1c",
  "answer": "The light-dependent reactions occur in four stages...",
  "sufficiency": "sufficient",
  "confidence": 0.94,
  "citations": [
    {
      "doc_id": "bio_s4_txt",
      "doc_title": "Biology Senior 4 Textbook",
      "page_start": 112,
      "page_end": 113,
      "chunk_preview": "...energy from sunlight is absorbed by chlorophyll...",
      "view_url": "/api/v1/docs/viewer/bio_s4_txt?page=112",
      "relevance_score": 0.98
    }
  ],
  "enhancements": {
    "analogy": "Think of the thylakoid like a solar panel charging a battery...",
    "real_world_context": "This reaction is the reason plants release oxygen into our atmosphere."
  },
  "created_at": "2026-03-05T22:31:05Z"
}
```

---

## 5. Thread History & Pagination

Threads use **cursor-based pagination** (reverse chronological).

### Fetch Messages
**Endpoint**: `GET /chat/conversations/{id}/messages?limit=20`

**Response Body**:
```json
{
  "messages": [
    { "message_id": "...", "question": "...", "answer": "...", "created_at": "..." },
    { "message_id": "...", "question": "...", "answer": "...", "created_at": "..." }
  ],
  "next_cursor": "eyJjcmVhdGVkX2F0IjogMTczMTI..."
}
```

**Loading More**: Use `?cursor={next_cursor}` to fetch older messages. If `next_cursor` is `null`, you've reached the start of the conversation.

---

## 6. Feedback & Quality Loops

Users/Teachers should rate AI answers to improve the model.

**Submit Feedback**: `POST /feedback`
```json
{
  "message_id": "msg_f3e4d5",
  "useful": true,
  "text": "The analogy was very clear!",
  "tags": ["pedagogically_sound", "helpful_analogy"]
}
```

**Check Feedback State**: `GET /feedback/{message_id}` (returns 404 if no feedback provided yet).

---

## 7. Quiz Generation

Generate a quiz based on the context discussed in a chat.

**Generate**: `POST /quiz/generate`
```json
{
  "topic_ids": ["photosynthesis_101"],
  "difficulty": "medium",
  "num_questions": 5,
  "include_answer_key": true
}
```
*Note: Returns a `job_id`. Poll `GET /quiz/{id}` until status is `completed`.*

---

## 8. Document Uploads (Custom context)

For advanced users uploading their own materials. This follows a **Chunked Upload** pattern.

1.  **Init**: `POST /upload/init?filename=notes.pdf&total_size=10485760&total_chunks=2&grade=S1&subject=science` -> returns `upload_id`.
2.  **Chunk**: `POST /upload/chunk/{upload_id}/{index}` (Send Binary `File`).
3.  **Complete**: `POST /upload/complete/{upload_id}` -> Triggers background RAG indexing.

---

## 9. Error Handling & Rate Limits

The backend returns standard RFC 7807 problem details in many cases.

| Code | Scenario | Pattern |
| :--- | :--- | :--- |
| **403** | Ownership Violation | Trying to access someone else's chat. |
| **429** | Rate Limited | `{"detail": "Rate limit exceeded. Please wait 60 seconds."}` |
| **501** | Not Implemented | e.g. Trying to use `ask/stream` (v2 scaffold). |
| **504** | LLM Timeout | AI took >30s. Display a "Server Busy" message. |

---

## 10. UI/UX Recommendations

- **Enhancement Boxes**: Render `analogy` and `real_world_context` in distinct, visually rich containers (e.g. use an icon of a lightbulb for analogies).
- **Citations Sidebar**: Don't crowd the bubble. Show a "See 2 Sources" badge that slides out a sidebar with the `chunk_preview`.
- **Latency Masking**: Use **Skeleton Loaders** for the answer bubble. RAG typically takes 4–8 seconds.
- **Auto-Title**: Don't ask the user for a title. Create the conv with a placeholder, then fetch its refreshed details after the first message; the backend will have auto-titled it by then.
