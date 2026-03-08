"""Stream adapters for converting non-seekable streams to seekable.

Implements multiple strategies (Strategy pattern) for different use cases.
"""

import asyncio
import io
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import BinaryIO

logger = logging.getLogger(__name__)


class MemoryAdapter:
    """Adapter that buffers stream to RAM.
    
    Fast but memory-intensive. Use for small files (<10MB).
    
    Strategy: Read entire stream into BytesIO.
    Memory: O(file_size)
    Speed: Fastest
    """

    __slots__ = ("_doc_id",)

    def __init__(self, doc_id: str | None = None):
        self._doc_id = doc_id or str(uuid.uuid4())

    async def adapt(self, stream: BinaryIO, size_hint: int | None = None) -> BinaryIO:
        """Buffer stream to memory.
        
        Args:
            stream: Input stream
            size_hint: Expected size (for pre-allocation)
        
        Returns:
            BytesIO (seekable)
        """
        logger.debug(
            f"[{self._doc_id}] Buffering to RAM (size_hint={size_hint or 'unknown'})"
        )

        # Pre-allocate if size known
        if size_hint:
            data = bytearray(size_hint)
            bytes_read = await asyncio.to_thread(stream.readinto, data)
            if bytes_read < size_hint:
                data = data[:bytes_read]
            result = io.BytesIO(bytes(data))
        else:
            # Size unknown, read all
            data = await asyncio.to_thread(stream.read)
            result = io.BytesIO(data)

        logger.debug(f"[{self._doc_id}] Buffered to RAM: {len(data):,} bytes")
        return result

    def get_strategy_name(self) -> str:
        return "memory"


class DiskAdapter:
    """Adapter that buffers stream to disk.
    
    Slower but handles large files. Use for files >100MB.
    
    Strategy: Stream to temp file in chunks.
    Memory: O(chunk_size) = constant
    Speed: Slower (disk I/O)
    """

    __slots__ = ("_doc_id", "_temp_dir", "_prefix", "_chunk_size")

    def __init__(
        self,
        doc_id: str | None = None,
        temp_dir: str | None = None,
        prefix: str = "somaai_",
        chunk_size: int = 64 * 1024,
    ):
        """Initialize disk adapter.
        
        Args:
            doc_id: Document identifier
            temp_dir: Custom temp directory
            prefix: Temp file prefix
            chunk_size: Bytes per chunk
        """
        self._doc_id = doc_id or str(uuid.uuid4())
        self._temp_dir = temp_dir
        self._prefix = prefix
        self._chunk_size = chunk_size

    async def adapt(self, stream: BinaryIO, size_hint: int | None = None) -> BinaryIO:
        """Buffer stream to disk.
        
        Args:
            stream: Input stream
            size_hint: Expected size (for logging)
        
        Returns:
            File stream (seekable)
        """
        logger.debug(
            f"[{self._doc_id}] Buffering to disk (size_hint={size_hint or 'unknown'})"
        )

        # Get temp directory
        temp_dir = Path(self._temp_dir or tempfile.gettempdir())
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Create temp file with unique ID
        temp_path = (
            temp_dir / f"{self._prefix}{self._doc_id}_{uuid.uuid4().hex[:8]}.tmp"
        )

        # Stream to disk in chunks
        bytes_written = 0
        with open(temp_path, "wb") as tmp:
            while True:
                chunk = await asyncio.to_thread(stream.read, self._chunk_size)
                if not chunk:
                    break
                await asyncio.to_thread(tmp.write, chunk)
                bytes_written += len(chunk)

            # Flush to disk
            await asyncio.to_thread(tmp.flush)
            await asyncio.to_thread(os.fsync, tmp.fileno())

        logger.info(
            f"[{self._doc_id}] Buffered to disk: {temp_path} ({bytes_written:,} bytes)"
        )

        # Open for reading
        result = await asyncio.to_thread(open, temp_path, "rb")

        # Store path for cleanup
        result._temp_path = temp_path  # type: ignore

        return result

    def get_strategy_name(self) -> str:
        return "disk"


class SpoolAdapter:
    """Adapter that uses SpooledTemporaryFile (RAM → disk spillover).
    
    Best balance for medium files (10-100MB). Starts in RAM, spills to disk.
    
    Strategy: Use SpooledTemporaryFile with threshold.
    Memory: O(min(file_size, threshold))
    Speed: Fast for small, acceptable for large
    """

    __slots__ = ("_doc_id", "_threshold", "_chunk_size")

    def __init__(
        self,
        doc_id: str | None = None,
        threshold: int = 10 * 1024 * 1024,
        chunk_size: int = 64 * 1024,
    ):
        """Initialize spool adapter.
        
        Args:
            doc_id: Document identifier
            threshold: Bytes before spilling to disk
            chunk_size: Bytes per chunk
        """
        self._doc_id = doc_id or str(uuid.uuid4())
        self._threshold = threshold
        self._chunk_size = chunk_size

    async def adapt(self, stream: BinaryIO, size_hint: int | None = None) -> BinaryIO:
        """Buffer stream with spillover.
        
        Args:
            stream: Input stream
            size_hint: Expected size
        
        Returns:
            SpooledTemporaryFile (seekable)
        """
        logger.debug(
            f"[{self._doc_id}] Buffering with spillover "
            f"(threshold={self._threshold:,}, size_hint={size_hint or 'unknown'})"
        )

        # Create spool file
        spool = tempfile.SpooledTemporaryFile(max_size=self._threshold, mode="w+b")

        # Stream in chunks
        bytes_written = 0
        while True:
            chunk = await asyncio.to_thread(stream.read, self._chunk_size)
            if not chunk:
                break
            await asyncio.to_thread(spool.write, chunk)
            bytes_written += len(chunk)

        # Rewind
        await asyncio.to_thread(spool.seek, 0)

        # Log if spilled
        if spool._rolled:  # type: ignore
            logger.info(
                f"[{self._doc_id}] Spilled to disk: {bytes_written:,} bytes "
                f"(exceeded {self._threshold:,} threshold)"
            )
        else:
            logger.debug(f"[{self._doc_id}] Buffered in RAM: {bytes_written:,} bytes")

        return spool

    def get_strategy_name(self) -> str:
        return "spool"


class AdapterFactory:
    """Factory for creating adapters based on file size (Strategy pattern).
    
    Automatically selects the best adapter strategy:
    - <10MB: MemoryAdapter (fastest)
    - 10-100MB: SpoolAdapter (balanced)
    - >100MB: DiskAdapter (handles large files)
    
    Example:
        >>> factory = AdapterFactory()
        >>> adapter = factory.create(size_hint=50_000_000)
        >>> seekable = await adapter.adapt(stream)
    """

    # Thresholds (configurable)
    SMALL_FILE_THRESHOLD = 10 * 1024 * 1024  # 10MB
    LARGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 100MB

    @classmethod
    def create(
        cls,
        size_hint: int | None = None,
        force_strategy: str | None = None,
        **kwargs,
    ):
        """Create adapter based on size.
        
        Args:
            size_hint: Expected file size
            force_strategy: Force specific strategy ('memory', 'disk', 'spool')
            **kwargs: Adapter-specific options
        
        Returns:
            Adapter instance
        """
        # Force specific strategy if requested
        if force_strategy:
            if force_strategy == "memory":
                return MemoryAdapter(**kwargs)
            elif force_strategy == "disk":
                return DiskAdapter(**kwargs)
            elif force_strategy == "spool":
                return SpoolAdapter(**kwargs)
            else:
                raise ValueError(f"Unknown strategy: {force_strategy}")

        # Auto-select based on size
        if size_hint is None:
            # Unknown size: use spool (safe default)
            return SpoolAdapter(**kwargs)

        if size_hint < cls.SMALL_FILE_THRESHOLD:
            return MemoryAdapter(**kwargs)
        elif size_hint < cls.LARGE_FILE_THRESHOLD:
            return SpoolAdapter(**kwargs)
        else:
            return DiskAdapter(**kwargs)

    @classmethod
    def configure_thresholds(cls, small: int, large: int) -> None:
        """Configure size thresholds.
        
        Args:
            small: Small file threshold (bytes)
            large: Large file threshold (bytes)
        """
        cls.SMALL_FILE_THRESHOLD = small
        cls.LARGE_FILE_THRESHOLD = large
        logger.info(
            f"Adapter thresholds configured: "
            f"small={small:,}, large={large:,}"
        )
