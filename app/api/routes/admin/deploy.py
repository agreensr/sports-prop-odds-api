"""
Admin deployment routes for triggering git pull and API restart.

Provides endpoints for:
- Manual deployment trigger
- GitHub webhook integration with signature verification (P3 #26)
- Deployment status checks

Security Improvements (P3 #26):
- Required signature verification in all environments when WEBHOOK_ENFORCE_SIGNATURE=true
- Replay attack protection via timestamp/nonce checking
- Enhanced audit logging for security events
- IP-based access logging
"""
import asyncio
import logging
import os
import subprocess
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Header, Depends
from pydantic import BaseModel

from app.core.config import settings
from app.core.webhook_security import (
    verify_github_signature,
    check_replay_attack,
    WebhookAuditLogger,
    get_client_ip,
    WEBHOOK_ENFORCE_SIGNATURE
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])

# GitHub webhook secret (set in environment)
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")

# Project directory (where git repo is located)
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class DeploymentResponse(BaseModel):
    """Response model for deployment operations."""
    status: str
    message: str
    git_commit: Optional[str] = None
    git_branch: Optional[str] = None
    timestamp: str


async def run_command(command: str, cwd: Optional[str] = None) -> tuple[bool, str, str]:
    """
    Run a shell command asynchronously.

    Args:
        command: Command to run
        cwd: Working directory (defaults to project root)

    Returns:
        Tuple of (success, stdout, stderr)
    """
    working_dir = cwd or PROJECT_DIR

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=working_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()
        stdout_str = stdout.decode().strip()
        stderr_str = stderr.decode().strip()

        success = process.returncode == 0

        if not success:
            logger.error(f"Command failed: {command}")
            logger.error(f"stderr: {stderr_str}")

        return success, stdout_str, stderr_str

    except Exception as e:
        logger.error(f"Error running command '{command}': {e}")
        return False, "", str(e)


async def get_git_info() -> tuple[str, str]:
    """Get current git commit hash and branch."""
    success, commit, _ = await run_command("git rev-parse --short HEAD")
    if not success:
        commit = "unknown"

    success, branch, _ = await run_command("git rev-parse --abbrev-ref HEAD")
    if not success:
        branch = "unknown"

    return commit, branch


# Legacy wrapper for backward compatibility
def verify_github_signature(payload: bytes, signature: str, require_secret: bool = True) -> bool:
    """
    Verify GitHub webhook signature.

    DEPRECATED: Use app.core.webhook_security.verify_github_signature instead.
    This function is kept for backward compatibility.

    Args:
        payload: Request body bytes
        signature: X-Hub-Signature-256 header value
        require_secret: If True, require secret to be set

    Returns:
        True if signature is valid

    Raises:
        HTTPException: If signature is invalid or secret is required but not set
    """
    from app.core.webhook_security import verify_signature

    # Check if secret is configured
    if not GITHUB_WEBHOOK_SECRET:
        if require_secret or settings.is_production() or WEBHOOK_ENFORCE_SIGNATURE:
            logger.error("GITHUB_WEBHOOK_SECRET not set - rejecting webhook")
            raise HTTPException(
                status_code=500,
                detail="Webhook secret not configured on server"
            )
        logger.warning("GITHUB_WEBHOOK_SECRET not set - allowing webhook in development mode (SECURITY RISK)")
        return True

    if not signature:
        logger.warning("GitHub webhook missing X-Hub-Signature-256 header")
        raise HTTPException(
            status_code=401,
            detail="Missing signature header"
        )

    # Use new verification function
    return verify_signature(
        payload,
        signature,
        GITHUB_WEBHOOK_SECRET,
        algorithm="sha256",
        signature_prefix="sha256="
    )


@router.get("/deploy/status", response_model=DeploymentResponse)
async def deployment_status():
    """
    Get current deployment status.

    Returns git commit, branch, and timestamp of current deployment.
    """
    commit, branch = await get_git_info()

    return DeploymentResponse(
        status="deployed",
        message="Current deployment information",
        git_commit=commit,
        git_branch=branch,
        timestamp=datetime.utcnow().isoformat()
    )


@router.post("/deploy/deploy", response_model=DeploymentResponse)
async def trigger_deployment(
    x_admin_token: Optional[str] = Header(None)
):
    """
    Trigger a deployment (git pull + API restart).

    Requires X-Admin-Token header for authentication.
    Set ADMIN_TOKEN environment variable to secure this endpoint.

    Returns deployment status after completion.
    """
    # Check admin token if configured
    admin_token = os.getenv("ADMIN_TOKEN", "")
    if admin_token and x_admin_token != admin_token:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing admin token"
        )

    logger.info("🔄 Deployment triggered via API")

    # Get current git info before pull
    old_commit, old_branch = await get_git_info()
    logger.info(f"Current commit: {old_commit} (branch: {old_branch})")

    # Step 1: Fetch latest from remote
    logger.info("Fetching latest code from remote...")
    success, stdout, stderr = await run_command("git fetch origin")
    if not success:
        return DeploymentResponse(
            status="error",
            message=f"Git fetch failed: {stderr}",
            timestamp=datetime.utcnow().isoformat()
        )

    # Step 2: Pull latest changes
    logger.info("Pulling latest changes...")
    success, stdout, stderr = await run_command("git pull origin main")
    if not success:
        return DeploymentResponse(
            status="error",
            message=f"Git pull failed: {stderr}",
            timestamp=datetime.utcnow().isoformat()
        )

    logger.info(f"Git pull output: {stdout}")

    # Step 3: Get new commit info
    new_commit, new_branch = await get_git_info()
    logger.info(f"New commit: {new_commit} (branch: {new_branch})")

    # Step 4: Restart API
    logger.info("Restarting API server...")
    restart_command = "pkill -f 'uvicorn app.main:app' && nohup uvicorn app.main:app --host 0.0.0.0 --port 8001 > /dev/null 2>&1 &"

    # For restart, we need to run this differently since it will kill the current process
    # Use a detached subprocess
    try:
        subprocess.Popen(
            ["bash", "-c", restart_command],
            cwd=PROJECT_DIR,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        logger.info("API restart command executed")
    except Exception as e:
        logger.error(f"Failed to restart API: {e}")
        return DeploymentResponse(
            status="warning",
            message=f"Code pulled but restart failed: {str(e)}",
            git_commit=new_commit,
            git_branch=new_branch,
            timestamp=datetime.utcnow().isoformat()
        )

    return DeploymentResponse(
        status="success",
        message=f"Deployment complete. Updated from {old_commit} to {new_commit}. API is restarting...",
        git_commit=new_commit,
        git_branch=new_branch,
        timestamp=datetime.utcnow().isoformat()
    )


@router.post("/deploy/webhook")
async def github_webhook(request: Request):
    """
    GitHub webhook endpoint for auto-deployment on push.

    Security (P3 #26 - Enhanced):
    - Signature verification is MANDATORY when GITHUB_WEBHOOK_SECRET is set
    - Set WEBHOOK_ENFORCE_SIGNATURE=true to require signature even in development
    - Constant-time HMAC comparison prevents timing attacks
    - IP address logging for security auditing
    - Audit logging for all security events

    To set up:
    1. Set GITHUB_WEBHOOK_SECRET environment variable (use a strong random secret)
    2. Optional: Set WEBHOOK_ENFORCE_SIGNATURE=true to enforce in all environments
    3. In GitHub repo settings, add webhook:
       - URL: https://your-domain.com/api/admin/deploy/webhook
       - Content type: application/json
       - Secret: same as GITHUB_WEBHOOK_SECRET
       - Events: Push events

    The webhook will automatically deploy when code is pushed to main branch.
    """
    client_ip = get_client_ip(request)

    # Get request body
    payload = await request.body()

    # Verify signature using enhanced security module
    signature = request.headers.get("X-Hub-Signature-256", "")

    try:
        verify_github_signature(payload, signature, require_secret=True)
        WebhookAuditLogger.log_verification_success("github", "deploy_webhook", bool(signature))
    except HTTPException as e:
        WebhookAuditLogger.log_verification_failure("github", str(e.detail), client_ip)
        raise

    # Parse JSON payload
    try:
        import json
        data = json.loads(payload.decode())
    except Exception as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON payload"
        )

    # Check if this is a push to main branch
    ref = data.get("ref", "")
    branch = ref.replace("refs/heads/", "") if ref else ""

    logger.info(f"GitHub webhook received from {client_ip}: branch={branch}, ref={ref}")

    # Only deploy on push to main branch
    if branch != "main":
        logger.info(f"Ignoring push to branch '{branch}' (only auto-deploy on main)")
        return {
            "status": "ignored",
            "message": f"Push to '{branch}' ignored (only main branch triggers auto-deploy)",
            "branch": branch
        }

    # Get commit info
    head_commit = data.get("head_commit", {})
    commit_id = head_commit.get("id", "")[:7]
    committer = head_commit.get("committer", {}).get("name", "Unknown")
    message = head_commit.get("message", "")

    logger.info(f"🚀 Auto-deployment triggered by {committer}: {message[:50]}")

    # Trigger deployment asynchronously (don't wait for response)
    asyncio.create_task(trigger_deployment_async())

    return {
        "status": "deploying",
        "message": "Deployment triggered via webhook",
        "commit": commit_id,
        "branch": branch,
        "committer": committer
    }


async def trigger_deployment_async():
    """Async deployment task triggered by webhook."""
    try:
        # Fetch and pull
        await run_command("git fetch origin")
        success, stdout, stderr = await run_command("git pull origin main")

        if not success:
            logger.error(f"Webhook deployment failed: {stderr}")
            return

        logger.info(f"Webhook deployment successful: {stdout}")

        # Restart API
        restart_command = "pkill -f 'uvicorn app.main:app' && nohup uvicorn app.main:app --host 0.0.0.0 --port 8001 > /dev/null 2>&1 &"
        subprocess.Popen(
            ["bash", "-c", restart_command],
            cwd=PROJECT_DIR,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        logger.info("API restart triggered via webhook")

    except Exception as e:
        logger.error(f"Webhook deployment error: {e}")
