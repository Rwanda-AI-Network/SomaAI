import argparse
import sys
import logging
from pathlib import Path
from . import extract_text, TextExtractionError

def setup_logging(verbose: bool):
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )

def main():
    parser = argparse.ArgumentParser(description="Extract text from PDF or Image files.")
    parser.add_argument("input_file", type=str, help="Path to the input file (PDF/Image)")
    parser.add_argument("--ocr", action="store_true", help="Force usage of OCR extraction")
    parser.add_argument("--language", type=str, default="eng", help="Language code for OCR (default: eng)")
    parser.add_argument("--output", type=str, help="Path to save output text file (optional)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()
    
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    input_path = Path(args.input_file)
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        sys.exit(1)

    try:
        logger.info(f"Extracting text from {input_path}")
        
        mode = 'force' if args.ocr else 'auto'
        
        # We can pass path directly now!
        result = extract_text(
            input_data=input_path, 
            filename=input_path.name, 
            ocr_mode=mode, 
            language=args.language
        )
        
        if args.output:
            output_path = Path(args.output)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(result.full_text)
            logger.info(f"Output saved to {output_path}")
        else:
            print(result.full_text)

    except TextExtractionError as e:
        logger.error(f"Extraction failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
