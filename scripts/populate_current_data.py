#!/usr/bin/env python3
"""
Fetch current NBA games and odds from APIs and populate database.

This script:
1. Fetches today's games from nba_api
2. Fetches current odds from The Odds API
3. Runs the sync matcher to create game mappings
4. Reports results
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Fetch current data and populate database."""
    from app.core.database import SessionLocal
    from app.services.sync.orchestrator import SyncOrchestrator

    db = SessionLocal()

    try:
        logger.info("Starting current data population...")

        # Run full sync
        orchestrator = SyncOrchestrator(db)

        # Sync games from nba_api and odds from odds_api
        logger.info("Syncing games from nba_api and odds_api...")
        results = await orchestrator.sync_games(
            lookback_days=1,  # Get games from yesterday through tomorrow
            lookahead_days=2,
            season="2025-26"
        )

        logger.info(f"Sync complete: {results}")

        # Check the matched games
        matched_games = orchestrator.get_matched_games()
        logger.info(f"\nMatched games: {len(matched_games)}")

        for game in matched_games[:10]:  # Show first 10
            logger.info(
                f"  {game['nba_game_id']}: "
                f"{game['game_date']} "
                f"(confidence: {game['match_confidence']:.2f}, "
                f"method: {game['match_method']})"
            )

        # Check for any issues
        queue = orchestrator.get_manual_review_queue()
        logger.info(f"\nUnmatched games: {len(queue['unmatched_games'])}")
        logger.info(f"Low confidence matches: {len(queue['low_confidence_matches'])}")

        # Get overall status
        status = orchestrator.get_sync_status()
        logger.info(f"\nSync Status: {status['health_status']}")
        logger.info(f"Total processed: {status['totals']['processed']}")
        logger.info(f"Total matched: {status['totals']['matched']}")
        logger.info(f"Total failed: {status['totals']['failed']}")

        logger.info("\n✓ Current data population completed successfully!")

    except Exception as e:
        logger.error(f"Failed to populate data: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
