"""Streaming infrastructure for text extraction.

This module provides a pluggable, scalable streaming system that works
seamlessly with any text extraction strategy.

Architecture:
    - Protocol-based design (duck typing)
    - Strategy pattern for different storage backends
    - Factory pattern for stream creation
    - Context managers for resource safety
    - Generators for memory efficiency

Example:
    >>> from somaai.utils.text_extractor.streaming import StreamFactory
    >>> 
    >>> # Create stream from any source
    >>> async with StreamFactory.create("s3://bucket/file.pdf") as stream:
    ...     # Use with any extractor
    ...     result = await extractor.extract(stream)
"""

from .factory import StreamFactory
from .protocols import StreamProtocol, StreamSourceProtocol
from .sources import BytesSource, LocalFileSource, S3Source

__all__ = [
    "StreamFactory",
    "StreamProtocol",
    "StreamSourceProtocol",
    "BytesSource",
    "LocalFileSource",
    "S3Source",
]

__version__ = "1.0.0"
