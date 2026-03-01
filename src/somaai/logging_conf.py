"""Logging configuration."""

import logging
import sys


def setup_logging() -> None:
    """Configure application logging with request traceability."""
    from somaai.utils.logging_ext import RequestIDFilter

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIDFilter())

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s - %(name)s - [%(request_id)s] - %(levelname)s - %(message)s"
        ),
        handlers=[handler],
        force=True,  # Ensure we override any existing basic config
    )


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)
