"""Document ingestion endpoints.

Ingest = {upload, chunk, embed, store}
"""

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from somaai.contracts.common import GradeLevel, JobStatus, Subject
from somaai.contracts.docs import DocumentResponse, IngestJobResponse
from somaai.contracts.jobs import JobResponse
from somaai.db import crud
from somaai.db.session import async_session_maker
from somaai.jobs.queue import enqueue_job, get_job_status
from somaai.providers.storage import get_storage
from somaai.utils.ids import generate_id

# Rate limiting setup
try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    limiter = Limiter(key_func=get_remote_address)
    RATE_LIMITING_ENABLED = True
except ImportError:
    limiter = None
    RATE_LIMITING_ENABLED = False

router = APIRouter(prefix="/ingest", tags=["ingest"])

# Allowed file extensions
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md"}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB


def validate_file(file: UploadFile) -> None:
    """Validate uploaded file.

    Args:
        file: Uploaded file

    Raises:
        HTTPException: If file is invalid
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )


@router.post("", response_model=IngestJobResponse)
async def ingest_document(
    request: Request,
    file: UploadFile = File(..., description="Document file (PDF, DOCX)"),
    grade: GradeLevel = Form(..., description="Grade level"),
    subject: Subject = Form(..., description="Subject"),
    title: str = Form(None, description="Document title (optional)"),
):
    """Upload and ingest a curriculum document.

    Accepts file upload with metadata.
    Processing runs as a background job.

    Steps:
    1. Validate file type
    2. Save to storage
    3. Create document record
    4. Enqueue ingestion job

    Returns:
    - job_id: Background job ID for tracking
    - doc_id: Document ID (immediate)
    - status: "pending"

    Ingestion job will:
    - Extract text from document
    - Split into chunks
    - Generate embeddings
    - Store in vector database
    """
    # 1. Validate file
    validate_file(file)

    # 2. Generate IDs
    doc_id = generate_id()
    filename = file.filename or "document"
    doc_title = title or Path(filename).stem

    # 3. Save file to storage
    storage = get_storage()
    storage_path = f"documents/{doc_id}/{filename}"

    try:
        file_content = await file.read()

        # Check file size
        if len(file_content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB",
            )

        # Save to storage
        full_path = await storage.save(file_content, storage_path)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save file: {str(e)}",
        )

    # 4. Create document record in database
    async with async_session_maker() as db:
        await crud.create_document(
            db=db,
            doc_id=doc_id,
            filename=filename,
            title=doc_title,
            storage_path=full_path,
            grade=grade.value,
            subject=subject.value,
        )

    # 5. Enqueue ingestion job
    job_id = await enqueue_job(
        task_name="ingest_document",
        payload={
            "doc_id": doc_id,
            "file_path": full_path,
            "grade": grade.value,
            "subject": subject.value,
            "title": doc_title,
        },
    )

    return IngestJobResponse(
        job_id=job_id,
        doc_id=doc_id,
        status=JobStatus.PENDING,
        message=f"Document '{doc_title}' uploaded. Ingestion started.",
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_ingest_job_status(job_id: str):
    """Get ingestion job status.

    Returns:
    - job_id
    - status: pending | running | completed | failed
    - progress_pct: 0-100
    - result_id: doc_id when completed
    - error: Error message if failed

    Poll this endpoint to track ingestion progress.

    Returns 404 if job not found.
    """
    job = await get_job_status(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return job


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: str):
    """Get document details by ID.

    Returns document metadata including:
    - Filename and title
    - Grade and subject
    - Page and chunk counts
    - Processing status

    Returns 404 if document not found.
    """
    # TODO: Implement database lookup
    raise HTTPException(status_code=404, detail="Document not found")


@router.delete("/{doc_id}")
async def delete_document(doc_id: str):
    """Delete a document and its chunks.

    Removes:
    - Document record from database
    - Chunks from vector database
    - File from storage

    Returns 404 if document not found.
    """
    # TODO: Implement full deletion
    raise HTTPException(status_code=404, detail="Document not found")
