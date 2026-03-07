# SomaAI Teacher API: Integration Guide

This document provides technical instructions for frontend developers building the **Teacher Dashboard** and **Teacher Chat Interface**. It focuses on teacher-specific profile management, pedagogical AI interactions, and lesson preparation tools.

---

## 📖 Table of Contents
1. [Teacher Profile Management](#1-teacher-profile-management)
2. [Pedagogical Chat Sessions](#2-pedagogical-chat-sessions)
3. [AI Response Enhancements](#3-ai-response-enhancements)
4. [Quiz Generation Workflow](#4-quiz-generation-workflow)
5. [Feedback & Quality Loops](#5-feedback--quality-loops)
6. [UI/UX Recommendations for Teachers](#6-uiux-recommendations-for-teachers)

---

## 1. Teacher Profile Management

Teachers have a unique profile that tracks the grades and subjects they teach, as well as their default preferences for AI explanations.

### Get Teacher Profile
**Endpoint**: `GET /api/v1/teacher/profile`
**Description**: Fetches current teacher settings. Creates a default profile if none exists.

**Example Response**:
```json
{
  "profile_id": "prof_123",
  "teacher_id": "user_456",
  "classes_taught": [
    { "grade": "S4", "subject": "biology" },
    { "grade": "S5", "subject": "chemistry" }
  ],
  "analogy_enabled": true,
  "realworld_enabled": true,
  "created_at": "2026-03-05T10:00:00Z",
  "updated_at": "2026-03-05T12:00:00Z"
}
```

### Update Teacher Profile
**Endpoint**: `POST /api/v1/teacher/profile`
**Description**: Updates classes taught and default AI preferences.

**Request Body**:
```json
{
  "classes_taught": [
    { "grade": "S4", "subject": "biology" }
  ],
  "analogy_enabled": true,
  "realworld_enabled": false
}
```

---

## 2. Pedagogical Chat Sessions

When a teacher interacts with the AI, the RAG (Retrieval-Augmented Generation) pipeline switches to **Teacher Mode**. This provides deeper technical details, teaching tips, and common misconceptions.

### Starting a Conversation
Use the standard conversation creation endpoint, but ensure the UI filters the `grade` and `subject` options based on the `classes_taught` in the teacher's profile for a better experience.

**Endpoint**: `POST /api/v1/chat/conversations`

### Asking a Question (Teacher Mode)
**Endpoint**: `POST /api/v1/chat/conversations/{id}/ask`
**Important**: Set `user_role` to `"teacher"` to trigger the pedagogical prompt.

**Request Body**:
```json
{
  "question": "How should I explain the Krebs cycle to Senior 4 students?",
  "user_role": "teacher",
  "preferences": {
    "enabled_enhancements": ["analogy", "real_world"]
  }
}
```

**Teacher-Specific Response Structure**:
The `answer` field for teachers typically follows this structure in Markdown:
1. **Direct Answer**: Technical explanation.
2. **Teaching Tips**: Strategies for the classroom.
3. **Common Misconceptions**: Things students often get wrong.

---

## 3. AI Response Enhancements

Teachers can toggle specific enhancements to help them create lesson materials.

- **Analogy**: Generates a relatable analogy (often local to Rwanda) to help explain a concept.
- **Real-World Application**: Provides examples of how the concept applies in Rwandan daily life, agriculture, or industry.

These appear in the `enhancements` object of the `ChatResponse`:
```json
{
  "answer": "...",
  "enhancements": {
    "analogy": "Think of the cell membrane like the gates of a school...",
    "real_world_context": "In Rwanda, osmosis is observed when drying coffee beans..."
  }
}
```

---

## 4. Quiz Generation Workflow

Teachers can generate quizzes based on specific curriculum topics covered in the conversation or from the general textbook.

### Generate Quiz
**Endpoint**: `POST /api/v1/quiz/generate`
**Description**: Starts a background job to generate questions.

**Request Body**:
```json
{
  "topic_ids": ["photosynthesis_102"],
  "difficulty": "medium",
  "num_questions": 10,
  "include_answer_key": true
}
```

**Response**:
```json
{
  "quiz_id": "quiz_abc",
  "job_id": "job_xyz",
  "status": "pending"
}
```

### Polling for Completion
**Endpoint**: `GET /api/v1/quiz/{quiz_id}`
Poll this until `status` is `"completed"`.

### Downloading for Print
**Endpoint**: `GET /api/v1/quiz/{quiz_id}/download?variant=questions_answers&format=pdf`
Provides a formatted PDF that teachers can print for their class.

---

## 5. Feedback & Quality Loops

Teachers are the primary source of quality control for the AI. The UI should prominently feature rating buttons for every AI response.

**Submit Feedback**: `POST /api/v1/feedback`
```json
{
  "message_id": "msg_f3e4d5",
  "useful": true,
  "text": "The misconceptions section was particularly helpful for my lesson prep.",
  "tags": ["pedagogically_sound"]
}
```

---

## 6. UI/UX Recommendations for Teachers

- **Lesson Plan Layout**: Use a side-by-side view where the AI chat is on the left and a "Generated Lesson Materials" (Quizzes, Analogies) pane is on the right.
- **Toggle Persistence**: Save the `analogy_enabled` and `realworld_enabled` toggles to the teacher's profile so they don't have to set them every time.
- **Citation Tooltips**: Instead of just links, show the `chunk_preview` of a citation in a tooltip when a teacher hovers over a source.
- **Export to Word/PDF**: Teachers often need to take AI content into physical classrooms. Always provide easy "Copy to Clipboard" or "Download as PDF" options for the `answer` text.
