#!/usr/bin/env python3
"""
Map NBA games to Odds API event IDs.

This script:
1. Fetches upcoming NBA games from the database
2. Queries the Odds API for basketball_nba events
3. Matches games by team abbreviations and date
4. Stores the odds_api_event_id mapping in the database

Run this before generating NBA predictions to ensure
all games have proper Odds API event mappings.
"""
import asyncio
import os
import sys
from datetime import date, timedelta, datetime
from pathlib import Path

# Add app directory to path
app_dir = Path(__file__).parent.parent
sys.path.insert(0, str(app_dir))

from sqlalchemy import create_engine, text
from app.core.config import settings


async def map_nba_games():
    """Map NBA games to Odds API event IDs."""

    # Get THE_ODDS_API_KEY from environment
    api_key = os.getenv("THE_ODDS_API_KEY")
    if not api_key:
        print("ERROR: THE_ODDS_API_KEY environment variable not set")
        return

    # Create database engine
    engine = create_engine(settings.DATABASE_URL)

    # Odds API base URL
    odds_base_url = "https://api.the-odds-api.com/v4"

    # Import httpx for async requests
    import httpx

    async with httpx.AsyncClient() as client:
        # Fetch upcoming NBA games from Odds API
        print("Fetching upcoming games from Odds API...")
        # Use odds endpoint to get upcoming games (no event ID = all upcoming)
        url = f"{odds_base_url}/sports/basketball_nba/odds"
        params = {
            "apiKey": api_key,
            "markets": "h2h",  # Only need head-to-head to get games
            "oddsFormat": "american",
            "bookmakers": "draftkings,fanduel,betmgm",  # Required parameter
            "daysFrom": 0,
            "daysTo": 7  # Fetch games for next 7 days
        }

        response = await client.get(url, params=params)
        if response.status_code != 200:
            print(f"ERROR: Odds API returned status {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return

        odds_games = response.json()
        print(f"Fetched {len(odds_games)} games from Odds API")

        # Get upcoming games from database
        with engine.connect() as conn:
            today = date.today()
            # Look ahead up to 7 days for future games
            end_date = today + timedelta(days=7)

            result = conn.execute(text("""
                SELECT id, home_team, away_team, game_date
                FROM games
                WHERE game_date >= :today
                  AND game_date <= :end_date
                  AND status = 'scheduled'
                ORDER BY game_date
            """), {"today": today, "end_date": end_date})

            db_games = result.fetchall()
            print(f"\nFound {len(db_games)} upcoming games in database")

            if not db_games:
                print("No upcoming games found in database")
                return

            # Map each database game to Odds API event
            mappings_created = 0

            for db_game in db_games:
                game_id = db_game[0]
                home_team = db_game[1]
                away_team = db_game[2]
                game_date = db_game[3]

                # Convert game_date to date for comparison
                if isinstance(game_date, datetime):
                    game_date = game_date.date()

                # Find matching Odds API game
                matched_odds_id = None

                for odds_game in odds_games:
                    # Get teams from Odds API
                    odds_home = odds_game.get("home_team", "")
                    odds_away = odds_game.get("away_team", "")

                    # Get commence date
                    commence_str = odds_game.get("commence_time", "")
                    if commence_str:
                        try:
                            commence_date = datetime.fromisoformat(
                                commence_str.replace("Z", "+00:00")
                            ).date()
                        except (ValueError, AttributeError):
                            continue
                    else:
                        continue

                    # Check date match (allow 1 day for timezone differences)
                    date_match = abs((commence_date - game_date).days) <= 1

                    if not date_match:
                        continue

                    # Check team match (case-insensitive)
                    # Odds API uses full names, we use abbreviations
                    # So we check if our abbreviation is in their name
                    away_match = (
                        away_team.lower() in odds_away.lower() or
                        odds_away.lower() in away_team.lower()
                    )
                    home_match = (
                        home_team.lower() in odds_home.lower() or
                        odds_home.lower() in home_team.lower()
                    )

                    if away_match and home_match:
                        matched_odds_id = odds_game.get("id")
                        print(f"\n✓ Matched: {away_team} @ {home_team}")
                        print(f"  DB Game ID: {game_id}")
                        print(f"  Odds Event ID: {matched_odds_id}")
                        print(f"  Odds API: {odds_away} @ {odds_home}")
                        break

                if matched_odds_id:
                    # Update the game with odds_api_event_id
                    conn.execute(text("""
                        UPDATE games
                        SET odds_api_event_id = :odds_id
                        WHERE id = :game_id
                    """), {"odds_id": matched_odds_id, "game_id": game_id})
                    mappings_created += 1
                else:
                    print(f"\n✗ No match found: {away_team} @ {home_team} on {game_date}")

            # Commit changes
            conn.commit()

            print(f"\n{'='*60}")
            print(f"Mapping complete: {mappings_created}/{len(db_games)} games mapped")
            print(f"{'='*60}")

            # Show current state
            result = conn.execute(text("""
                SELECT COUNT(*) as total,
                       COUNT(odds_api_event_id) as mapped
                FROM games
                WHERE game_date >= :today
                  AND game_date <= :end_date
                  AND status = 'scheduled'
            """), {"today": today, "end_date": end_date})

            row = result.fetchone()
            print(f"\nGames today/tomorrow: {row[0]} total, {row[1]} mapped")


if __name__ == "__main__":
    asyncio.run(map_nba_games())
