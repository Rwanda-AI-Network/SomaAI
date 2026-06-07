"""Streaming infrastructure for text extraction.

This module provides a pluggable streaming system that works
seamlessly with any text extraction strategy.

Architecture:
    - Protocol-based design (duck typing)
    - Strategy pattern for different storage backends
    - Factory pattern for stream creation
    - Context managers for resource safety

Example:
    >>> from somaai.utils.text_extractor.streaming import StreamFactory
    >>>
    >>> # Create stream from any source
    >>> async with StreamFactory.create("/path/to/file.pdf") as stream:
    ...     result = await extractor.extract(stream)
"""

from .factory import StreamFactory
from .protocols import StreamProtocol, StreamSourceProtocol
from .sources import BytesSource, LocalFileSource

__all__ = [
    "StreamFactory",
    "StreamProtocol",
    "StreamSourceProtocol",
    "BytesSource",
    "LocalFileSource",
]

__version__ = "1.0.0"
