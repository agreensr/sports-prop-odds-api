"""
Automated task scheduler for sports-bet-ai-api.

This module provides scheduled background jobs for:
- Game schedule fetching from NBA API
- Player stats updates
- Odds fetching from bookmakers
- Injury data updates
- Lineup projections
- Prediction generation
- Result verification

Scheduler: APScheduler (lightweight, FastAPI-compatible)
"""
import logging
from datetime import time, datetime, timedelta
from typing import Optional
import asyncio
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.services.sync.orchestrator import SyncOrchestrator
from app.services.nba.prediction_service import PredictionService
from app.services.nba.injury_service import InjuryService
from app.services.nba.lineup_service import LineupService
from app.services.core.odds_api_service import OddsApiService
from app.services.nba.boxscore_import_service import BoxscoreImportService

logger = logging.getLogger(__name__)


class AutomationScheduler:
    """
    Main scheduler for automated background tasks.

    All scheduled jobs should be defined here with clear
    schedules and error handling.
    """

    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.running = False

    async def start(self):
        """Start the scheduler."""
        if self.running:
            logger.warning("Scheduler already running")
            return

        logger.info("Starting automation scheduler...")

        # Create scheduler
        self.scheduler = AsyncIOScheduler(
            timezone='America/Chicago',
            job_defaults={
                'coalesce': True,  # Combine missed runs into one
                'max_instances': 1,  # Only one instance of each job
                'misfire_grace_time': 300  # 5 minutes grace for misfires
            }
        )

        # Add all scheduled jobs
        self._schedule_games_fetch()
        self._schedule_odds_fetch()
        self._schedule_player_stats()
        self._schedule_roster_sync()
        self._schedule_injury_updates()
        self._schedule_lineup_updates()
        self._schedule_prediction_generation()
        self._schedule_result_verification()

        # Start the scheduler
        self.scheduler.start()
        self.running = True

        logger.info("✅ Scheduler started with %d jobs", len(self.scheduler.get_jobs()))

        # Log all scheduled jobs
        self._log_scheduled_jobs()

    async def stop(self):
        """Stop the scheduler."""
        if not self.running:
            return

        logger.info("Stopping scheduler...")
        self.scheduler.shutdown(wait=True)
        self.running = False
        logger.info("✅ Scheduler stopped")

    def _schedule_games_fetch(self):
        """
        Schedule: Fetch NBA games schedule.

        Frequency: Every 6 hours (6AM, 12PM, 6PM, 12AM CT)
        Purpose: Keep games table up to date for next 14 days
        """
        if self.scheduler is None:
            return

        @self.scheduler.scheduled_job(
            trigger=CronTrigger(
                hour='6,12,18,0',  # 6AM, 12PM, 6PM, 12AM CT
                minute=15,
                timezone='America/Chicago'
            ),
            id='games_fetch',
            name='Fetch NBA Games Schedule',
            misfire_grace_time=600
        )
        async def fetch_games_job():
            db = SessionLocal()
            try:
                orchestrator = SyncOrchestrator(db)
                result = await orchestrator.sync_games(
                    lookback_days=7,
                    lookahead_days=14,
                    season='2025-26'
                )
                logger.info(
                    f"✅ Games fetch: {result['matched']}/{result['processed']} "
                    f"matched ({result['duration_ms']}ms)"
                )
            except Exception as e:
                logger.error(f"❌ Games fetch failed: {e}")
            finally:
                db.close()

        logger.info("📅 Scheduled: Games fetch (every 6 hours at :15)")

    def _schedule_odds_fetch(self):
        """
        Schedule: Fetch betting odds from bookmakers.

        Frequency: TWICE DAILY (12PM CT, 5PM CT)
        Purpose: Update odds for upcoming games

        Note: Weekend and holiday games start as early as 12PM CT.
        - Midday: Get opening odds for early games (Sat/Sun/Holidays)
        - Evening: Check for line movements before late games
        - 2 requests/day = 60 requests/month (well within quota)
        """
        if self.scheduler is None:
            return

        # Midday fetch - for early games (12 PM CT)
        @self.scheduler.scheduled_job(
            trigger=CronTrigger(
                hour=12,  # 12PM CT (noon)
                minute=0,
                timezone='America/Chicago'
            ),
            id='odds_fetch_midday',
            name='Fetch Odds (Midday)',
            misfire_grace_time=600
        )
        async def fetch_odds_midday():
            db = SessionLocal()
            try:
                orchestrator = SyncOrchestrator(db)
                result = await orchestrator.sync_odds(
                    upcoming_only=True,
                    days=7
                )
                logger.info(f"✅ Morning odds fetch: {result['processed']} games")
            except Exception as e:
                logger.error(f"❌ Morning odds fetch failed: {e}")
            finally:
                db.close()

        # Evening fetch - check for line movements (5 PM CT)
        @self.scheduler.scheduled_job(
            trigger=CronTrigger(
                hour=17,  # 5PM CT
                minute=0,
                timezone='America/Chicago'
            ),
            id='odds_fetch_evening',
            name='Fetch Odds (Evening)',
            misfire_grace_time=600
        )
        async def fetch_odds_evening():
            db = SessionLocal()
            try:
                orchestrator = SyncOrchestrator(db)
                result = await orchestrator.sync_odds(
                    upcoming_only=True,
                    days=3
                )
                logger.info(f"✅ Evening odds fetch: {result['processed']} games")
            except Exception as e:
                logger.error(f"❌ Evening odds fetch failed: {e}")
            finally:
                db.close()

        logger.info("💰 Scheduled: Odds fetch (twice daily at 12PM and 5PM CT)")

    def _schedule_player_stats(self):
        """
        Schedule: Update player season stats.

        Frequency: Daily at 2AM CT
        Purpose: Refresh per-36 stats for all players
        """
        if self.scheduler is None:
            return

        @self.scheduler.scheduled_job(
            trigger=CronTrigger(
                hour=2,  # 2AM CT
                minute=0,
                timezone='America/Chicago'
            ),
            id='player_stats_update',
            name='Update Player Stats',
            misfire_grace_time=3600  # 1 hour grace
        )
        async def update_player_stats():
            db = SessionLocal()
            try:
                orchestrator = SyncOrchestrator(db)
                result = await orchestrator.sync_player_stats(
                    games_limit=50,
                    season='2025-26'
                )
                logger.info(
                    f"✅ Player stats: {result['success']}/{result['total']} "
                    f"updated ({result['total'] - result['errors'] - result['no_data']} players)"
                )
            except Exception as e:
                logger.error(f"❌ Player stats update failed: {e}")
            finally:
                db.close()

        logger.info("📊 Scheduled: Player stats update (daily 2AM CT)")

    def _schedule_roster_sync(self):
        """
        Schedule: Sync team rosters from NBA API.

        Frequency: Weekly on Sundays at 3AM CT
        Purpose: Update player.team assignments to match current rosters
        """
        if self.scheduler is None:
            return

        @self.scheduler.scheduled_job(
            trigger=CronTrigger(
                day_of_week='sun',  # Sunday
                hour=3,  # 3AM CT
                minute=0,
                timezone='America/Chicago'
            ),
            id='roster_sync',
            name='Team Roster Sync',
            misfire_grace_time=3600
        )
        async def sync_rosters():
            import subprocess
            import sys
            try:
                result = subprocess.run(
                    [sys.executable, 'scripts/sync_team_rosters.py'],
                    cwd='/Users/seangreen/Documents/my-projects/sports-bet-ai-api',
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minutes
                )
                if result.returncode == 0:
                    logger.info("✅ Roster sync completed successfully")
                else:
                    logger.error(f"❌ Roster sync failed: {result.stderr}")
            except Exception as e:
                logger.error(f"❌ Roster sync failed: {e}")

        logger.info("🏀 Scheduled: Team roster sync (weekly Sundays 3AM CT)")

    def _schedule_injury_updates(self):
        """
        Schedule: Fetch injury data from ESPN.

        Frequency: Every 2 hours
        Purpose: Keep injury statuses current
        """
        if self.scheduler is None:
            return

        @self.scheduler.scheduled_job(
            trigger=CronTrigger(
                minute='*/30',  # Every 30 minutes
                timezone='America/Chicago'
            ),
            id='injury_fetch',
            name='Fetch Injury Data',
            misfire_grace_time=600
        )
        async def fetch_injuries():
            db = SessionLocal()
            try:
                injury_service = InjuryService(db)
                result = await injury_service.fetch_injuries()
                logger.info(f"✅ Injury fetch: {len(result)} injuries updated")
            except Exception as e:
                logger.error(f"❌ Injury fetch failed: {e}")
            finally:
                db.close()

        logger.info("🏥 Scheduled: Injury fetch (every 30 minutes)")

    def _schedule_lineup_updates(self):
        """
        Schedule: Fetch projected lineups.

        Frequency: Every 2 hours, plus 1 hour before games
        Purpose: Keep lineup projections current
        """
        if self.scheduler is None:
            return

        @self.scheduler.scheduled_job(
            trigger=CronTrigger(
                minute='*/30',  # Every 30 minutes
                timezone='America/Chicago'
            ),
            id='lineup_fetch',
            name='Fetch Lineup Data',
            misfire_grace_time=600
        )
        async def fetch_lineups():
            db = SessionLocal()
            try:
                lineup_service = LineupService(db)
                result = await lineup_service.fetch_lineups()
                logger.info(f"✅ Lineup fetch: {len(result)} lineups updated")
            except Exception as e:
                logger.error(f"❌ Lineup fetch failed: {e}")
            finally:
                db.close()

        logger.info("👥 Scheduled: Lineup fetch (every 30 minutes)")

    def _schedule_prediction_generation(self):
        """
        Schedule: Generate predictions for upcoming games.

        Frequency: Daily at 8AM CT, plus 1 hour before each game
        Purpose: Auto-generate prop predictions
        """
        if self.scheduler is None:
            return

        # Daily prediction refresh
        @self.scheduler.scheduled_job(
            trigger=CronTrigger(
                hour=8,  # 8AM CT
                minute=0,
                timezone='America/Chicago'
            ),
            id='predictions_daily',
            name='Daily Predictions',
            misfire_grace_time=1800
        )
        async def daily_predictions():
            db = SessionLocal()
            try:
                prediction_service = PredictionService(db)

                # Get games for next 3 days
                from datetime import date, timedelta
                today = date.today()

                for days_ahead in range(3):
                    game_date = today + timedelta(days=days_ahead)

                    # Fetch games for this date
                    from app.models import Game
                    games = db.query(Game).filter(
                        Game.game_date >= game_date,
                        Game.game_date < game_date + timedelta(days=1),
                        Game.status == 'scheduled'
                    ).all()

                    for game in games:
                        try:
                            await prediction_service.generate_predictions_for_game(game.id)
                            logger.info(f"✅ Generated predictions for game {game.external_id}")
                        except Exception as e:
                            logger.error(f"❌ Prediction generation failed for game {game.external_id}: {e}")

                logger.info("✅ Daily predictions complete")
            except Exception as e:
                logger.error(f"❌ Daily predictions failed: {e}")
            finally:
                db.close()

        logger.info("🎯 Scheduled: Daily predictions (8AM CT)")

    def _schedule_result_verification(self):
        """
        Schedule: Verify prediction results against actual stats.

        Frequency: Daily at 1AM CT
        Purpose: Check predictions against completed games
        """
        if self.scheduler is None:
            return

        @self.scheduler.scheduled_job(
            trigger=CronTrigger(
                hour=1,  # 1AM CT
                minute=0,
                timezone='America/Chicago'
            ),
            id='result_verification',
            name='Verify Results',
            misfire_grace_time=3600
        )
        async def verify_results():
            db = SessionLocal()
            try:
                boxscore_service = BoxscoreImportService(db)

                # Get completed games from yesterday
                from datetime import date, timedelta
                yesterday = date.today() - timedelta(days=1)

                result = await boxscore_service.import_boxscores_for_date(yesterday)
                logger.info(f"✅ Result verification: {result.get('games_processed', 0)} games")
            except Exception as e:
                logger.error(f"❌ Result verification failed: {e}")
            finally:
                db.close()

        logger.info("✅ Scheduled: Result verification (daily 1AM CT)")

    def _log_scheduled_jobs(self):
        """Log all scheduled jobs for visibility."""
        jobs = self.scheduler.get_jobs()

        logger.info("=" * 60)
        logger.info("SCHEDULED AUTOMATION JOBS")
        logger.info("=" * 60)

        for job in jobs:
            next_run = job.next_run_time
            if next_run:
                next_run_str = next_run.strftime('%Y-%m-%d %I:%M %p CT')
            else:
                next_run_str = 'Pending'

            logger.info(f"  • {job.name}")
            logger.info(f"    ID: {job.id}")
            logger.info(f"    Next run: {next_run_str}")
            logger.info("")

        logger.info("=" * 60)
        logger.info(f"Total jobs scheduled: {len(jobs)}")
        logger.info("=" * 60)


# Global scheduler instance
_scheduler: Optional[AutomationScheduler] = None


async def start_scheduler():
    """Start the global scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AutomationScheduler()
        await _scheduler.start()
    return _scheduler


async def stop_scheduler():
    """Stop the global scheduler."""
    global _scheduler
    if _scheduler is not None:
        await _scheduler.stop()
        _scheduler = None


def get_scheduler() -> Optional[AutomationScheduler]:
    """Get the global scheduler instance."""
    return _scheduler
