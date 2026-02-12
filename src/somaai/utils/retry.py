"""Retry utilities for resilient operations.

Provides retry decorators with exponential backoff for API calls.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable
from functools import wraps

logger = logging.getLogger(__name__)


class RetryError(Exception):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, message: str, last_exception: Exception | None = None):
        super().__init__(message)
        self.last_exception = last_exception


def retry_async(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable[[Exception, int], None] | None = None,
):
    """Decorator for async functions with exponential backoff retry.

    Args:
        max_attempts: Maximum number of attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay between retries
        exponential_base: Base for exponential backoff
        jitter: Add random jitter to delays
        retryable_exceptions: Exceptions that trigger retry
        on_retry: Callback on each retry (exception, attempt_number)

    Returns:
        Decorated function
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)

                except retryable_exceptions as e:
                    last_exception = e

                    if attempt >= max_attempts:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        raise RetryError(
                            f"Max retries ({max_attempts}) exceeded",
                            last_exception=e,
                        )

                    # Calculate delay with exponential backoff
                    delay = min(
                        base_delay * (exponential_base ** (attempt - 1)),
                        max_delay,
                    )

                    # Add jitter
                    if jitter:
                        delay *= 0.5 + random.random()

                    logger.warning(
                        f"{func.__name__} attempt {attempt} failed: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )

                    if on_retry:
                        on_retry(e, attempt)

                    await asyncio.sleep(delay)

            raise RetryError(
                "Unexpected retry loop exit",
                last_exception=last_exception,
            )

        return wrapper

    return decorator


def retry_sync(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
):
    """Decorator for sync functions with exponential backoff retry.

    Args:
        max_attempts: Maximum number of attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay between retries
        exponential_base: Base for exponential backoff
        jitter: Add random jitter to delays
        retryable_exceptions: Exceptions that trigger retry

    Returns:
        Decorated function
    """
    import time

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)

                except retryable_exceptions as e:
                    last_exception = e

                    if attempt >= max_attempts:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        raise RetryError(
                            f"Max retries ({max_attempts}) exceeded",
                            last_exception=e,
                        )

                    delay = min(
                        base_delay * (exponential_base ** (attempt - 1)),
                        max_delay,
                    )

                    if jitter:
                        delay *= 0.5 + random.random()

                    logger.warning(
                        f"{func.__name__} attempt {attempt} failed: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )

                    time.sleep(delay)

            raise RetryError(
                "Unexpected retry loop exit",
                last_exception=last_exception,
            )

        return wrapper

    return decorator


# Common retry configurations
EMBEDDING_RETRY = {
    "max_attempts": 3,
    "base_delay": 2.0,
    "max_delay": 30.0,
    "retryable_exceptions": (ConnectionError, TimeoutError, Exception),
}

API_RETRY = {
    "max_attempts": 5,
    "base_delay": 1.0,
    "max_delay": 60.0,
}
