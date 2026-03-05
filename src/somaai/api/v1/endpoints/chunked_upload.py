import asyncio
import hashlib
import json
import logging
import mimetypes
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession


from somaai.contracts.docs import IngestJobResponse
from somaai.db.session import get_session
from somaai.services.ingest_service import IngestionService
from somaai.utils.ids import generate_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])

# Session TTL (2 hours)
SESSION_TTL = 7200
NAMESPACE = "somaai:upload"


async def _get_redis():
    """Get Redis client using project's centralized Redis utility."""
    from somaai.utils.redis import get_general_redis

    return await get_general_redis()


def _session_key(upload_id: str) -> str:
    """Generate Redis key for upload session."""
    return f"{NAMESPACE}:session:{upload_id}"


async def _get_session(upload_id: str) -> dict | None:
    """Get upload session from Redis."""
    try:
        redis = await _get_redis()
        data = await redis.get(_session_key(upload_id))
        if data:
            return json.loads(data)
    except Exception as e:
        logger.warning(f"Redis get failed, using fallback: {e}")
    return None


async def _save_session(upload_id: str, session: dict) -> None:
    """Save upload session to Redis."""
    try:
        redis = await _get_redis()
        await redis.setex(
            _session_key(upload_id),
            SESSION_TTL,
            json.dumps(session),
        )
    except Exception as e:
        logger.warning(f"Redis save failed: {e}")


async def _delete_session(upload_id: str) -> None:
    """Delete upload session from Redis."""
    try:
        redis = await _get_redis()
        await redis.delete(_session_key(upload_id))
    except Exception as e:
        logger.warning(f"Redis delete failed: {e}")


def _get_storage():
    """Get storage backend."""
    from somaai.providers.storage import get_storage

    return get_storage()


@router.post("/init")
async def init_upload(
    filename: str,
    total_size: int,
    total_chunks: int,
    grade: str,
    subject: str,
    title: str | None = None,
) -> dict:
    """Initialize a chunked upload session with curriculum metadata.

    Args:
        filename: Original filename
        total_size: Total file size in bytes
        total_chunks: Expected number of chunks
        grade: Grade level for ingestion
        subject: Subject for ingestion
        title: Optional document title
    """
    # Validate inputs
    if total_chunks <= 0:
        raise HTTPException(status_code=400, detail="total_chunks must be > 0")
    if total_size <= 0:
        raise HTTPException(status_code=400, detail="total_size must be > 0")
    if not filename or not filename.strip():
        raise HTTPException(status_code=400, detail="filename is required")

    upload_id = generate_id()

    session = {
        "upload_id": upload_id,
        "filename": filename,
        "total_size": total_size,
        "total_chunks": total_chunks,
        "grade": grade,
        "subject": subject,
        "title": title or Path(filename).stem,
        "received_chunks": [],
        "staging_prefix": f"_uploads/{upload_id}",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    await _save_session(upload_id, session)

    return {
        "upload_id": upload_id,
        "chunk_size": 5 * 1024 * 1024,  # 5MB recommended chunk size
    }


@router.post("/chunk/{upload_id}/{chunk_index}")
async def upload_chunk(
    upload_id: str,
    chunk_index: int,
    chunk: UploadFile = File(...),
) -> dict:
    """Upload a single chunk to object storage."""
    session = await _get_session(upload_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail="Upload session not found or expired",
        )

    # Validate chunk_index bounds
    if chunk_index < 0 or chunk_index >= session["total_chunks"]:
        raise HTTPException(
            status_code=400,
            detail=f"chunk_index {chunk_index} out of bounds",
        )

    storage = _get_storage()

    # Read chunk content
    content = await chunk.read()

    # Store chunk in object storage under staging prefix
    chunk_key = f"{session['staging_prefix']}/chunk_{chunk_index:05d}"
    await storage.save(content, chunk_key)

    # Update received chunks
    if chunk_index not in session["received_chunks"]:
        session["received_chunks"].append(chunk_index)
        await _save_session(upload_id, session)

    progress = len(session["received_chunks"]) / session["total_chunks"]

    return {
        "upload_id": upload_id,
        "chunk_index": chunk_index,
        "size": len(content),
        "status": "received",
        "progress": progress,
    }


@router.post("/complete/{upload_id}", response_model=IngestJobResponse)
async def complete_upload(
    upload_id: str,
    db: AsyncSession = Depends(get_session),
) -> IngestJobResponse:
    """Complete upload: reassemble chunks and trigger unified ingestion.

    Architecture Decision: Upon assembly, the document is immediately handed
    over to the IngestionService to ensure consistency with standard uploads.
    """
    session = await _get_session(upload_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail="Upload session not found or expired",
        )

    filename = session["filename"]
    staging_prefix = session["staging_prefix"]

    # Check all chunks received
    expected = set(range(session["total_chunks"]))
    received = set(session["received_chunks"])
    missing = expected - received

    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing {len(missing)} chunks. Cannot complete.",
        )

    storage = _get_storage()

    # 1. Compute final SHA-256 hash by STREAMING chunks from storage
    # Memory: O(64KB buffer) regardless of total file size
    sha256 = hashlib.sha256()
    src_paths = []

    for i in range(session["total_chunks"]):
        chunk_key = f"{staging_prefix}/chunk_{i:05d}"
        src_paths.append(chunk_key)

        async with storage.open(chunk_key) as stream:
            while block := stream.read(65536):
                sha256.update(block)

    content_hash = sha256.hexdigest()
    ext = Path(filename).suffix.lower()
    object_key = f"documents/{content_hash}{ext}"

    # 2. Check for deduplication
    if not await storage.exists(object_key):
        # 3. Assemble chunks server-side (zero-copy)
        content_type, _ = mimetypes.guess_type(filename)
        logger.info(f"Assembling {len(src_paths)} chunks -> {object_key}")
        success = await storage.compose_objects(
            dest_path=object_key,
            src_paths=src_paths,
            content_type=content_type,
        )
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to assemble chunks in storage",
            )

    # 4. Cleanup staging chunks concurrently
    async def _delete_chunk(key: str) -> None:
        try:
            await storage.delete(key)
        except Exception:
            pass

    await asyncio.gather(*[_delete_chunk(k) for k in src_paths])

    # 5. Remove session from Redis
    await _delete_session(upload_id)

    # 6. Centralized Handover to Ingestion Pipeline
    return await IngestionService.trigger_ingestion(
        db=db,
        doc_id=generate_id(),
        storage_key=object_key,
        grade=session["grade"],
        subject=session["subject"],
        title=session["title"],
        filename=filename,
        content_hash=content_hash,
    )


@router.delete("/cancel/{upload_id}")
async def cancel_upload(upload_id: str) -> dict:
    """Cancel an upload session and cleanup staging chunks."""
    session = await _get_session(upload_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    storage = _get_storage()
    staging_prefix = session["staging_prefix"]

    try:
        staged_objects = await storage.list_objects(staging_prefix)

        async def _delete_obj(key: str) -> None:
            try:
                await storage.delete(key)
            except Exception:
                pass

        await asyncio.gather(*[_delete_obj(k) for k in staged_objects])
    except Exception as e:
        logger.warning(f"Cleanup failed: {e}")

    await _delete_session(upload_id)
    return {"upload_id": upload_id, "status": "cancelled"}
