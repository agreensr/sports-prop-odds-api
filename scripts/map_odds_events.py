"""Map Odds API event IDs to database games."""
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal
from app.models import Game
from app.services.core.odds_api_service import OddsApiService
from datetime import datetime

# Team name normalization
ODDS_TO_DB_TEAMS = {
    "San Antonio Spurs": "SAS",
    "Charlotte Hornets": "CHA",
    "Atlanta Hawks": "ATL",
    "Indiana Pacers": "IND",
    "New Orleans Pelicans": "NOP",
    "Philadelphia 76ers": "PHI",
    "Chicago Bulls": "CHI",
    "Miami Heat": "MIA",
    "Minnesota Timberwolves": "MIN",
    "Memphis Grizzlies": "MEM",
    "Los Angeles Lakers": "LAL",
    "Golden State Warriors": "GSW",
    # Add more as needed
}

def normalize_team(full_name: str) -> str:
    """Convert full team name to abbreviation."""
    return ODDS_TO_DB_TEAMS.get(full_name, full_name[:3].upper())

async def map_odds_events():
    db = SessionLocal()
    api_key = '8ad802abc3050bd7ff719830103602d6'
    odds = OddsApiService(api_key)

    # Get upcoming games from Odds API
    print("Fetching upcoming games from Odds API...")
    games_odds = await odds.get_upcoming_games_with_odds('basketball_nba')

    mapped_count = 0
    for odds_game in games_odds:
        away_full = odds_game.get('away_team')
        home_full = odds_game.get('home_team')
        odds_event_id = odds_game.get('id')

        away_abbr = normalize_team(away_full)
        home_abbr = normalize_team(home_full)

        # Find matching game in database (today or tomorrow)
        from datetime import timedelta
        start = datetime.now().replace(hour=0, minute=0, second=0)
        end = start + timedelta(days=2)

        game = db.query(Game).filter(
            Game.away_team == away_abbr,
            Game.home_team == home_abbr,
            Game.game_date >= start,
            Game.game_date <= end
        ).first()

        if game:
            old_event_id = game.odds_api_event_id
            game.odds_api_event_id = odds_event_id
            print(f"Mapped: {away_abbr} @ {home_abbr} -> {odds_event_id}")
            if old_event_id != odds_event_id:
                print(f"  (was: {old_event_id})")
            mapped_count += 1
        else:
            print(f"Not found: {away_abbr} @ {home_abbr}")

    db.commit()
    print(f"\nMapped {mapped_count} games")

    # Check quota
    print(f"\nQuota: {odds._requests_remaining} remaining")

    await odds.close()
    db.close()

if __name__ == '__main__':
    asyncio.run(map_odds_events())
