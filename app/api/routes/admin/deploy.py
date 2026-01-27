"""
Admin deployment routes for triggering git pull and API restart.

Provides endpoints for:
- Manual deployment trigger
- GitHub webhook integration
- Deployment status checks
"""
import asyncio
import logging
import os
import subprocess
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Header, Depends
from pydantic import BaseModel
import hashlib
import hmac

from app.core.config import settings

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


def verify_github_signature(payload: bytes, signature: str) -> bool:
    """
    Verify GitHub webhook signature.

    Args:
        payload: Request body bytes
        signature: X-Hub-Signature-256 header value

    Returns:
        True if signature is valid
    """
    if not GITHUB_WEBHOOK_SECRET:
        logger.warning("GITHUB_WEBHOOK_SECRET not set - skipping signature verification")
        return True

    if not signature:
        return False

    # Signature format: sha256=<hash>
    if not signature.startswith("sha256="):
        return False

    hash_algorithm, github_signature = signature.split("=", 1)

    # Compute expected signature
    expected_signature = hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    # Compare signatures using constant-time comparison
    return hmac.compare_digest(expected_signature, github_signature)


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

    To set up:
    1. Set GITHUB_WEBHOOK_SECRET environment variable
    2. In GitHub repo settings, add webhook:
       - URL: https://your-domain.com/api/admin/deploy/webhook
       - Content type: application/json
       - Secret: your webhook secret
       - Events: Push events

    The webhook will automatically deploy when code is pushed to main branch.
    """
    # Get request body
    payload = await request.body()

    # Verify signature
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_github_signature(payload, signature):
        logger.warning("Invalid GitHub webhook signature")
        raise HTTPException(
            status_code=401,
            detail="Invalid signature"
        )

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

    logger.info(f"GitHub webhook received: branch={branch}, ref={ref}")

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
