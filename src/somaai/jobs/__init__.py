"""Background jobs module.

Provides async job queue for long-running tasks like
document ingestion and quiz generation.
"""

from somaai.jobs.queue import enqueue_job, get_job_status
from somaai.jobs.tasks import generate_quiz_task, ingest_document_task

__all__ = [
    "enqueue_job",
    "get_job_status",
    "ingest_document_task",
    "generate_quiz_task",
]
