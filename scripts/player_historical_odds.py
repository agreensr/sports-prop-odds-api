#!/usr/bin/env python3
"""
Pull FanDuel player props for a specific player's last N games from The Odds API.

Process:
1. Get player's recent games from our database (to get event IDs)
2. For each game, fetch historical FanDuel player props from The Odds API
3. Extract just this player's props (points, rebounds, assists, threes)
"""
import asyncio
import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.nba.models import Player, PlayerStats

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

THE_ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY")
STAT_TYPES = ["player_points", "player_rebounds", "player_assists", "player_threes"]
BOOKMAKER = "fanduel"
GAMES_BACK = 10


def format_american_odds(decimal_odds: float) -> str:
    """Convert decimal odds to American odds format."""
    if decimal_odds >= 2.0:
        return f"+{int((decimal_odds - 1) * 100)}"
    else:
        return f"{int(-100 / (decimal_odds - 1))}"


async def get_player_event_ids(player_name: str, games_back: int = GAMES_BACK):
    """Get event IDs for player's recent games from our database."""
    db = SessionLocal()
    try:
        # Get player by name
        player = db.query(Player).filter(Player.name == player_name).first()
        if not player:
            return None, f"Player not found: {player_name}"

        # Get player's recent game stats (these have game info)
        player_stats = db.query(PlayerStats).filter(
            PlayerStats.player_id == player.id
        ).order_by(PlayerStats.created_at.desc()).limit(games_back).all()

        # Extract unique game IDs
        game_ids = list(set(ps.game_id for ps in player_stats if ps.game_id))

        return player, game_ids
    finally:
        db.close()


async def get_historical_odds_for_event(event_id: str):
    """
    Get historical FanDuel odds for a specific event.

    The Odds API stores historical odds and they're accessible via the
    odds endpoint with historical data.
    """
    async with httpx.AsyncClient() as client:
        url = f"https://api.the-odds-api.com/v4/sports/basketball_nba/events/{event_id}/odds"
        params = {
            "apiKey": THE_ODDS_API_KEY,
            "bookmakers": BOOKMAKER,
            "markets": ",".join(STAT_TYPES)
        }

        response = await client.get(url, params=params)

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            logger.warning(f"Event {event_id}: No odds available (404)")
            return None
        else:
            logger.error(f"Event {event_id}: HTTP {response.status_code}")
            return None


def extract_player_props(odds_data, player_name: str):
    """Extract just the requested player's props from odds data."""
    if not odds_data:
        return {}

    player_props = {
        "points": None,
        "rebounds": None,
        "assists": None,
        "threes": None
    }

    # Find FanDuel bookmaker
    bookmakers = odds_data.get('bookmakers', [])
    fanduel = next((b for b in bookmakers if b.get('key') == BOOKMAKER), None)

    if not fanduel:
        return player_props

    # Extract props for each stat type
    for market in fanduel.get('markets', []):
        market_key = market.get('key', '')  # player_points, player_rebounds, etc.
        stat_type = market_key.replace('player_', '')  # points, rebounds, etc.

        for outcome in market.get('outcomes', []):
            if outcome.get('description') == player_name:
                line = outcome.get('point')
                price = outcome.get('price')  # Usually "Over" price

                player_props[stat_type] = {
                    'line': line,
                    'over_price': format_american_odds(price) if price else None,
                    'over_decimal': price
                }
                break

    return player_props


async def main():
    """Main function to pull player's historical FanDuel props."""
    if not THE_ODDS_API_KEY:
        logger.error("THE_ODDS_API_KEY not set")
        return 1

    player_name = "Joel Embiid"

    logger.info("=" * 70)
    logger.info(f"Fanduel Player Props - {player_name} (Last {GAMES_BACK} Games)")
    logger.info("=" * 70)

    # Get player's game IDs
    logger.info(f"Finding {player_name}'s recent games...")
    player, game_ids = await get_player_event_ids(player_name, GAMES_BACK)

    if not player:
        logger.error(f"Could not find player: {player_name}")
        return 1

    logger.info(f"Found {len(game_ids)} recent games for {player_name}")
    logger.info("")

    # Fetch odds for each game
    all_game_props = []

    for i, game_id in enumerate(game_ids, 1):
        logger.info(f"[{i}/{len(game_ids)}] Fetching odds for event {game_id}...")

        odds_data = await get_historical_odds_for_event(game_id)

        if odds_data:
            props = extract_player_props(odds_data, player_name)

            # Get game date from odds data
            commence_time = odds_data.get('commence_time', 'Unknown')
            home_team = odds_data.get('home_team', '')
            away_team = odds_data.get('away_team', '')

            all_game_props.append({
                'game_id': game_id,
                'date': commence_time[:10] if commence_time else 'Unknown',
                'matchup': f"{away_team} @ {home_team}",
                'props': props
            })

            # Display immediately
            logger.info(f"  Date: {all_game_props[-1]['date']}")
            logger.info(f"  Matchup: {all_game_props[-1]['matchup']}")

            for stat, prop in props.items():
                if prop:
                    logger.info(f"    {stat.upper()}: {prop['line']} (O: {prop['over_price']})")
                else:
                    logger.info(f"    {stat.upper()}: N/A")
            logger.info("")
        else:
            logger.info(f"  No odds available for this game")
            logger.info("")

    # Summary
    logger.info("=" * 70)
    logger.info("Summary - Historical FanDuel Props Found")
    logger.info("=" * 70)

    # Count how many games have data for each stat
    stats_with_data = {
        'points': 0,
        'rebounds': 0,
        'assists': 0,
        'threes': 0
    }

    for game_data in all_game_props:
        for stat, prop in game_data['props'].items():
            if prop:
                stats_with_data[stat] += 1

    for stat, count in stats_with_data.items():
        logger.info(f"{stat.upper()}: {count}/{GAMES_BACK} games")

    logger.info("")
    logger.info("Format: For each game showing FanDuel line and OVER price")
    logger.info("(Actual performance would be pulled separately from nba_api)")

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
