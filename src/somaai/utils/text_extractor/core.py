import io
import logging
import re
from collections import Counter
from pathlib import Path
from typing import BinaryIO

from .exceptions import TextExtractionError
from .registry import ExtractorRegistry
from .strategies.base import ExtractionResult

logger = logging.getLogger(__name__)


def _check_text_quality(text: str) -> dict:
    """Check if extracted text appears to be readable or garbled.

    Returns a dict with:
        - is_suspect: True if text quality is poor
        - reason: Why it's suspect
        - score: Quality score 0-1 (1 = perfect)

    Detects two main failure modes from PDF font encoding issues:
    1. Fused words (missing space detection in pdfplumber)
    2. Character substitution (CMap decoding failures)
    """
    if not text or len(text.strip()) < 100:
        return {"is_suspect": True, "reason": "too_short", "score": 0.0}

    words = text.split()
    if not words:
        return {"is_suspect": True, "reason": "no_words", "score": 0.0}

    score = 1.0
    reasons = []

    # Check 1: Fused words — words > 30 chars that aren't URLs/paths
    # Normal English rarely has words > 25 chars.
    # "theremotehostmaintainsthissessionforawhile" = 43 chars
    long_words = [
        w
        for w in words
        if len(w) > 30
        and not w.startswith(("http", "/", "\\"))
        and not re.match(r"^[\d\W]+$", w)  # Skip pure numbers/symbols
    ]
    fused_ratio = len(long_words) / len(words) if words else 0
    if fused_ratio > 0.03:  # More than 3% of words are suspiciously long
        score -= 0.4
        reasons.append(f"fused_words ({fused_ratio:.1%} of words >30 chars)")

    # Check 2: Character frequency sanity check
    # English letter frequency: e≈13%, t≈9%, a≈8%, o≈7.5%, i≈7%, n≈7%
    # CMap-garbled text shifts these frequencies significantly.
    # We check if the top-6 most common English letters appear at reasonable rates.
    alpha_chars = [c.lower() for c in text if c.isalpha()]
    if len(alpha_chars) > 200:  # Need enough text for meaningful stats
        freq = Counter(alpha_chars)
        total = len(alpha_chars)

        # The 6 most common English letters should make up ~50-55% of text
        common_english = set("etaoin")
        common_ratio = sum(freq.get(c, 0) for c in common_english) / total

        if common_ratio < 0.30:
            # Severely abnormal — likely character substitution
            score -= 0.5
            reasons.append(
                f"char_frequency_anomaly (etaoin={common_ratio:.1%}, expected ~50%)"
            )
        elif common_ratio < 0.38:
            # Mildly abnormal — could be non-English or partial corruption
            score -= 0.2
            reasons.append(
                f"char_frequency_low (etaoin={common_ratio:.1%}, expected ~50%)"
            )

    # Check 3: Vowel ratio (existing heuristic, reinforced)
    # English is typically ~38-42% vowels. Garbled text often drops below 25%.
    if alpha_chars:
        vowel_count = sum(1 for c in alpha_chars if c in "aeiou")
        vowel_ratio = vowel_count / len(alpha_chars)
        if vowel_ratio < 0.20:
            score -= 0.3
            reasons.append(f"low_vowels ({vowel_ratio:.1%}, expected ~40%)")

    is_suspect = score < 0.5
    reason = "; ".join(reasons) if reasons else "ok"

    return {"is_suspect": is_suspect, "reason": reason, "score": max(0.0, score)}


class TextExtractor:
    """
    High-level orchestrator for text extraction.
    Simplifies the process by handling input normalization and strategy selection.
    """

    @staticmethod
    def extract(
        input_data: str | Path | bytes | BinaryIO,
        filename: str | None = None,
        ocr_mode: str = "auto",  # 'auto', 'force', 'skip'
        language: str = "eng",
    ) -> ExtractionResult:
        """
        Extract text from various input sources.

        Args:
            input_data: File path (str/Path), bytes, or file-like object.
            filename: Optional filename to help with type detection
                (useful if input is bytes).
            ocr_mode: 'auto' (default), 'force' (always use OCR),
                'skip' (never use OCR).
            language: Language code for OCR (default: 'eng').

        Returns:
            ExtractionResult object.
        """
        stream: BinaryIO | None = None
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
            use_ocr_flag = ocr_mode == "force"
            strategy = ExtractorRegistry.auto_select_strategy(
                filename, enable_ocr=use_ocr_flag
            )

            # 3. Execute Extraction
            result = strategy.extract(stream, language=language)

            # --- SMART FALLBACK CHECK ---
            # If we used native PDF strategy, check if the output is actually usable.
            # Two failure modes that native PDF extraction can't handle:
            #   A) Scanned PDF (no text at all) → caught by chars-per-page check
            #   B) Font encoding issue (garbled text) → caught by quality check
            from .strategies.pdf import PdfStructuredStrategy

            is_native_pdf = isinstance(strategy, PdfStructuredStrategy)

            if ocr_mode == "auto" and is_native_pdf:
                text_len = len(result.full_text.strip())
                page_count = result.metadata.get("page_count", 0)

                needs_ocr_fallback = False
                fallback_reason = ""

                # Check A: Too few characters per page (scanned PDF)
                if page_count > 0:
                    avg_chars_per_page = text_len / page_count

                    if avg_chars_per_page < 20:
                        needs_ocr_fallback = True
                        fallback_reason = (
                            f"scanned_pdf: {avg_chars_per_page:.1f} chars/page "
                            f"(total: {text_len} chars)"
                        )

                # Check B: Text exists but is garbled (font encoding issue)
                if not needs_ocr_fallback and text_len > 200:
                    quality = _check_text_quality(result.full_text)

                    if quality["is_suspect"]:
                        needs_ocr_fallback = True
                        fallback_reason = (
                            f"garbled_text: quality_score={quality['score']:.2f}, "
                            f"{quality['reason']}"
                        )

                if needs_ocr_fallback:
                    logger.warning(
                        f"Native PDF extraction suspect ({fallback_reason}). "
                        f"Falling back to OCR."
                    )

                    # Reset stream for retry - handle non-seekable streams
                    try:
                        if hasattr(stream, "seek"):
                            stream.seek(0)
                    except OSError as e:
                        # Stream is not seekable (e.g., HTTP response stream)
                        # We can't retry with OCR without re-reading the file
                        logger.error(
                            f"Cannot fallback to OCR: stream is not seekable ({e}). "
                            f"Consider buffering the stream before extraction."
                        )
                        # Return the original result rather than failing completely
                        result.metadata["fallback_failed"] = True
                        result.metadata["fallback_reason"] = str(e)
                        return result

                    # Switch to OCR Strategy
                    ocr_strategy = ExtractorRegistry.get_strategy("ocr")
                    ocr_result = ocr_strategy.extract(stream, language=language)

                    # Append metadata to indicate fallback occurred
                    ocr_result.metadata["fallback_triggered"] = True
                    ocr_result.metadata["fallback_reason"] = fallback_reason
                    ocr_result.metadata["original_method"] = "pdf_structured"
                    ocr_result.metadata["original_quality_score"] = (
                        quality["score"] if "quality" in dir() else None
                    )

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
    input_data: str | Path | bytes | BinaryIO,
    filename: str | None = None,
    ocr_mode: str = "auto",
    language: str = "eng",
) -> ExtractionResult:
    """Helper function to extract text without instantiating a class."""
    return TextExtractor.extract(input_data, filename, ocr_mode, language)
