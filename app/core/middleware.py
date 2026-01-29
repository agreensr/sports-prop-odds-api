"""
FastAPI middleware for request correlation ID tracking.

This module provides middleware that:
1. Reads or generates X-Correlation-ID header
2. Stores it in request state for access in endpoints
3. Returns it in response headers
4. Sets it in the logging context for structured logs
"""
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging import set_correlation_id, clear_correlation_id, get_logger

logger = get_logger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add correlation ID tracking to all requests.

    This middleware:
    1. Checks for X-Correlation-ID in the request headers
    2. Generates a new UUID if not present
    3. Stores it in request.state.correlation_id
    4. Adds it to the logging context for all log calls
    5. Returns it in the X-Correlation-ID response header

    Usage:
        app.add_middleware(CorrelationIdMiddleware)

    Access in endpoints:
        correlation_id = request.state.correlation_id
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialize the middleware."""
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Response]
    ) -> Response:
        """
        Process request with correlation ID tracking.

        Args:
            request: Incoming request
            call_next: Next middleware or route handler

        Returns:
            Response with X-Correlation-ID header
        """
        # Get correlation ID from headers or generate new one
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Store in request state for access in endpoints
        request.state.correlation_id = correlation_id

        # Set in logging context for all log calls during this request
        token = set_correlation_id(correlation_id)

        try:
            # Process request
            response = await call_next(request)

            # Add correlation ID to response headers
            response.headers["X-Correlation-ID"] = correlation_id

            logger.debug(
                f"Request completed: {request.method} {request.url.path}",
                extra={"method": request.method, "path": request.url.path, "status": response.status_code},
            )

            return response
        finally:
            # Clear correlation ID from logging context
            clear_correlation_id(token)
