"""Logging extensions for observability."""

import logging
from contextvars import ContextVar, Token

# Global context for request ID traceability
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestIDFilter(logging.Filter):
    """Logging filter that injects request_id into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get() or "-"
        return True


def get_request_id() -> str | None:
    """Get the current request ID from context."""
    return request_id_ctx.get()


def set_request_id(request_id: str | None) -> Token[str | None]:
    """Set the current request ID in context.

    Returns:
        Token for resetting context via request_id_ctx.reset(token).
    """
    return request_id_ctx.set(request_id)
