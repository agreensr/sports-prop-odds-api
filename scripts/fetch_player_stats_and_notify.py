#!/usr/bin/env python3
"""
Fetch Player Stats and Send Telegram Notification

This script fetches player career stats for the 2025-26 NBA season,
including the last 10 games played, and sends a Telegram notification
when complete.

Usage:
    python scripts/fetch_player_stats_and_notify.py [--skip-telegram]

Requirements:
    - Database connection configured
    - TELEGRAM_CHAT_ID environment variable set (optional if --skip-telegram)
"""
import asyncio
import sys
import os
import logging
from datetime import datetime
import argparse

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.services.nba.player_career_stats_service import PlayerCareerStatsService
from app.services.telegram_service import send_batch_completion_notification, send_message

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Season to fetch
SEASON = "2025-26"

# Date range for stats (November 2025 to January 24, 2026)
START_DATE = "2025-11-01"
END_DATE = "2026-01-24"


async def main(skip_telegram=False):
    """Main function to fetch player stats and send notification."""
    logger.info(f"Starting player stats fetch for {SEASON} season")
    logger.info(f"Date range: {START_DATE} to {END_DATE}")

    # Initialize database session
    db = SessionLocal()

    try:
        # Initialize the player career stats service
        service = PlayerCareerStatsService(db)

        # Send start notification
        if not skip_telegram:
            send_message(
                f"🚀 Starting player stats fetch for {SEASON} season...\n"
                f"Fetching stats for all active players (last 10 games)."
            )
        else:
            logger.info("Skipping Telegram notification (skip_telegram=True)")

        # Fetch stats for all active players
        logger.info("Fetching stats for all active players...")
        results = await service.sync_all_active_players_career_stats(season=SEASON)

        # Log results
        logger.info(f"Stats fetch complete:")
        logger.info(f"  Total players: {results['total']}")
        logger.info(f"  Successful: {results['success']}")
        logger.info(f"  No data: {results['no_data']}")
        logger.info(f"  Errors: {results['errors']}")

        # Send completion notification
        if not skip_telegram:
            send_batch_completion_notification(
                total_players=results['total'],
                success_count=results['success'],
                error_count=results['errors']
            )

        # Print sample stats for first few players
        if results['results']:
            logger.info("\n" + "="*60)
            logger.info("Sample Player Stats (first 5 players):")
            logger.info("="*60)

            for result in results['results'][:5]:
                player_name = result['player_name']
                stats = result['stats']
                career = stats.get('career_stats', {})
                last_10_avg = stats.get('last_10_avg', {})

                logger.info(f"\n{player_name} ({career.get('team_abbr', 'N/A')})")
                logger.info(f"  Season Avg: {career.get('points_per_game', 0):.1f} PTS, "
                           f"{career.get('rebounds_per_game', 0):.1f} REB, "
                           f"{career.get('assists_per_game', 0):.1f} AST, "
                           f"{career.get('threes_per_game', 0):.1f} 3PM")

                if last_10_avg:
                    logger.info(f"  Last 10 Avg: {last_10_avg['points']:.1f} PTS, "
                               f"{last_10_avg['rebounds']:.1f} REB, "
                               f"{last_10_avg['assists']:.1f} AST, "
                               f"{last_10_avg['threes']:.1f} 3PM")

        logger.info("\n✅ Player stats fetch completed successfully!")

    except Exception as e:
        logger.error(f"Error during stats fetch: {e}", exc_info=True)

        # Send error notification
        if not skip_telegram:
            send_message(
                f"❌ Player stats fetch failed!\n\nError: {str(e)}"
            )
        sys.exit(1)

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch player stats from nba_api")
    parser.add_argument("--skip-telegram", action="store_true",
                        help="Skip Telegram notifications")
    args = parser.parse_args()

    asyncio.run(main(skip_telegram=args.skip_telegram))
