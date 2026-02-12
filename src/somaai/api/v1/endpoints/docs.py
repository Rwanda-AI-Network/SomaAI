"""Document endpoints — metadata and file serving."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from somaai.contracts.docs import DocumentResponse, DocumentViewLinkResponse
from somaai.db.crud import get_document
from somaai.db.models import Chunk
from somaai.db.session import get_session
from somaai.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/docs", tags=["documents"])

# Allowed MIME types for serving documents
_MIME_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    ".doc": "application/msword",
    ".txt": "text/plain",
    ".pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
}


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document_metadata(
    doc_id: str,
    db: AsyncSession = Depends(get_session),
) -> DocumentResponse:
    """Get document metadata.

    Returns document details including filename, title,
    grade, subject, page and chunk counts, and timestamps.
    """
    doc = await get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Count chunks via explicit query (async SQLAlchemy can't lazy-load)
    result = await db.execute(
        select(func.count()).where(Chunk.document_id == doc_id)
    )
    chunk_count = result.scalar() or 0

    return DocumentResponse(
        doc_id=str(doc.id),
        filename=str(doc.filename),
        title=str(doc.title),
        grade=str(doc.grade),
        subject=str(doc.subject),
        page_count=int(doc.page_count or 0),
        chunk_count=chunk_count,
        storage_backend=str(doc.storage_backend or "local"),
        uploaded_at=doc.uploaded_at,
        processed_at=doc.processed_at,
        metadata=doc.metadata_json,
    )


@router.get("/{doc_id}/view")
async def get_document_view(
    doc_id: str,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    db: AsyncSession = Depends(get_session),
) -> FileResponse:
    """Serve a document file for viewing.

    Returns the raw file (e.g. PDF) so the browser can render it.
    The `page` query parameter is passed as a URL fragment hint
    for PDF viewers (#page=N).

    Currently supports local storage. S3 support can be added by
    extending the storage backend without changing this endpoint.
    """
    doc = await get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    storage_path = str(doc.storage_path)
    backend = str(doc.storage_backend or "local")

    # Resolve file path based on storage backend
    file_path = _resolve_file_path(storage_path, backend)

    if file_path is None or not file_path.is_file():
        logger.error(
            "Document file not found: doc_id=%s, path=%s",
            doc_id,
            storage_path,
        )
        raise HTTPException(
            status_code=404,
            detail="Document file not found on disk",
        )

    # Determine content type
    suffix = file_path.suffix.lower()
    media_type = _MIME_TYPES.get(suffix, "application/octet-stream")

    # For PDFs, set headers so the browser renders inline (not download)
    headers = {
        "Content-Disposition": f'inline; filename="{file_path.name}"',
    }

    # Add page hint for PDF viewers
    if suffix == ".pdf" and page > 1:
        headers["X-PDF-Page"] = str(page)

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        headers=headers,
    )


@router.get("/{doc_id}/view-link", response_model=DocumentViewLinkResponse)
async def get_document_view_link(
    doc_id: str,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    db: AsyncSession = Depends(get_session),
) -> DocumentViewLinkResponse:
    """Get a URL to view the document.

    Returns a link that can be opened in a browser to view
    the document. For local storage, this is the API endpoint
    itself. For S3, this would be a presigned URL.
    """
    doc = await get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    backend = str(doc.storage_backend or "local")

    if backend == "local":
        # Point back to the /view endpoint which serves the file
        url = f"/api/v1/docs/{doc_id}/view?page={page}"
    else:
        # Future: generate presigned S3 URL
        raise HTTPException(
            status_code=501,
            detail=f"Storage backend '{backend}' not yet supported for viewing",
        )

    return DocumentViewLinkResponse(url=url)


def _resolve_file_path(storage_path: str, backend: str) -> Path | None:
    """Resolve a storage path to an absolute file path.

    Args:
        storage_path: Path stored in the database (relative or absolute)
        backend: Storage backend type ('local', 's3', etc.)

    Returns:
        Absolute Path to the file, or None if backend is unsupported.
    """
    if backend != "local":
        return None

    path = Path(storage_path)

    # If already absolute, use directly
    if path.is_absolute():
        return path

    base = Path(settings.storage_local_path)
    
    # If path already starts with the base directory name (e.g. "uploads/"), 
    # strip it to avoid duplication (e.g. "uploads/uploads/...")
    if str(path).startswith(base.name + "/"):
        # Determine strict relative path
        try:
            path = path.relative_to(base.name)
        except ValueError:
            pass

    return base / path
