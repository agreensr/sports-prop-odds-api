"""
Sync scheduled NBA games from ESPN API.

This script fetches upcoming games from ESPN and stores them in the database.
ESPN API has reliable scheduled game data unlike nba_api which only has historical games.

Usage:
    python scripts/sync_espn_schedule.py --days 7
"""
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.services.core.espn_service import ESPNApiService
from app.models import Game
from sqlalchemy import and_

# ESPN to NBA team abbreviation mapping
# ESPN API returns inconsistent abbreviations - normalize to database format
ESPN_TO_NBA_TEAMS = {
    # Direct 3-letter mappings
    'ATL': 'ATL', 'BOS': 'BOS', 'BKN': 'BKN', 'CHA': 'CHA', 'CHI': 'CHI',
    'CLE': 'CLE', 'DAL': 'DAL', 'DEN': 'DEN', 'DET': 'DET', 'GSW': 'GSW',
    'HOU': 'HOU', 'IND': 'IND', 'LAC': 'LAC', 'LAL': 'LAL', 'MEM': 'MEM',
    'MIA': 'MIA', 'MIL': 'MIL', 'MIN': 'MIN', 'NOP': 'NOP', 'NYK': 'NYK',
    'OKC': 'OKC', 'ORL': 'ORL', 'PHI': 'PHI', 'PHX': 'PHX', 'POR': 'POR',
    'SAC': 'SAC', 'SAS': 'SAS', 'TOR': 'TOR', 'UTA': 'UTA', 'WAS': 'WAS',
    # ESPN special cases - need conversion
    'SA': 'SAS',      # San Antonio Spurs
    'UTAH': 'UTA',    # Utah Jazz
    'NO': 'NOP',      # New Orleans Pelicans
    'NY': 'NYK',      # New York Knicks
    'GS': 'GSW',      # Golden State Warriors
    # Full names from ESPN
    'San Antonio Spurs': 'SAS',
    'Charlotte Hornets': 'CHA',
    'Atlanta Hawks': 'ATL',
    'Indiana Pacers': 'IND',
    'New Orleans Pelicans': 'NOP',
    'Philadelphia 76ers': 'PHI',
    'Chicago Bulls': 'CHI',
    'Miami Heat': 'MIA',
    'Minnesota Timberwolves': 'MIN',
    'Memphis Grizzlies': 'MEM',
    'Dallas Mavericks': 'DAL',
    'Houston Rockets': 'HOU',
    'Toronto Raptors': 'TOR',
    'Utah Jazz': 'UTA',
}


def normalize_team_abbr(abbr: str) -> str:
    """Normalize ESPN team abbreviation to NBA format."""
    abbr = abbr.upper().strip()
    return ESPN_TO_NBA_TEAMS.get(abbr, abbr)


async def sync_espn_schedule(days_ahead: int = 7, dry_run: bool = False) -> dict:
    """
    Sync upcoming games from ESPN API to database.

    Args:
        days_ahead: Number of days to look ahead
        dry_run: If True, don't save to database

    Returns:
        Dictionary with sync results
    """
    db = SessionLocal()
    service = ESPNApiService()

    results = {
        'fetched': 0,
        'created': 0,
        'updated': 0,
        'skipped': 0,
        'games': []
    }

    try:
        print(f"Fetching scheduled games from ESPN (next {days_ahead} days)...")

        # Get upcoming games from ESPN
        games = await service.get_upcoming_games('nba', days_ahead=days_ahead)
        results['fetched'] = len(games)

        print(f"Found {len(games)} scheduled games")
        print()

        for game_data in games:
            away_abbr = normalize_team_abbr(game_data.get('away_abbr', ''))
            home_abbr = normalize_team_abbr(game_data.get('home_abbr', ''))
            game_date = game_data.get('date')
            espn_id = game_data.get('id')

            if not away_abbr or not home_abbr or not game_date:
                print(f"  ⚠️  Skipping: {game_data.get('name')} - missing data")
                results['skipped'] += 1
                continue

            # Check if game already exists
            existing = db.query(Game).filter(
                and_(
                    Game.away_team == away_abbr,
                    Game.home_team == home_abbr,
                    Game.game_date == game_date
                )
            ).first()

            if existing:
                # Update ESPN ID if missing
                if not existing.espn_game_id:
                    existing.espn_game_id = str(espn_id)
                    if not dry_run:
                        db.commit()
                    results['updated'] += 1
                    print(f"  ✓ Updated: {away_abbr} @ {home_abbr} (added ESPN ID)")
                else:
                    results['skipped'] += 1
                    print(f"  ⊙ Exists: {away_abbr} @ {home_abbr}")
            else:
                # Create new game
                if not dry_run:
                    new_game = Game(
                        id=f"espn_{espn_id}",
                        sport_id='nba',
                        external_id=str(espn_id),
                        espn_game_id=str(espn_id),
                        away_team=away_abbr,
                        home_team=home_abbr,
                        game_date=game_date,
                        status='scheduled',
                        season=2025,  # Season as integer year
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    db.add(new_game)
                    db.commit()
                    print(f"  + Created: {away_abbr} @ {home_abbr} | {game_date.strftime('%Y-%m-%d %H:%M')}")
                else:
                    print(f"  + Would create: {away_abbr} @ {home_abbr} | {game_date.strftime('%Y-%m-%d %H:%M')}")

                results['created'] += 1
                results['games'].append({
                    'away': away_abbr,
                    'home': home_abbr,
                    'date': game_date.isoformat(),
                    'espn_id': espn_id
                })

        print()
        print(f"Sync complete: {results['created']} created, {results['updated']} updated, {results['skipped']} skipped")

        return results

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        if not dry_run:
            db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync NBA schedule from ESPN API")
    parser.add_argument('--days', type=int, default=7, help='Days ahead to fetch (default: 7)')
    parser.add_argument('--dry-run', action='store_true', help='Simulate without saving')

    args = parser.parse_args()

    import asyncio
    asyncio.run(sync_espn_schedule(days_ahead=args.days, dry_run=args.dry_run))
