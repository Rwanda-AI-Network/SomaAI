"""File utilities for storage and file operations.

Provides utilities for:
- File existence checks with overwrite protection
- Safe file operations with atomic writes
- File hashing for deduplication
- Path manipulation and validation
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO

import aiofiles
import aiofiles.os


def ensure_dir(path: str | Path) -> Path:
    """Ensure a directory exists, creating if necessary.

    Args:
        path: Directory path to ensure

    Returns:
        Path object of the directory
    """
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_file_extension(filename: str) -> str:
    """Get file extension (lowercase, with dot).

    Args:
        filename: Filename or path

    Returns:
        Extension like ".pdf" or empty string
    """
    return Path(filename).suffix.lower()


def get_file_size(path: str | Path) -> int:
    """Get file size in bytes.

    Args:
        path: Path to file

    Returns:
        File size in bytes
    """
    return os.path.getsize(path)


def file_exists(path: str | Path) -> bool:
    """Check if a file exists.

    Args:
        path: Path to check

    Returns:
        True if file exists
    """
    return Path(path).is_file()


def dir_exists(path: str | Path) -> bool:
    """Check if a directory exists.

    Args:
        path: Path to check

    Returns:
        True if directory exists
    """
    return Path(path).is_dir()


def safe_filename(filename: str) -> str:
    """Sanitize a filename by removing/replacing unsafe characters.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename safe for filesystem
    """
    # Characters not allowed in filenames
    unsafe_chars = '<>:"/\\|?*'
    result = filename
    for char in unsafe_chars:
        result = result.replace(char, "_")
    # Remove leading/trailing spaces and dots
    result = result.strip(". ")
    return result or "unnamed"


def generate_unique_path(base_path: Path, filename: str) -> Path:
    """Generate a unique path that doesn't overwrite existing files.

    If file exists, adds a counter suffix: file.pdf -> file_1.pdf -> file_2.pdf

    Args:
        base_path: Base directory
        filename: Desired filename

    Returns:
        Unique path that doesn't exist
    """
    path = base_path / filename
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    counter = 1

    while True:
        new_name = f"{stem}_{counter}{suffix}"
        new_path = base_path / new_name
        if not new_path.exists():
            return new_path
        counter += 1


def compute_file_hash(file: bytes | BinaryIO, algorithm: str = "sha256") -> str:
    """Compute hash of file content for deduplication.

    Args:
        file: File content as bytes or file-like object
        algorithm: Hash algorithm (sha256, md5, sha1)

    Returns:
        Hex digest of the hash
    """
    hasher = hashlib.new(algorithm)
    content = file if isinstance(file, bytes) else file.read()
    hasher.update(content)
    return hasher.hexdigest()


async def async_file_exists(path: str | Path) -> bool:
    """Async check if a file exists.

    Args:
        path: Path to check

    Returns:
        True if file exists
    """
    try:
        await aiofiles.os.stat(str(path))
        return True
    except FileNotFoundError:
        return False


async def async_ensure_dir(path: str | Path) -> Path:
    """Async ensure a directory exists.

    Args:
        path: Directory path

    Returns:
        Path object
    """
    p = Path(path)
    try:
        await aiofiles.os.makedirs(str(p), exist_ok=True)
    except FileExistsError:
        pass
    return p


async def async_read_file(path: str | Path) -> bytes:
    """Async read file content.

    Args:
        path: Path to file

    Returns:
        File content as bytes

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    async with aiofiles.open(path, "rb") as f:
        return await f.read()


async def async_write_file(
    path: str | Path,
    content: bytes,
    overwrite: bool = True,
) -> Path:
    """Async write file with optional overwrite protection.

    Args:
        path: Destination path
        content: File content
        overwrite: If False, raises error if file exists

    Returns:
        Path where file was written

    Raises:
        FileExistsError: If file exists and overwrite=False
    """
    p = Path(path)

    if not overwrite and p.exists():
        raise FileExistsError(f"File already exists: {path}")

    # Ensure parent directory
    await async_ensure_dir(p.parent)

    async with aiofiles.open(p, "wb") as f:
        await f.write(content)

    return p


async def async_safe_write(
    path: str | Path,
    content: bytes,
) -> Path:
    """Async atomic write - writes to temp file then moves.

    Ensures file is either fully written or not at all.

    Args:
        path: Final destination path
        content: File content

    Returns:
        Path where file was written
    """
    p = Path(path)
    await async_ensure_dir(p.parent)

    # Write to temp file first
    fd, temp_path = tempfile.mkstemp(dir=str(p.parent))
    try:
        async with aiofiles.open(temp_path, "wb") as f:
            await f.write(content)
        # Atomic move
        shutil.move(temp_path, str(p))
    except Exception:
        # Cleanup temp file on error
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
    finally:
        try:
            os.close(fd)
        except OSError:
            pass

    return p


async def async_delete_file(path: str | Path) -> bool:
    """Async delete a file.

    Args:
        path: Path to delete

    Returns:
        True if deleted, False if not found
    """
    try:
        await aiofiles.os.remove(str(path))
        return True
    except FileNotFoundError:
        return False


def get_all_files(directory: str | Path, recursive: bool = False) -> list[Path]:
    """Get all files in a directory.

    Args:
        directory: Directory to scan
        recursive: If True, scan subdirectories

    Returns:
        List of file paths
    """
    p = Path(directory)
    if recursive:
        return [f for f in p.rglob("*") if f.is_file()]
    return [f for f in p.iterdir() if f.is_file()]


def get_all_directories(directory: str | Path) -> list[Path]:
    """Get all subdirectories in a directory.

    Args:
        directory: Directory to scan

    Returns:
        List of directory paths
    """
    p = Path(directory)
    return [d for d in p.iterdir() if d.is_dir()]
