"""
Lineup tracking routes for NBA player prop predictions.

Provides access to projected starting lineups and minutes allocations
from multiple sources (Rotowire, ESPN, NBA.com).
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.models import ExpectedLineup, Player, Game
from app.core.database import get_db
from app.services.nba.lineup_service import LineupService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lineups", tags=["lineups"])


class LineupFetchResponse(BaseModel):
    """Response model for lineup fetch operations."""
    success: bool
    message: str
    source: str
    count: int = 0


def lineup_to_dict(lineup: ExpectedLineup) -> dict:
    """Convert ExpectedLineup model to dictionary."""
    return {
        "id": str(lineup.id),
        "game_id": str(lineup.game_id) if lineup.game_id else None,
        "team": lineup.team,
        "player": {
            "id": str(lineup.player.id),
            "external_id": lineup.player.external_id,
            "name": lineup.player.name,
            "position": lineup.player.position
        } if lineup.player else None,
        "starter_position": lineup.starter_position,
        "is_confirmed": lineup.is_confirmed,
        "minutes_projection": lineup.minutes_projection,
        "created_at": lineup.created_at.isoformat(),
        "updated_at": lineup.updated_at.isoformat()
    }


@router.get("/game/{game_id}")
async def get_game_lineups(
    game_id: str,
    db: Session = Depends(get_db)
):
    """
    Get projected lineups for a game grouped by team.

    Returns:
    - Two keys (away_team and home_team) with lists of players
    - Each player includes position, starter status, and minutes projection
    """
    # Verify game exists
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

    lineup_service = LineupService(db)
    lineups = lineup_service.get_game_lineups(game_id)

    return {
        "game": {
            "id": str(game.id),
            "external_id": game.external_id,
            "away_team": game.away_team,
            "home_team": game.home_team,
            "game_date": game.game_date.isoformat()
        },
        "lineups": lineups
    }


@router.get("/player/{player_id}")
async def get_player_lineups(
    player_id: str,
    limit: int = Query(10, ge=1, le=50, description="Max number of lineup entries"),
    db: Session = Depends(get_db)
):
    """
    Get lineup history for a specific player.

    Returns recent lineup projections and confirmed lineups.
    """
    # Look up player
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        # Try external_id lookup
        player = db.query(Player).filter(Player.external_id == player_id).first()

    if not player:
        raise HTTPException(status_code=404, detail=f"Player {player_id} not found")

    # Get lineup entries for player
    lineups = db.query(ExpectedLineup).filter(
        ExpectedLineup.player_id == player.id
    ).order_by(ExpectedLineup.created_at.desc()).limit(limit).all()

    return {
        "player": {
            "id": str(player.id),
            "external_id": player.external_id,
            "name": player.name,
            "team": player.team,
            "position": player.position
        },
        "lineup_count": len(lineups),
        "lineups": [lineup_to_dict(l) for l in lineups]
    }


@router.get("/player/{player_id}/minutes")
async def get_player_minutes_projection(
    player_id: str,
    game_id: Optional[str] = Query(None, description="Game-specific projection"),
    db: Session = Depends(get_db)
):
    """
    Get minutes projection for a player.

    If game_id is provided, returns game-specific projection.
    Otherwise, returns the most recent projection available.
    """
    # Look up player
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        # Try external_id lookup
        player = db.query(Player).filter(Player.external_id == player_id).first()

    if not player:
        raise HTTPException(status_code=404, detail=f"Player {player_id} not found")

    lineup_service = LineupService(db)
    minutes = lineup_service.get_player_minutes_projection(player_id, game_id)

    # If no specific projection, estimate based on team depth
    if minutes is None:
        minutes = lineup_service.estimate_minutes_from_lineups(
            player_id, player.team, game_id
        )

    return {
        "player": {
            "id": str(player.id),
            "name": player.name,
            "team": player.team
        },
        "game_id": game_id,
        "minutes_projection": minutes
    }


@router.post("/fetch")
async def fetch_lineups(
    source: str = Query("rotowire", description="Data source (rotowire, espn, nba)"),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    Trigger manual fetch of lineup data from external sources.

    Fetches from:
    - Rotowire (default)
    - ESPN
    - NBA.com

    Runs in background to avoid blocking the response.
    """
    async def fetch_task():
        """Background task to fetch lineups."""
        lineup_service = LineupService(db)

        try:
            # Fetch lineups
            lineups = await lineup_service.fetch_lineups_from_firecrawl(source)
            logger.info(f"Fetched {len(lineups)} lineup entries from {source}")

            # Ingest to database
            ingested = lineup_service.ingest_lineups(lineups)
            logger.info(f"Ingested {ingested} lineup entries to database")

        except Exception as e:
            logger.error(f"Error in lineup fetch background task: {e}")

    # Schedule background task
    if background_tasks:
        background_tasks.add_task(fetch_task)
    else:
        # Run synchronously if no background tasks
        import asyncio
        await fetch_task()

    return LineupFetchResponse(
        success=True,
        message=f"Lineup fetch from {source} started",
        source=source
    )


@router.get("/team/{team}")
async def get_team_lineups(
    team: str,
    limit: int = Query(5, ge=1, le=20, description="Max games to return"),
    db: Session = Depends(get_db)
):
    """
    Get recent lineup projections for a team.

    Returns the most recent lineup projections for all games
    involving the specified team.
    """
    # Get recent lineup entries for this team
    lineups = db.query(ExpectedLineup).filter(
        ExpectedLineup.team == team.upper()
    ).order_by(ExpectedLineup.created_at.desc()).limit(limit * 15).all()

    # Group by game
    games_dict: dict = {}
    for lineup in lineups:
        if lineup.game_id not in games_dict:
            games_dict[lineup.game_id] = {
                "game_id": str(lineup.game_id) if lineup.game_id else None,
                "team": team,
                "players": []
            }
        games_dict[lineup.game_id]["players"].append(lineup_to_dict(lineup))

    # Convert to list
    result = list(games_dict.values())[:limit]

    return {
        "team": team.upper(),
        "lineup_count": len(result),
        "lineups": result
    }


@router.get("/stats/summary")
async def get_lineup_stats(
    db: Session = Depends(get_db)
):
    """
    Get lineup statistics summary.

    Returns counts of projected starters, bench players,
    and confirmation status.
    """
    # Get all lineup entries
    lineups = db.query(ExpectedLineup).all()

    # Count starters vs bench
    starters = sum(1 for l in lineups if l.starter_position is not None)
    bench = len(lineups) - starters

    # Count confirmed vs projected
    confirmed = sum(1 for l in lineups if l.is_confirmed)
    projected = len(lineups) - confirmed

    # Average minutes by position
    position_minutes: dict = {}
    for lineup in lineups:
        pos = lineup.starter_position or "BENCH"
        if pos not in position_minutes:
            position_minutes[pos] = []
        if lineup.minutes_projection:
            position_minutes[pos].append(lineup.minutes_projection)

    avg_minutes = {
        pos: round(sum(mins) / len(mins), 1) if mins else 0
        for pos, mins in position_minutes.items()
    }

    return {
        "total_lineup_entries": len(lineups),
        "starters": starters,
        "bench_players": bench,
        "confirmed": confirmed,
        "projected": projected,
        "average_minutes_by_position": avg_minutes
    }
