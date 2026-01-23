#!/usr/bin/env python3
"""
Capture Upcoming Odds Script

Captures player props odds for games starting soon (within 2 hours).

This should run frequently (every 30 minutes) to capture:
- Opening odds when they first become available
- Line movements as game time approaches

Usage:
    python scripts/capture_upcoming_odds.py [--hours-ahead HOURS]

Cron (every 30 minutes):
    */30 * * * * cd /opt/sports-bet-ai-api && venv/bin/python scripts/capture_upcoming_odds.py

Rate Limit Strategy:
- Only processes games within 2 hours of start time
- Skips games that already have recent snapshots (within 30 minutes)
- This minimizes API calls while still capturing line movements
"""
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.nba.models import Game, HistoricalOddsSnapshot
from app.services.nba.historical_odds_service import HistoricalOddsService
from sqlalchemy import and_

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/capture_upcoming_odds.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
DEFAULT_HOURS_AHEAD = 2  # Capture odds for games starting within 2 hours
SNAPSHOT_FRESHNESS_MINUTES = 30  # Don't re-capture if snapshot exists within this time
ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY")


async def main():
    """Main entry point."""
    import argparse
    parser = argparse.ArgumentParser(
        description="Capture odds for upcoming games"
    )
    parser.add_argument(
        "--hours-ahead",
        type=int,
        default=DEFAULT_HOURS_AHEAD,
        help=f"Capture games starting within this many hours (default: {DEFAULT_HOURS_AHEAD})"
    )
    parser.add_argument(
        "--starters-only",
        action="store_true",
        default=True,
        help="Only capture odds for starters (default: True)"
    )
    parser.add_argument(
        "--all-players",
        action="store_true",
        help="Include all players, not just starters"
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Capture Upcoming Odds Script")
    logger.info("=" * 60)

    # Check API key
    if not ODDS_API_KEY:
        logger.error("THE_ODDS_API_KEY environment variable not set")
        sys.exit(1)

    db = SessionLocal()
    service = HistoricalOddsService(db)

    try:
        now = datetime.now(timezone.utc)
        start_window = now
        end_window = now + timedelta(hours=args.hours_ahead)

        logger.info(f"Time window: {start_window.strftime('%Y-%m-%d %H:%M')} UTC to "
                   f"{end_window.strftime('%Y-%m-%d %H:%M')} UTC")

        # Get scheduled games within the time window
        games = db.query(Game).filter(
            Game.status == "scheduled",
            Game.game_date >= start_window,
            Game.game_date <= end_window
        ).order_by(Game.game_date).all()

        if not games:
            logger.info("No games found within the time window")
            return

        logger.info(f"Found {len(games)} scheduled games")

        # Process each game
        captured_total = 0
        skipped_fresh = 0
        skipped_no_id = 0
        errors = []

        for game in games:
            cst_time = game.game_date.replace(tzinfo=timezone.utc).astimezone(
                timezone(timedelta(hours=-6))
            )
            hours_until = (game.game_date.replace(tzinfo=timezone.utc) - now).total_seconds() / 3600

            logger.info(
                f"\nGame: {game.away_team} @ {game.home_team} "
                f"({cst_time.strftime('%a %m/%d %I:%M %p CST')}, {hours_until:.1f}h from now)"
            )

            # Check if game has Odds API format ID (32 character hex)
            if len(game.external_id) != 32:
                logger.info(f"  Skipping: not an Odds API game ID format")
                skipped_no_id += 1
                continue

            # Check if we have a recent snapshot (within freshness window)
            freshness_cutoff = now - timedelta(minutes=SNAPSHOT_FRESHNESS_MINUTES)
            recent_snapshot_count = db.query(HistoricalOddsSnapshot).filter(
                HistoricalOddsSnapshot.game_id == game.id,
                HistoricalOddsSnapshot.snapshot_time >= freshness_cutoff
            ).count()

            if recent_snapshot_count > 0:
                logger.info(
                    f"  Skipping: {recent_snapshot_count} snapshots exist "
                    f"within last {SNAPSHOT_FRESHNESS_MINUTES} minutes"
                )
                skipped_fresh += 1
                continue

            # Capture odds
            try:
                starters_only = args.starters_only and not args.all_players

                result = await service.batch_capture_game_odds(
                    game_id=str(game.id),
                    starters_only=starters_only
                )

                captured = result.get("captured", 0)
                errs = result.get("errors", 0)
                captured_total += captured

                if captured > 0:
                    logger.info(f"  Captured: {captured} snapshots")
                else:
                    logger.info(f"  No odds available (may not be posted yet)")

                if errs > 0:
                    logger.warning(f"  Errors: {errs}")

            except Exception as e:
                error_msg = f"{game.external_id}: {str(e)}"
                errors.append(error_msg)
                logger.error(f"  Error: {e}")

        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("Capture Complete")
        logger.info("=" * 60)
        logger.info(f"Games checked: {len(games)}")
        logger.info(f"Snapshots captured: {captured_total}")
        logger.info(f"Skipped (fresh data): {skipped_fresh}")
        logger.info(f"Skipped (no Odds API ID): {skipped_no_id}")

        if errors:
            logger.warning(f"\nErrors: {len(errors)}")
            for error in errors[:5]:
                logger.warning(f"  - {error}")
            if len(errors) > 5:
                logger.warning(f"  ... and {len(errors) - 5} more")

        # Show database stats
        total_snapshots = db.query(HistoricalOddsSnapshot).count()
        logger.info(f"\nDatabase: {total_snapshots} total snapshots")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
