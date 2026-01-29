#!/usr/bin/env python3
"""
NBA Player Population Script.

Fetches all NBA players from NBA API and stores them in the unified
Player model with sport_id='nba'.

This script:
1. Uses the nba_api library to fetch rosters for all teams
2. Stores/updates players in the database

Usage:
    python scripts/populate_nba_players.py

Options:
    --team TEAM    Only fetch players for specific team (e.g., "LAL", "BOS")
    --force        Update existing players even if data hasn't changed
    --dry-run      Show what would be done without making changes

Requirements:
    - nba_api library installed
    - Database migrations must be run first
    - Sport registry should have 'nba' entry
"""
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.unified import Player, Sport
from app.core.logging import get_logger
from app.services.sync.utils.name_normalizer import normalize as canonicalize_name

logger = get_logger(__name__)

# NBA Team IDs from nba_api
NBA_TEAMS = {
    "ATL": {"id": 1610612737, "name": "Atlanta Hawks"},
    "BOS": {"id": 1610612738, "name": "Boston Celtics"},
    "BKN": {"id": 1610612751, "name": "Brooklyn Nets"},
    "CHA": {"id": 1610612766, "name": "Charlotte Hornets"},
    "CHI": {"id": 1610612741, "name": "Chicago Bulls"},
    "CLE": {"id": 1610612739, "name": "Cleveland Cavaliers"},
    "DAL": {"id": 1610612742, "name": "Dallas Mavericks"},
    "DEN": {"id": 1610612743, "name": "Denver Nuggets"},
    "DET": {"id": 1610612765, "name": "Detroit Pistons"},
    "GSW": {"id": 1610612744, "name": "Golden State Warriors"},
    "HOU": {"id": 1610612745, "name": "Houston Rockets"},
    "IND": {"id": 1610612754, "name": "Indiana Pacers"},
    "LAC": {"id": 1610612746, "name": "Los Angeles Clippers"},
    "LAL": {"id": 1610612747, "name": "Los Angeles Lakers"},
    "MEM": {"id": 1610612760, "name": "Memphis Grizzlies"},
    "MIA": {"id": 1610612748, "name": "Miami Heat"},
    "MIL": {"id": 1610612749, "name": "Milwaukee Bucks"},
    "MIN": {"id": 1610612750, "name": "Minnesota Timberwolves"},
    "NOP": {"id": 1610612740, "name": "New Orleans Pelicans"},
    "NYK": {"id": 1610612752, "name": "New York Knicks"},
    "OKC": {"id": 1610612760, "name": "Oklahoma City Thunder"},
    "ORL": {"id": 1610612753, "name": "Orlando Magic"},
    "PHI": {"id": 1610612755, "name": "Philadelphia 76ers"},
    "PHX": {"id": 1610612756, "name": "Phoenix Suns"},
    "POR": {"id": 1610612757, "name": "Portland Trail Blazers"},
    "SAS": {"id": 1610612759, "name": "San Antonio Spurs"},
    "TOR": {"id": 1610612761, "name": "Toronto Raptors"},
    "UTA": {"id": 1610612762, "name": "Utah Jazz"},
    "WAS": {"id": 1610612762, "name": "Washington Wizards"},
}

DEFAULT_SEASON = "2024-25"
REQUEST_DELAY = 0.5  # Delay between NBA API requests


def ensure_sport_entry(db: Session) -> Sport:
    """Ensure NBA exists in sports registry."""
    sport = db.query(Sport).filter(Sport.id == "nba").first()

    if not sport:
        sport = Sport(
            id="nba",
            name="National Basketball Association",
            active=True,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.add(sport)
        db.commit()
        logger.info("Created NBA entry in sports registry")
    else:
        logger.info("NBA entry found in sports registry")

    return sport


def create_player_from_nba_api(
    row: Dict,
    team: str
) -> Dict:
    """
    Create player data dict from NBA API row data.

    Args:
        row: Dictionary row from CommonTeamRoster dataframe
        team: Team abbreviation

    Returns:
        Dictionary with player data for database
    """
    # Extract data from the row
    # The dataframe has columns like PLAYER_ID, PLAYER, POSITION, etc.
    player_id = int(row.get("PLAYER_ID"))
    player_name = row.get("PLAYER")
    position = row.get("POSITION", "")
    jersey_number = row.get("NUM", "")

    # Convert jersey to int if possible
    if jersey_number and str(jersey_number).isdigit():
        jersey_number = int(jersey_number)
    else:
        jersey_number = None

    # Extract height (usually in format "6-4")
    height = row.get("HEIGHT", "")
    # Extract weight (usually in lbs)
    weight = row.get("WEIGHT", "")
    if weight:
        try:
            weight = int(weight)
        except (ValueError, TypeError):
            weight = None

    # Get experience (years in league)
    experience = row.get("EXP", "")
    years_experience = None
    if experience and experience != "R":
        try:
            years_experience = int(experience)
        except (ValueError, TypeError):
            pass

    return {
        "id": str(uuid4()),
        "sport_id": "nba",
        "external_id": f"nba_{player_id}",
        "id_source": "nba_api",
        "nba_api_id": player_id,
        "canonical_name": canonicalize_name(player_name),
        "name": player_name,
        "team": team,
        "position": position,
        "jersey_number": jersey_number,
        "height": height,
        "weight": weight,
        "active": True,  # Roster players are active
        "data_source": "nba_api",
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
        "last_roster_check": datetime.now(),
    }


async def fetch_team_roster(
    team_abbr: str,
    season: str = DEFAULT_SEASON
) -> List[Dict]:
    """
    Fetch roster for a specific team from NBA API.

    Args:
        team_abbr: Team abbreviation (e.g., "LAL", "BOS")
        season: NBA season (e.g., "2024-25")

    Returns:
        List of dictionaries with player data
    """
    team_info = NBA_TEAMS.get(team_abbr)
    if not team_info:
        logger.error(f"Unknown team: {team_abbr}")
        return []

    team_id = team_info["id"]

    logger.debug(f"Fetching roster for {team_abbr} (ID: {team_id})...")

    try:
        from nba_api.stats.endpoints import commonteamroster

        # Add delay to avoid rate limiting
        await asyncio.sleep(REQUEST_DELAY)

        roster = commonteamroster.CommonTeamRoster(
            team_id=team_id,
            season=season
        )

        df = roster.get_data_frames()[0] if roster.get_data_frames() else None

        if df is None or df.empty:
            logger.warning(f"No roster data for {team_abbr}")
            return []

        # Convert dataframe rows to list of dicts
        players = []
        for _, row in df.iterrows():
            players.append(row.to_dict())

        logger.debug(f"Found {len(players)} players for {team_abbr}")
        return players

    except Exception as e:
        logger.error(f"Error fetching roster for {team_abbr}: {e}")
        return []


def find_existing_player(
    db: Session,
    player_data: Dict
) -> Optional[Player]:
    """
    Find existing player by various identifiers.

    Priority:
    1. nba_api_id exact match
    2. external_id match
    3. canonical_name + team match
    4. name + team match
    """
    # Try NBA API ID first
    if player_data.get("nba_api_id"):
        player = db.query(Player).filter(
            Player.sport_id == "nba",
            Player.nba_api_id == player_data["nba_api_id"]
        ).first()
        if player:
            return player

    # Try external ID
    if player_data.get("external_id"):
        player = db.query(Player).filter(
            Player.sport_id == "nba",
            Player.external_id == player_data["external_id"]
        ).first()
        if player:
            return player

    # Try canonical name + team
    if player_data.get("canonical_name") and player_data.get("team"):
        player = db.query(Player).filter(
            Player.sport_id == "nba",
            Player.canonical_name == player_data["canonical_name"],
            Player.team == player_data["team"]
        ).first()
        if player:
            return player

    # Try name + team as fallback
    if player_data.get("name") and player_data.get("team"):
        player = db.query(Player).filter(
            Player.sport_id == "nba",
            Player.name == player_data["name"],
            Player.team == player_data["team"]
        ).first()
        if player:
            return player

    return None


def update_player_data(player: Player, player_data: Dict, force: bool = False) -> bool:
    """
    Update player data if changed.

    Returns True if player was updated.
    """
    updated = False

    # Fields to update if changed or force=True
    updatable_fields = [
        "team", "position", "jersey_number", "height", "weight",
        "active", "last_roster_check", "updated_at"
    ]

    for field in updatable_fields:
        if field in player_data:
            new_value = player_data[field]
            current_value = getattr(player, field, None)

            if current_value != new_value:
                if force or field in ["updated_at", "last_roster_check"]:
                    setattr(player, field, new_value)
                    updated = True

    return updated


async def populate_nba_players(
    team_filter: Optional[str] = None,
    force: bool = False,
    dry_run: bool = False,
    season: str = DEFAULT_SEASON
) -> Dict:
    """
    Main function to populate NBA players from NBA API.

    Args:
        team_filter: Optional team abbreviation to filter
        force: Update existing players even if unchanged
        dry_run: Show changes without committing
        season: NBA season (e.g., "2024-25")

    Returns:
        Summary dictionary
    """
    db = SessionLocal()

    try:
        # Ensure sport registry entry exists
        ensure_sport_entry(db)

        # Get list of teams to process
        teams_to_process = list(NBA_TEAMS.items())

        # Filter teams if specified
        if team_filter:
            team_filter_upper = team_filter.upper()
            teams_to_process = [
                (abbr, info) for abbr, info in teams_to_process
                if abbr == team_filter_upper
            ]
            if not teams_to_process:
                logger.error(f"Team {team_filter} not found")
                return {
                    "status": "error",
                    "error": f"Team {team_filter} not found"
                }

        # Summary tracking
        summary = {
            "timestamp": datetime.now().isoformat(),
            "season": season,
            "teams_processed": 0,
            "players_created": 0,
            "players_updated": 0,
            "players_skipped": 0,
            "errors": [],
            "status": "success"
        }

        logger.info("=" * 60)
        logger.info("NBA Player Population Started")
        logger.info("=" * 60)
        logger.info(f"Season: {season}")
        if team_filter:
            logger.info(f"Team filter: {team_filter}")
        if dry_run:
            logger.info("DRY RUN MODE - No changes will be committed")

        start_time = datetime.now()

        # Process each team
        for team_abbr, team_info in teams_to_process:
            team_name = team_info["name"]

            logger.info(f"\n📋 Processing {team_name} ({team_abbr})...")

            # Fetch roster
            roster = await fetch_team_roster(team_abbr, season)

            if not roster:
                logger.warning(f"  No roster data for {team_abbr}")
                summary["errors"].append(f"No roster for {team_abbr}")
                continue

            logger.info(f"  Found {len(roster)} players")

            # Process each player
            for player_row in roster:
                try:
                    player_data = create_player_from_nba_api(player_row, team_abbr)

                    # Check if player exists
                    existing = find_existing_player(db, player_data)

                    if existing:
                        # Update existing player
                        updated = update_player_data(existing, player_data, force)

                        if updated:
                            summary["players_updated"] += 1
                            logger.debug(f"  ✓ Updated {player_data['name']}")
                        else:
                            summary["players_skipped"] += 1
                            logger.debug(f"  - Skipped {player_data['name']} (no changes)")
                    else:
                        # Create new player
                        if not dry_run:
                            new_player = Player(**player_data)
                            db.add(new_player)
                        summary["players_created"] += 1
                        logger.info(f"  + Added {player_data['name']} ({team_abbr})")

                except Exception as e:
                    player_name = player_row.get("PLAYER", "Unknown")
                    logger.error(f"  ✗ Error processing {player_name}: {e}")
                    summary["errors"].append(f"{player_name}: {str(e)}")

            summary["teams_processed"] += 1

            # Commit after each team to avoid losing progress
            if not dry_run:
                try:
                    db.commit()
                except Exception as e:
                    logger.error(f"Error committing changes for {team_abbr}: {e}")
                    db.rollback()
                    summary["errors"].append(f"Commit failed for {team_abbr}")

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        summary["duration_seconds"] = duration

        # Print summary
        logger.info("\n" + "=" * 60)
        logger.info("Population Summary")
        logger.info("=" * 60)
        logger.info(f"Season: {season}")
        logger.info(f"Teams processed: {summary['teams_processed']}")
        logger.info(f"Players created: {summary['players_created']}")
        logger.info(f"Players updated: {summary['players_updated']}")
        logger.info(f"Players skipped: {summary['players_skipped']}")
        if summary["errors"]:
            logger.info(f"Errors: {len(summary['errors'])}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info("=" * 60)

        # Get total player count
        total_players = db.query(Player).filter(Player.sport_id == "nba").count()
        logger.info(f"Total NBA players in database: {total_players}")

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


async def main():
    """Entry point for the script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Populate NBA players from NBA API"
    )
    parser.add_argument(
        "--team",
        type=str,
        help="Only fetch players for specific team (e.g., LAL, BOS)"
    )
    parser.add_argument(
        "--season",
        type=str,
        default=DEFAULT_SEASON,
        help=f"NBA season (default: {DEFAULT_SEASON})"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Update existing players even if data hasn't changed"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )

    args = parser.parse_args()

    result = await populate_nba_players(
        team_filter=args.team,
        season=args.season,
        force=args.force,
        dry_run=args.dry_run
    )

    if result.get("status") == "success":
        logger.info("\n✅ Script completed successfully")
        sys.exit(0)
    else:
        logger.error(f"\n❌ Script failed: {result.get('error')}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
