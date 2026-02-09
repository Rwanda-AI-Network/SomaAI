"""OCR extraction strategy updated for new schema."""

from pdf2image import convert_from_bytes, convert_from_path, pdfinfo_from_path
import pytesseract
from PIL import Image
from .base import BaseExtractionStrategy, ExtractionResult, Page
from ..exceptions import OcrError
import logging

logger = logging.getLogger(__name__)


class OcrStrategy(BaseExtractionStrategy):
    """Extracts text from PDFs/Images using OCR (Tesseract)."""

    def extract(self, file_stream, language: str = 'eng') -> ExtractionResult:
        logger.info(f"Starting OCR extraction with language={language}")
        try:
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                if hasattr(file_stream, 'seek'):
                    file_stream.seek(0)
                
                import shutil
                shutil.copyfileobj(file_stream, tmp_file)
                tmp_path = tmp_file.name
            
            try:
                logger.info(f"Processing via temp file: {tmp_path}")
                
                # Try PDF processing
                try:
                    info = pdfinfo_from_path(tmp_path)
                    total_pages = info["Pages"]
                    
                    pages_data = []
                    BATCH_SIZE = 5
                    
                    for start_page in range(1, total_pages + 1, BATCH_SIZE):
                        end_page = min(start_page + BATCH_SIZE - 1, total_pages)
                        logger.info(f"OCR batch: Pages {start_page} to {end_page}")
                        
                        batch_images = convert_from_path(
                            tmp_path,
                            first_page=start_page,
                            last_page=end_page,
                            thread_count=2,
                            fmt='jpeg'
                        )
                        
                        from concurrent.futures import ThreadPoolExecutor
                        
                        def process_image(img_tuple):
                            idx, img = img_tuple
                            try:
                                txt = pytesseract.image_to_string(img, lang=language)
                                return idx, txt
                            finally:
                                if hasattr(img, 'close'):
                                    img.close()
                        
                        with ThreadPoolExecutor(max_workers=min(BATCH_SIZE, os.cpu_count() or 4)) as executor:
                            results = list(executor.map(process_image, enumerate(batch_images, start=start_page)))
                            
                            for page_num, text in results:
                                pages_data.append(Page(
                                    page_number=page_num,
                                    content=text,
                                    metadata={"method": "ocr"}
                                ))
                        
                        del batch_images
                
                except Exception as pdf_err:
                    logger.info(f"PDF processing failed ({pdf_err}), trying single image")
                    image = Image.open(tmp_path)
                    text = pytesseract.image_to_string(image, lang=language)
                    pages_data = [Page(
                        page_number=1,
                        content=text,
                        metadata={"method": "ocr"}
                    )]
                    
                    if hasattr(image, 'close'):
                        image.close()
                
                full_text = "\n\n".join(page.content for page in pages_data)
            
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            
            logger.info(f"OCR extraction successful. Extracted {len(pages_data)} pages.")
            
            return ExtractionResult(
                full_text=full_text,
                pages=pages_data,
                hierarchy=[],  # OCR doesn't detect structure
                tables=[],
                metadata={
                    "method": "ocr",
                    "language": language,
                    "page_count": len(pages_data)
                }
            )
        
        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            raise OcrError(f"OCR process failed: {str(e)}")
