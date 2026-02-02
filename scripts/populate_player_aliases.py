#!/usr/bin/env python3
"""
Populate player_aliases table with all players from the database.

This script creates alias entries for all players in the players table
with the odds_api source, enabling PlayerResolver to work correctly.
"""
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal
from app.models.nba.models import Player, PlayerAlias
import uuid

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def populate_player_aliases(dry_run=True):
    """
    Populate player_aliases table with all players.

    Args:
        dry_run: If True, don't actually commit changes

    Returns:
        Dictionary with statistics
    """
    db = SessionLocal()

    try:
        # Get all players with nba_api_id
        players = db.query(Player).filter(
            Player.nba_api_id.isnot(None)
        ).all()

        logger.info(f"Found {len(players)} players with nba_api_id")

        created = 0
        skipped = 0
        errors = 0

        for player in players:
            try:
                # Check if alias already exists
                existing = db.query(PlayerAlias).filter(
                    PlayerAlias.alias_name == player.name,
                    PlayerAlias.alias_source == 'odds_api'
                ).first()

                if existing:
                    skipped += 1
                    logger.debug(f"Skipping {player.name} - alias already exists")
                    continue

                # Create new alias
                alias = PlayerAlias(
                    id=str(uuid.uuid4()),
                    nba_player_id=player.nba_api_id,
                    canonical_name=player.name,
                    alias_name=player.name,
                    alias_source='odds_api',
                    match_confidence=1.0,  # Exact match from database
                    is_verified=True,  # From database, so verified
                    created_at=datetime.now(timezone.utc)
                )

                db.add(alias)
                created += 1
                logger.info(f"Created alias: {player.name} -> ID {player.nba_api_id}")

            except Exception as e:
                logger.error(f"Error processing {player.name}: {e}")
                errors += 1

        if not dry_run:
            db.commit()
            logger.info(f"\n✅ Committed {created} new aliases")
        else:
            db.rollback()
            logger.info(f"\n🔍 Dry run complete - would have created {created} aliases")

        logger.info(f"\nSummary:")
        logger.info(f"  Total players: {len(players)}")
        logger.info(f"  Created: {created}")
        logger.info(f"  Skipped: {skipped}")
        logger.info(f"  Errors: {errors}")

        return {
            'total': len(players),
            'created': created,
            'skipped': skipped,
            'errors': errors
        }

    except Exception as e:
        db.rollback()
        logger.error(f"\n❌ Error: {e}")
        raise

    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Populate player_aliases table with all players"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Actually commit changes (use with caution)'
    )

    args = parser.parse_args()

    dry_run = not args.force

    if dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be made")
        logger.info("Use --force to actually populate the table\n")

    populate_player_aliases(dry_run=dry_run)
