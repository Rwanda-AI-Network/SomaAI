"""Chunked file upload for large documents.

Supports uploading files larger than 50MB by splitting into chunks.
Uses Redis for session state to support horizontal scaling.
Uses aiofiles for efficient async file I/O.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from somaai.utils.ids import generate_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])

# Use temp directory for chunk storage
CHUNK_DIR = Path("/tmp/somaai_uploads")
CHUNK_DIR.mkdir(exist_ok=True)

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


@router.post("/init")
async def init_upload(
    filename: str,
    total_size: int,
    total_chunks: int,
) -> dict:
    """Initialize a chunked upload session.

    Args:
        filename: Original filename
        total_size: Total file size in bytes
        total_chunks: Expected number of chunks

    Returns:
        Upload session info with upload_id and chunk_size
    """
    upload_id = generate_id()
    session_dir = CHUNK_DIR / upload_id

    try:
        import aiofiles.os

        await aiofiles.os.makedirs(session_dir, exist_ok=True)
    except ImportError:
        session_dir.mkdir(parents=True, exist_ok=True)

    session = {
        "upload_id": upload_id,
        "filename": filename,
        "total_size": total_size,
        "total_chunks": total_chunks,
        "received_chunks": [],
        "session_dir": str(session_dir),
        "created_at": datetime.utcnow().isoformat(),
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
    """Upload a single chunk.

    Args:
        upload_id: Session ID from init_upload
        chunk_index: Zero-based chunk index
        chunk: Chunk file data

    Returns:
        Chunk receipt confirmation
    """
    session = await _get_session(upload_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail="Upload session not found or expired",
        )

    session_dir = Path(session["session_dir"])
    chunk_path = session_dir / f"chunk_{chunk_index:05d}"

    content = await chunk.read()

    try:
        import aiofiles

        async with aiofiles.open(chunk_path, "wb") as f:
            await f.write(content)
    except ImportError:
        with open(chunk_path, "wb") as f:
            f.write(content)

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


@router.post("/complete/{upload_id}")
async def complete_upload(upload_id: str) -> dict:
    """Complete upload and reassemble chunks.

    Args:
        upload_id: Session ID from init_upload

    Returns:
        Final file path and status
    """
    session = await _get_session(upload_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail="Upload session not found or expired",
        )

    session_dir = Path(session["session_dir"])
    filename = session["filename"]

    # Check all chunks received
    expected = set(range(session["total_chunks"]))
    received = set(session["received_chunks"])
    missing = expected - received

    if missing:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Missing chunks: {sorted(list(missing)[:10])}"
                f"{'...' if len(missing) > 10 else ''}"
            ),
        )

    # Reassemble chunks
    chunks = sorted(session_dir.glob("chunk_*"))
    final_path = session_dir / filename

    try:
        import aiofiles

        async with aiofiles.open(final_path, "wb") as out:
            for chunk_path in chunks:
                async with aiofiles.open(chunk_path, "rb") as inp:
                    await out.write(await inp.read())
    except ImportError:
        with open(final_path, "wb") as out:
            for chunk_path in chunks:
                with open(chunk_path, "rb") as inp:
                    out.write(inp.read())

    # Cleanup chunk files
    for chunk_path in chunks:
        chunk_path.unlink()

    # Remove session from Redis
    await _delete_session(upload_id)

    logger.info(f"Completed chunked upload: {upload_id} -> {final_path}")

    return {
        "upload_id": upload_id,
        "file_path": str(final_path),
        "filename": filename,
        "status": "complete",
    }


@router.delete("/cancel/{upload_id}")
async def cancel_upload(upload_id: str) -> dict:
    """Cancel an upload session and cleanup.

    Args:
        upload_id: Session ID to cancel

    Returns:
        Cancellation confirmation
    """
    session = await _get_session(upload_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail="Upload session not found or expired",
        )

    session_dir = Path(session["session_dir"])

    # Delete all chunk files
    for chunk_path in session_dir.glob("chunk_*"):
        try:
            chunk_path.unlink()
        except Exception:
            pass

    # Try to remove directory
    try:
        session_dir.rmdir()
    except OSError:
        pass

    # Remove session from Redis
    await _delete_session(upload_id)

    logger.info(f"Cancelled chunked upload: {upload_id}")

    return {
        "upload_id": upload_id,
        "status": "cancelled",
    }
