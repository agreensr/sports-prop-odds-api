#!/usr/bin/env python3
"""
Test the game matching logic with simulated data.

This simulates odds API responses and tests the GameMatcher.
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
    """Test game matching with simulated odds data."""
    from app.core.database import SessionLocal
    from app.services.sync.matchers.game_matcher import GameMatcher

    db = SessionLocal()

    try:
        # Simulate odds API data matching our sample games
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)

        simulated_odds_games = [
            {
                'id': 'odds_event_001',
                'sport_key': 'basketball_nba',
                'sport_title': 'NBA',
                'commence_time': today.replace(hour=19, minute=0, second=0),
                'home_team': 'Philadelphia 76ers',
                'away_team': 'Boston Celtics',
                'bookmakers': []
            },
            {
                'id': 'odds_event_002',
                'sport_key': 'basketball_nba',
                'sport_title': 'NBA',
                'commence_time': today.replace(hour=21, minute=30, second=0),
                'home_team': 'Golden State Warriors',
                'away_team': 'Los Angeles Lakers',
                'bookmakers': []
            },
            {
                'id': 'odds_event_003',
                'sport_key': 'basketball_nba',
                'sport_title': 'NBA',
                'commence_time': tomorrow.replace(hour=20, minute=0, second=0),
                'home_team': 'New York Knicks',
                'away_team': 'Miami Heat',
                'bookmakers': []
            },
            {
                'id': 'odds_event_004',
                'sport_key': 'basketball_nba',
                'sport_title': 'NBA',
                'commence_time': tomorrow.replace(hour=22, minute=0, second=0),
                'home_team': 'Denver Nuggets',
                'away_team': 'Phoenix Suns',
                'bookmakers': []
            },
        ]

        logger.info("Simulating odds API responses...")
        logger.info(f"Simulated {len(simulated_odds_games)} odds games")

        # Get NBA games from database
        from app.models.nba.models import Game
        nba_games = db.query(Game).all()

        logger.info(f"Found {len(nba_games)} NBA games in database")

        # Create game matcher
        matcher = GameMatcher(db)

        # Test batch matching
        logger.info("\n" + "="*60)
        logger.info("Testing GameMatcher with simulated odds data...")
        logger.info("="*60)

        # Convert NBA games to the format expected by matcher
        nba_games_data = []
        for game in nba_games:
            # Get team IDs from team_mappings
            from app.models.nba.models import TeamMapping

            home_team = db.query(TeamMapping).filter(
                TeamMapping.nba_abbreviation == game.home_team
            ).first()

            away_team = db.query(TeamMapping).filter(
                TeamMapping.nba_abbreviation == game.away_team
            ).first()

            if home_team and away_team:
                nba_games_data.append({
                    'id': game.external_id,
                    'game_date': game.game_date,
                    'home_team': game.home_team,
                    'away_team': game.away_team,
                    'home_team_id': home_team.nba_team_id,
                    'away_team_id': away_team.nba_team_id,
                    'season': game.season,
                    'status': game.status
                })
            else:
                logger.warning(f"Could not find team mapping for {game.external_id}")

        # Run batch matching
        results = await matcher.batch_match_games(nba_games_data, simulated_odds_games)

        logger.info("\n" + "="*60)
        logger.info("Matching Results:")
        logger.info("="*60)
        logger.info(f"Total games: {results['total']}")
        logger.info(f"Matched: {results['matched']}")
        logger.info(f"Unmatched: {results['unmatched']}")
        logger.info("")

        # Show detailed match results
        for match in results.get('matches', []):
            if not match.get('cached'):
                logger.info(f"✓ Matched: {match['nba_game_id']}")
                logger.info(f"  → Odds Event: {match['odds_event_id']}")
                logger.info(f"  → Confidence: {match['match_confidence']:.2f}")
                logger.info(f"  → Method: {match['match_method']}")
                logger.info("")

        # Verify mappings in database
        logger.info("="*60)
        logger.info("Verifying game_mappings table...")
        logger.info("="*60)

        from app.models.nba.models import GameMapping
        mappings = db.query(GameMapping).all()

        for mapping in mappings:
            logger.info(f"Game Mapping:")
            logger.info(f"  nba_game_id: {mapping.nba_game_id}")
            logger.info(f"  odds_event_id: {mapping.odds_event_id}")
            logger.info(f"  match_confidence: {mapping.match_confidence}")
            logger.info(f"  match_method: {mapping.match_method}")
            logger.info(f"  status: {mapping.status}")
            logger.info("")

        logger.info("="*60)
        logger.info("✓ Matching test completed successfully!")
        logger.info("="*60)

    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
