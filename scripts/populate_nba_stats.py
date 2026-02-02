#!/usr/bin/env python3
"""
NBA Player Stats Population Script.

Fetches game-by-game and season statistics for NBA players from NBA API
and stores them in the unified PlayerStats and PlayerSeasonStats models.

Usage:
    python scripts/populate_nba_stats.py

Options:
    --season SEASON    NBA season (default: 2024-25)
    --player ID        Only fetch stats for specific player
    --games-only       Only fetch game-by-game stats
    --season-only      Only fetch season stats
    --limit N          Limit number of players to process

Requirements:
    - nba_api library installed
    - Players must exist in database first (run populate_nba_players.py)
"""
import asyncio
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.unified import Player, PlayerStats, PlayerSeasonStats, Game
from app.core.logging import get_logger
from sqlalchemy import and_, or_

logger = get_logger(__name__)

DEFAULT_SEASON = "2024-25"
REQUEST_DELAY = 0.6  # Delay between NBA API requests


def parse_game_date(date_str: str) -> Optional[datetime]:
    """Parse NBA API game date string."""
    if not date_str:
        return None
    try:
        # Format: "Oct 24, 2024"
        return datetime.strptime(date_str, "%b %d, %Y")
    except Exception:
        return None


def parse_minutes(min_str: str) -> Optional[int]:
    """Parse minutes string to integer."""
    if not min_str:
        return None
    try:
        # Format: "36:15" or "36"
        if ":" in min_str:
            return int(min_str.split(":")[0])
        return int(min_str)
    except Exception:
        return None


async def fetch_player_game_log(
    player_id: int,
    season: str = DEFAULT_SEASON
) -> List[Dict]:
    """
    Fetch game log for a player from NBA API.

    Args:
        player_id: NBA API player ID
        season: NBA season (e.g., "2024-25")

    Returns:
        List of game stat dictionaries
    """
    try:
        from nba_api.stats.endpoints import playergamelog

        await asyncio.sleep(REQUEST_DELAY)

        gamelog = playergamelog.PlayerGameLog(
            player_id=player_id,
            season=season
        )

        df = gamelog.get_data_frames()[0] if gamelog.get_data_frames() else None

        if df is None or df.empty:
            return []

        games = []
        for _, row in df.iterrows():
            games.append({
                "game_id": row.get("Game_ID"),
                "game_date": parse_game_date(row.get("GAME_DATE")),
                "matchup": row.get("MATCHUP"),
                "won_loss": row.get("WL"),
                "minutes": parse_minutes(row.get("MIN")),
                "points": int(row.get("PTS", 0)) if row.get("PTS") else None,
                "rebounds": int(row.get("REB", 0)) if row.get("REB") else None,
                "assists": int(row.get("AST", 0)) if row.get("AST") else None,
                "steals": int(row.get("STL", 0)) if row.get("STL") else None,
                "blocks": int(row.get("BLK", 0)) if row.get("BLK") else None,
                "turnovers": int(row.get("TOV", 0)) if row.get("TOV") else None,
                "fg_made": int(row.get("FGM", 0)) if row.get("FGM") else None,
                "fg_attempted": int(row.get("FGA", 0)) if row.get("FGA") else None,
                "fg_pct": float(row.get("FG_PCT", 0)) if row.get("FG_PCT") else None,
                "threes_made": int(row.get("FG3M", 0)) if row.get("FG3M") else None,
                "threes_attempted": int(row.get("FG3A", 0)) if row.get("FG3A") else None,
                "threes_pct": float(row.get("FG3_PCT", 0)) if row.get("FG3_PCT") else None,
            })

        return games

    except Exception as e:
        logger.error(f"Error fetching game log for player {player_id}: {e}")
        return []


async def fetch_player_season_stats(
    player_id: int,
    season: str = DEFAULT_SEASON
) -> Optional[Dict]:
    """
    Fetch season average stats for a player from NBA API.

    Args:
        player_id: NBA API player ID
        season: NBA season (e.g., "2024-25")

    Returns:
        Dictionary with season stats
    """
    try:
        from nba_api.stats.endpoints import playercareerstats

        await asyncio.sleep(REQUEST_DELAY)

        career = playercareerstats.PlayerCareerStats(player_id=player_id)
        dfs = career.get_data_frames()

        if not dfs:
            return None

        # Season totals are in the first dataframe
        season_totals = dfs[0] if len(dfs) > 0 else None

        if season_totals is None or season_totals.empty:
            return None

        # Find the requested season
        season_id = f"2{season.replace('-', '')}"  # "2024-25" -> "2202425"
        season_row = season_totals[season_totals["SEASON_ID"] == season_id]

        if season_row.empty:
            # Try alternate format
            season_id_alt = season.replace("-", "")
            season_row = season_totals[season_totals["SEASON_ID"].astype(str).str.contains(season)]

        if season_row.empty:
            return None

        row = season_row.iloc[0]

        return {
            "games_played": int(row.get("GP", 0)) if row.get("GP") else None,
            "games_started": int(row.get("GS", 0)) if row.get("GS") else None,
            "minutes": float(row.get("MIN", 0)) if row.get("MIN") else None,
            "points": float(row.get("PTS", 0)) if row.get("PTS") else None,
            "rebounds": float(row.get("REB", 0)) if row.get("REB") else None,
            "assists": float(row.get("AST", 0)) if row.get("AST") else None,
            "steals": float(row.get("STL", 0)) if row.get("STL") else None,
            "blocks": float(row.get("BLK", 0)) if row.get("BLK") else None,
            "threes": float(row.get("FG3M", 0)) if row.get("FG3M") else None,
            "fg_pct": float(row.get("FG_PCT", 0)) if row.get("FG_PCT") else None,
        }

    except Exception as e:
        logger.error(f"Error fetching season stats for player {player_id}: {e}")
        return None


def calculate_per_36_stats(stats: Dict) -> Dict:
    """Calculate per-36 minute stats from season totals."""
    minutes = stats.get("minutes", 0) or 0

    if minutes and minutes > 0:
        return {
            "points_per_36": ((stats.get("points") or 0) / minutes) * 36,
            "rebounds_per_36": ((stats.get("rebounds") or 0) / minutes) * 36,
            "assists_per_36": ((stats.get("assists") or 0) / minutes) * 36,
            "threes_per_36": ((stats.get("threes") or 0) / minutes) * 36,
            "avg_minutes": minutes / max(stats.get("games_played") or 1, 1),
        }
    else:
        return {
            "points_per_36": 0.0,
            "rebounds_per_36": 0.0,
            "assists_per_36": 0.0,
            "threes_per_36": 0.0,
            "avg_minutes": 0.0,
        }


def save_game_stats(
    db,
    player: Player,
    games: List[Dict],
    season: str
) -> int:
    """Save game-by-game stats to database."""
    saved = 0

    for game_data in games:
        # Check if game stats already exist
        existing = db.query(PlayerStats).filter(
            PlayerStats.player_id == player.id,
            PlayerStats.game_id == game_data["game_id"]
        ).first()

        if existing:
            continue

        # Create new game stats
        stats = PlayerStats(
            id=str(uuid4()),
            player_id=player.id,
            game_id=game_data["game_id"],
            points=game_data["points"],
            rebounds=game_data["rebounds"],
            assists=game_data["assists"],
            threes=game_data["threes_made"],
            minutes=game_data["minutes"],
            created_at=datetime.now()
        )
        db.add(stats)
        saved += 1

    return saved


def save_season_stats(
    db,
    player: Player,
    stats: Dict,
    season: str
) -> bool:
    """Save season stats to database."""
    # Calculate per-36 stats
    per_36 = calculate_per_36_stats(stats)

    # Check if season stats exist
    existing = db.query(PlayerSeasonStats).filter(
        PlayerSeasonStats.player_id == player.id,
        PlayerSeasonStats.season == season
    ).first()

    if existing:
        # Update existing
        existing.points_per_36 = per_36["points_per_36"]
        existing.rebounds_per_36 = per_36["rebounds_per_36"]
        existing.assists_per_36 = per_36["assists_per_36"]
        existing.threes_per_36 = per_36["threes_per_36"]
        existing.avg_minutes = per_36["avg_minutes"]
        existing.games_count = stats.get("games_played", 0)
        existing.fetched_at = datetime.now()
        existing.updated_at = datetime.now()
    else:
        # Create new
        season_stats = PlayerSeasonStats(
            id=str(uuid4()),
            player_id=player.id,
            season=season,
            games_count=stats.get("games_played", 0),
            points_per_36=per_36["points_per_36"],
            rebounds_per_36=per_36["rebounds_per_36"],
            assists_per_36=per_36["assists_per_36"],
            threes_per_36=per_36["threes_per_36"],
            avg_minutes=per_36["avg_minutes"],
            fetched_at=datetime.now(),
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.add(season_stats)

    return True


async def populate_nba_stats(
    season: str = DEFAULT_SEASON,
    player_filter: Optional[int] = None,
    games_only: bool = False,
    season_only: bool = False,
    limit: Optional[int] = None
) -> Dict:
    """
    Main function to populate NBA player stats.

    Args:
        season: NBA season
        player_filter: Optional specific player ID
        games_only: Only fetch game-by-game stats
        season_only: Only fetch season stats
        limit: Limit number of players to process

    Returns:
        Summary dictionary
    """
    db = SessionLocal()

    try:
        # Get players to process
        query = db.query(Player).filter(
            Player.sport_id == "nba",
            Player.nba_api_id.isnot(None)
        )

        if player_filter:
            query = query.filter(Player.nba_api_id == player_filter)

        if limit:
            query = query.limit(limit)

        players = query.all()

        if not players:
            logger.error("No players found in database")
            return {
                "status": "error",
                "error": "No players found"
            }

        # Summary tracking
        summary = {
            "timestamp": datetime.now().isoformat(),
            "season": season,
            "players_processed": 0,
            "game_stats_saved": 0,
            "season_stats_saved": 0,
            "errors": [],
            "status": "success"
        }

        logger.info("=" * 60)
        logger.info("NBA Player Stats Population Started")
        logger.info("=" * 60)
        logger.info(f"Season: {season}")
        logger.info(f"Players to process: {len(players)}")
        logger.info(f"Game stats: {'No' if season_only else 'Yes'}")
        logger.info(f"Season stats: {'No' if games_only else 'Yes'}")

        start_time = datetime.now()

        for idx, player in enumerate(players, 1):
            player_id = player.nba_api_id

            logger.info(f"\n[{idx}/{len(players)}] Processing {player.name}...")

            # Fetch and save game stats
            if not season_only:
                games = await fetch_player_game_log(player_id, season)
                if games:
                    saved = save_game_stats(db, player, games, season)
                    summary["game_stats_saved"] += saved
                    logger.info(f"  Saved {saved} game stats")
                else:
                    logger.warning(f"  No game stats found")

            # Fetch and save season stats
            if not games_only:
                stats = await fetch_player_season_stats(player_id, season)
                if stats:
                    save_season_stats(db, player, stats, season)
                    summary["season_stats_saved"] += 1
                    pts = stats.get('points') or 0
                    reb = stats.get('rebounds') or 0
                    ast = stats.get('assists') or 0
                    logger.info(f"  Saved season stats: {pts:.1f} pts, {reb:.1f} reb, {ast:.1f} ast")
                else:
                    logger.warning(f"  No season stats found")

            summary["players_processed"] += 1

            # Commit every 10 players
            if idx % 10 == 0:
                db.commit()
                logger.info(f"  Committed at {idx} players")

        db.commit()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        summary["duration_seconds"] = duration

        # Print summary
        logger.info("\n" + "=" * 60)
        logger.info("Stats Population Summary")
        logger.info("=" * 60)
        logger.info(f"Players processed: {summary['players_processed']}")
        logger.info(f"Game stats saved: {summary['game_stats_saved']}")
        logger.info(f"Season stats saved: {summary['season_stats_saved']}")
        if summary["errors"]:
            logger.info(f"Errors: {len(summary['errors'])}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info("=" * 60)

        return summary

    except Exception as e:
        logger.error(f"Error during stats population: {e}", exc_info=True)
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
        description="Populate NBA player stats from NBA API"
    )
    parser.add_argument(
        "--season",
        type=str,
        default=DEFAULT_SEASON,
        help=f"NBA season (default: {DEFAULT_SEASON})"
    )
    parser.add_argument(
        "--player",
        type=int,
        help="Only fetch stats for specific player ID"
    )
    parser.add_argument(
        "--games-only",
        action="store_true",
        help="Only fetch game-by-game stats"
    )
    parser.add_argument(
        "--season-only",
        action="store_true",
        help="Only fetch season stats"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of players to process"
    )

    args = parser.parse_args()

    result = await populate_nba_stats(
        season=args.season,
        player_filter=args.player,
        games_only=args.games_only,
        season_only=args.season_only,
        limit=args.limit
    )

    if result.get("status") == "success":
        logger.info("\n✅ Script completed successfully")
        sys.exit(0)
    else:
        logger.error(f"\n❌ Script failed: {result.get('error')}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
