# Frontend Integration Guide

**Last Updated**: March 7, 2026

## Quick Start

### Authentication (Session-Based)

SomaAI uses **cookieless anonymous sessions**. No login required.

```typescript
// Sessions are automatic via HttpOnly cookies
const response = await fetch('/api/v1/chat/conversations', {
  method: 'POST',
  credentials: 'include', // Important!
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ grade: 'S1', subject: 'mathematics' })
});
```

### Teacher Chat Flow

```typescript
// 1. Create conversation
const conv = await api.post('/chat/conversations', {
  grade: 'S1',
  subject: 'mathematics'
});

// 2. Ask question with enhancements
const response = await api.post(`/chat/conversations/${conv.id}/ask`, {
  question: 'How do I teach quadratic equations?',
  user_role: 'teacher',
  preferences: {
    enabled_enhancements: ['analogy', 'real_world']
  }
});

// Response includes: answer, citations, enhancements (analogy, real_world_context)
```

### Topic Management

```typescript
// List topics
const topics = await api.get('/meta/topics', {
  params: { grade: 'S1', subject: 'mathematics' }
});

// Create topic
const topic = await api.post('/meta/topics', {
  title: 'Quadratic Equations',
  grade: 'S1',
  subject: 'mathematics',
  page_start: 45,
  page_end: 52,
  path: ['Unit 3: Algebra', 'Chapter 2']
});
```

### Quiz Generation

```typescript
// Generate quiz from topics
const quiz = await api.post('/quiz/generate', {
  topic_ids: ['topic_id_1', 'topic_id_2'],
  grade: 'S1',
  subject: 'mathematics',
  difficulty: 'medium',
  num_questions: 10,
  include_answer_key: true
});

// Poll for completion
const completed = await api.get(`/quiz/${quiz.quiz_id}`);
```

## Key Concepts

### Session Management
- **No passwords**: System generates anonymous `actor_id` (e.g., `anon_abc123`)
- **90-day sessions**: Stored in Redis, auto-renewed
- **Conversation ownership**: All conversations tied to actor_id

### Teacher Features
- **Role-based prompts**: Different LLM prompts for teachers vs students
- **Enhancement preferences**: Analogies and real-world context
- **Profile defaults**: Teacher profiles store default preferences

### Topics
- **Manual creation**: Topics are NOT auto-extracted
- **Quiz generation**: Primary use case for topics
- **Hierarchical paths**: Support nested curriculum structure

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/chat/conversations` | POST | Create conversation |
| `/chat/conversations/{id}/ask` | POST | Ask question |
| `/meta/topics` | GET | List topics |
| `/meta/topics` | POST | Create topic |
| `/quiz/generate` | POST | Generate quiz |

## Complete Documentation

For detailed technical documentation, see:
- `ARCHITECTURE.md` - System design
- `api.md` - Complete API reference
- `DEVELOPMENT.md` - Local setup guide

---

**Note**: This is a summary guide. Full technical documentation was created during development session on March 7, 2026.
