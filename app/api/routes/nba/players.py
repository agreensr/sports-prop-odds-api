"""
Player search and lookup routes.
Allows searching players by name and looking up by NBA.com ID.
"""
import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from app.models.nba.models import Player, Prediction
from app.core.database import get_db

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
    query = db.query(Player)

    # Case-insensitive name search
    name_filter = f"%{name.lower()}%"
    query = query.filter(
        or_(
            func.lower(Player.name).ilike(name_filter),
            Player.external_id == name  # Also allow searching by NBA.com ID
        )
    )

    if team:
        query = query.filter(Player.team == team.upper())

    if position:
        query = query.filter(Player.position == position.upper())

    players = query.order_by(Player.name).limit(limit).all()

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
        player = db.query(Player).filter(Player.id == player_uuid).first()
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
    player = db.query(Player).filter(Player.external_id == nba_id).first()

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
    player = db.query(Player).filter(Player.external_id == nba_id).first()

    if not player:
        raise HTTPException(
            status_code=404,
            detail=f"Player with NBA ID {nba_id} not found"
        )

    predictions = (
        db.query(Prediction)
        .filter(Prediction.player_id == player.id)
        .order_by(Prediction.created_at.desc())
        .limit(limit)
        .all()
    )

    from app.api.routes.predictions import prediction_to_dict

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
    query = db.query(Player)

    if team:
        query = query.filter(Player.team == team.upper())

    if position:
        query = query.filter(Player.position == position.upper())

    total = query.count()
    players = query.order_by(Player.name).offset(offset).limit(limit).all()

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
    """
    from sqlalchemy import func

    teams = (
        db.query(Player.team, func.count(Player.id).label("count"))
        .filter(Player.team.isnot(None))
        .group_by(Player.team)
        .order_by(func.count(Player.id).desc())
        .all()
    )

    return {
        "teams": [{"team": t[0], "players_count": t[1]} for t in teams]
    }
