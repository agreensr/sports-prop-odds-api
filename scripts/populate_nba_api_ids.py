#!/usr/bin/env python3
"""
Populate nba_api_id values for players in the database.

This script fetches all NBA players from nba_api and matches them
by name to our database players, then updates the nba_api_id column.

Usage:
    python scripts/populate_nba_api_ids.py [--dry-run]

The matching algorithm:
1. Fetch all players from nba_api commonallplayers endpoint
2. Match by exact name (case-insensitive)
3. If multiple matches, use team abbreviation as tiebreaker
4. Update nba_api_id for matched players

Note: nba_api uses numeric IDs (e.g., 1629029 for Luka Dončić)
which are different from our string-based external_ids.
"""
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.nba.models import Player

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/populate_nba_api_ids.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def get_nba_api_players():
    """
    Fetch all players from nba_api commonallplayers endpoint.

    Returns:
        dict mapping player name to (nba_api_id, team_abbr) tuple
        {
            "Luka Dončić": (1629029, "DAL"),
            "LeBron James": (2544, "LAL"),
            ...
        }
    """
    try:
        from nba_api.stats.static import players

        logger.info("Fetching players from nba_api...")

        # Get all players from nba_api
        all_players = players.get_active_players()

        # Create mapping: name -> (id, team_abbr)
        player_map = {}
        for p in all_players:
            name = p.get('full_name', '')
            nba_id = p.get('id', None)
            team_abbr = p.get('team_abbreviation', None)

            if name and nba_id:
                # Handle multiple players with same name (use team as tiebreaker)
                if name in player_map:
                    logger.warning(f"Duplicate name in nba_api: {name} (teams: {player_map[name][1]}, {team_abbr})")

                player_map[name] = (nba_id, team_abbr)

        logger.info(f"Fetched {len(player_map)} players from nba_api")
        return player_map

    except ImportError as e:
        logger.error(f"Failed to import nba_api: {e}")
        logger.error("Install with: pip install nba_api")
        return None
    except Exception as e:
        logger.error(f"Error fetching players from nba_api: {e}")
        return None


def populate_nba_api_ids(dry_run: bool = True) -> dict:
    """
    Populate nba_api_id for players in database.

    Args:
        dry_run: If True, don't actually update database

    Returns:
        dict with results
    """
    db = SessionLocal()

    try:
        logger.info("=" * 60)
        logger.info("Populate nba_api_id Script Started")
        logger.info("=" * 60)
        logger.info(f"Dry run: {dry_run}")

        start_time = datetime.now()

        # Fetch players from nba_api
        nba_players = get_nba_api_players()

        if not nba_players:
            logger.error("Failed to fetch players from nba_api")
            return {
                "status": "error",
                "error": "Failed to fetch players from nba_api"
            }

        # Get all players from database
        db_players = db.query(Player).filter(Player.active == True).all()

        matched_count = 0
        not_found_count = 0
        updated_count = 0
        already_has_id_count = 0

        for player in db_players:
            # Check if already has nba_api_id
            if player.nba_api_id is not None:
                already_has_id_count += 1
                continue

            # Try to match by name
            nba_data = nba_players.get(player.name)

            if not nba_data:
                # Try with common name variations
                # Remove accents, handle Jr./Sr., etc.
                normalized_name = player.name.lower().strip()

                # Try to find by normalized name
                for nba_name, data in nba_players.items():
                    if nba_name.lower().strip() == normalized_name:
                        nba_data = data
                        break

            if nba_data:
                nba_id, team_abbr = nba_data

                # Verify team matches if available
                if team_abbr and team_abbr != player.team:
                    logger.warning(
                        f"Team mismatch for {player.name}: DB={player.team}, nba_api={team_abbr}. Using anyway."
                    )

                matched_count += 1

                if not dry_run:
                    player.nba_api_id = nba_id
                    logger.info(f"Updated {player.name} ({player.team}): nba_api_id = {nba_id}")
                    updated_count += 1
                else:
                    logger.info(f"[DRY RUN] Would update {player.name} ({player.team}): nba_api_id = {nba_id}")
            else:
                not_found_count += 1
                logger.debug(f"No match found in nba_api for: {player.name} ({player.team})")

        # Commit changes if not dry run
        if not dry_run and updated_count > 0:
            db.commit()
            logger.info(f"Committed {updated_count} updates to database")

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        summary = {
            "timestamp": start_time.isoformat(),
            "dry_run": dry_run,
            "duration_seconds": duration,
            "total_db_players": len(db_players),
            "already_has_id": already_has_id_count,
            "matched": matched_count,
            "updated": updated_count if not dry_run else 0,
            "not_found": not_found_count,
            "status": "success"
        }

        # Log summary
        logger.info("=" * 60)
        logger.info("Populate nba_api_id Summary")
        logger.info("=" * 60)
        logger.info(f"Total DB players: {summary['total_db_players']}")
        logger.info(f"Already have nba_api_id: {summary['already_has_id']}")
        logger.info(f"Matched in nba_api: {summary['matched']}")
        logger.info(f"Updated: {summary['updated']}")
        logger.info(f"Not found in nba_api: {summary['not_found']}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info("=" * 60)

        return summary

    except Exception as e:
        logger.error(f"Error during population: {e}", exc_info=True)
        db.rollback()
        return {
            "status": "error",
            "error": str(e)
        }
    finally:
        db.close()


def main():
    """Entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Populate nba_api_id values for players in database"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Actually update database (use with caution)"
    )

    args = parser.parse_args()

    # Default to dry-run for safety unless --force is specified
    dry_run = not args.force

    if args.force:
        logger.info("Force mode enabled - will update database")
    else:
        logger.info("Dry run mode - use --force to actually update database")

    result = populate_nba_api_ids(dry_run=dry_run)

    if result.get("status") == "success":
        if dry_run:
            logger.info("Dry run completed successfully")
            logger.info("Run with --force to actually update the database")
        else:
            logger.info("Database updated successfully")
        sys.exit(0)
    else:
        logger.error("Script completed with errors")
        sys.exit(1)


if __name__ == "__main__":
    main()
