from .core import TextExtractor, extract
from .exceptions import OcrError, TextExtractionError, UnsupportedFileTypeError
from .registry import ExtractorRegistry
from .strategies.base import ExtractionResult, Page, Section, Table

# Alias for backward compatibility or cleaner naming
extract_text = extract

__all__ = [
    "ExtractorRegistry",
    "TextExtractionError",
    "OcrError",
    "UnsupportedFileTypeError",
    "ExtractionResult",
    "Page",
    "Section",
    "Table",
    "extract_text",
    "TextExtractor",
]
