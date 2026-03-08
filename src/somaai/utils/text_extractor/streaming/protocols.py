"""Protocol definitions for streaming system.

Uses Python's Protocol (PEP 544) for structural subtyping, enabling
duck typing with type safety.
"""

from typing import AsyncIterator, BinaryIO, Protocol, runtime_checkable


@runtime_checkable
class StreamProtocol(Protocol):
    """Protocol for stream objects.
    
    Any object implementing these methods can be used as a stream,
    enabling maximum flexibility and extensibility.
    """

    def read(self, n: int = -1) -> bytes:
        """Read up to n bytes."""
        ...

    def seek(self, pos: int, whence: int = 0) -> int:
        """Seek to position."""
        ...

    def tell(self) -> int:
        """Return current position."""
        ...

    def close(self) -> None:
        """Close the stream."""
        ...

    @property
    def closed(self) -> bool:
        """Check if stream is closed."""
        ...


@runtime_checkable
class SeekableStreamProtocol(StreamProtocol, Protocol):
    """Protocol for seekable streams.
    
    Extends StreamProtocol with seekability guarantee.
    """

    def seekable(self) -> bool:
        """Check if stream is seekable."""
        ...


@runtime_checkable
class StreamSourceProtocol(Protocol):
    """Protocol for stream sources.
    
    A stream source knows how to create streams from a specific
    storage backend (S3, local file, bytes, etc.).
    
    This enables the Strategy pattern - different sources can be
    swapped without changing client code.
    """

    async def open(self, **kwargs) -> BinaryIO:
        """Open and return a stream.
        
        Returns:
            Binary stream object
        """
        ...

    async def get_metadata(self) -> dict:
        """Get metadata about the source.
        
        Returns:
            Dict with keys: size, content_type, etc.
        """
        ...

    def supports_seeking(self) -> bool:
        """Check if source supports seeking.
        
        Returns:
            True if seekable, False otherwise
        """
        ...


@runtime_checkable
class StreamAdapterProtocol(Protocol):
    """Protocol for stream adapters.
    
    Adapters convert non-seekable streams to seekable ones.
    Multiple adapter strategies can be implemented.
    """

    async def adapt(self, stream: BinaryIO, **kwargs) -> BinaryIO:
        """Adapt stream to be seekable.
        
        Args:
            stream: Input stream (may be non-seekable)
            **kwargs: Adapter-specific options
        
        Returns:
            Seekable stream
        """
        ...

    def get_strategy_name(self) -> str:
        """Get adapter strategy name.
        
        Returns:
            Strategy name (e.g., 'memory', 'disk', 'spool')
        """
        ...
