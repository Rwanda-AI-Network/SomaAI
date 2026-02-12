"""Circuit breakers for external services using pybreaker.

Provides pre-configured circuit breakers for different services.
Uses industry-standard pybreaker library instead of custom implementation.
"""

import logging
from pybreaker import CircuitBreaker, CircuitBreakerError

logger = logging.getLogger(__name__)


# Circuit breaker for Qdrant operations
qdrant_breaker = CircuitBreaker(
    fail_max=5,              # Open after 5 failures
    timeout_duration=60,     # Try again after 60 seconds
    name="qdrant",
    expected_exception=Exception,
)

# Circuit breaker for LLM API calls
llm_breaker = CircuitBreaker(
    fail_max=3,              # More sensitive for LLM
    timeout_duration=30,     # Shorter timeout
    name="llm_api",
    expected_exception=Exception,
)

# Circuit breaker for Redis operations
redis_breaker = CircuitBreaker(
    fail_max=10,             # More tolerant for cache
    timeout_duration=15,     # Quick recovery
    name="redis",
    expected_exception=Exception,
)


def get_circuit_breaker(service: str) -> CircuitBreaker:
    """Get circuit breaker for a service.
    
    Args:
        service: Service name ('qdrant', 'llm', 'redis')
        
    Returns:
        Configured CircuitBreaker instance
    """
    breakers = {
        "qdrant": qdrant_breaker,
        "llm": llm_breaker,
        "redis": redis_breaker,
    }
    return breakers.get(service, qdrant_breaker)


# Export for backward compatibility
CircuitBreakerOpenError = CircuitBreakerError


# Add listeners for monitoring
def _on_breaker_open(breaker, remaining):
    """Called when circuit breaker opens."""
    logger.error(
        f"Circuit breaker '{breaker.name}' OPENED after {breaker.fail_counter} failures. "
        f"Will retry in {remaining}s"
    )


def _on_breaker_close(breaker):
    """Called when circuit breaker closes."""
    logger.info(f"Circuit breaker '{breaker.name}' CLOSED - service recovered")


def _on_breaker_half_open(breaker):
    """Called when circuit breaker enters half-open state."""
    logger.info(f"Circuit breaker '{breaker.name}' HALF-OPEN - testing recovery")


# Register listeners
for breaker in [qdrant_breaker, llm_breaker, redis_breaker]:
    breaker.add_listener(_on_breaker_open)
    breaker.add_listener(_on_breaker_close)
    breaker.add_listener(_on_breaker_half_open)
