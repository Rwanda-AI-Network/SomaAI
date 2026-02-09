from .strategies.base import BaseExtractionStrategy
from .strategies.pdf import PdfStructuredStrategy
from .strategies.ocr import OcrStrategy
from .strategies.text import RawTextStrategy
from .strategies.docx import DocxStructuredStrategy
from .exceptions import UnsupportedFileTypeError

class ExtractorRegistry:
    """Factory and registry for text extraction strategies."""
    
    _strategies = {
        'pdf_native': PdfStructuredStrategy(),  # Now RAG-optimized
        'ocr': OcrStrategy(),
        'raw_text': RawTextStrategy(),
        'docx': DocxStructuredStrategy()  # Now extracts headings/tables
    }

    @staticmethod
    def get_strategy(method: str) -> BaseExtractionStrategy:
        """
        Get a specific extraction strategy.
        
        Args:
           method: 'pdf_native' or 'ocr'
        """
        if method not in ExtractorRegistry._strategies:
             raise UnsupportedFileTypeError(f"Unknown extraction method: {method}")
        return ExtractorRegistry._strategies[method]

    @staticmethod
    def auto_select_strategy(filename: str, enable_ocr: bool = False) -> BaseExtractionStrategy:
        """
        Selects the best strategy based on filename and user preference.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # Simple logic for now, can be expanded to detect scanned PDFs automatically
        if enable_ocr:
            logger.info("Strategy selected: OCR (User override)")
            return ExtractorRegistry.get_strategy('ocr')
        
        if filename.lower().endswith('.pdf'):
            logger.info("Strategy selected: PDF Native")
            return ExtractorRegistry.get_strategy('pdf_native')
        
        # If it's an image, default to OCR
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp')):
            logger.info("Strategy selected: OCR (Image detected)")
            return ExtractorRegistry.get_strategy('ocr')
            
        # Raw text
        if filename.lower().endswith(('.txt', '.md', '.csv', '.json', '.xml')):
            logger.info("Strategy selected: Raw Text")
            return ExtractorRegistry.get_strategy('raw_text')

        # Word Docs
        if filename.lower().endswith('.docx'):
            logger.info("Strategy selected: Docx")
            return ExtractorRegistry.get_strategy('docx')
            
        logger.warning(f"Unknown file type for {filename}, falling back to PDF Native")
        return ExtractorRegistry.get_strategy('pdf_native') # Default fallback?
