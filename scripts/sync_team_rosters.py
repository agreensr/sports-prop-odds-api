#!/usr/bin/env python3
"""
Team Roster Sync Script.

Syncs current team rosters from NBA API to fix outdated team assignments.
This ensures players are listed on their correct current teams, preventing
picks for players who have been traded or are no longer active.

Critical for data integrity - prevents picks for:
- Traded players (e.g., Clint Capela - HOU→ATL 2020)
- Retired players
- Players who changed teams in free agency

Usage:
    python scripts/sync_team_rosters.py

Schedule:
    Run daily to keep rosters current during trade season
    Run weekly during off-season

NBA API Reference:
    https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/commonteamroster.md
"""
import asyncio
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
        logging.FileHandler('/tmp/sync_team_rosters.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# NBA Team IDs (from nba_api)
NBA_TEAM_IDS = {
    "ATL": 1610612737,  # Atlanta Hawks
    "BOS": 1610612738,  # Boston Celtics
    "BKN": 1610612751,  # Brooklyn Nets
    "CHA": 1610612766,  # Charlotte Hornets
    "CHI": 1610612741,  # Chicago Bulls
    "CLE": 1610612739,  # Cleveland Cavaliers
    "DAL": 1610612742,  # Dallas Mavericks
    "DEN": 1610612743,  # Denver Nuggets
    "DET": 1610612765,  # Detroit Pistons
    "GSW": 1610612744,  # Golden State Warriors
    "HOU": 1610612745,  # Houston Rockets
    "IND": 1610612754,  # Indiana Pacers
    "LAC": 1610612746,  # Los Angeles Clippers
    "LAL": 1610612747,  # Los Angeles Lakers
    "MEM": 1610612760,  # Memphis Grizzlies
    "MIA": 1610612748,  # Miami Heat
    "MIL": 1610612749,  # Milwaukee Bucks
    "MIN": 1610612750,  # Minnesota Timberwolves
    "NOP": 1610612740,  # New Orleans Pelicans
    "NYK": 1610612752,  # New York Knicks
    "OKC": 1610612760,  # Oklahoma City Thunder
    "ORL": 1610612753,  # Orlando Magic
    "PHI": 1610612755,  # Philadelphia 76ers
    "PHX": 1610612756,  # Phoenix Suns
    "POR": 1610612757,  # Portland Trail Blazers
    "SAC": 1610612758,  # Sacramento Kings
    "SAS": 1610612759,  # San Antonio Spurs
    "TOR": 1610612761,  # Toronto Raptors
    "UTA": 1610612762,  # Utah Jazz
    "WAS": 1610612762,  # Washington Wizards
}

DEFAULT_SEASON = "2025-26"
REQUEST_DELAY = 1.0  # Delay between NBA API requests


async def fetch_team_roster(team_abbr: str, season: str = DEFAULT_SEASON) -> list:
    """
    Fetch current roster for a team from NBA API.

    Args:
        team_abbr: Team abbreviation (e.g., "HOU")
        season: NBA season (e.g., "2024-25")

    Returns:
        List of player dicts with nba_api_id and name
    """
    try:
        from nba_api.stats.endpoints import commonteamroster

        team_id = NBA_TEAM_IDS.get(team_abbr)
        if not team_id:
            logger.error(f"Unknown team abbreviation: {team_abbr}")
            return []

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

        # Extract player info
        players = []
        name_idx = df.columns.get_loc('PLAYER')
        id_idx = df.columns.get_loc('PLAYER_ID')

        for _, row in df.iterrows():
            players.append({
                'nba_api_id': int(row.iloc[id_idx]),
                'name': row.iloc[name_idx],
                'team': team_abbr
            })

        logger.info(f"Fetched {len(players)} players for {team_abbr}")
        return players

    except Exception as e:
        logger.error(f"Error fetching roster for {team_abbr}: {e}")
        return []


async def sync_all_rosters(season: str = DEFAULT_SEASON) -> dict:
    """
    Sync all team rosters from NBA API and update player.team in database.

    This is the main function that:
    1. Fetches rosters from all 30 NBA teams
    2. Maps nba_api_id to current team
    3. Updates player.team in database

    Args:
        season: NBA season

    Returns:
        Dict with sync results
    """
    db = SessionLocal()

    try:
        logger.info("=" * 60)
        logger.info("Team Roster Sync Script Started")
        logger.info("=" * 60)
        logger.info(f"Season: {season}")

        start_time = datetime.now()

        # Step 1: Fetch all rosters
        logger.info("\n📋 Step 1: Fetching rosters from NBA API...")
        all_roster_players = []

        for team_abbr in sorted(NBA_TEAM_IDS.keys()):
            roster = await fetch_team_roster(team_abbr, season)
            all_roster_players.extend(roster)

        logger.info(f"   ✅ Fetched {len(all_roster_players)} total players")

        if not all_roster_players:
            logger.error("No roster data fetched from NBA API")
            return {"status": "error", "error": "No roster data"}

        # Step 2: Build nba_api_id -> team mapping
        logger.info("\n🗺️  Step 2: Building player-to-team mapping...")
        player_team_map = {p['nba_api_id']: p['team'] for p in all_roster_players}
        logger.info(f"   ✅ Mapped {len(player_team_map)} players to teams")

        # Step 3: Update players in database
        logger.info("\n🔄 Step 3: Updating player teams in database...")

        updated_count = 0
        not_found_count = 0
        no_change_count = 0
        team_change_count = 0
        nba_api_id_updated = 0
        changes = []  # Track team changes

        for roster_player in all_roster_players:
            nba_api_id = roster_player['nba_api_id']
            correct_team = roster_player['team']
            player_name = roster_player['name']

            # First try to match by nba_api_id (exact match) - most reliable
            player = db.query(Player).filter(
                Player.nba_api_id == nba_api_id
            ).first()

            # If not found by ID, try to match by exact name
            if not player:
                player = db.query(Player).filter(
                    Player.name == player_name
                ).first()

                if player:
                    # Update nba_api_id for future matches
                    if player.nba_api_id != nba_api_id:
                        player.nba_api_id = nba_api_id
                        nba_api_id_updated += 1

            if not player:
                not_found_count += 1
                continue

            if player.team != correct_team:
                old_team = player.team
                player.team = correct_team
                updated_count += 1
                team_change_count += 1
                changes.append(f"  {player.name}: {old_team} → {correct_team}")
            else:
                no_change_count += 1

        db.commit()

        # Log team changes
        if changes:
            logger.info("\n📝 Team Changes:")
            for change in changes[:20]:  # First 20
                logger.info(change)
            if len(changes) > 20:
                logger.info(f"  ... and {len(changes) - 20} more")

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        summary = {
            "timestamp": start_time.isoformat(),
            "season": season,
            "total_in_rosters": len(all_roster_players),
            "updated_count": updated_count,
            "team_change_count": team_change_count,
            "no_change_count": no_change_count,
            "not_found_in_db": not_found_count,
            "nba_api_id_updated": nba_api_id_updated,
            "duration_seconds": duration,
            "status": "success"
        }

        # Log summary
        logger.info("\n" + "=" * 60)
        logger.info("Team Roster Sync Summary")
        logger.info("=" * 60)
        logger.info(f"Total players in rosters: {summary['total_in_rosters']}")
        logger.info(f"Players updated: {summary['updated_count']}")
        logger.info(f"Team changes: {summary['team_change_count']}")
        logger.info(f"No changes needed: {summary['no_change_count']}")
        logger.info(f"Not found in DB: {summary['not_found_in_db']}")
        logger.info(f"nba_api_id populated: {summary['nba_api_id_updated']}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info("=" * 60)

        return summary

    except Exception as e:
        logger.error(f"Error during roster sync: {e}", exc_info=True)
        db.rollback()
        return {
            "timestamp": datetime.now().isoformat(),
            "status": "error",
            "error": str(e)
        }
    finally:
        db.close()


async def verify_team_assignments() -> dict:
    """
    Verify team assignments by checking known problematic players.

    Returns dict with verification results.
    """
    db = SessionLocal()

    try:
        # Known players to verify
        test_cases = [
            ("Clint Capela", "ATL"),  # Should be ATL, not HOU
            ("Kevin Durant", "PHX"),  # Should be PHX, not HOU
            ("Steven Adams", "NOP"),  # Should be NOP, not HOU
            ("Alperen Sengun", "HOU"),  # Should be HOU
            ("Jalen Green", "HOU"),  # Should be HOU
        ]

        results = []
        all_correct = True

        for name, expected_team in test_cases:
            player = db.query(Player).filter(Player.name == name).first()

            if player:
                is_correct = player.team == expected_team
                results.append({
                    'name': name,
                    'current_team': player.team,
                    'expected_team': expected_team,
                    'correct': is_correct
                })

                if not is_correct:
                    all_correct = False
                    logger.warning(f"❌ {name}: {player.team} (expected {expected_team})")
                else:
                    logger.info(f"✅ {name}: {player.team}")
            else:
                logger.warning(f"⚠️  {name}: Not found in database")

        return {
            'all_correct': all_correct,
            'results': results
        }

    finally:
        db.close()


async def main():
    """Entry point for the script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Sync NBA team rosters from NBA API to fix outdated team assignments"
    )
    parser.add_argument(
        "--season",
        type=str,
        default=DEFAULT_SEASON,
        help=f"NBA season (default: {DEFAULT_SEASON})"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Only verify team assignments without syncing"
    )

    args = parser.parse_args()

    if args.verify:
        # Verification only mode
        logger.info("Verifying team assignments...")
        result = await verify_team_assignments()

        if result['all_correct']:
            logger.info("✅ All verified players have correct team assignments")
            sys.exit(0)
        else:
            logger.error("❌ Some players have incorrect team assignments")
            sys.exit(1)
    else:
        # Full sync mode
        result = await sync_all_rosters(season=args.season)

        if result.get("status") == "success":
            logger.info("\n✅ Script completed successfully")

            # Verify after sync
            logger.info("\n🔍 Verifying known problematic players...")
            await verify_team_assignments()

            sys.exit(0)
        else:
            logger.error(f"\n❌ Script failed: {result.get('error')}")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
