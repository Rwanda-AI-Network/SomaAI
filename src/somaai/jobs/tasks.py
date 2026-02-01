"""Background task definitions.

Contains the actual task logic for background jobs.
Tasks are executed by the worker process.
"""

from __future__ import annotations

from typing import Any

from somaai.contracts.jobs import JobStatus
from somaai.jobs.queue import update_job_progress, update_job_status


async def ingest_document_task(
    job_id: str,
    doc_id: str,
    file_path: str,
    grade: str,
    subject: str,
    title: str | None = None,
) -> None:
    """Process document ingestion.

    Executed as a background job after document upload.

    Steps:
        1. Load document from storage
        2. Extract text and metadata
        3. Split into chunks
        4. Generate embeddings for chunks
        5. Store chunks and embeddings in vector DB
        6. Update document status

    Args:
        job_id: Job ID for progress updates
        doc_id: Document ID to process
        file_path: Path to the document file
        grade: Grade level
        subject: Subject
        title: Optional document title
    """
    import asyncio

    from somaai.db import crud
    from somaai.db.session import async_session_maker
    from somaai.modules.ingest.pipeline import IngestPipeline
    from somaai.settings import settings

    try:
        await update_job_status(job_id, JobStatus.RUNNING)

        pipeline = IngestPipeline(settings)

        # Sync-compatible progress callback that schedules async DB updates
        def on_progress(stage: str, pct: int) -> None:
            """Sync progress callback - schedules async update."""
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(update_job_progress(job_id, pct, stage))
            except RuntimeError:
                pass  # No running loop, skip progress update

        result = await pipeline.run(
            doc_id=doc_id,
            file_path=file_path,
            grade=grade,
            subject=subject,
            title=title,
            on_progress=on_progress,
        )

        # Update document with processing results
        page_count = result.get("pages", 0) if isinstance(result, dict) else 0
        async with async_session_maker() as db:
            await crud.update_document_processed(db, doc_id, page_count)

        await update_job_status(
            job_id,
            JobStatus.COMPLETED,
            progress_pct=100,
            result_id=doc_id,
        )

    except Exception as e:
        await update_job_status(
            job_id,
            JobStatus.FAILED,
            error=str(e),
        )
        raise


async def generate_quiz_task(
    job_id: str,
    quiz_id: str,
    topic_ids: list[str],
    grade: str,
    subject: str,
    difficulty: str,
    num_questions: int,
    include_answer_key: bool = True,
) -> None:
    """Generate quiz questions.

    Executed as a background job after quiz generation request.

    Steps:
        1. Load topics and related chunks from DB
        2. Construct prompt with topic content
        3. Call LLM to generate questions
        4. Parse and validate generated questions
        5. Extract citations for answer keys
        6. Store quiz items in DB
        7. Update quiz status

    Args:
        job_id: Job ID for progress updates
        quiz_id: Quiz ID to generate
        topic_ids: Topic IDs to generate questions from
        grade: Grade level
        subject: Subject
        difficulty: Difficulty level (easy/medium/hard)
        num_questions: Number of questions to generate
        include_answer_key: Include answers with citations
    """
    from somaai.modules.quiz.generator import QuizGenerator

    try:
        await update_job_status(job_id, JobStatus.RUNNING)
        await update_job_progress(job_id, 10, "Loading topics")

        generator = QuizGenerator()

        await update_job_progress(job_id, 30, "Generating questions")

        # Generate questions
        items = await generator.generate_questions(
            topic_ids=topic_ids,
            difficulty=difficulty,
            num_questions=num_questions,
            include_answer_key=include_answer_key,
        )

        await update_job_progress(job_id, 80, "Saving quiz")

        # Save to database would happen here
        # For now, just mark complete

        await update_job_status(
            job_id,
            JobStatus.COMPLETED,
            progress_pct=100,
            result_id=quiz_id,
        )

    except Exception as e:
        await update_job_status(
            job_id,
            JobStatus.FAILED,
            error=str(e),
        )
        raise


# Task registry for dynamic dispatch
TASK_REGISTRY: dict[str, Any] = {
    "ingest_document": ingest_document_task,
    "generate_quiz": generate_quiz_task,
}
