"""Local file storage backend.

Stores files on the local filesystem with async operations
and safe file handling using utility functions.
"""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from somaai.providers.storage import StorageBackend
from somaai.utils.files import (
    async_delete_file,
    async_ensure_dir,
    async_file_exists,
    async_read_file,
    async_safe_write,
    async_write_file,
    compute_file_hash,
    generate_unique_path,
    safe_filename,
)
from somaai.utils.ids import generate_id


class LocalStorage(StorageBackend):
    """Local filesystem storage backend.

    Features:
    - Async file operations using aiofiles
    - Safe atomic writes to prevent corruption
    - Overwrite protection with unique path generation
    - File hashing for deduplication
    """

    def __init__(self, base_path: str | None = None) -> None:
        """Initialize local storage.

        Args:
            base_path: Base directory for file storage
        """
        from somaai.settings import settings

        self.base_path = Path(base_path or settings.storage_local_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _full_path(self, path: str) -> Path:
        """Get full filesystem path.

        Args:
            path: Relative path

        Returns:
            Full absolute path
        """
        return self.base_path / path

    async def save(
        self,
        file: bytes | BinaryIO,
        path: str,
        overwrite: bool = True,
        safe_write: bool = True,
    ) -> str:
        """Save a file to local storage.

        Args:
            file: File content as bytes or file-like object
            path: Relative destination path
            overwrite: If False, generate unique path if file exists
            safe_write: If True, use atomic write (temp file then move)

        Returns:
            Full filesystem path of saved file
        """
        full_path = self._full_path(path)

        # Ensure parent directory exists
        await async_ensure_dir(full_path.parent)

        # Get content
        content = file if isinstance(file, bytes) else file.read()

        # Handle overwrite protection
        if not overwrite and await async_file_exists(full_path):
            full_path = generate_unique_path(full_path.parent, full_path.name)

        # Write file
        if safe_write:
            await async_safe_write(full_path, content)
        else:
            await async_write_file(full_path, content, overwrite=True)

        return str(full_path)

    async def save_with_hash(
        self,
        file: bytes | BinaryIO,
        directory: str,
        original_filename: str,
    ) -> tuple[str, str]:
        """Save file using content hash as filename for deduplication.

        Args:
            file: File content
            directory: Target directory
            original_filename: Original filename for extension

        Returns:
            Tuple of (full_path, content_hash)
        """
        content = file if isinstance(file, bytes) else file.read()
        content_hash = compute_file_hash(content)

        # Use hash + original extension as filename
        ext = Path(original_filename).suffix
        hash_filename = f"{content_hash}{ext}"

        path = f"{directory}/{hash_filename}"
        full_path = self._full_path(path)

        # Only write if file doesn't exist (deduplication)
        if not await async_file_exists(full_path):
            await async_ensure_dir(full_path.parent)
            await async_safe_write(full_path, content)

        return str(full_path), content_hash

    async def get(self, path: str) -> bytes | None:
        """Retrieve file content from storage.

        Args:
            path: Relative storage path

        Returns:
            File content as bytes, or None if not found
        """
        full_path = self._full_path(path)

        if not await async_file_exists(full_path):
            return None

        return await async_read_file(full_path)

    async def get_url(self, path: str, expires_in: int = 3600) -> str | None:
        """Get a URL to access the file.

        For local storage, returns the filesystem path as file:// URL.
        In production, this might return a signed URL.

        Args:
            path: Relative storage path
            expires_in: Ignored for local storage

        Returns:
            File path as URL-like string, or None if not found
        """
        full_path = self._full_path(path)

        if not await async_file_exists(full_path):
            return None

        return f"file://{full_path}"

    async def delete(self, path: str) -> bool:
        """Delete a file from storage.

        Args:
            path: Relative storage path

        Returns:
            True if deleted, False if not found
        """
        full_path = self._full_path(path)
        return await async_delete_file(full_path)

    async def exists(self, path: str) -> bool:
        """Check if a file exists in storage.

        Args:
            path: Relative storage path

        Returns:
            True if file exists
        """
        return await async_file_exists(self._full_path(path))

    async def get_hash(self, path: str) -> str | None:
        """Get the content hash of a stored file.

        Useful for checking if content has changed.

        Args:
            path: Relative storage path

        Returns:
            SHA-256 hash of file content, or None if not found
        """
        content = await self.get(path)
        if content is None:
            return None
        return compute_file_hash(content)

    def sanitize_filename(self, filename: str) -> str:
        """Sanitize a filename for safe storage.

        Args:
            filename: Original filename

        Returns:
            Safe filename
        """
        return safe_filename(filename)

    def generate_storage_path(
        self,
        category: str,
        filename: str,
        use_id: bool = True,
    ) -> str:
        """Generate a structured storage path.

        Args:
            category: Category subdirectory (e.g., "documents", "images")
            filename: Original filename
            use_id: If True, include unique ID in path

        Returns:
            Relative storage path like "documents/abc123/file.pdf"
        """
        safe_name = self.sanitize_filename(filename)

        if use_id:
            unique_id = generate_id()
            return f"{category}/{unique_id}/{safe_name}"

        return f"{category}/{safe_name}"
