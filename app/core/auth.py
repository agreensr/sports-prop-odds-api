"""
API authentication middleware and dependencies.

Provides API key-based authentication for protecting endpoints.
"""
import os
from typing import Optional
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader
from starlette.requests import Request

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# API Key header name
API_KEY_NAME = "X-API-Key"

# Create API key header security scheme
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def get_api_key(request: Request, api_key: Optional[str] = Security(api_key_header)) -> str:
    """
    Validate API key from request header.

    Args:
        request: The incoming request
        api_key: API key from X-API-Key header

    Returns:
        The validated API key

    Raises:
        HTTPException: If API key is missing or invalid
    """
    # Skip auth for health endpoints
    if request.url.path in ["/health", "/docs", "/openapi.json", "/redoc", "/api/health"]:
        return "_health_skip_"
    
    # Skip auth if no API key is configured (development mode warning)
    if not settings.API_KEY:
        if settings.is_production():
            logger.warning("API_KEY not configured in production - rejecting request")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key required. Configure API_KEY environment variable."
            )
        else:
            logger.debug("API_KEY not configured - allowing request in development mode")
            return "_dev_skip_"
    
    # Validate API key
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key missing. Provide X-API-Key header."
        )
    
    if api_key != settings.API_KEY:
        logger.warning(f"Invalid API key attempt from {request.client.host if request.client else 'unknown'}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key."
        )
    
    return api_key


def optional_api_key(request: Request, api_key: Optional[str] = Security(api_key_header)) -> Optional[str]:
    """
    Optional API key validation - doesn't fail if missing.

    Useful for endpoints that have enhanced features with auth but work without it.

    Args:
        request: The incoming request
        api_key: API key from X-API-Key header

    Returns:
        The validated API key or None if not provided
    """
    if not api_key or not settings.API_KEY:
        return None
    
    if api_key == settings.API_KEY:
        return api_key
    
    # Invalid key but don't fail - just return None
    return None


class Authenticated:
    """
    Dependency class for requiring authentication on endpoints.

    Usage:
        @router.get("/protected")
        def protected_endpoint(auth: str = Depends(Authenticated)):
            return {"message": "authenticated"}
    """
    def __call__(self, request: Request, api_key: str = Security(get_api_key)) -> str:
        return api_key


# Singleton instance for use as dependency
authenticated = Authenticated()


def validate_admin_token(admin_token: Optional[str] = None) -> bool:
    """
    Validate admin token for administrative operations.

    Args:
        admin_token: Admin token from request

    Returns:
        True if valid admin token

    Raises:
        HTTPException: If token is invalid
    """
    if not settings.ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Admin functionality not enabled. Set ADMIN_TOKEN environment variable."
        )
    
    if not admin_token or admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin token."
        )
    
    return True


# Public endpoint paths (no auth required)
PUBLIC_PATHS = {
    "/health",
    "/api/health",
    "/docs",
    "/redoc",
    "/openapi.json",
}
