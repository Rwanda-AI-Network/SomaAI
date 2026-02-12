"""Quiz endpoints."""

from fastapi import APIRouter, Query

from somaai.contracts.quiz import (
    DownloadFormat,
    DownloadVariant,
    QuizGenerateRequest,
    QuizResponse,
)

router = APIRouter(prefix="/quiz", tags=["quiz"])


@router.post("/generate", response_model=dict)
async def generate_quiz(
    data: QuizGenerateRequest,
):
    """Generate a new quiz.

    Request body:
    - topic_ids: List of topic IDs to cover
    - difficulty: easy | medium | hard
    - num_questions: Number of questions (1-50)
    - include_answer_key: Include detailed answers with citations

    Returns:
    - quiz_id: ID for the quiz
    - job_id: Background job ID for tracking
    - status: "pending"

    Quiz generation runs as a background job.
    Poll GET /quiz/{quiz_id} for completion.
    """
    pass


@router.get("/{quiz_id}", response_model=QuizResponse)
async def get_quiz(quiz_id: str):
    """Get quiz details and questions.

    Returns quiz with:
    - Status (pending/generating/completed/failed)
    - Topic names and difficulty
    - Questions and answers (if completed)

    Returns 404 if quiz not found.
    """
    pass


@router.get("/{quiz_id}/download")
async def download_quiz(
    quiz_id: str,
    variant: DownloadVariant = Query(
        DownloadVariant.QUESTIONS,
        description="Content variant",
    ),
    format: DownloadFormat = Query(
        DownloadFormat.PDF,
        description="File format",
    ),
):
    """Download quiz as PDF or DOCX.

    Query params:
    - variant: "questions" or "questions_answers"
    - format: "pdf" or "docx" (pdf implemented first)

    Returns file download.

    Returns 400 if quiz not completed.
    Returns 404 if quiz not found.
    """
    pass
