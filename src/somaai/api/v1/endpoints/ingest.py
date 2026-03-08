import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from somaai.contracts.docs import (
    IngestJobResponse,
    IngestStorageRequest,
)
from somaai.contracts.jobs import JobResponse
from somaai.db.session import get_session
from somaai.jobs.queue import get_job_status
from somaai.providers.storage import get_storage
from somaai.services.ingest_service import IngestionService
from somaai.settings import settings
from somaai.utils.ids import generate_id
from somaai.utils.security import sanitize_filename, validate_file_content

logger = logging.getLogger(__name__)

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
MAX_FILE_SIZE = settings.ingest.max_file_size
VALIDATION_THRESHOLD = settings.ingest.validation_threshold


def validate_file(file: UploadFile) -> None:
    """Validate uploaded file.

    Args:
        file: Uploaded file

    Raises:
        HTTPException: If file is invalid
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Sanitize filename
    safe_filename = sanitize_filename(file.filename)
    if not safe_filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    ext = Path(safe_filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type: {ext}. "
                f"Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            ),
        )


@router.post("", response_model=IngestJobResponse)
async def ingest_document(
    request: Request,
    file: UploadFile = File(..., description="Document file (PDF, DOCX)"),
    grade: str = Form(..., description="Grade level"),
    subject: str = Form(..., description="Subject"),
    title: str = Form(None, description="Document title (optional)"),
    db: AsyncSession = Depends(get_session),
):
    """Upload and ingest a curriculum document.

    Accepts file upload with metadata.
    Processing runs as a background job.
    """
    # 1. Validate file type
    validate_file(file)

    # 2. Logic Preparation
    doc_id = generate_id()
    filename = sanitize_filename(file.filename or "document")
    doc_title = title or Path(filename).stem

    # 3. Check file size early
    if file.size is not None:
        if file.size == 0:
            raise HTTPException(
                status_code=400,
                detail="Empty file uploaded. Please upload a valid document.",
            )
        if file.size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)}MB"
                ),
            )

    try:
        # 4. Content validation for small files
        if file.size and file.size < VALIDATION_THRESHOLD:
            content_sample = await file.read()
            validate_file_content(content_sample, filename)
            await file.seek(0)

        # 5. Save to object storage with SHA-256 deduplication
        storage = get_storage()
        object_key, content_hash, was_deduped = await storage.save_deduplicated(
            file.file,
            directory="documents",
            original_filename=filename,
        )

        if was_deduped:
            logger.info(f"Dedup hit for '{filename}' ({content_hash[:12]}…)")

    except (HTTPException, ValueError) as e:
        if isinstance(e, ValueError):
            raise HTTPException(status_code=400, detail=str(e))
        raise
    except ConnectionError as e:
        logger.error(
            "Storage service connection failed",
            extra={"filename": filename, "error": str(e)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail="Storage service temporarily unavailable. Please try again shortly.",
        )
    except Exception as e:
        logger.error(
            "Ingestion failed",
            extra={
                "doc_id": doc_id,
                "filename": filename,
                "grade": grade,
                "subject": subject,
                "error": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please try again.",
        )

    # 6. Centralized Handover to Ingestion Pipeline
    return await IngestionService.trigger_ingestion(
        db=db,
        doc_id=doc_id,
        storage_key=object_key,
        grade=grade,
        subject=subject,
        title=doc_title,
        filename=filename,
        content_hash=content_hash,
    )


@router.post("/storage", response_model=IngestJobResponse)
async def ingest_from_storage(
    request: IngestStorageRequest,
    db: AsyncSession = Depends(get_session),
):
    """Trigger ingestion for a file already present in storage.

    DSA Mentality: O(1) existence validation before enqueuing.
    Exempted from standard size limits as it bypasses API server buffering.
    """
    storage = get_storage()

    # 1. Existence and Metadata Check (High efficiency)
    metadata = await storage.get_metadata(request.storage_key)
    if not metadata:
        raise HTTPException(
            status_code=404, detail=f"File not found in storage: {request.storage_key}"
        )

    # 2. Extension Validation
    ext = Path(request.storage_key).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type: {ext}. "
                f"Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            ),
        )

    # 3. Preparation
    doc_id = generate_id()
    doc_title = (
        request.title or Path(request.storage_key).stem.replace("_", " ").title()
    )

    # 4. Centralized Handover to Ingestion Pipeline
    return await IngestionService.trigger_ingestion(
        db=db,
        doc_id=doc_id,
        storage_key=request.storage_key,
        grade=request.grade,
        subject=request.subject,
        title=doc_title,
        filename=Path(request.storage_key).name,
        content_hash=None,
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_ingest_job_status(job_id: str):
    """Get ingestion job status."""
    job = await get_job_status(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return job
