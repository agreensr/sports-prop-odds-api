"""
Player search and lookup routes.

This module has been refactored to use the Repository Pattern for data access.
All database queries are now abstracted through the PlayerRepository.

Benefits:
1. Separation of concerns - data access logic is in the repository
2. Easier testing - can mock the repository
3. Consistent interface for data operations
4. Single place to maintain query logic
"""
import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.models import Player, Prediction
from app.core.database import get_db
from app.repositories.nba.player_repository import PlayerRepository
from app.repositories.nba.prediction_repository import PredictionRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/players", tags=["players"])


def player_to_dict(player: Player, include_stats: bool = False) -> dict:
    """Convert Player model to dictionary."""
    data = {
        "id": str(player.id),
        "external_id": player.external_id,
        "name": player.name,
        "team": player.team,
        "position": player.position,
        "created_at": player.created_at.isoformat()
    }

    if include_stats:
        prediction_count = len(player.predictions) if player.predictions else 0
        data["stats"] = {
            "predictions_count": prediction_count
        }

    return data


@router.get("/search")
async def search_players(
    name: str = Query(..., min_length=2, description="Player name to search for"),
    team: Optional[str] = Query(None, description="Filter by team abbreviation"),
    position: Optional[str] = Query(None, description="Filter by position"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Search for players by name.

    The search is case-insensitive and matches partial names.
    Example: /api/players/search?name=lebron
    Example: /api/players/search?name=curry&team=GSW
    Example: /api/players/search?name=james&position=SF
    """
    player_repo = PlayerRepository(db)

    # First try to find by external ID if it matches exactly
    player_by_id = player_repo.find_by_external_id(name)
    players = []

    if player_by_id:
        # Apply team/position filters to direct ID match
        if team and player_by_id.team != team.upper():
            players = []
        elif position and player_by_id.position != position.upper():
            players = []
        else:
            players = [player_by_id]

    # If no ID match or filters didn't match, do name search
    if not players:
        players = player_repo.search_by_name(name, limit=limit)

        # Apply team filter
        if team:
            players = [p for p in players if p.team == team.upper()]

        # Apply position filter
        if position:
            players = [p for p in players if p.position == position.upper()]

    if not players:
        return {
            "players": [],
            "count": 0,
            "message": f"No players found matching '{name}'"
        }

    return {
        "players": [player_to_dict(p, include_stats=True) for p in players],
        "count": len(players)
    }


@router.get("/{player_id}")
async def get_player(player_id: str, db: Session = Depends(get_db)):
    """
    Get a single player by database UUID.
    Use /api/players/nba/{nba_id} for NBA.com ID lookup.
    """
    try:
        player_uuid = UUID(player_id)
        player_repo = PlayerRepository(db)
        player = player_repo.find_by_id(str(player_uuid))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid player ID format. Use UUID or /api/players/nba/{{nba_id}}"
        )

    if not player:
        raise HTTPException(status_code=404, detail=f"Player {player_id} not found")

    return player_to_dict(player, include_stats=True)


@router.get("/nba/{nba_id}")
async def get_player_by_nba_id(nba_id: str, db: Session = Depends(get_db)):
    """
    Get a player by NBA.com external_id.

    This endpoint allows looking up players using their NBA.com player ID.
    Example: /api/players/nba/2544 (LeBron James)

    Returns the player's database UUID, which can be used with other endpoints.
    """
    player_repo = PlayerRepository(db)
    player = player_repo.find_by_external_id(nba_id)

    if not player:
        raise HTTPException(
            status_code=404,
            detail=f"Player with NBA ID {nba_id} not found in database"
        )

    return player_to_dict(player, include_stats=True)


@router.get("/nba/{nba_id}/predictions")
async def get_player_predictions_by_nba_id(
    nba_id: str,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get predictions for a player by NBA.com ID.

    This is a convenience endpoint that combines player lookup and predictions.
    Example: /api/players/nba/2544/predictions?limit=5
    """
    player_repo = PlayerRepository(db)
    prediction_repo = PredictionRepository(db)

    player = player_repo.find_by_external_id(nba_id)

    if not player:
        raise HTTPException(
            status_code=404,
            detail=f"Player with NBA ID {nba_id} not found"
        )

    predictions = prediction_repo.find_by_player(player.id, limit=limit)

    from app.api.routes.nba.predictions import prediction_to_dict

    return {
        "player": player_to_dict(player),
        "predictions": [prediction_to_dict(p) for p in predictions],
        "count": len(predictions)
    }


@router.get("/")
async def list_players(
    team: Optional[str] = Query(None, description="Filter by team abbreviation"),
    position: Optional[str] = Query(None, description="Filter by position"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    List all players with optional filtering.

    Example: /api/players?team=LAL&limit=20
    Example: /api/players?position=PG
    """
    player_repo = PlayerRepository(db)

    # Apply filters
    if team and position:
        players = player_repo.find_by_team_and_position(
            team.upper(),
            position.upper(),
            active_only=True
        )
    elif team:
        players = player_repo.find_by_team(team.upper(), active_only=True)
    elif position:
        players = player_repo.find_by_position(position.upper(), active_only=True)
    else:
        players = player_repo.find_active()

    # Get total before pagination
    total = len(players)

    # Apply pagination
    players = players[offset:offset + limit]

    return {
        "players": [player_to_dict(p, include_stats=True) for p in players],
        "count": len(players),
        "total": total,
        "offset": offset,
        "limit": limit
    }


@router.get("/teams/list")
async def list_teams(db: Session = Depends(get_db)):
    """
    Get list of all teams in the database with player counts.

    Now using the repository's get_team_counts() method.
    """
    player_repo = PlayerRepository(db)
    team_counts = player_repo.get_team_counts(active_only=True)

    return {
        "teams": [{"team": t, "players_count": count} for t, count in team_counts]
    }
