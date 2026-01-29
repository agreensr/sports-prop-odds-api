"""
Circuit breaker pattern for external API calls.

This module provides circuit breakers for external API calls to prevent
cascading failures when downstream services are unavailable.

Uses pybreaker library for circuit breaker implementation.

Circuit Breaker States:
- CLOSED: Requests pass through normally
- OPEN: Requests fail immediately with fallback (after fail_max failures)
- HALF_OPEN: One request allowed to test if service has recovered

Circuit Breakers:
- odds_api_breaker: For The Odds API calls
- espn_api_breaker: For ESPN API calls
- nba_api_breaker: For NBA API calls (nba_api library)
"""
from pybreaker import CircuitBreaker, CircuitBreakerError
from typing import Any, Callable
from functools import wraps
import logging

from app.core.logging import get_logger

logger = get_logger(__name__)

# Default circuit breaker configuration
DEFAULT_FAIL_MAX = 5  # Number of failures before opening circuit
DEFAULT_RESET_TIMEOUT = 60  # Seconds before attempting to close circuit


# ============================================================================
# CIRCUIT BREAKERS
# ============================================================================

odds_api_breaker = CircuitBreaker(
    fail_max=DEFAULT_FAIL_MAX,
    reset_timeout=DEFAULT_RESET_TIMEOUT,
    name="odds_api",
)


espn_api_breaker = CircuitBreaker(
    fail_max=DEFAULT_FAIL_MAX,
    reset_timeout=DEFAULT_RESET_TIMEOUT,
    name="espn_api",
)


nba_api_breaker = CircuitBreaker(
    fail_max=DEFAULT_FAIL_MAX,
    reset_timeout=DEFAULT_RESET_TIMEOUT,
    name="nba_api",
)


# ============================================================================
# CIRCUIT BREAKER STATE MONITORING
# ============================================================================

def get_breaker_state(breaker: CircuitBreaker) -> str:
    """
    Get the current state of a circuit breaker.

    Args:
        breaker: The circuit breaker instance

    Returns:
        State string: 'closed', 'open', or 'half_open'
    """
    return breaker.current_state


def get_all_breaker_states() -> dict[str, str]:
    """
    Get the current state of all circuit breakers.

    Returns:
        Dictionary mapping breaker names to their states
    """
    return {
        "odds_api": get_breaker_state(odds_api_breaker),
        "espn_api": get_breaker_state(espn_api_breaker),
        "nba_api": get_breaker_state(nba_api_breaker),
    }


def reset_breaker(breaker: CircuitBreaker) -> None:
    """
    Manually reset a circuit breaker to closed state.

    Use with caution - only reset if you know the service has recovered.

    Args:
        breaker: The circuit breaker instance to reset
    """
    breaker.close()
    logger.warning(f"Circuit breaker '{breaker.name}' manually reset to CLOSED state")


# ============================================================================
# DECORATORS AND HELPERS
# ============================================================================

def with_circuit_breaker(
    breaker: CircuitBreaker,
    fallback: Any = None,
    fallback_func: Callable | None = None,
):
    """
    Decorator to wrap a function with circuit breaker protection.

    Args:
        breaker: The circuit breaker to use
        fallback: Value to return when circuit is open
        fallback_func: Optional function to call when circuit is open
                       (takes precedence over fallback)

    Returns:
        Decorated function

    Example:
        @with_circuit_breaker(odds_api_breaker, fallback=[])
        async def fetch_odds():
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await breaker.call_async(func, *args, **kwargs)
            except CircuitBreakerError:
                logger.warning(
                    f"Circuit breaker '{breaker.name}' is OPEN - using fallback for {func.__name__}"
                )
                if fallback_func:
                    return fallback_func(*args, **kwargs)
                return fallback

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return breaker.call(func, *args, **kwargs)
            except CircuitBreakerError:
                logger.warning(
                    f"Circuit breaker '{breaker.name}' is OPEN - using fallback for {func.__name__}"
                )
                if fallback_func:
                    return fallback_func(*args, **kwargs)
                return fallback

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# ============================================================================
# FALLBACK FUNCTIONS
# ============================================================================

def empty_list_fallback(*args, **kwargs) -> list:
    """Default fallback returning empty list."""
    return []


def empty_dict_fallback(*args, **kwargs) -> dict:
    """Default fallback returning empty dict."""
    return {}


def none_fallback(*args, **kwargs) -> None:
    """Default fallback returning None."""
    return None


# ============================================================================
# PRE-CONFIGURED DECORATORS FOR COMMON USE CASES
# ============================================================================

def odds_api_protected(fallback: Any = empty_list_fallback):
    """
    Decorator for Odds API calls with circuit breaker protection.

    Args:
        fallback: Fallback value when circuit is open

    Example:
        @odds_api_protected(fallback=[])
        async def fetch_odds():
            ...
    """
    return with_circuit_breaker(odds_api_breaker, fallback=fallback)


def espn_api_protected(fallback: Any = empty_list_fallback):
    """
    Decorator for ESPN API calls with circuit breaker protection.

    Args:
        fallback: Fallback value when circuit is open

    Example:
        @espn_api_protected(fallback=[])
        async def fetch_scores():
            ...
    """
    return with_circuit_breaker(espn_api_breaker, fallback=fallback)


def nba_api_protected(fallback: Any = empty_list_fallback):
    """
    Decorator for NBA API calls with circuit breaker protection.

    Args:
        fallback: Fallback value when circuit is open

    Example:
        @nba_api_protected(fallback=[])
        async def fetch_players():
            ...
    """
    return with_circuit_breaker(nba_api_breaker, fallback=fallback)
