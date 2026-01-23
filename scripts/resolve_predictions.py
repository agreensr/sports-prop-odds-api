#!/usr/bin/env python3
"""
Backfill Resolution Script

Resolves predictions for completed games by fetching boxscores from NBA API.

This script is useful for:
- Backfilling historical accuracy data
- Manually triggering resolution for recent games
- Testing the resolution pipeline with dry-run mode

Usage:
    # Resolve games from last 7 days (dry run)
    python scripts/resolve_predictions.py --days=7 --dry-run

    # Resolve games from last 7 days (actual execution)
    python scripts/resolve_predictions.py --days=7

    # Resolve a specific game
    python scripts/resolve_predictions.py --game-id=<uuid>

    # Resolve all unresolved games (up to 30 days back)
    python scripts/resolve_predictions.py --all
"""
import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.services.nba.boxscore_import_service import BoxscoreImportService

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/resolve_predictions.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Resolve predictions with actual game results"
    )

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        '--days',
        type=int,
        help='Resolve completed games from last N days'
    )
    mode_group.add_argument(
        '--game-id',
        type=str,
        help='Resolve predictions for a specific game ID (UUID)'
    )
    mode_group.add_argument(
        '--all',
        action='store_true',
        help='Resolve all unresolved games (up to 30 days back)'
    )

    # Options
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simulate without making database changes'
    )
    parser.add_argument(
        '--hours-back',
        type=int,
        default=48,
        help='Hours back to look for completed games (default: 48)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    return parser.parse_args()


async def resolve_by_days(days: int, dry_run: bool, verbose: bool):
    """
    Resolve predictions for completed games in the last N days.

    Args:
        days: Number of days back to process
        dry_run: If True, simulate without making changes
        verbose: Enable verbose logging
    """
    logger.info(f"Resolving predictions from last {days} days (dry_run={dry_run})")

    db = SessionLocal()

    try:
        service = BoxscoreImportService(db)

        # Get unresolved games status first
        status = service.get_resolution_status()
        logger.info(f"Current resolution status:")
        logger.info(f"  Total predictions: {status['total_predictions']}")
        logger.info(f"  Resolved: {status['resolved_predictions']}")
        logger.info(f"  Unresolved: {status['unresolved_predictions']}")
        logger.info(f"  Resolution rate: {status['resolution_rate']:.1%}")

        # Resolve games
        hours_back = days * 24
        result = await service.resolve_predictions_for_completed_games(
            hours_back=hours_back,
            dry_run=dry_run
        )

        # Log results
        logger.info("\n" + "=" * 60)
        logger.info("Resolution Results")
        logger.info("=" * 60)
        logger.info(f"Games processed: {result['games_processed']}")
        logger.info(f"Predictions resolved: {result['predictions_resolved']}")
        logger.info(f"PlayerStats created: {result['player_stats_created']}")
        logger.info(f"PlayerStats updated: {result['player_stats_updated']}")

        if result['errors']:
            logger.warning(f"Errors: {len(result['errors'])}")
            for error in result['errors'][:10]:  # Show first 10
                logger.warning(f"  - {error}")

        logger.info("=" * 60)

        if not dry_run:
            db.commit()
            logger.info("Changes committed to database")
        else:
            logger.info("Dry run complete - no changes made")

    except Exception as e:
        logger.error(f"Error resolving predictions: {e}")
        db.rollback()
        raise
    finally:
        db.close()


async def resolve_by_game_id(game_id: str, dry_run: bool, verbose: bool):
    """
    Resolve predictions for a specific game.

    Args:
        game_id: Game UUID
        dry_run: If True, simulate without making changes
        verbose: Enable verbose logging
    """
    logger.info(f"Resolving predictions for game {game_id} (dry_run={dry_run})")

    db = SessionLocal()

    try:
        service = BoxscoreImportService(db)
        result = await service.resolve_predictions_for_game(game_id, dry_run=dry_run)

        # Log results
        logger.info("\n" + "=" * 60)
        logger.info("Resolution Results")
        logger.info("=" * 60)
        logger.info(f"Predictions resolved: {result['predictions_resolved']}")
        logger.info(f"PlayerStats created: {result['player_stats_created']}")
        logger.info(f"PlayerStats updated: {result['player_stats_updated']}")

        if result['errors']:
            logger.warning(f"Errors: {len(result['errors'])}")
            for error in result['errors']:
                logger.warning(f"  - {error}")

        logger.info("=" * 60)

        if not dry_run:
            db.commit()
            logger.info("Changes committed to database")
        else:
            logger.info("Dry run complete - no changes made")

    except Exception as e:
        logger.error(f"Error resolving game {game_id}: {e}")
        db.rollback()
        raise
    finally:
        db.close()


async def resolve_all_unresolved(dry_run: bool, verbose: bool, hours_back: int = 720):
    """
    Resolve all unresolved games within the time window.

    Args:
        dry_run: If True, simulate without making changes
        verbose: Enable verbose logging
        hours_back: Hours to look back (default: 720 = 30 days)
    """
    logger.info(f"Resolving all unresolved games (last {hours_back // 24} days, dry_run={dry_run})")

    db = SessionLocal()

    try:
        service = BoxscoreImportService(db)

        # First, get list of unresolved games
        unresolved = service.get_unresolved_games(hours_back=hours_back)

        logger.info(f"Found {len(unresolved)} unresolved games")

        if not unresolved:
            logger.info("No unresolved games found")
            return

        # Show first few games
        logger.info("\nUnresolved games (first 10):")
        for i, game in enumerate(unresolved[:10], 1):
            logger.info(f"  {i}. {game['away_team']} @ {game['home_team']} "
                       f"({game['game_date'][:10]}) - {game['unresolved_predictions']} predictions")

        if len(unresolved) > 10:
            logger.info(f"  ... and {len(unresolved) - 10} more")

        # Resolve all
        result = await service.resolve_predictions_for_completed_games(
            hours_back=hours_back,
            dry_run=dry_run
        )

        # Log results
        logger.info("\n" + "=" * 60)
        logger.info("Resolution Results")
        logger.info("=" * 60)
        logger.info(f"Games processed: {result['games_processed']}")
        logger.info(f"Predictions resolved: {result['predictions_resolved']}")
        logger.info(f"PlayerStats created: {result['player_stats_created']}")
        logger.info(f"PlayerStats updated: {result['player_stats_updated']}")

        if result['errors']:
            logger.warning(f"Errors: {len(result['errors'])}")
            for error in result['errors'][:10]:
                logger.warning(f"  - {error}")

        logger.info("=" * 60)

        if not dry_run:
            db.commit()
            logger.info("Changes committed to database")
        else:
            logger.info("Dry run complete - no changes made")

    except Exception as e:
        logger.error(f"Error resolving predictions: {e}")
        db.rollback()
        raise
    finally:
        db.close()


async def main():
    """Main entry point."""
    args = parse_args()

    # Set verbose logging if requested
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 60)
    logger.info("Backfill Resolution Script")
    logger.info(f"Started at: {datetime.now(timezone.utc).isoformat()}")
    logger.info("=" * 60)

    try:
        if args.days is not None:
            await resolve_by_days(args.days, args.dry_run, args.verbose)
        elif args.game_id:
            await resolve_by_game_id(args.game_id, args.dry_run, args.verbose)
        elif args.all:
            await resolve_all_unresolved(args.dry_run, args.verbose)

        logger.info("\n" + "=" * 60)
        logger.info("Script completed successfully")
        logger.info(f"Finished at: {datetime.now(timezone.utc).isoformat()}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Script failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
