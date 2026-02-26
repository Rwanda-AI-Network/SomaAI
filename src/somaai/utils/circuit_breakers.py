"""Circuit breakers for external services using pybreaker.

Provides pre-configured circuit breakers for different services.
Uses industry-standard pybreaker library instead of custom implementation.
"""

import logging

from pybreaker import CircuitBreaker, CircuitBreakerError, CircuitBreakerListener

logger = logging.getLogger(__name__)


# Circuit breaker for Qdrant operations
qdrant_breaker = CircuitBreaker(
    fail_max=5,  # Open after 5 failures
    reset_timeout=60,  # Try again after 60 seconds
    name="qdrant",
    exclude=[Exception],
)

# Circuit breaker for LLM API calls
llm_breaker = CircuitBreaker(
    fail_max=3,  # More sensitive for LLM
    reset_timeout=30,  # Shorter timeout
    name="llm_api",
    exclude=[Exception],
)

# Circuit breaker for Redis operations
redis_breaker = CircuitBreaker(
    fail_max=10,  # More tolerant for cache
    reset_timeout=15,  # Quick recovery
    name="redis",
    exclude=[Exception],
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


# Listener for monitoring circuit breaker state changes
class _BreakerMonitor(CircuitBreakerListener):
    """Listener for circuit breaker state changes."""

    def state_change(self, cb: CircuitBreaker, old_state, new_state) -> None:
        """Called when circuit breaker state changes."""
        logger.info(
            f"Circuit breaker '{cb.name}' changed state: "
            f"{old_state.name} -> {new_state.name}"
        )

    def failure(self, cb: CircuitBreaker, exc: Exception) -> None:
        """Called when a protected call fails."""
        logger.warning(f"Circuit breaker '{cb.name}' recorded failure: {exc}")

    def success(self, cb: CircuitBreaker) -> None:
        """Called when a protected call succeeds."""
        pass  # Too noisy to log every success


# Register listener
_monitor = _BreakerMonitor()
for breaker in [qdrant_breaker, llm_breaker, redis_breaker]:
    breaker.add_listener(_monitor)
