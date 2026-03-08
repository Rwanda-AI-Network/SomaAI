# Error Handling Testing Guide

Quick reference for testing error handling improvements in Swagger UI.

---

## Access Swagger UI

```
http://localhost:8000/docs
```

---

## Test Scenarios

### 1. Invalid Grade (400 with helpful message)

**Endpoint:** `POST /api/v1/chat/conversations`

**Request:**
```json
{
  "grade": "S7",
  "subject": "biology",
  "title": "Test Chat"
}
```

**Expected Response:** `400 Bad Request`
```json
{
  "detail": "Invalid grade 'S7'. Valid grades: P6, S1, S2, S3, S4, S5, S6"
}
```

---

### 2. Invalid Subject (400 with helpful message)

**Endpoint:** `POST /api/v1/chat/conversations`

**Request:**
```json
{
  "grade": "S2",
  "subject": "invalid_subject",
  "title": "Test Chat"
}
```

**Expected Response:** `400 Bad Request`
```json
{
  "detail": "Invalid subject 'invalid_subject'. Valid subjects: mathematics, biology, ..."
}
```

---

### 3. Empty File Upload (400)

**Endpoint:** `POST /api/v1/ingest`

**Request:**
- file: (select an empty file or create one)
- grade: S2
- subject: biology

**Expected Response:** `400 Bad Request`
```json
{
  "detail": "Empty file uploaded. Please upload a valid document."
}
```

---

### 4. File Too Large (400)

**Endpoint:** `POST /api/v1/ingest`

**Request:**
- file: (file larger than 50MB)
- grade: S2
- subject: biology

**Expected Response:** `400 Bad Request`
```json
{
  "detail": "File too large. Maximum size: 50MB"
}
```

---

### 5. Non-Existent Conversation (404 without ID)

**Endpoint:** `GET /api/v1/chat/conversations/{id}`

**Request:** Use a fake ID like `invalid_conversation_id`

**Expected Response:** `404 Not Found`
```json
{
  "detail": "Conversation not found or not owned"
}
```

**Note:** Message doesn't reveal if conversation exists but not owned (security)

---

### 6. Non-Existent Message (404 without ID)

**Endpoint:** `GET /api/v1/chat/conversations/{conversation_id}/messages/{message_id}`

**Request:** Use valid conversation ID but fake message ID

**Expected Response:** `404 Not Found`
```json
{
  "detail": "Message not found"
}
```

**Note:** No message ID in error (prevents enumeration)

---

### 7. Duplicate Grade Creation (409)

**Endpoint:** `POST /api/v1/meta/grades`

**Request:**
```json
{
  "id": "S1",
  "name": "Senior 1",
  "display_order": 1,
  "level": "secondary"
}
```

**Expected Response:** `409 Conflict`
```json
{
  "detail": "Grade with ID 'S1' already exists"
}
```

---

### 8. Missing Required Field (422)

**Endpoint:** `POST /api/v1/meta/grades`

**Request:**
```json
{
  "id": "S8",
  "name": "Senior 8"
  // Missing display_order and level
}
```

**Expected Response:** `422 Unprocessable Entity`
```json
{
  "detail": "Required field is missing"
}
```

---

### 9. Rate Limiting (429)

**Endpoint:** `POST /api/v1/chat/conversations/{id}/ask`

**Test:** Send many requests rapidly (>10 per minute)

**Expected Response:** `429 Too Many Requests`
```json
{
  "detail": "Too many requests. Please wait a moment before trying again. This helps us maintain quality service for all users."
}
```

---

### 10. Chat Timeout (504)

**Endpoint:** `POST /api/v1/chat/conversations/{id}/ask`

**Request:**
```json
{
  "question": "Explain quantum mechanics in extreme detail with all mathematical proofs and historical context...",
  "user_role": "student"
}
```

**Expected Response:** `504 Gateway Timeout` (after 30 seconds)
```json
{
  "detail": "Request timeout — please try again with a simpler question"
}
```

---

## Positive Test Cases

### 1. Valid Conversation Creation

**Endpoint:** `POST /api/v1/chat/conversations`

**Request:**
```json
{
  "grade": "S2",
  "subject": "biology",
  "title": "Cell Biology Questions"
}
```

**Expected Response:** `201 Created`
```json
{
  "id": "conv_...",
  "title": "Cell Biology Questions",
  "grade": "S2",
  "subject": "biology",
  "message_count": 0,
  "created_at": "2026-03-08T...",
  "updated_at": "2026-03-08T..."
}
```

---

### 2. Valid File Upload

**Endpoint:** `POST /api/v1/ingest`

**Request:**
- file: (valid PDF, <50MB)
- grade: S2
- subject: biology
- title: Test Document

**Expected Response:** `200 OK`
```json
{
  "job_id": "job_...",
  "doc_id": "doc_...",
  "status": "pending"
}
```

---

### 3. Valid Chat Question

**Endpoint:** `POST /api/v1/chat/conversations/{id}/ask`

**Request:**
```json
{
  "question": "What is photosynthesis?",
  "user_role": "student"
}
```

**Expected Response:** `201 Created`
```json
{
  "message_id": "msg_...",
  "conversation_id": "conv_...",
  "answer": "Photosynthesis is...",
  "sufficiency": "sufficient",
  "confidence": 0.95,
  "citations": [...],
  "created_at": "2026-03-08T..."
}
```

---

## Error Logging Verification

After each error test, check the logs for proper structured logging:

```bash
# View logs
docker logs somaai-backend

# Look for structured log entries like:
{
  "level": "error",
  "message": "External service connection failed",
  "actor_id": "anon_...",
  "conversation_id": "conv_...",
  "error": "Connection refused",
  "timestamp": "2026-03-08T..."
}
```

---

## Security Checks

### 1. No Internal Details Leaked

❌ **Bad:** `"Internal server error: Connection to postgres://user:pass@localhost:5432/db failed"`

✅ **Good:** `"An unexpected error occurred. Please try again."`

### 2. No Enumeration

❌ **Bad:** `"Message msg_123 not found"` (reveals message doesn't exist)

✅ **Good:** `"Message not found"` (doesn't reveal existence)

### 3. No Stack Traces

❌ **Bad:** Error response includes Python traceback

✅ **Good:** Stack trace only in server logs, not in response

---

## Performance Checks

### 1. Timeout Handling

- Chat requests should timeout after 30 seconds
- Qdrant searches should timeout after 5 seconds
- No hanging requests

### 2. Rate Limiting

- Should limit to configured rate (default: 10/minute for chat)
- Should return 429 with clear message
- Should reset after time window

---

## Quick Test Script

```bash
#!/bin/bash

BASE_URL="http://localhost:8000/api/v1"

echo "Testing invalid grade..."
curl -X POST "$BASE_URL/chat/conversations" \
  -H "Content-Type: application/json" \
  -d '{"grade":"S7","subject":"biology"}' \
  | jq

echo "\nTesting empty file..."
touch empty.pdf
curl -X POST "$BASE_URL/ingest" \
  -F "file=@empty.pdf" \
  -F "grade=S2" \
  -F "subject=biology" \
  | jq
rm empty.pdf

echo "\nTesting non-existent conversation..."
curl -X GET "$BASE_URL/chat/conversations/invalid_id" | jq

echo "\nDone!"
```

---

## Expected Behavior Summary

| Test | Expected Code | Expected Message Pattern |
|------|---------------|-------------------------|
| Invalid grade | 400 | Shows valid options |
| Invalid subject | 400 | Shows valid options |
| Empty file | 400 | "Empty file uploaded" |
| File too large | 400 | Shows size limit |
| Not found | 404 | Generic, no IDs |
| Duplicate | 409 | "already exists" |
| Missing field | 422 | "Required field" |
| Rate limit | 429 | User-friendly explanation |
| Unexpected error | 500 | Generic message |
| Service down | 503 | Service name |
| Timeout | 504 | "Request timeout" |

---

## Troubleshooting

### Issue: Getting 500 instead of 400

**Cause:** Validation error not caught properly

**Check:** Look at server logs for the actual error

**Fix:** Ensure ValueError is caught and converted to 400

### Issue: Error message shows internal details

**Cause:** Exception not caught at endpoint level

**Check:** Search code for `detail=str(e)` or `detail=f"...{e}"`

**Fix:** Use generic message for unexpected errors

### Issue: Rate limiting not working

**Cause:** slowapi not installed or not configured

**Check:** `pip list | grep slowapi`

**Fix:** Install with `pip install slowapi`

---

**Ready to test!** Start with the invalid grade test and work through the list.
