"""Storage backend abstraction.

Provides unified interface for file storage with multiple backend support.
"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, BinaryIO

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class StorageStream:
    """RAII wrapper around raw storage streams.

    Guarantees cleanup of the underlying stream regardless of how the caller
    exits (return, exception, cancel). Works with both MinIO responses
    (which need ``release_conn()``) and S3/boto ``StreamingBody`` objects.

    Usage::

        async with storage.open(key) as stream:
            while chunk := stream.read(65536):
                sha256.update(chunk)
        # stream is guaranteed closed here

    You can also hash the entire stream in one call::

        digest = stream.hexdigest()
    """

    __slots__ = ("_raw", "_closed")

    def __init__(self, raw: BinaryIO) -> None:
        self._raw = raw
        self._closed = False

    # --- Delegate reads to the underlying stream ---

    def read(self, n: int = -1) -> bytes:
        """Read up to *n* bytes from the stream."""
        return self._raw.read(n)

    def seek(self, pos: int, whence: int = 0) -> int:
        """Seek if the underlying stream supports it."""
        return self._raw.seek(pos, whence)

    def tell(self) -> int:
        """Return the current stream position."""
        return self._raw.tell()

    @property
    def closed(self) -> bool:
        return self._closed

    # --- Hashing helpers ---

    def hexdigest(self, algo: str = "sha256", chunk_size: int = 65536) -> str:
        """Compute hex digest by streaming through the hash.

        Reads the stream in ``chunk_size`` windows, so memory stays O(chunk_size)
        regardless of file size. Seeks back to 0 if the stream is seekable.

        Args:
            algo: Hash algorithm name (anything in ``hashlib``).
            chunk_size: Read buffer size in bytes.

        Returns:
            Hex digest string.
        """
        h = hashlib.new(algo)
        while block := self._raw.read(chunk_size):
            h.update(block)
        # Try to rewind for downstream consumers
        try:
            self._raw.seek(0)
        except Exception:
            pass
        return h.hexdigest()

    # --- Context manager protocol ---

    async def __aenter__(self) -> StorageStream:
        return self

    async def __aexit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        """Release all resources held by the stream."""
        if self._closed:
            return
        self._closed = True
        try:
            if hasattr(self._raw, "close"):
                self._raw.close()
        except Exception as e:
            logger.debug(f"Error closing stream: {e}")
        try:
            # MinIO responses need explicit connection release
            if hasattr(self._raw, "release_conn"):
                self._raw.release_conn()
        except Exception as e:
            logger.debug(f"Error releasing connection: {e}")

    def __del__(self) -> None:
        """Safety net — close if the caller forgot."""
        if not self._closed:
            self.close()


class StorageBackend(ABC):
    """Abstract base class for storage backends.

    Implement this interface to add new storage backends.
    All backends must support:
    - save / save_deduplicated (upload)
    - get / get_stream / open (download)
    - get_url (presigned URL)
    - delete / exists / list_objects / compose_objects
    """

    @abstractmethod
    async def save(self, file: bytes | BinaryIO, path: str) -> str:
        """Save a file to storage.

        Args:
            file: File-like object or bytes to save
            path: Destination path/key

        Returns:
            Object key of saved file
        """
        pass

    @abstractmethod
    async def save_deduplicated(
        self,
        file: bytes | BinaryIO,
        directory: str,
        original_filename: str,
    ) -> tuple[str, str, bool]:
        """Save with SHA-256 content-hash deduplication.

        Computes SHA-256 of content and uses it as the object key.
        Skips upload if an object with the same hash already exists.

        Args:
            file: File content as bytes or file-like object
            directory: Target directory/prefix (e.g. "documents")
            original_filename: Original filename (used for extension)

        Returns:
            Tuple of (object_key, content_hash, was_deduplicated)
        """
        pass

    @abstractmethod
    async def get(self, path: str) -> bytes | None:
        """Retrieve file content from storage.

        Args:
            path: Storage path/key

        Returns:
            File content as bytes, or None if not found
        """
        pass

    @abstractmethod
    async def get_stream(self, path: str) -> BinaryIO | None:
        """Retrieve file as a raw stream from storage.

        .. note::
            Prefer :meth:`open` which returns a :class:`StorageStream` context
            manager that guarantees cleanup.

        Args:
            path: Object key

        Returns:
            File-like object (BinaryIO), or None if not found
        """
        pass

    @asynccontextmanager
    async def open(self, path: str) -> AsyncGenerator[StorageStream, None]:
        """Open a storage object as a managed stream.

        This is the **preferred** way to read from storage. The returned
        :class:`StorageStream` is an async context manager that guarantees
        ``close()`` and ``release_conn()`` are called on exit.

        Usage::

            async with storage.open("documents/abc.pdf") as stream:
                digest = stream.hexdigest()  # O(64KB) memory

        Args:
            path: Object key

        Yields:
            StorageStream wrapping the raw provider response

        Raises:
            FileNotFoundError: if the object does not exist
        """
        raw = await self.get_stream(path)
        if raw is None:
            raise FileNotFoundError(f"Object not found in storage: {path}")
        wrapper = StorageStream(raw)
        try:
            yield wrapper
        finally:
            wrapper.close()

    @abstractmethod
    async def get_url(self, path: str, expires_in: int = 3600) -> str | None:
        """Get a URL to access the file.

        Args:
            path: Storage path/key
            expires_in: URL expiration time in seconds (for signed URLs)

        Returns:
            Accessible URL for the file, or None if not found
        """
        pass

    @abstractmethod
    async def delete(self, path: str) -> bool:
        """Delete a file from storage.

        Args:
            path: Storage path/key

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def get_metadata(self, path: str) -> dict[str, Any] | None:
        """Get object metadata (size, content_type, etc.).

        Args:
            path: Storage path/key

        Returns:
            Dict of metadata, or None if not found
        """
        pass

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if a file exists in storage.

        Args:
            path: Storage path/key

        Returns:
            True if file exists
        """
        pass

    @abstractmethod
    async def list_objects(self, prefix: str) -> list[str]: ...

    @abstractmethod
    async def compose_objects(
        self,
        dest_path: str,
        src_paths: list[str],
        content_type: str | None = None,
    ) -> bool:
        """Combine multiple objects into a single one (server-side).

        Args:
            dest_path: Storage path/key for the final combined object
            src_paths: List of object keys to combine, in order
            content_type: Optional MIME type for the destination object

        Returns:
            True if successful
        """
        pass


def get_storage() -> StorageBackend:
    """Get configured storage backend.

    Returns storage backend based on STORAGE_BACKEND env var:
        - 'minio': MinioProvider (development)
        - 's3': S3Provider (production)

    Returns:
        Configured StorageBackend instance

    Raises:
        ValueError: If STORAGE_BACKEND is not recognized
    """
    from somaai.settings import settings

    backend = settings.storage_backend.lower()

    if backend == "minio":
        from somaai.providers.storage_minio import MinioProvider

        return MinioProvider()

    if backend == "s3":
        from somaai.providers.storage_s3 import S3Provider

        return S3Provider()

    raise ValueError(
        f"Unknown storage backend: '{backend}'. "
        f"Supported backends: 'minio' (dev), 's3' (prod)"
    )
