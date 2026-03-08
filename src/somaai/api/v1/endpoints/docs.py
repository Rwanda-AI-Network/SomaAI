"""Document endpoints — metadata and file serving."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from somaai.contracts.docs import DocumentResponse, DocumentViewLinkResponse
from somaai.db.crud import get_document
from somaai.db.session import get_session
from somaai.providers.storage import get_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/docs", tags=["documents"])

# Allowed MIME types for serving documents
_MIME_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".txt": "text/plain",
    ".pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
    ".md": "text/markdown",
}


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document_metadata(
    doc_id: str,
    db: AsyncSession = Depends(get_session),
) -> DocumentResponse:
    """Get document metadata.

    Architecture Decision: Uses denormalized chunk_count (O(1)) to avoid
    expensive SQL counts across millions of chunks.
    """
    doc = await get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return DocumentResponse(
        doc_id=str(doc.id),
        filename=str(doc.filename),
        title=str(doc.title),
        grade=str(doc.grade),
        subject=str(doc.subject),
        page_count=int(doc.page_count or 0),
        chunk_count=int(doc.chunk_count or 0),
        status=str(doc.status or "pending"),
        error_message=doc.error_message,
        uploaded_at=doc.uploaded_at,
        processed_at=doc.processed_at,
        metadata=doc.metadata_json,
    )


@router.get("/{doc_id}/view")
async def get_document_view(
    doc_id: str,
    page: int = Query(1, ge=1, description="Page number hint"),
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Serve a document file for viewing via streaming.

    Architecture Decision: Uses StorageBackend.open() + StreamingResponse to
    supporting any backend (Local/MinIO/S3) with O(1) memory footprint.
    """
    doc = await get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    storage = get_storage()

    # Check file exists BEFORE starting stream (can't raise HTTP errors mid-stream)
    try:
        # Note: Not all storage backends implement exists(), so we'll handle in stream
        pass
    except Exception as e:
        logger.error(
            "Storage check failed",
            extra={"doc_id": doc_id, "error": str(e)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail="Storage service temporarily unavailable",
        )

    suffix = Path(doc.filename).suffix.lower()
    media_type = _MIME_TYPES.get(suffix, "application/octet-stream")

    # Headers for inline browser rendering
    headers = {
        "Content-Disposition": f'inline; filename="{doc.filename}"',
    }
    if suffix == ".pdf" and page > 1:
        headers["X-PDF-Page"] = str(page)

    async def _file_stream():
        try:
            async with storage.open(doc.storage_path) as stream:
                while chunk := stream.read(65536):  # 64KB windows
                    yield chunk
        except FileNotFoundError:
            logger.error(
                "File not found in storage",
                extra={"doc_id": doc_id, "storage_path": doc.storage_path},
            )
            # Can't raise HTTPException here - headers already sent
            # Client will see connection drop
            return
        except Exception as e:
            logger.error(
                "Streaming failed",
                extra={"doc_id": doc_id, "error": str(e)},
                exc_info=True,
            )
            # Can't raise HTTPException here - headers already sent
            return

    return StreamingResponse(
        _file_stream(),
        media_type=media_type,
        headers=headers,
    )


@router.get("/{doc_id}/view-link", response_model=DocumentViewLinkResponse)
async def get_document_view_link(
    doc_id: str,
    page: int = Query(1, ge=1, description="Page number hint"),
    db: AsyncSession = Depends(get_session),
) -> DocumentViewLinkResponse:
    """Get a URL to view the document.

    Architecture Decision: Returns presigned URLs for remote storage (S3/MinIO)
    to offload bandwidth from the API server. Falls back to the /view endpoint
    for local/proxied access.
    """
    doc = await get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    storage = get_storage()

    # Attempt to get a direct access URL (e.g. presigned S3 URL)
    url = await storage.get_url(doc.storage_path)

    if not url:
        # Fallback: Point to the /view endpoint which streams the bits
        # This occurs for 'local' storage or if URL generation is disabled
        url = f"/api/v1/docs/{doc_id}/view?page={page}"

    return DocumentViewLinkResponse(url=url)
