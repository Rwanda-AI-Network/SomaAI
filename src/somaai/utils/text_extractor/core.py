import io
import logging
from pathlib import Path
from typing import Union, Optional, BinaryIO

from .registry import ExtractorRegistry
from .strategies.base import ExtractionResult
from .exceptions import TextExtractionError

logger = logging.getLogger(__name__)

class TextExtractor:
    """
    High-level orchestrator for text extraction.
    Simplifies the process by handling input normalization and strategy selection.
    """

    @staticmethod
    def extract(
        input_data: Union[str, Path, bytes, BinaryIO],
        filename: Optional[str] = None,
        ocr_mode: str = 'auto',  # 'auto', 'force', 'skip'
        language: str = 'eng'
    ) -> ExtractionResult:
        """
        Extract text from various input sources.

        Args:
            input_data: File path (str/Path), bytes, or file-like object.
            filename: Optional filename to help with type detection (useful if input is bytes).
            ocr_mode: 'auto' (default), 'force' (always use OCR), 'skip' (never use OCR).
            language: Language code for OCR (default: 'eng').

        Returns:
            ExtractionResult object.
        """
        stream: Optional[BinaryIO] = None
        should_close = False

        try:
            # 1. Normalize Input to Stream
            if isinstance(input_data, (str, Path)):
                path = Path(input_data)
                if not path.exists():
                    raise TextExtractionError(f"File not found: {path}")
                filename = filename or path.name
                stream = open(path, "rb")
                should_close = True
            elif isinstance(input_data, bytes):
                stream = io.BytesIO(input_data)
                filename = filename or "unknown_file"
            elif hasattr(input_data, "read"):
                stream = input_data
                filename = filename or getattr(input_data, "name", "unknown_stream")
            else:
                raise TextExtractionError(f"Unsupported input type: {type(input_data)}")

            logger.info(f"Processing extraction for: {filename} (Mode: {ocr_mode})")

            # 2. Determine Strategy
            enable_ocr = False
            if ocr_mode == 'force':
                enable_ocr = True
            elif ocr_mode == 'auto':
                # Heuristics can go here. For now, Registry handles basic logic.
                # If we want to be smarter (e.g. try PDF first, if empty then OCR), we can do it here.
                # Let's trust the Registry's auto-select or just pass flags.
                # The registry currently takes `enable_ocr` bool.
                # We might need to refactor Registry or just simpler logic here:
                pass
            
            # Simple mapping for now
            use_ocr_flag = (ocr_mode == 'force')

            strategy = ExtractorRegistry.auto_select_strategy(filename, enable_ocr=use_ocr_flag)
            
            # 3. Execute Extraction
            result = strategy.extract(stream, language=language)
            
            # --- SMART FALLBACK CHECK ---
            # If we used PDF strategy but got very little text, it might be a scanned PDF.
            # We should fallback to OCR automatically if ocr_mode was 'auto'.
            from .strategies.pdf import PdfStructuredStrategy
            
            is_native_pdf = isinstance(strategy, PdfStructuredStrategy)
            
            if ocr_mode == 'auto' and is_native_pdf:
                text_len = len(result.full_text.strip())
                page_count = result.metadata.get('page_count', 0)
                
                # Improved heuristic: Check average chars per page
                # < 20 chars/page suggests scanned document
                if page_count > 0:
                    avg_chars_per_page = text_len / page_count
                    
                    if avg_chars_per_page < 20:
                        logger.warning(
                            f"Native extraction yielded {avg_chars_per_page:.1f} chars/page "
                            f"(total: {text_len} chars). Falling back to OCR."
                        )
                        
                        # Reset stream for retry
                        if hasattr(stream, 'seek'):
                            stream.seek(0)
                            
                        # Switch to OCR Strategy
                        ocr_strategy = ExtractorRegistry.get_strategy('ocr')
                        ocr_result = ocr_strategy.extract(stream, language=language)
                        
                        # Append metadata to indicate fallback occurred
                        ocr_result.metadata['fallback_triggered'] = True
                        ocr_result.metadata['original_method'] = 'pdf_structured'
                        ocr_result.metadata['original_chars_per_page'] = avg_chars_per_page
                        
                        return ocr_result

            return result

        except Exception as e:
            logger.error(f"Extraction failed for {filename}: {e}")
            raise
        finally:
            if should_close and stream:
                stream.close()

# Functional Alias for ease of use
def extract(
    input_data: Union[str, Path, bytes, BinaryIO],
    filename: Optional[str] = None,
    ocr_mode: str = 'auto',
    language: str = 'eng'
) -> ExtractionResult:
    """Helper function to extract text without instantiating a class."""
    return TextExtractor.extract(input_data, filename, ocr_mode, language)
