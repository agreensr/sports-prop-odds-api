#!/usr/bin/env python3
"""
Seed sync infrastructure tables with initial data.

Seeds:
- team_mappings (30 NBA teams)
- player_aliases (50 problematic player name variations)
"""
import os
import sys
import json
import uuid
from pathlib import Path
from datetime import datetime

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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


def seed_team_mappings(session):
    """Seed team_mappings table with all 30 NBA teams."""
    logger.info("Seeding team_mappings...")

    from app.models.nba.models import TeamMapping

    # Read seed data
    seed_path = PROJECT_ROOT / "seeds" / "team_mappings_seed.json"
    with open(seed_path, 'r') as f:
        data = json.load(f)

    seeded_count = 0
    for team_data in data['teams']:
        # Check if already exists
        existing = session.query(TeamMapping).filter(
            TeamMapping.nba_team_id == team_data['nba_team_id']
        ).first()

        if existing:
            logger.debug(f"Team mapping already exists for {team_data['nba_abbreviation']}")
            continue

        # Create new mapping
        mapping = TeamMapping(
            id=str(uuid.uuid4()),
            nba_team_id=team_data['nba_team_id'],
            nba_abbreviation=team_data['nba_abbreviation'],
            nba_full_name=team_data['nba_full_name'],
            nba_city=team_data['nba_city'],
            odds_api_name=team_data.get('odds_api_name'),
            odds_api_key=team_data.get('odds_api_key'),
            alternate_names=json.dumps(team_data.get('alternate_names', [])),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        session.add(mapping)
        seeded_count += 1

    session.commit()
    logger.info(f"✓ Seeded {seeded_count} team mappings")


def seed_player_aliases(session):
    """Seed player_aliases table with common name variations."""
    logger.info("Seeding player_aliases...")

    from app.models.nba.models import PlayerAlias

    # Read seed data
    seed_path = PROJECT_ROOT / "seeds" / "player_aliases_seed.json"
    with open(seed_path, 'r') as f:
        data = json.load(f)

    seeded_count = 0
    for alias_data in data['player_aliases']:
        # Check if already exists
        existing = session.query(PlayerAlias).filter(
            PlayerAlias.alias_name == alias_data['alias_name'],
            PlayerAlias.alias_source == alias_data['alias_source']
        ).first()

        if existing:
            logger.debug(f"Player alias already exists for {alias_data['alias_name']}")
            continue

        # Create new alias
        alias = PlayerAlias(
            id=alias_data['id'],
            nba_player_id=alias_data['nba_player_id'],
            canonical_name=alias_data['canonical_name'],
            alias_name=alias_data['alias_name'],
            alias_source=alias_data['alias_source'],
            match_confidence=alias_data['match_confidence'],
            is_verified=alias_data.get('is_verified', False),
            created_at=datetime.utcnow(),
            verified_at=datetime.utcnow() if alias_data.get('is_verified') else None,
            verified_by='seed_script' if alias_data.get('is_verified') else None
        )
        session.add(alias)
        seeded_count += 1

    session.commit()
    logger.info(f"✓ Seeded {seeded_count} player aliases")


def main():
    """Run all seed operations."""
    logger.info("Starting data seeding...")

    # Get database URL
    db_url = get_database_url()
    logger.info(f"Connecting to database: {db_url[:30]}...")

    # Create engine and session
    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)

    session = SessionLocal()

    try:
        # Seed team mappings
        seed_team_mappings(session)

        # Seed player aliases
        seed_player_aliases(session)

        logger.info("\n" + "="*50)
        logger.info("Seeding completed successfully! ✓")
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
