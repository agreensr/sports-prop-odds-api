"""
Background task scheduler for automated data fetching.

TODO: Implement scheduled tasks for:
- Injury report updates (every 30 minutes)
- Lineup updates (every hour)
- Historical odds fetching (daily)
- Opening odds tracking (before games)
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

async def start_scheduler():
    """Initialize the task scheduler."""
    logger.info("Scheduler initialized (no tasks configured yet)")
    # Stub implementation - allows app to start
    # Future: Add APScheduler or similar for background tasks
    pass

async def stop_scheduler():
    """Shutdown the task scheduler."""
    logger.info("Scheduler stopped")
    pass
