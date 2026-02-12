"""API v1 router.

Aggregates all v1 endpoint routers.
"""

from fastapi import APIRouter

from somaai.api.v1.endpoints import (
    actors,
    chat,
    chunked_upload,
    docs,
    feedback,
    ingest,
    meta,
    quiz,
    # retrieval,
    teacher,
)

v1_router = APIRouter()

# Chat - Student and teacher Q&A
v1_router.include_router(chat.router)

# Meta - Grades, subjects, topics
v1_router.include_router(meta.router)

# Teacher - Profile management
v1_router.include_router(teacher.router)

# Quiz - Quiz generation and download
v1_router.include_router(quiz.router)

# Documents - Document viewing
v1_router.include_router(docs.router)

# Ingest - Document ingestion
v1_router.include_router(ingest.router)

# Chunked Upload - Large file support
v1_router.include_router(chunked_upload.router)

# Retrieval - Debug/admin search
# v1_router.include_router(retrieval.router)

# Feedback - Response ratings
# Feedback - Response ratings
v1_router.include_router(feedback.router)

# Actors - Anonymous user management
v1_router.include_router(actors.router)
