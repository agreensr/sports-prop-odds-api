#!/usr/bin/env python3
"""
Seed sample games and odds data to test the sync matching logic.

Creates realistic NBA games with proper team IDs and odds API data
that can be matched by the GameMatcher.
"""
import os
import sys
import uuid
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_database_url():
    """Get database URL from environment or settings."""
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return db_url

    from app.core.config import settings
    return settings.DATABASE_URL


def seed_sample_games(session):
    """Seed sample NBA games for testing."""
    from app.models.nba.models import Game

    logger.info("Seeding sample NBA games...")

    # Sample games with real team IDs from team_mappings
    # Games for today and tomorrow
    today = datetime.utcnow()
    tomorrow = today + timedelta(days=1)

    sample_games = [
        {
            'id': str(uuid.uuid4()),
            'external_id': '0022400001',  # nba_game_id format
            'id_source': 'nba',
            'game_date': today.replace(hour=19, minute=0, second=0, microsecond=0),
            'away_team': 'BOS',  # Boston Celtics (ID: 1610612738)
            'home_team': 'PHI',  # Philadelphia 76ers (ID: 1610612755)
            'season': 2025,
            'status': 'scheduled',
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        },
        {
            'id': str(uuid.uuid4()),
            'external_id': '0022400002',
            'id_source': 'nba',
            'game_date': today.replace(hour=21, minute=30, second=0, microsecond=0),
            'away_team': 'LAL',  # Lakers (ID: 1610612747)
            'home_team': 'GSW',  # Warriors (ID: 1610612744)
            'season': 2025,
            'status': 'scheduled',
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        },
        {
            'id': str(uuid.uuid4()),
            'external_id': '0022400003',
            'id_source': 'nba',
            'game_date': tomorrow.replace(hour=20, minute=0, second=0, microsecond=0),
            'away_team': 'MIA',  # Heat (ID: 1610612748)
            'home_team': 'NYK',  # Knicks (ID: 1610612752)
            'season': 2025,
            'status': 'scheduled',
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        },
        {
            'id': str(uuid.uuid4()),
            'external_id': '0022400004',
            'id_source': 'nba',
            'game_date': tomorrow.replace(hour=22, minute=0, second=0, microsecond=0),
            'away_team': 'PHX',  # Suns (ID: 1610612756)
            'home_team': 'DEN',  # Nuggets (ID: 1610612743)
            'season': 2025,
            'status': 'scheduled',
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        },
    ]

    seeded_count = 0
    for game_data in sample_games:
        # Check if already exists
        existing = session.query(Game).filter(
            Game.external_id == game_data['external_id']
        ).first()

        if existing:
            logger.debug(f"Game already exists: {game_data['external_id']}")
            continue

        game = Game(**game_data)
        session.add(game)
        seeded_count += 1

    session.commit()
    logger.info(f"✓ Seeded {seeded_count} sample games")


def main():
    """Run seeding operations."""
    logger.info("Starting sample data seeding...")

    # Get database URL
    db_url = get_database_url()
    logger.info(f"Connecting to database: {db_url[:30]}...")

    # Create engine and session
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)

    session = SessionLocal()

    try:
        # Seed sample games
        seed_sample_games(session)

        logger.info("\n" + "="*50)
        logger.info("Sample data seeding completed successfully! ✓")
        logger.info("="*50)

    except Exception as e:
        logger.error(f"Seeding failed: {e}")
        session.rollback()
        sys.exit(1)
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    main()
