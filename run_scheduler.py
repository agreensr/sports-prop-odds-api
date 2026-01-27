#!/usr/bin/env python3
"""
Background runner for sports-bet-ai-api automation scheduler.

This script runs the automation scheduler as a standalone background service.
It can be run via systemd, supervisor, or directly.

Usage:
    python run_scheduler.py              # Run in foreground
    python run_scheduler.py --daemon     # Run as daemon
    python run_scheduler.py --status    # Check status
"""
import asyncio
import argparse
import signal
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.scheduler import AutomationScheduler
from app.core.config import settings
import logging

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SchedulerRunner:
    """Runner for the automation scheduler."""

    def __init__(self):
        self.scheduler: AutomationScheduler = None
        self.shutdown = False

    async def start(self):
        """Start the scheduler and run until shutdown."""
        logger.info("🚀 Starting scheduler runner...")

        # Create and start scheduler
        self.scheduler = AutomationScheduler()
        await self.scheduler.start()

        logger.info("✅ Scheduler is now running")
        logger.info("Press Ctrl+C to stop")

        # Setup signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: self._set_shutdown())

        # Keep running until shutdown
        while not self.shutdown:
            await asyncio.sleep(1)

        # Cleanup
        await self.scheduler.stop()
        logger.info("✅ Scheduler runner stopped")

    def _set_shutdown(self):
        """Set shutdown flag."""
        logger.info("⏹️  Shutdown signal received")
        self.shutdown = True


async def run_status_check() -> bool:
    """Check if scheduler is running and print status."""
    from app.core.scheduler import get_scheduler

    scheduler = get_scheduler()

    if scheduler is None:
        print("❌ Scheduler is not running")
        return False

    if scheduler.running:
        print("✅ Scheduler is running")

        jobs = scheduler.scheduler.get_jobs()
        print(f"   Total jobs: {len(jobs)}")
        print()
        print("   Scheduled Jobs:")
        for job in jobs:
            next_run = job.next_run_time
            next_run_str = next_run.strftime('%Y-%m-%d %I:%M %p CT') if next_run else 'Pending'
            print(f"   • {job.name}")
            print(f"     Next run: {next_run_str}")
            print()

        return True
    else:
        print("❌ Scheduler is not running")
        return False


async def run_trigger_job(job_id: str):
    """Manually trigger a specific job."""
    from app.core.scheduler import get_scheduler

    scheduler = get_scheduler()

    if scheduler is None:
        print("❌ Scheduler is not running")
        return False

    # Find and trigger the job
    job = None
    for j in scheduler.scheduler.get_jobs():
        if j.id == job_id:
            job = j
            break

    if not job:
        print(f"❌ Job '{job_id}' not found")
        return False

    try:
        print(f"🔄 Triggering job: {job.name}")
        await job.func()
        print(f"✅ Job '{job_id}' triggered successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to trigger job: {e}")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Run the sports-bet-ai-api automation scheduler'
    )

    parser.add_argument(
        '--daemon',
        action='store_true',
        help='Run as daemon (background process)'
    )

    parser.add_argument(
        '--status',
        action='store_true',
        help='Check scheduler status and exit'
    )

    parser.add_argument(
        '--trigger',
        type=str,
        metavar='JOB_ID',
        help='Manually trigger a specific job by ID'
    )

    parser.add_argument(
        '--list-jobs',
        action='store_true',
        help='List all scheduled jobs and exit'
    )

    args = parser.parse_args()

    # Handle status check
    if args.status:
        asyncio.run(run_status_check())
        return 0

    # Handle list jobs
    if args.list_jobs:
        asyncio.get_event_loop().run_until_complete(
            _list_jobs_and_exit()
        )
        return 0

    # Handle manual job trigger
    if args.trigger:
        result = asyncio.run(run_trigger_job(args.trigger))
        return 0 if result else 1

    # Run the scheduler
    if args.daemon:
        # Run as daemon - fork to background
        # (simplified for now - could use proper daemonization)
        logger.info("Running in daemon mode (background)")
        # For proper daemonization, consider using python-daemon package

    runner = SchedulerRunner()

    try:
        asyncio.run(runner.start())
    except KeyboardInterrupt:
        logger.info("🛑 Received interrupt, shutting down...")
        return 0
    except Exception as e:
        logger.error(f"❌ Scheduler error: {e}")
        return 1


async def _list_jobs_and_exit():
    """List jobs and exit."""
    from app.core.scheduler import get_scheduler
    from datetime import datetime

    print("=" * 60)
    print("SCHEDULED AUTOMATION JOBS")
    print("=" * 60)
    print()

    scheduler = get_scheduler()

    if scheduler is None or not scheduler.running:
        print("⚠️  Scheduler is not running")
        print()
        print("Start the scheduler first:")
        print("  python run_scheduler.py")
        print("  OR")
        print("  POST /api/sync/scheduler/start (via API)")
        return

    jobs = scheduler.scheduler.get_jobs()

    print(f"Total jobs: {len(jobs)}")
    print()

    for job in jobs:
        next_run = job.next_run_time
        if next_run:
            next_run_str = next_run.strftime('%Y-%m-%d %I:%M %p CT')
        else:
            next_run_str = 'Pending'

        # Parse trigger
        trigger_str = str(job.trigger)

        print(f"📋 {job.name}")
        print(f"   ID: {job.id}")
        print(f"   Schedule: {trigger_str}")
        print(f"   Next run: {next_run_str}")
        print()

    print("=" * 60)


if __name__ == '__main__':
    sys.exit(main())
