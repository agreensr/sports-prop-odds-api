#!/usr/bin/env python3
"""
Backfill Historical Odds Script (ONE-TIME USE)

This script populates historical odds data for PAST completed games.

IMPORTANT: This is a ONE-TIME or ON-DEMAND script for backfilling historical data.
For ongoing operations, use:
  - capture_upcoming_odds.py (pre-game, runs every 30 min)
  - resolve_snapshots.py (post-game, runs daily at 3 AM)

Process:
1. Finds completed games without historical odds snapshots
2. Fetches player props odds from The Odds API
3. Resolves snapshots with actual game results

Usage (one-time backfill):
    # Backfill 50 recent completed games
    python scripts/backfill_historical_odds.py --games 50

    # Backfill specific date range (modify script filter)

When to run:
  - Initial setup: Run once to populate historical data
  - After catching up: Let capture_upcoming_odds.py handle new games
  - Manual catch-up: Run occasionally if you missed games

Rate Limit Strategy:
- Free tier: 500 requests/month (~16/day)
- Process 50 games = ~50 requests (one-time)
- After backfill: Only capture_upcoming_odds.py uses quota (~20-30/day)
"""
import argparse
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
from app.services.core.odds_api_service import get_odds_service

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/backfill_historical_odds.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY")


def check_api_quota() -> dict:
    """Check remaining API quota."""
    if not ODDS_API_KEY:
        return {"remaining": 0, "status": "no_key"}

    try:
        odds_api = get_odds_service(ODDS_API_KEY)
        # This is async, need to run it
        return asyncio.run(odds_api.get_quota_status())
    except Exception as e:
        logger.error(f"Error checking quota: {e}")
        return {"remaining": "unknown", "status": "error"}


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Backfill historical odds data for hit rate calculation"
    )
    parser.add_argument(
        "--games",
        type=int,
        default=5,
        help="Max games to process (default: 5)"
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
    parser.add_argument(
        "--check-quota",
        action="store_true",
        help="Check API quota before running"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without executing"
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Historical Odds Backfill Script")
    logger.info("=" * 60)

    # Check API key
    if not ODDS_API_KEY:
        logger.error("THE_ODDS_API_KEY environment variable not set")
        sys.exit(1)

    # Check quota if requested
    if args.check_quota:
        logger.info("Checking API quota...")
        quota = check_api_quota()
        logger.info(f"Quota status: {quota}")
        if quota.get("remaining") == "0":
            logger.error("API quota exhausted. Exiting.")
            sys.exit(1)

    db = SessionLocal()
    service = HistoricalOddsService(db)

    try:
        # Find completed games without snapshots
        games_without_snapshots = (
            db.query(Game)
            .filter(Game.status == "final")
            .filter(~Game.id.in_(
                db.query(HistoricalOddsSnapshot.game_id).distinct()
            ))
            .order_by(Game.game_date.desc())
            .limit(args.games)
            .all()
        )

        if not games_without_snapshots:
            logger.info("No games to backfill")
            return

        logger.info(f"Found {len(games_without_snapshots)} games to backfill")

        # Show games to be processed
        logger.info("\nGames to process:")
        for game in games_without_snapshots[:10]:  # Show first 10
            cst_time = game.game_date.replace(tzinfo=timezone.utc).astimezone(
                timezone(timedelta(hours=-6))
            )
            logger.info(
                f"  - {game.external_id}: {game.away_team} @ {game.home_team} "
                f"({cst_time.strftime('%Y-%m-%d %I:%M %p CST')})"
            )
        if len(games_without_snapshots) > 10:
            logger.info(f"  ... and {len(games_without_snapshots) - 10} more")

        if args.dry_run:
            logger.info("\nDry run - exiting without changes")
            return

        captured_total = 0
        resolved_total = 0
        errors = []

        for game in games_without_snapshots:
            try:
                logger.info(
                    f"\nProcessing game {game.external_id}: "
                    f"{game.away_team} @ {game.home_team}"
                )

                # Check if game has Odds API format ID
                if len(game.external_id) != 32:
                    logger.info(
                        f"  Skipping: not an Odds API game ID format "
                        f"(expected 32 chars, got {len(game.external_id)})"
                    )
                    continue

                starters_only = args.starters_only and not args.all_players

                # Capture odds
                capture_result = await service.batch_capture_game_odds(
                    game_id=str(game.id),
                    starters_only=starters_only
                )
                captured_total += capture_result.get("captured", 0)

                if capture_result.get("captured", 0) > 0:
                    logger.info(
                        f"  Captured {capture_result['captured']} snapshots "
                        f"({capture_result.get('errors', 0)} errors)"
                    )
                else:
                    logger.info("  No snapshots captured (odds may not be available)")

                # Resolve with actual results
                resolve_result = service.resolve_snapshots_for_game(str(game.id))
                resolved_total += resolve_result.get("resolved", 0)

                if resolve_result.get("resolved", 0) > 0:
                    logger.info(
                        f"  Resolved {resolve_result['resolved']} snapshots "
                        f"({resolve_result.get('errors', 0)} errors)"
                    )

                if resolve_result.get("errors", 0) > 0:
                    errors.append(f"{game.external_id}: {resolve_result['errors']} errors")

            except Exception as e:
                error_msg = f"{game.external_id}: {str(e)}"
                errors.append(error_msg)
                logger.error(f"Error processing game {game.external_id}: {e}")

        # Final summary
        logger.info("\n" + "=" * 60)
        logger.info("Backfill Complete")
        logger.info("=" * 60)
        logger.info(f"Games processed: {len(games_without_snapshots)}")
        logger.info(f"Snapshots captured: {captured_total}")
        logger.info(f"Snapshots resolved: {resolved_total}")

        if errors:
            logger.warning(f"\nErrors: {len(errors)}")
            for error in errors[:5]:  # Show first 5
                logger.warning(f"  - {error}")
            if len(errors) > 5:
                logger.warning(f"  ... and {len(errors) - 5} more")

        # Show total snapshots in database
        total_snapshots = db.query(HistoricalOddsSnapshot).count()
        resolved_snapshots = db.query(HistoricalOddsSnapshot).filter(
            HistoricalOddsSnapshot.hit_result.isnot(None)
        ).count()

        logger.info(f"\nDatabase totals:")
        logger.info(f"  Total snapshots: {total_snapshots}")
        logger.info(f"  Resolved snapshots: {resolved_snapshots}")
        logger.info(f"  Resolution rate: "
                   f"{resolved_snapshots / total_snapshots * 100:.1f}%" if total_snapshots > 0 else "N/A")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
