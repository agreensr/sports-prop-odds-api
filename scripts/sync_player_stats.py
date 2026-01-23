#!/usr/bin/env python3
"""
Player stats sync script for scheduled execution.

Syncs player statistics from nba_api to database cache.
This improves prediction accuracy by using actual player data
instead of position averages.

Usage:
    python scripts/sync_player_stats.py

Cron scheduling (every 6 hours):
    0 */6 * * * cd /opt/sports-bet-ai-api && /opt/sports-bet-ai-api/venv/bin/python scripts/sync_player_stats.py >> /tmp/sync_player_stats.log 2>&1
"""
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.services.nba_api_service import NbaApiService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/sync_player_stats.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Default season
DEFAULT_SEASON = "2025-26"
DEFAULT_GAMES_LIMIT = 50


async def sync_player_stats(
    season: str = DEFAULT_SEASON,
    games_limit: int = DEFAULT_GAMES_LIMIT
) -> dict:
    """
    Sync all active players' season stats from nba_api.

    Args:
        season: NBA season (e.g., "2024-25")
        games_limit: Number of recent games to average

    Returns:
        dict with sync results
    """
    db = SessionLocal()
    nba_service = NbaApiService(db)

    try:
        logger.info("=" * 60)
        logger.info("Player Stats Sync Script Started")
        logger.info("=" * 60)
        logger.info(f"Season: {season}")
        logger.info(f"Games limit: {games_limit}")

        start_time = datetime.now()

        # Check if nba_api is available
        if not nba_service.nba_api:
            logger.error("nba_api package not available. Install with: pip install nba_api")
            return {
                "timestamp": start_time.isoformat(),
                "status": "error",
                "error": "nba_api package not available"
            }

        # Sync all active players
        result = await nba_service.sync_all_active_players(
            games_limit=games_limit,
            season=season
        )

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        summary = {
            "timestamp": start_time.isoformat(),
            "season": season,
            "games_limit": games_limit,
            "total_players": result['total'],
            "success_count": result['success'],
            "no_data_count": result['no_data'],
            "error_count": result['errors'],
            "duration_seconds": duration,
            "status": "success" if result['success'] > 0 else "no_new_data"
        }

        # Log summary
        logger.info("=" * 60)
        logger.info("Player Stats Sync Summary")
        logger.info("=" * 60)
        logger.info(f"Total players: {summary['total_players']}")
        logger.info(f"Successfully synced: {summary['success_count']}")
        logger.info(f"No data available: {summary['no_data_count']}")
        logger.info(f"Errors: {summary['error_count']}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info(f"Status: {summary['status']}")
        logger.info("=" * 60)

        return summary

    except Exception as e:
        logger.error(f"Error during player stats sync: {e}", exc_info=True)
        return {
            "timestamp": datetime.now().isoformat(),
            "status": "error",
            "error": str(e)
        }
    finally:
        db.close()


async def sync_single_player(
    player_nba_api_id: int,
    season: str = DEFAULT_SEASON,
    games_limit: int = DEFAULT_GAMES_LIMIT
) -> dict:
    """
    Sync stats for a single player.

    Args:
        player_nba_api_id: Player's nba_api numeric ID
        season: NBA season
        games_limit: Number of games to average

    Returns:
        dict with sync results
    """
    db = SessionLocal()
    nba_service = NbaApiService(db)

    try:
        logger.info(f"Syncing stats for nba_api_id {player_nba_api_id}...")

        stats = await nba_service.get_player_season_averages(
            player_nba_api_id,
            games_limit,
            season
        )

        if stats:
            logger.info(f"Successfully synced stats for nba_api_id {player_nba_api_id}: {stats}")
            return {
                "player_nba_api_id": player_nba_api_id,
                "status": "success",
                "stats": stats
            }
        else:
            logger.warning(f"No stats available for nba_api_id {player_nba_api_id}")
            return {
                "player_nba_api_id": player_nba_api_id,
                "status": "no_data"
            }

    except Exception as e:
        logger.error(f"Error syncing nba_api_id {player_nba_api_id}: {e}", exc_info=True)
        return {
            "player_nba_api_id": player_nba_api_id,
            "status": "error",
            "error": str(e)
        }
    finally:
        db.close()


def main():
    """Entry point for the script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Sync NBA player stats from nba_api to database cache"
    )
    parser.add_argument(
        "--player-id",
        type=int,
        default=None,
        help="Sync a single player by nba_api_id (default: sync all active players)"
    )
    parser.add_argument(
        "--season",
        type=str,
        default=DEFAULT_SEASON,
        help=f"NBA season (default: {DEFAULT_SEASON})"
    )
    parser.add_argument(
        "--games-limit",
        type=int,
        default=DEFAULT_GAMES_LIMIT,
        help=f"Number of recent games to average (default: {DEFAULT_GAMES_LIMIT})"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force sync even if cache is recent (bypasses TTL check)"
    )

    args = parser.parse_args()

    if args.player_id:
        # Sync single player
        logger.info(f"Syncing single player with nba_api_id: {args.player_id}")
        result = asyncio.run(sync_single_player(
            args.player_id,
            args.season,
            args.games_limit
        ))

        if result.get("status") == "success":
            logger.info("Script completed successfully")
            sys.exit(0)
        else:
            logger.error("Script completed with errors")
            sys.exit(1)
    else:
        # Sync all active players
        result = asyncio.run(sync_player_stats(
            args.season,
            args.games_limit
        ))

        if result.get("status") == "success":
            logger.info("Script completed successfully")
            sys.exit(0)
        else:
            logger.error("Script completed with errors")
            sys.exit(1)


if __name__ == "__main__":
    main()
