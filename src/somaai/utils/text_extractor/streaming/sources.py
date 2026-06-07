"""Stream source implementations (Strategy pattern).

Each source knows how to create streams from a specific storage backend.
New sources can be added without modifying existing code.
"""

import asyncio
import io
import logging
import uuid
from pathlib import Path
from typing import BinaryIO

logger = logging.getLogger(__name__)


class BytesSource:
    """Stream source for in-memory bytes.

    Use for small files or when data is already in memory.

    Example:
        >>> source = BytesSource(pdf_bytes)
        >>> async with source.open() as stream:
        ...     process(stream)
    """

    __slots__ = ("_data", "_doc_id")

    def __init__(self, data: bytes, doc_id: str | None = None):
        """Initialize bytes source.

        Args:
            data: Binary data
            doc_id: Document identifier
        """
        self._data = data
        self._doc_id = doc_id or str(uuid.uuid4())

    async def open(self, **kwargs) -> BinaryIO:
        """Open bytes as stream.

        Returns:
            BytesIO stream (seekable)
        """
        logger.debug(f"[{self._doc_id}] Opening BytesIO: {len(self._data)} bytes")
        return io.BytesIO(self._data)

    async def get_metadata(self) -> dict:
        """Get metadata.

        Returns:
            Dict with size and content_type
        """
        return {
            "size": len(self._data),
            "content_type": "application/octet-stream",
            "source": "memory",
            "doc_id": self._doc_id,
        }

    def supports_seeking(self) -> bool:
        """BytesIO is always seekable.

        Returns:
            True
        """
        return True


class LocalFileSource:
    """Stream source for local files.

    Use for files on the local filesystem.

    Example:
        >>> source = LocalFileSource("/path/to/file.pdf")
        >>> async with source.open() as stream:
        ...     process(stream)
    """

    __slots__ = ("_path", "_doc_id")

    def __init__(self, path: Path | str, doc_id: str | None = None):
        """Initialize local file source.

        Args:
            path: File path
            doc_id: Document identifier
        """
        self._path = Path(path)
        self._doc_id = doc_id or str(uuid.uuid4())

    async def open(self, **kwargs) -> BinaryIO:
        """Open local file.

        Returns:
            File stream (seekable)

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        if not self._path.exists():
            raise FileNotFoundError(f"File not found: {self._path}")

        logger.debug(f"[{self._doc_id}] Opening local file: {self._path}")
        return await asyncio.to_thread(open, self._path, "rb")

    async def get_metadata(self) -> dict:
        """Get file metadata.

        Returns:
            Dict with size, content_type, etc.
        """
        stat = await asyncio.to_thread(self._path.stat)

        return {
            "size": stat.st_size,
            "content_type": self._guess_content_type(),
            "source": "local",
            "path": str(self._path),
            "doc_id": self._doc_id,
        }

    def supports_seeking(self) -> bool:
        """Local files are always seekable.

        Returns:
            True
        """
        return True

    def _guess_content_type(self) -> str:
        """Guess content type from extension."""
        import mimetypes

        content_type, _ = mimetypes.guess_type(str(self._path))
        return content_type or "application/octet-stream"


class HTTPSource:
    """Stream source for HTTP/HTTPS URLs.

    Use for downloading files from web servers.

    Example:
        >>> source = HTTPSource("https://example.com/file.pdf")
        >>> async with source.open() as stream:
        ...     process(stream)
    """

    __slots__ = ("_url", "_doc_id")

    def __init__(self, url: str, doc_id: str | None = None):
        """Initialize HTTP source.

        Args:
            url: HTTP/HTTPS URL
            doc_id: Document identifier
        """
        self._url = url
        self._doc_id = doc_id or str(uuid.uuid4())

    async def open(self, **kwargs) -> BinaryIO:
        """Open HTTP URL as stream.

        Uses httpx for async streaming.

        Returns:
            Stream object (not seekable)
        """
        import httpx

        logger.debug(f"[{self._doc_id}] Opening HTTP stream: {self._url}")

        # Create async client
        client = httpx.AsyncClient(follow_redirects=True)

        # Stream response
        response = await client.get(self._url)
        response.raise_for_status()

        # Wrap in BytesIO for now (could be improved with streaming)
        content = await response.aread()
        await client.aclose()

        return io.BytesIO(content)

    async def get_metadata(self) -> dict:
        """Get HTTP metadata.

        Returns:
            Dict with size, content_type, etc.
        """
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.head(self._url, follow_redirects=True)
            return {
                "size": int(response.headers.get("content-length", 0)),
                "content_type": response.headers.get(
                    "content-type", "application/octet-stream"
                ),
                "source": "http",
                "url": self._url,
                "doc_id": self._doc_id,
            }

    def supports_seeking(self) -> bool:
        """HTTP streams are not seekable.

        Returns:
            False
        """
        return False
