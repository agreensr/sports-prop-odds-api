#!/usr/bin/env python3
"""
Pull last 20 games of historical FanDuel player props from The Odds API.

Uses paid subscription tier to access historical odds data.
For: Knicks @ 76ers game players, starters only.
Stats: points, rebounds, assists, threes
"""
import asyncio
import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
import httpx

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.nba.models import Player, Game, ExpectedLineup

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

THE_ODDS_API_KEY = "8ad802abc3050bd7ff719830103602d6"
STAT_TYPES = ["player_points", "player_rebounds", "player_assists", "player_threes"]
BOOKMAKER = "fanduel"
GAMES_BACK = 20


async def get_team_games(team_abbr: str, days_back: int = 30):
    """Get recent games for a team from The Odds API."""
    async with httpx.AsyncClient() as client:
        # Get completed games
        url = f"https://api.the-odds-api.com/v4/sports/basketball_nba/scores"
        params = {
            "apiKey": THE_ODDS_API_KEY,
            "days_from": (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%S")
        }

        response = await client.get(url, params=params)
        response.raise_for_status()

        games = response.json()

        # Filter for team's games
        team_games = []
        for game in games:
            if game.get('completed') and (
                game.get('home_team') == team_abbr or
                game.get('away_team') == team_abbr or
                team_abbr in game.get('home_team', '') or
                team_abbr in game.get('away_team', '')
            ):
                team_games.append(game)

        return sorted(team_games, key=lambda x: x.get('commence_time', ''), reverse=True)[:GAMES_BACK]


async def get_event_player_props(event_id: str):
    """Get player props for a specific event from The Odds API."""
    async with httpx.AsyncClient() as client:
        url = f"https://api.the-odds-api.com/v4/sports/basketball_nba/events/{event_id}/odds"
        params = {
            "apiKey": THE_ODDS_API_KEY,
            "bookmakers": BOOKMAKER,
            "markets": ",".join(STAT_TYPES)
        }

        response = await client.get(url, params=params)
        response.raise_for_status()

        return response.json()


def format_american_odds(decimal_odds: float) -> str:
    """Convert decimal odds to American odds format."""
    if decimal_odds >= 2.0:
        return f"+{int((decimal_odds - 1) * 100)}"
    else:
        return f"{int(-100 / (decimal_odds - 1))}"


async def main():
    """Main function to pull historical player props."""
    logger.info("=" * 70)
    logger.info(f"Historical FanDuel Player Props - Last {GAMES_BACK} Games")
    logger.info("=" * 70)

    # Get today's Knicks vs 76ers game
    db = SessionLocal()
    try:
        today = datetime.now()
        today_start = today.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today.replace(hour=23, minute=59, second=59, microsecond=999999)

        game = db.query(Game).filter(
            Game.game_date >= today_start,
            Game.game_date <= today_end,
            Game.away_team.in_(["NYK", "PHI"]),
            Game.home_team.in_(["NYK", "PHI"])
        ).first()

        if not game:
            logger.error("Could not find Knicks vs 76ers game")
            return 1

        logger.info(f"Today's game: {game.away_team} @ {game.home_team}")
        logger.info(f"Date: {game.game_date}")
        logger.info("")

        # Get expected starters (starter_position is not null)
        lineups = db.query(ExpectedLineup).filter(
            ExpectedLineup.game_id == game.id,
            ExpectedLineup.starter_position.isnot(None)
        ).all()

        starter_ids = {lineup.player_id for lineup in lineups}
        logger.info(f"Found {len(starter_ids)} starters from lineups")

        # Get active players
        players = db.query(Player).filter(
            Player.team.in_([game.away_team, game.home_team]),
            Player.active == True
        ).all()

        # If no lineups, get all active players
        if len(starter_ids) == 0:
            logger.info("No lineup data, using all active players")
            target_players = players
        else:
            target_players = [p for p in players if p.id in starter_ids]
            logger.info(f"Filtering to {len(target_players)} starters")

        # Pull last 20 games for both teams and collect player props
        logger.info("")
        logger.info("=" * 70)
        logger.info("Fetching historical games...")
        logger.info("=" * 70)

        # Get Knicks games
        knicks_games = await get_team_games("Knicks")
        logger.info(f"Found {len(knicks_games)} recent Knicks games")

        # Get 76ers games
        phi_games = await get_team_games("Philadelphia 76ers")
        logger.info(f"Found {len(phi_games)} recent 76ers games")

        # Combine and dedupe
        all_games = {g['id']: g for g in knicks_games + phi_games}
        game_ids = list(all_games.keys())[:GAMES_BACK]

        logger.info(f"Total unique games: {len(game_ids)}")
        logger.info("")

        # For each player, collect their props across all games
        all_player_data = {}

        for player in target_players:
            logger.info(f"{'=' * 70}")
            logger.info(f"Player: {player.name} ({player.team})")
            logger.info(f"{'=' * 70}")

            player_data = {
                "player": player.name,
                "team": player.team,
                "props": []
            }

            for game_id in game_ids:
                try:
                    game_data = await get_event_player_props(game_id)

                    # Extract player's props
                    fanduel = game_data.get('bookmakers', [])
                    if not fanduel:
                        continue

                    for market in fanduel[0].get('markets', []):
                        market_key = market.get('key')

                        for outcome in market.get('outcomes', []):
                            if outcome.get('description') == player.name:
                                player_data['props'].append({
                                    'game_id': game_id,
                                    'game_date': all_games[game_id].get('commence_time'),
                                    'stat_type': market_key.replace('player_', ''),
                                    'line': outcome.get('point'),
                                    'over_price': format_american_odds(outcome.get('price', 0)),
                                    'over_decimal': outcome.get('price', 0)
                                })

                except Exception as e:
                    logger.warning(f"Error fetching game {game_id}: {e}")
                    continue

            if player_data['props']:
                # Sort by date
                player_data['props'].sort(key=lambda x: x.get('game_date', ''), reverse=True)

                # Group by stat type
                by_stat = {}
                for prop in player_data['props']:
                    stat = prop['stat_type']
                    if stat not in by_stat:
                        by_stat[stat] = []
                    by_stat[stat].append(prop)

                # Display results
                for stat, props in sorted(by_stat.items()):
                    logger.info(f"\n{stat.upper()}:")
                    for i, prop in enumerate(props[:10], 1):  # Last 10
                        game_date = prop.get('game_date', '')[:10] if prop.get('game_date') else 'N/A'
                        logger.info(f"  {i}. {game_date}: {prop['line']} (O: {prop['over_price']})")

                    if len(props) > 10:
                        logger.info(f"  ... ({len(props) - 10} more games)")

                all_player_data[player.name] = player_data

        # Save summary
        logger.info("")
        logger.info("=" * 70)
        logger.info("Summary")
        logger.info("=" * 70)
        logger.info(f"Total players processed: {len(all_player_data)}")

        for player_name, data in all_player_data.items():
            total_props = len(data['props'])
            logger.info(f"  {player_name}: {total_props} prop records")

    finally:
        db.close()

    logger.info("")
    logger.info("=" * 70)
    logger.info("Historical odds pull complete!")
    logger.info("=" * 70)

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
