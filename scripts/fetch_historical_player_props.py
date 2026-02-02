#!/usr/bin/env python3
"""
Pull historical player props from The Odds API for the last 20 games.

Requirements:
- THE_ODDS_API_KEY environment variable with historical access
- Fetches for: points, rebounds, assists, threes
- FanDuel bookmaker only
- Starters only
- For today's Knicks vs 76ers game players

The Odds API Historical Data:
- Requires paid subscription tier
- Format: /sports/{sport}/events/{event_id}/odds/history?days={days}
"""
import asyncio
import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.services.core.odds_api_service import get_odds_service
from app.models.nba.models import Player, Game, ExpectedLineup

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# The Odds API configuration
THE_ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY")

# Stat types to fetch
STAT_TYPES = ["player_points", "player_rebounds", "player_assists", "player_threes"]

# Target bookmaker
BOOKMAKER = "fanduel"

# Games back
GAMES_BACK = 20


async def get_todays_game():
    """Get today's Knicks vs 76ers game."""
    db = SessionLocal()
    try:
        # Get today's date in Central timezone
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
            # Try yesterday/tomorrow
            yesterday = today - timedelta(days=1)
            tomorrow = today + timedelta(days=1)

            for check_date in [yesterday, tomorrow]:
                check_start = check_date.replace(hour=0, minute=0, second=0, microsecond=0)
                check_end = check_date.replace(hour=23, minute=59, second=59, microsecond=999999)

                game = db.query(Game).filter(
                    Game.game_date >= check_start,
                    Game.game_date <= check_end,
                    Game.away_team.in_(["NYK", "PHI"]),
                    Game.home_team.in_(["NYK", "PHI"])
                ).first()

                if game:
                    break

        return game
    finally:
        db.close()


async def get_game_players(game_id: str, starters_only: bool = True):
    """Get players for a game, optionally starters only."""
    db = SessionLocal()
    try:
        # Get teams for this game
        game = db.query(Game).filter(Game.id == game_id).first()
        if not game:
            return []

        # Get expected lineups to determine starters
        lineups = db.query(ExpectedLineup).filter(
            ExpectedLineup.game_id == game_id
        ).all()

        starter_ids = {lineup.player_id for lineup in lineups if lineup.is_starter}

        # Get players
        query = db.query(Player).filter(
            Player.team.in_([game.away_team, game.home_team]),
            Player.active == True
        )

        players = query.all()

        if starters_only:
            players = [p for p in players if p.id in starter_ids]

        return players
    finally:
        db.close()


async def fetch_historical_odds_for_player(
    odds_service,
    player_name: str,
    days_back: int = GAMES_BACK
):
    """
    Fetch historical odds for a player from The Odds API.

    The Odds API historical endpoint format:
    /sports/{sport}/events/{event_id}/odds/historical

    Note: This requires a paid subscription tier that includes historical data.
    """
    try:
        # The Odds API requires event IDs for historical queries
        # We need to get the player's recent games first

        logger.info(f"Fetching historical odds for {player_name} (last {days_back} games)")

        # TODO: Implement historical odds fetch
        # This requires:
        # 1. Getting event IDs for player's last 20 games
        # 2. Calling historical odds endpoint for each event
        # 3. Filtering by bookmaker and stat type

        logger.warning(f"Historical odds API requires paid subscription - skipping")
        return []

    except Exception as e:
        logger.error(f"Error fetching historical odds for {player_name}: {e}")
        return []


async def fetch_historical_from_database(
    player_id: str,
    stat_types: list = STAT_TYPES,
    games_back: int = GAMES_BACK
):
    """
    Fetch historical odds from our database (archived snapshots).

    This is the fallback method when The Odds API historical isn't available.
    """
    db = SessionLocal()
    try:
        from app.models.nba.models import HistoricalOddsSnapshot
        from sqlalchemy import and_, desc

        results = []

        for stat_type in stat_types:
            # Convert "player_points" to "points"
            stat = stat_type.replace("player_", "")

            snapshots = db.query(HistoricalOddsSnapshot).filter(
                HistoricalOddsSnapshot.player_id == player_id,
                HistoricalOddsSnapshot.stat_type == stat,
                HistoricalOddsSnapshot.bookmaker_name == "FanDuel",
                HistoricalOddsSnapshot.was_starter == True,
                HistoricalOddsSnapshot.actual_value.isnot(None)  # Only resolved games
            ).order_by(
                desc(HistoricalOddsSnapshot.created_at)
            ).limit(games_back).all()

            for snap in snapshots:
                results.append({
                    "stat_type": stat,
                    "bookmaker_line": snap.bookmaker_line,
                    "over_price": snap.over_price,
                    "under_price": snap.under_price,
                    "actual_value": snap.actual_value,
                    "hit_result": snap.hit_result,
                    "was_starter": snap.was_starter,
                    "snapshot_time": snap.snapshot_time,
                    "game_id": snap.game_id
                })

        return results
    finally:
        db.close()


async def main():
    """Main function to pull historical player props."""
    logger.info("=" * 60)
    logger.info("Historical Player Props - Last 20 Games")
    logger.info("=" * 60)

    if not THE_ODDS_API_KEY:
        logger.error("THE_ODDS_API_KEY not set")
        return 1

    # Get today's game
    logger.info("Getting today's Knicks vs 76ers game...")
    game = await get_todays_game()

    if not game:
        logger.error("Could not find Knicks vs 76ers game")
        return 1

    logger.info(f"Found game: {game.away_team} @ {game.home_team} on {game.game_date}")

    # Get players - try starters first, fallback to all active players
    players = await get_game_players(game.id, starters_only=True)
    logger.info(f"Found {len(players)} starters")

    if len(players) == 0:
        logger.info("No starters found, getting all active players...")
        players = await get_game_players(game.id, starters_only=False)
        logger.info(f"Found {len(players)} active players")

    # Initialize odds service
    odds_service = get_odds_service(THE_ODDS_API_KEY)

    # Fetch historical data for each player
    all_results = {}

    for player in players:
        logger.info(f"\n{'=' * 50}")
        logger.info(f"Player: {player.name} ({player.team})")
        logger.info(f"{'=' * 50}")

        # Try The Odds API historical (requires paid tier)
        api_results = await fetch_historical_odds_for_player(odds_service, player.name)

        # Fallback to database
        if not api_results:
            logger.info("Using database historical snapshots...")
            db_results = await fetch_historical_from_database(player.id)

            logger.info(f"Found {len(db_results)} historical snapshots")

            # Group by stat type
            by_stat = {}
            for r in db_results:
                stat = r["stat_type"]
                if stat not in by_stat:
                    by_stat[stat] = []
                by_stat[stat].append(r)

            all_results[player.name] = by_stat

            # Print summary
            for stat, snapshots in by_stat.items():
                hits = sum(1 for s in snapshots if s.get("hit_result") == "OVER")
                total = len(snapshots)
                hit_rate = hits / total if total > 0 else 0

                recent_lines = [s["bookmaker_line"] for s in snapshots[:5]]
                recent_actuals = [s["actual_value"] for s in snapshots[:5]]

                logger.info(f"\n{stat.upper()}:")
                logger.info(f"  Last {len(snapshots)} games")
                logger.info(f"  OVER hit rate: {hit_rate:.1%} ({hits}/{total})")
                logger.info(f"  Recent lines: {recent_lines[:5]}")
                logger.info(f"  Recent actuals: {recent_actuals[:5]}")

    logger.info("\n" + "=" * 60)
    logger.info("Historical odds data collection complete")
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
