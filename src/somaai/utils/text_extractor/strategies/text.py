"""Simple text file extraction returning new schema format."""

import logging

from .base import BaseExtractionStrategy, ExtractionResult, Page

logger = logging.getLogger(__name__)


class RawTextStrategy(BaseExtractionStrategy):
    """Extracts text from raw text files (.txt, .md, .csv, .json, .xml)."""

    def extract(self, file_stream, language: str = "eng") -> ExtractionResult:
        logger.info("Starting Raw Text extraction.")
        try:
            if hasattr(file_stream, "seek"):
                file_stream.seek(0)

            # Memory optimization: Read in chunks
            chunk_size = 1024 * 1024  # 1MB chunks
            text_chunks = []
            total_size = 0

            try:
                while True:
                    chunk = file_stream.read(chunk_size)
                    if not chunk:
                        break

                    # Decode chunk
                    try:
                        decoded_chunk = chunk.decode("utf-8")
                    except UnicodeDecodeError:
                        logger.warning("UTF-8 decode failed, falling back to latin-1")
                        decoded_chunk = chunk.decode("latin-1", errors="ignore")

                    text_chunks.append(decoded_chunk)
                    total_size += len(chunk)

                    if total_size > 500 * 1024 * 1024:
                        megabytes = total_size / (1024 * 1024)
                        logger.warning(f"Large text file: {megabytes:.1f} MB")

            except AttributeError:
                # file_stream might be bytes directly
                if isinstance(file_stream, bytes):
                    try:
                        text = file_stream.decode("utf-8")
                    except UnicodeDecodeError:
                        logger.warning("UTF-8 decode failed, falling back to latin-1")
                        text = file_stream.decode("latin-1")
                    text_chunks = [text]
                else:
                    raise

            text = "".join(text_chunks)

            # Create single page with new schema
            pages = [
                Page(page_number=1, content=text, metadata={"char_count": len(text)})
            ]

            logger.info(f"Raw text extraction successful. Length: {len(text)} chars.")

            return ExtractionResult(
                full_text=text,
                pages=pages,
                hierarchy=[],  # No hierarchy for plain text
                tables=[],
                metadata={"method": "raw_text", "page_count": 1},
            )

        except Exception as e:
            logger.error(f"Raw text extraction failed: {e}")
            raise Exception(f"Failed to extract text from file: {str(e)}")
