class TextExtractionError(Exception):
    """Base exception for text extraction errors."""
    pass

class UnsupportedFileTypeError(TextExtractionError):
    """Raised when the file type is not supported."""
    pass

class OcrError(TextExtractionError):
    """Raised when OCR fails."""
    pass
