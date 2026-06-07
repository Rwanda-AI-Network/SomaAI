"""Logging extensions for observability."""

import logging
from contextvars import ContextVar, Token

# Global context for request traceability
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
actor_id_ctx: ContextVar[str | None] = ContextVar("actor_id", default=None)
conversation_id_ctx: ContextVar[str | None] = ContextVar(
    "conversation_id", default=None
)


class RequestIDFilter(logging.Filter):
    """Logging filter that injects tracing context into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get() or "-"
        record.actor_id = actor_id_ctx.get() or "-"
        record.conversation_id = conversation_id_ctx.get() or "-"
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


def set_actor_id(actor_id: str | None) -> Token[str | None]:
    """Set the current actor ID in context.

    Returns:
        Token for resetting context via actor_id_ctx.reset(token).
    """
    return actor_id_ctx.set(actor_id)


def set_conversation_id(conversation_id: str | None) -> Token[str | None]:
    """Set the current conversation ID in context.

    Returns:
        Token for resetting context via conversation_id_ctx.reset(token).
    """
    return conversation_id_ctx.set(conversation_id)
