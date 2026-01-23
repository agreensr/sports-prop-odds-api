#!/usr/bin/env python3
"""
Resolve Historical Odds Snapshots Script

Resolves captured odds snapshots with actual game results.

This should run after games complete to:
1. Match captured odds with actual boxscore statistics
2. Determine hit results (OVER, UNDER, PUSH)
3. Update snapshots for hit rate calculation

Usage:
    python scripts/resolve_snapshots.py [--hours-back HOURS]

Cron (daily at 3 AM CST, after all games finish):
    0 3 * * * cd /opt/sports-bet-ai-api && venv/bin/python scripts/resolve_snapshots.py

Process:
1. Find completed games with unresolved snapshots
2. Fetch actual stats from PlayerStats table
3. Compare actual values vs betting lines
4. Update snapshots with hit_result (OVER/UNDER/PUSH)
"""
import logging
import os
import sys
from datetime import datetime, timedelta, timezone, UTC
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.nba.models import Game, HistoricalOddsSnapshot, PlayerStats
from app.services.nba.historical_odds_service import HistoricalOddsService
from sqlalchemy import func

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/resolve_snapshots.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
DEFAULT_HOURS_BACK = 48  # Process games completed in last 48 hours


def main():
    """Main entry point."""
    import argparse
    parser = argparse.ArgumentParser(
        description="Resolve odds snapshots with actual game results"
    )
    parser.add_argument(
        "--hours-back",
        type=int,
        default=DEFAULT_HOURS_BACK,
        help=f"Process games completed within this many hours (default: {DEFAULT_HOURS_BACK})"
    )
    parser.add_argument(
        "--game-id",
        type=str,
        help="Process specific game ID only"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be resolved without making changes"
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Resolve Historical Odds Snapshots Script")
    logger.info("=" * 60)

    db = SessionLocal()
    service = HistoricalOddsService(db)

    try:
        if args.game_id:
            # Process specific game
            game = db.query(Game).filter(Game.id == args.game_id).first()
            if not game:
                logger.error(f"Game {args.game_id} not found")
                sys.exit(1)

            games_to_process = [game]
            logger.info(f"Processing specific game: {game.away_team} @ {game.home_team}")
        else:
            # Find completed games with unresolved snapshots
            cutoff = datetime.now(UTC) - timedelta(hours=args.hours_back)

            # Subquery: find games with unresolved snapshots
            games_with_unresolved = db.query(
                HistoricalOddsSnapshot.game_id
            ).filter(
                HistoricalOddsSnapshot.hit_result.is_(None)
            ).distinct().all()

            game_ids = [g[0] for g in games_with_unresolved]

            if not game_ids:
                logger.info("No games with unresolved snapshots found")
                return

            # Get games that are completed
            games_to_process = db.query(Game).filter(
                Game.id.in_(game_ids),
                Game.status == "final",
                Game.game_date >= cutoff
            ).order_by(Game.game_date.desc()).all()

            if not games_to_process:
                logger.info(
                    f"No completed games with unresolved snapshots "
                    f"within last {args.hours_back} hours"
                )
                return

            logger.info(
                f"Found {len(games_to_process)} completed games "
                f"with unresolved snapshots"
            )

        if args.dry_run:
            logger.info("\nDry run - showing what would be resolved:")
            for game in games_to_process:
                unresolved_count = db.query(HistoricalOddsSnapshot).filter(
                    HistoricalOddsSnapshot.game_id == game.id,
                    HistoricalOddsSnapshot.hit_result.is_(None)
                ).count()

                logger.info(
                    f"  - {game.external_id}: {game.away_team} @ {game.home_team} "
                    f"({unresolved_count} unresolved snapshots)"
                )
            logger.info("\nDry run - exiting without changes")
            return

        # Process each game
        resolved_total = 0
        error_total = 0
        processed_games = 0
        no_stats_games = 0

        for game in games_to_process:
            cst_time = game.game_date.replace(tzinfo=timezone.utc).astimezone(
                timezone(timedelta(hours=-6))
            )

            logger.info(
                f"\nProcessing: {game.external_id} - "
                f"{game.away_team} @ {game.home_team} "
                f"({cst_time.strftime('%a %m/%d %I:%M %P CST')})"
            )

            # Check if PlayerStats exist for this game
            stats_count = db.query(PlayerStats).filter(
                PlayerStats.game_id == game.id
            ).count()

            if stats_count == 0:
                logger.info(f"  Skipping: No player stats found in database")
                logger.info(f"  (Run boxscore import first: scripts/fetch_boxscores.py)")
                no_stats_games += 1
                continue

            # Resolve snapshots
            result = service.resolve_snapshots_for_game(str(game.id))

            resolved = result.get("resolved", 0)
            errs = result.get("errors", 0)

            resolved_total += resolved
            error_total += errs

            if resolved > 0:
                processed_games += 1
                logger.info(f"  Resolved: {resolved} snapshots")

            if errs > 0:
                logger.warning(f"  Errors: {errs}")

        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("Resolution Complete")
        logger.info("=" * 60)
        logger.info(f"Games processed: {processed_games}")
        logger.info(f"Snapshots resolved: {resolved_total}")
        logger.info(f"Errors: {error_total}")
        logger.info(f"Skipped (no stats): {no_stats_games}")

        # Show hit rate statistics
        if resolved_total > 0:
            logger.info("\nHit Result Distribution:")
            hit_results = db.query(
                HistoricalOddsSnapshot.hit_result,
                func.count(HistoricalOddsSnapshot.id)
            ).filter(
                HistoricalOddsSnapshot.hit_result.isnot(None)
            ).group_by(HistoricalOddsSnapshot.hit_result).all()

            for result_type, count in hit_results:
                logger.info(f"  {result_type}: {count}")

        # Database totals
        total_snapshots = db.query(HistoricalOddsSnapshot).count()
        resolved_snapshots = db.query(HistoricalOddsSnapshot).filter(
            HistoricalOddsSnapshot.hit_result.isnot(None)
        ).count()
        unresolved_snapshots = total_snapshots - resolved_snapshots

        logger.info(f"\nDatabase Totals:")
        logger.info(f"  Total snapshots: {total_snapshots}")
        logger.info(f"  Resolved: {resolved_snapshots} ({resolved_snapshots/total_snapshots*100:.1f}%)"
                   if total_snapshots > 0 else "  Resolved: 0")
        logger.info(f"  Unresolved: {unresolved_snapshots}")

        # Sample size statistics (for hit rate reliability)
        if resolved_snapshots >= 100:
            logger.info(f"\nData Quality: Strong (100+ resolved snapshots)")
        elif resolved_snapshots >= 50:
            logger.info(f"\nData Quality: Moderate (50+ resolved snapshots)")
        elif resolved_snapshots >= 20:
            logger.info(f"\nData Quality: Building (20+ resolved snapshots)")
        else:
            logger.info(f"\nData Quality: Initial (<20 resolved snapshots)")
            logger.info(f"  Run backfill to populate historical data:")
            logger.info(f"    python scripts/backfill_historical_odds.py --games 50")

    finally:
        db.close()


if __name__ == "__main__":
    main()
