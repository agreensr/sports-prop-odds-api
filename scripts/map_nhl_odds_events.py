#!/usr/bin/env python3
"""
Create Odds API event ID mappings for NHL games.

This script matches games in our database to Odds API events using
team names and timestamps, then stores the mappings.
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db
from app.models.nhl.models import Game
from app.services.core.odds_api_service import get_odds_service


# Team abbreviation to full name mapping for Odds API matching
TEAM_NAMES = {
    "ANA": "Anaheim Ducks",
    "ARI": "Arizona Coyotes",
    "BOS": "Boston Bruins",
    "BUF": "Buffalo Sabres",
    "CGY": "Calgary Flames",
    "CAR": "Carolina Hurricanes",
    "CHI": "Chicago Blackhawks",
    "COL": "Colorado Avalanche",
    "CBJ": "Columbus Blue Jackets",
    "DAL": "Dallas Stars",
    "DET": "Detroit Red Wings",
    "EDM": "Edmonton Oilers",
    "FLA": "Florida Panthers",
    "LAK": "Los Angeles Kings",  # Odds API uses this
    "LA": "Los Angeles Kings",   # Our DB has this
    "MIN": "Minnesota Wild",
    "MTL": "Montreal Canadiens",
    "NSH": "Nashville Predators",
    "NJD": "New Jersey Devils",
    "NYI": "New York Islanders",
    "NYR": "New York Rangers",
    "OTT": "Ottawa Senators",
    "PHI": "Philadelphia Flyers",
    "PIT": "Pittsburgh Penguins",
    "SJS": "San Jose Sharks",
    "SEA": "Seattle Kraken",
    "STL": "St. Louis Blues",
    "TBL": "Tampa Bay Lightning",
    "TOR": "Toronto Maple Leafs",
    "VAN": "Vancouver Canucks",
    "VGK": "Vegas Golden Knights",
    "WSH": "Washington Capitals",
    "WPG": "Winnipeg Jets",
}


async def map_games_to_odds_api():
    """Map NHL games to Odds API event IDs."""
    db = next(get_db())

    # First, add the odds_event_id column if it doesn't exist
    try:
        db.execute(text("""
            ALTER TABLE nhl_games
            ADD COLUMN IF NOT EXISTS odds_event_id VARCHAR(64);
        """))
        db.commit()
        print("✓ odds_event_id column ready")
    except Exception as e:
        print(f"Column check: {e}")

    api_key = '8ad802abc3050bd7ff719830103602d6'
    odds_service = get_odds_service(api_key, sport="nhl")

    # Get our upcoming games
    games = db.query(Game).filter(
        Game.status == 'scheduled',
        Game.game_date >= datetime.now()
    ).order_by(Game.game_date).limit(15).all()

    print(f"Found {len(games)} upcoming NHL games")

    # Fetch odds API games
    odds_games = await odds_service.get_upcoming_games_with_odds(days_ahead=7)
    print(f"Odds API returned {len(odds_games)} games")

    # Match games by team names and approximate time
    matched = 0
    for game in games:
        our_away = TEAM_NAMES.get(game.away_team, game.away_team)
        our_home = TEAM_NAMES.get(game.home_team, game.home_team)

        # Also check the alternate abbreviation
        alt_away = our_away
        alt_home = our_home
        if game.away_team == "LA":
            alt_away = "Los Angeles Kings"
        if game.home_team == "LA":
            alt_home = "Los Angeles Kings"

        # Convert game time to UTC for comparison
        game_utc = game.game_date
        if game_utc.tzinfo is None:
            import datetime as dt
            game_utc = game_utc.replace(tzinfo=dt.timezone.utc)

        # Look for matching odds API game
        for odds_game in odds_games:
            odds_away = odds_game.get('away_team', '')
            odds_home = odds_game.get('home_team', '')
            odds_time_str = odds_game.get('commence_time', '')

            if not odds_time_str:
                continue

            odds_time = datetime.fromisoformat(odds_time_str.replace('Z', '+00:00'))

            # Check if teams match (try both name variations)
            teams_match = (
                (odds_away == our_away or odds_away == alt_away) and
                (odds_home == our_home or odds_home == alt_home)
            ) or (
                (odds_away == our_home or odds_away == alt_home) and
                (odds_home == our_away or odds_home == alt_away)
            )

            # Check if time is within 24 hours (allowing for timezone differences)
            time_diff = abs((odds_time - game_utc).total_seconds())

            if teams_match and time_diff < 86400:  # 24 hours
                # Store mapping directly in nhl_games table
                odds_id = odds_game.get('id')

                db.execute(text("""
                    UPDATE nhl_games
                    SET odds_event_id = :odds_id
                    WHERE id = :game_id
                """), {"odds_id": odds_id, "game_id": str(game.id)})

                matched += 1
                print(f"✓ {game.away_team} @ {game.home_team} ({game.game_date.strftime('%Y-%m-%d %H:%M')}) -> {odds_id}")
                break

    db.commit()
    print(f"\nCreated {matched} mappings")

    await odds_service.close()
    db.close()


if __name__ == "__main__":
    asyncio.run(map_games_to_odds_api())
