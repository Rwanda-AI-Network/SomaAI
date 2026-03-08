"""MinIO object storage backend.

Provides S3-compatible object storage for local development.
Uses content-hash (SHA-256) based deduplication to prevent duplicate uploads.
"""

from __future__ import annotations

import hashlib
import io
import logging
from pathlib import Path
from typing import Any, BinaryIO

from somaai.providers.storage import StorageBackend

logger = logging.getLogger(__name__)


class MinioProvider(StorageBackend):
    """MinIO object storage backend for development.

    Features:
    - S3-compatible API via MinIO Python SDK
    - Auto-creates bucket on initialization
    - SHA-256 content-hash deduplication
    - Presigned URLs for file access
    - Thread-safe (sync SDK wrapped in asyncio.to_thread)
    """

    def __init__(
        self,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        secure: bool | None = None,
    ) -> None:
        """Initialize MinIO client.

        Args:
            endpoint: MinIO server endpoint (host:port)
            access_key: Access key (username)
            secret_key: Secret key (password)
            bucket: Default bucket name
            secure: Use HTTPS
        """
        from minio import Minio

        from somaai.settings import settings

        self.endpoint = endpoint or settings.storage.minio_endpoint
        self.access_key = access_key or settings.storage.minio_access_key
        if secret_key is not None:
            self.secret_key = (
                secret_key.get_secret_value()
                if hasattr(secret_key, "get_secret_value")
                else secret_key
            )
        else:
            self.secret_key = (
                settings.storage.minio_secret_key.get_secret_value()
                if settings.storage.minio_secret_key
                else ""
            )
        self.bucket = bucket or settings.storage.minio_bucket
        self.secure = secure if secure is not None else settings.storage.minio_secure

        self.client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure,
        )

        # Auto-create bucket if it doesn't exist
        self._ensure_bucket()

    @property
    def backend_type(self) -> str:
        return "minio"

    def _ensure_bucket(self) -> None:
        """Create bucket if it does not exist."""
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
                logger.info(f"Created MinIO bucket: {self.bucket}")
        except Exception as e:
            logger.warning(f"Could not verify/create bucket '{self.bucket}': {e}")

    @staticmethod
    def _compute_hash(content: bytes) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content).hexdigest()

    async def save(self, file: bytes | BinaryIO, path: str) -> str:
        """Save a file to MinIO.

        Args:
            file: File content as bytes or file-like object
            path: Object key (destination path in bucket)

        Returns:
            Object key of saved file
        """
        import asyncio

        if isinstance(file, bytes):
            data = io.BytesIO(file)
            length = len(file)
        else:
            data = file
            # Try to get length, fallback to -1 (stream) if unknown
            try:
                data.seek(0, io.SEEK_END)
                length = data.tell()
                data.seek(0)
            except (AttributeError, io.UnsupportedOperation):
                length = -1

        await asyncio.to_thread(
            self.client.put_object,
            self.bucket,
            path,
            data,
            length=length,
            # Use 10MB parts for streaming (unknown-length) uploads.
            # Default 5MB creates too many parts for large files.
            part_size=10 * 1024 * 1024 if length == -1 else 0,
        )

        logger.debug(f"Saved object: {self.bucket}/{path}")
        return path

    async def save_deduplicated(
        self,
        file: bytes | BinaryIO,
        directory: str,
        original_filename: str,
    ) -> tuple[str, str, bool]:
        """Upload with SHA-256 content-hash deduplication.

        Args:
            file: File content as bytes or file-like object
            directory: Target directory prefix (e.g. "documents")
            original_filename: Original filename (used for extension)

        Returns:
            Tuple of (object_key, content_hash, was_deduplicated)
        """
        import tempfile

        # Handle raw bytes
        if isinstance(file, bytes):
            content_hash = self._compute_hash(file)
            data_to_save = file
        else:
            # Handle file-like objects
            sha256 = hashlib.sha256()

            # Check if seekable. If not, we MUST buffer to compute hash first.
            try:
                file.seek(0)
                is_seekable = True
            except (AttributeError, io.UnsupportedOperation):
                is_seekable = False

            if is_seekable:
                # Seekable stream: hash in chunks, then rewind
                while chunk := file.read(65536):
                    sha256.update(chunk)
                content_hash = sha256.hexdigest()
                file.seek(0)
                data_to_save = file
            else:
                # Non-seekable stream: buffer to a spooled temporary file
                # This keeps small files in RAM and spills large ones to disk.
                tmp = tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024)
                while chunk := file.read(65536):
                    sha256.update(chunk)
                    tmp.write(chunk)

                content_hash = sha256.hexdigest()
                tmp.seek(0)
                data_to_save = tmp

        # Build object key: directory/hash.ext
        ext = Path(original_filename).suffix.lower()
        object_key = f"{directory}/{content_hash}{ext}"

        # Check if object already exists (dedup)
        if await self.exists(object_key):
            logger.info(f"Dedup hit: {object_key} already exists, skipping upload")
            # Close the temp file if we created one
            if not isinstance(file, bytes) and not is_seekable:
                data_to_save.close()
            return object_key, content_hash, True

        # Upload using the base save method
        try:
            await self.save(data_to_save, object_key)
        finally:
            # Cleanup temp file if created
            if not isinstance(file, bytes) and not is_seekable:
                data_to_save.close()

        logger.info(f"Uploaded new object: {self.bucket}/{object_key}")
        return object_key, content_hash, False

    async def get(self, path: str) -> bytes | None:
        """Retrieve file content from MinIO.

        Args:
            path: Object key

        Returns:
            File content as bytes, or None if not found
        """
        stream = await self.get_stream(path)
        if stream is None:
            return None

        from somaai.providers.storage import StorageStream

        async with StorageStream(stream) as s:
            return s.read()

    async def get_stream(self, path: str) -> BinaryIO | None:
        """Retrieve file as a stream from MinIO.

        Args:
            path: Object key

        Returns:
            File-like object (BinaryIO), or None if not found
        """
        import asyncio

        try:
            response = await asyncio.to_thread(
                self.client.get_object, self.bucket, path
            )
            return response
        except Exception as e:
            if "NoSuchKey" in str(e) or "not found" in str(e).lower():
                return None
            raise

    async def delete(self, path: str) -> bool:
        """Delete a file from MinIO.

        Args:
            path: Object key

        Returns:
            True if deleted, False if not found
        """
        import asyncio

        if not await self.exists(path):
            return False

        await asyncio.to_thread(self.client.remove_object, self.bucket, path)
        return True

    async def get_metadata(self, path: str) -> dict[str, Any] | None:
        """Get object metadata from MinIO."""
        import asyncio

        try:
            stat = await asyncio.to_thread(self.client.stat_object, self.bucket, path)
            return {
                "size": stat.size,
                "content_type": stat.content_type,
                "last_modified": stat.last_modified,
                "metadata": stat.metadata,
                "etag": stat.etag,
            }
        except Exception:
            return None

    async def get_url(self, path: str, expires_in: int = 3600) -> str | None:
        """Get a presigned URL to access the file from MinIO.

        Args:
            path: Object key
            expires_in: URL expiration time in seconds

        Returns:
            Presigned URL, or None if not found or on error
        """
        import asyncio
        from datetime import timedelta

        if not await self.exists(path):
            return None

        try:
            url = await asyncio.to_thread(
                self.client.presigned_get_object,
                self.bucket,
                path,
                expires=timedelta(seconds=expires_in),
            )
            return url
        except Exception as e:
            logger.error(f"Failed to generate presigned URL for {path}: {e}")
            return None

    async def exists(self, path: str) -> bool:
        import asyncio

        try:
            await asyncio.to_thread(self.client.stat_object, self.bucket, path)
            return True
        except Exception:
            return False

    async def list_objects(self, prefix: str) -> list[str]:
        """List objects with a given prefix.

        Args:
            prefix: Object key prefix to filter by

        Returns:
            List of object keys matching the prefix
        """
        import asyncio

        objects = await asyncio.to_thread(
            lambda: list(self.client.list_objects(self.bucket, prefix=prefix))
        )
        return [obj.object_name for obj in objects if obj.object_name]

    async def compose_objects(
        self,
        dest_path: str,
        src_paths: list[str],
        content_type: str | None = None,
    ) -> bool:
        """Combine multiple objects into a single one (server-side).

        Uses MinIO's compose_object which is a server-side operation.
        """
        import asyncio

        from minio.commonconfig import ComposeSource

        sources = [ComposeSource(self.bucket, src) for src in src_paths]

        try:
            await asyncio.to_thread(
                self.client.compose_object,
                self.bucket,
                dest_path,
                sources,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to compose objects to {dest_path}: {e}")
            return False
