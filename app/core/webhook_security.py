"""
Webhook signature verification and security utilities.

Provides secure signature verification for webhooks from various providers:
- GitHub webhooks (HMAC-SHA256)
- Generic HMAC webhooks
- Replay attack protection
- Signature audit logging

P3 #26: Webhook Signature Verification
"""
import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from fastapi import HTTPException, Request

from app.core.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Environment variable to enforce signature verification even in development
WEBHOOK_ENFORCE_SIGNATURE = os.getenv("WEBHOOK_ENFORCE_SIGNATURE", "false").lower() == "true"

# Replay attack protection: Time window for valid signatures (default 5 minutes)
WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS = int(os.getenv("WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS", "300"))

# Store seen nonces/timestamps for replay protection (in production, use Redis)
_seen_nonces: Dict[str, datetime] = {}


# =============================================================================
# SIGNATURE VERIFICATION
# =============================================================================

def verify_signature(
    payload: bytes,
    signature: str,
    secret: str,
    algorithm: str = "sha256",
    signature_prefix: str = "sha256="
) -> bool:
    """
    Verify webhook HMAC signature.

    Args:
        payload: Request body bytes
        signature: Signature header value
        secret: Webhook secret
        algorithm: Hash algorithm (sha256, sha1)
        signature_prefix: Expected prefix before the hash

    Returns:
        True if signature is valid

    Raises:
        HTTPException: If signature is invalid
    """
    if not secret:
        if WEBHOOK_ENFORCE_SIGNATURE or settings.is_production():
            logger.error("Webhook secret not configured and enforcement is enabled")
            raise HTTPException(
                status_code=500,
                detail="Webhook secret not configured"
            )
        # Development mode with enforcement disabled
        logger.warning("Webhook secret not configured - allowing request in development mode")
        return True

    if not signature:
        logger.warning("Webhook missing signature header")
        raise HTTPException(
            status_code=401,
            detail="Missing signature header"
        )

    # Check signature format
    if not signature.startswith(signature_prefix):
        logger.warning(f"Webhook signature has invalid format (expected prefix: {signature_prefix})")
        raise HTTPException(
            status_code=401,
            detail="Invalid signature format"
        )

    # Extract the hash value
    try:
        _, received_hash = signature.split("=", 1)
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Malformed signature"
        )

    # Compute expected signature
    hash_func = getattr(hashlib, algorithm, hashlib.sha256)
    expected_hash = hmac.new(
        secret.encode(),
        payload,
        hash_func
    ).hexdigest()

    # Constant-time comparison to prevent timing attacks
    is_valid = hmac.compare_digest(expected_hash, received_hash)

    if not is_valid:
        logger.warning("Webhook signature verification failed")
        raise HTTPException(
            status_code=401,
            detail="Invalid signature"
        )

    return True


def verify_github_signature(
    payload: bytes,
    signature: str,
    secret: Optional[str] = None
) -> bool:
    """
    Verify GitHub webhook signature (X-Hub-Signature-256).

    GitHub uses HMAC-SHA256 with the webhook secret.

    Args:
        payload: Request body bytes
        signature: X-Hub-Signature-256 header value
        secret: Webhook secret (defaults to GITHUB_WEBHOOK_SECRET env var)

    Returns:
        True if signature is valid
    """
    if secret is None:
        secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")

    return verify_signature(
        payload,
        signature,
        secret,
        algorithm="sha256",
        signature_prefix="sha256="
    )


# =============================================================================
# REPLAY ATTACK PROTECTION
# =============================================================================

def check_replay_attack(
    request_id: str,
    timestamp: Optional[datetime] = None,
    nonce: Optional[str] = None,
    tolerance_seconds: int = WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS
) -> bool:
    """
    Check for replay attacks using timestamp and/or nonce.

    Args:
        request_id: Unique identifier for this request (for tracking)
        timestamp: Request timestamp (if provided by webhook)
        nonce: Unique nonce value (if provided by webhook)
        tolerance_seconds: Max age of valid timestamp

    Returns:
        True if request is not a replay attack

    Raises:
        HTTPException: If replay attack detected
    """
    now = datetime.utcnow()

    # Check timestamp if provided
    if timestamp:
        time_diff = abs((now - timestamp).total_seconds())

        if time_diff > tolerance_seconds:
            logger.warning(
                f"Webhook timestamp outside tolerance: {time_diff}s > {tolerance_seconds}s"
            )
            raise HTTPException(
                status_code=401,
                detail=f"Request too old or future clock skew ({time_diff}s > {tolerance_seconds}s)"
            )

    # Check nonce if provided (for exact duplicate detection)
    if nonce:
        nonce_key = f"{request_id}:{nonce}"

        if nonce_key in _seen_nonces:
            last_seen = _seen_nonces[nonce_key]
            logger.warning(f"Webhook nonce reuse detected (first seen: {last_seen})")
            raise HTTPException(
                status_code=401,
                detail="Duplicate request detected"
            )

        # Store this nonce
        _seen_nonces[nonce_key] = now

        # Clean up old nonces (older than 2x tolerance)
        cutoff = now - timedelta(seconds=tolerance_seconds * 2)
        _seen_nonces.update({
            k: v for k, v in _seen_nonces.items()
            if v > cutoff
        })

    return True


def clean_old_nonces(max_age_seconds: int = 3600):
    """
    Clean up old nonce entries from memory.

    In production, use Redis with automatic expiration instead.
    This is a simple in-memory implementation for development.

    Args:
        max_age_seconds: Remove nonces older than this (default 1 hour)
    """
    global _seen_nonces
    cutoff = datetime.utcnow() - timedelta(seconds=max_age_seconds)
    _seen_nonces.update({
        k: v for k, v in _seen_nonces.items()
        if v > cutoff
    })


# =============================================================================
# AUDIT LOGGING
# =============================================================================

class WebhookAuditLogger:
    """Audit logger for webhook security events."""

    @staticmethod
    def log_verification_success(
        source: str,
        webhook_id: str,
        has_signature: bool = True
    ):
        """Log successful webhook verification."""
        logger.info(
            f"Webhook verification succeeded: source={source}, "
            f"webhook_id={webhook_id}, signature_present={has_signature}"
        )

    @staticmethod
    def log_verification_failure(
        source: str,
        reason: str,
        client_ip: Optional[str] = None
    ):
        """Log failed webhook verification."""
        logger.warning(
            f"Webhook verification FAILED: source={source}, "
            f"reason={reason}, client_ip={client_ip}"
        )

    @staticmethod
    def log_replay_attack_detected(
        source: str,
        client_ip: Optional[str] = None
    ):
        """Log replay attack detection."""
        logger.warning(
            f"POTENTIAL REPLAY ATTACK: source={source}, "
            f"client_ip={client_ip}, action=blocked"
        )


# =============================================================================
# FASTAPI DEPENDENCY FOR WEBHOOK VERIFICATION
# =============================================================================

async def verify_webhook_signature(
    request: Request,
    secret: str,
    header_name: str = "X-Hub-Signature-256",
    algorithm: str = "sha256"
) -> Tuple[bytes, str]:
    """
    FastAPI dependency for verifying webhook signatures.

    Usage:
        @router.post("/webhook")
        async def webhook(
            request: Request,
            verified: Tuple[bytes, str] = Depends(
                lambda r: verify_webhook_signature(
                    r,
                    secret=os.getenv("WEBHOOK_SECRET")
                )
            )
        ):
            payload, signature = verified
            # Process webhook...

    Args:
        request: FastAPI Request object
        secret: Webhook secret
        header_name: Name of signature header
        algorithm: Hash algorithm

    Returns:
        Tuple of (payload_bytes, signature)

    Raises:
        HTTPException: If verification fails
    """
    payload = await request.body()
    signature = request.headers.get(header_name, "")

    # Verify signature
    verify_signature(
        payload,
        signature,
        secret,
        algorithm=algorithm,
        signature_prefix=f"{algorithm}="
    )

    return payload, signature


# =============================================================================
# HELPERS
# =============================================================================

def get_client_ip(request: Request) -> str:
    """Get client IP address from request, handling proxies."""
    # Check for forwarded header (reverse proxy)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    # Check for real IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fall back to direct address
    if request.client:
        return request.client.host

    return "unknown"
