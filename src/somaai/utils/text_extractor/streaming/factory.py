"""Stream factory for creating streams from any source (Factory pattern).

Provides a unified interface for creating streams from different sources
with automatic adapter selection for seekability.
"""

import asyncio
import logging
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Self

from .adapters import AdapterFactory
from .sources import BytesSource, HTTPSource, LocalFileSource

logger = logging.getLogger(__name__)


class ManagedStream:
    """Managed stream with automatic cleanup (Context Manager + RAII).

    Wraps a stream and ensures cleanup even on exceptions.
    Implements async context manager protocol.

    Example:
        >>> async with ManagedStream(stream, temp_path) as managed:
        ...     process(managed.stream)
        ... # Automatic cleanup here
    """

    __slots__ = ("stream", "temp_path", "doc_id", "_closed", "_cleanup_callbacks")

    def __init__(
        self,
        stream: BinaryIO,
        temp_path: Path | None = None,
        doc_id: str | None = None,
    ):
        """Initialize managed stream.

        Args:
            stream: Stream to manage
            temp_path: Temp file path (for cleanup)
            doc_id: Document identifier
        """
        self.stream = stream
        self.temp_path = temp_path
        self.doc_id = doc_id
        self._closed = False
        self._cleanup_callbacks: list = []

    def add_cleanup_callback(self, callback) -> None:
        """Add callback to run on cleanup."""
        self._cleanup_callbacks.append(callback)

    async def _cleanup(self) -> None:
        """Internal cleanup."""
        if self._closed:
            return

        self._closed = True

        # Run callbacks
        for callback in self._cleanup_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.warning(f"[{self.doc_id}] Cleanup callback failed: {e}")

        # Close stream
        try:
            if hasattr(self.stream, "close"):
                await asyncio.to_thread(self.stream.close)
        except Exception as e:
            logger.warning(f"[{self.doc_id}] Failed to close stream: {e}")

        # Delete temp file
        if self.temp_path and self.temp_path.exists():
            try:
                await asyncio.to_thread(self.temp_path.unlink)
                logger.debug(f"[{self.doc_id}] Deleted temp file: {self.temp_path}")
            except Exception as e:
                logger.warning(f"[{self.doc_id}] Failed to delete temp file: {e}")

        # Check for temp path stored on stream object
        if hasattr(self.stream, "_temp_path"):
            temp_path = Path(self.stream._temp_path)
            if temp_path.exists():
                try:
                    await asyncio.to_thread(temp_path.unlink)
                    logger.debug(
                        "[%s] Deleted adapter temp file: %s", self.doc_id, temp_path
                    )
                except Exception as e:
                    logger.warning(
                        "[%s] Failed to delete adapter temp: %s", self.doc_id, e
                    )

    async def __aenter__(self) -> Self:
        """Enter async context."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit async context with cleanup."""
        await self._cleanup()

    def __del__(self):
        """Destructor as safety net."""
        if not self._closed:
            logger.warning(
                f"[{self.doc_id}] ManagedStream not properly closed. "
                "Use 'async with' for guaranteed cleanup."
            )


class StreamFactory:
    """Factory for creating managed streams from any source.

    Provides a unified interface for creating streams with automatic:
    - Source detection (S3, local, bytes, HTTP)
    - Adapter selection (memory, disk, spool)
    - Resource management (cleanup)

    Example:
        >>> # From S3
        >>> async with StreamFactory.create("s3://bucket/key.pdf") as stream:
        ...     process(stream.stream)
        >>>
        >>> # From local file
        >>> async with StreamFactory.create("/path/to/file.pdf") as stream:
        ...     process(stream.stream)
        >>>
        >>> # From bytes
        >>> async with StreamFactory.create(pdf_bytes) as stream:
        ...     process(stream.stream)
    """

    @classmethod
    async def create(
        cls,
        source: str | bytes | Path,
        doc_id: str | None = None,
        ensure_seekable: bool = True,
        adapter_strategy: str | None = None,
        **kwargs,
    ) -> ManagedStream:
        """Create managed stream from any source.

        Args:
            source: Source (URI, bytes, or Path)
            doc_id: Document identifier
            ensure_seekable: Convert to seekable if needed
            adapter_strategy: Force adapter strategy ('memory', 'disk', 'spool')
            **kwargs: Source-specific options

        Returns:
            ManagedStream instance

        Example:
            >>> # S3 with custom endpoint
            >>> stream = await StreamFactory.create(
            ...     "s3://bucket/key.pdf",
            ...     endpoint="http://minio:9000",
            ...     access_key="...",
            ...     secret_key="..."
            ... )
        """
        # Detect source type and create appropriate source
        if isinstance(source, bytes):
            # Bytes source
            source_obj = BytesSource(source, doc_id=doc_id)

        elif isinstance(source, (str, Path)):
            source_str = str(source)

            if source_str.startswith(("http://", "https://")):
                # HTTP source
                source_obj = HTTPSource(source_str, doc_id=doc_id)

            else:
                # Local file
                source_obj = LocalFileSource(source_str, doc_id=doc_id)

        else:
            raise TypeError(f"Unsupported source type: {type(source)}")

        # Get metadata
        metadata = await source_obj.get_metadata()
        doc_id = metadata["doc_id"]

        logger.info(
            f"[{doc_id}] Creating stream from {metadata['source']} "
            f"(size={metadata.get('size', 'unknown')})"
        )

        # Open stream
        stream = await source_obj.open(**kwargs)

        # Check if seekable
        is_seekable = cls._is_seekable(stream)

        if ensure_seekable and not is_seekable:
            # Need to adapt
            logger.info(f"[{doc_id}] Stream not seekable, adapting...")

            # Create adapter
            adapter = AdapterFactory.create(
                size_hint=metadata.get("size"),
                force_strategy=adapter_strategy,
                doc_id=doc_id,
                **kwargs,
            )

            # Adapt stream
            stream = await adapter.adapt(stream, size_hint=metadata.get("size"))

            logger.info(
                "[%s] Stream adapted using %s strategy",
                doc_id,
                adapter.get_strategy_name(),
            )

        # Create managed stream
        return ManagedStream(stream=stream, doc_id=doc_id)



    @staticmethod
    def _is_seekable(stream: BinaryIO) -> bool:
        """Check if stream is seekable.

        Args:
            stream: Stream to check

        Returns:
            True if seekable
        """
        try:
            if hasattr(stream, "seekable"):
                return stream.seekable()

            # Try seeking
            pos = stream.tell()
            stream.seek(pos)
            return True
        except (AttributeError, OSError):
            return False

    @classmethod
    def configure(cls, **settings) -> None:
        """Configure factory settings.

        Args:
            **settings: Configuration options
                - small_threshold: Small file threshold (bytes)
                - large_threshold: Large file threshold (bytes)

        Example:
            >>> StreamFactory.configure(
            ...     small_threshold=5 * 1024 * 1024,  # 5MB
            ...     large_threshold=50 * 1024 * 1024  # 50MB
            ... )
        """
        if "small_threshold" in settings and "large_threshold" in settings:
            AdapterFactory.configure_thresholds(
                small=settings["small_threshold"], large=settings["large_threshold"]
            )

        logger.info(f"StreamFactory configured: {settings}")
