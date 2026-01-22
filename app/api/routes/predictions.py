"""
Prediction routes with NBA.com external_id lookup support.

Provides access to AI-generated player prop predictions with odds pricing
from bookmakers.
"""
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session

from app.models.models import Player, Game, Prediction, Base
from app.core.database import get_db
from app.services.prediction_service import PredictionService
from app.utils.timezone import format_game_time_central, utc_to_central

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


def prediction_to_dict(pred: Prediction) -> dict:
    """Convert Prediction model to dictionary with odds pricing and Central time."""
    # Convert game UTC time to Central Time for display
    central_time = utc_to_central(pred.game.game_date)

    return {
        "id": str(pred.id),
        "player": {
            "id": str(pred.player.id),
            "external_id": pred.player.external_id,
            "name": pred.player.name,
            "team": pred.player.team,
            "position": pred.player.position
        },
        "game": {
            "id": str(pred.game.id),
            "external_id": pred.game.external_id,
            "date_utc": pred.game.game_date.isoformat(),
            "date_central": central_time.isoformat(),
            "date_display": format_game_time_central(pred.game.game_date),
            "away_team": pred.game.away_team,
            "home_team": pred.game.home_team,
            "status": pred.game.status
        },
        "stat_type": pred.stat_type,
        "predicted_value": pred.predicted_value,
        "bookmaker_line": pred.bookmaker_line,
        "bookmaker_name": pred.bookmaker_name,
        "recommendation": pred.recommendation,
        "confidence": pred.confidence,
        "model_version": pred.model_version,
        # Odds pricing fields
        "over_price": pred.over_price,
        "under_price": pred.under_price,
        "odds_fetched_at": pred.odds_fetched_at.isoformat() if pred.odds_fetched_at else None,
        "odds_last_updated": pred.odds_last_updated.isoformat() if pred.odds_last_updated else None,
        "created_at": pred.created_at.isoformat()
    }


@router.get("/player/{player_id}")
async def get_player_predictions(
    player_id: str,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get predictions for a player by database UUID.

    Note: This is the original endpoint that requires the internal database UUID.
    For NBA.com ID lookup, use /api/predictions/player/nba/{nba_id}
    """
    # Try exact match first (database stores IDs as VARCHAR, may have mixed formats)
    player = db.query(Player).filter(Player.id == player_id).first()

    # If not found and input looks like UUID, try the stringified version
    if not player:
        try:
            player_uuid = UUID(player_id)
            player = db.query(Player).filter(Player.id == str(player_uuid)).first()
        except ValueError:
            pass  # Not a UUID format, skip to external_id lookup

    # If still not found, try external_id as fallback
    if not player:
        logger.info(f"Player ID {player_id} not found, trying external_id lookup")
        player = db.query(Player).filter(Player.external_id == player_id).first()

    if not player:
        raise HTTPException(
            status_code=404,
            detail=f"Player {player_id} not found. Use /api/predictions/player/nba/{{nba_id}} for NBA.com ID lookup"
        )

    predictions = (
        db.query(Prediction)
        .filter(Prediction.player_id == player.id)
        .order_by(Prediction.created_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "player": {
            "id": str(player.id),
            "external_id": player.external_id,
            "name": player.name,
            "team": player.team,
            "position": player.position
        },
        "predictions": [prediction_to_dict(p) for p in predictions],
        "count": len(predictions)
    }


@router.get("/player/nba/{nba_id}")
async def get_player_predictions_by_nba_id(
    nba_id: str,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get predictions for a player by NBA.com external_id.

    Users can query using NBA.com player IDs (e.g., "2544" for LeBron James).

    Example: /api/predictions/player/nba/2544
    """
    player = db.query(Player).filter(Player.external_id == nba_id).first()

    if not player:
        # Provide helpful error message
        raise HTTPException(
            status_code=404,
            detail=f"Player with NBA ID {nba_id} not found in database. "
                   f"The player may not have been imported from NBA.com yet. "
                   f"Use /api/players/search to find players."
        )

    predictions = (
        db.query(Prediction)
        .filter(Prediction.player_id == player.id)
        .order_by(Prediction.created_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "player": {
            "id": str(player.id),
            "external_id": player.external_id,
            "name": player.name,
            "team": player.team,
            "position": player.position
        },
        "predictions": [prediction_to_dict(p) for p in predictions],
        "count": len(predictions)
    }


@router.get("/game/{game_id}")
async def get_game_predictions(
    game_id: str,
    db: Session = Depends(get_db)
):
    """
    Get all predictions for a specific game by database UUID.
    """
    # Try exact match first (database stores IDs as VARCHAR, may have mixed formats)
    game = db.query(Game).filter(Game.id == game_id).first()

    # If not found and input looks like UUID, try the stringified version
    if not game:
        try:
            game_uuid = UUID(game_id)
            game = db.query(Game).filter(Game.id == str(game_uuid)).first()
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid game ID format: {game_id}")

    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

    predictions = (
        db.query(Prediction)
        .filter(Prediction.game_id == game.id)
        .order_by(Prediction.confidence.desc())
        .all()
    )

    return {
        "game": {
            "id": str(game.id),
            "external_id": game.external_id,
            "date": game.game_date.isoformat(),
            "away_team": game.away_team,
            "home_team": game.home_team,
            "status": game.status
        },
        "predictions": [prediction_to_dict(p) for p in predictions],
        "count": len(predictions)
    }


@router.get("/game/nba/{nba_game_id}")
async def get_game_predictions_by_nba_id(
    nba_game_id: str,
    db: Session = Depends(get_db)
):
    """
    Get all predictions for a game by NBA.com game ID.

    Example: /api/predictions/game/nba/0022400001
    """
    game = db.query(Game).filter(Game.external_id == nba_game_id).first()

    if not game:
        raise HTTPException(
            status_code=404,
            detail=f"Game with NBA ID {nba_game_id} not found in database"
        )

    predictions = (
        db.query(Prediction)
        .filter(Prediction.game_id == game.id)
        .order_by(Prediction.confidence.desc())
        .all()
    )

    return {
        "game": {
            "id": str(game.id),
            "external_id": game.external_id,
            "date": game.game_date.isoformat(),
            "away_team": game.away_team,
            "home_team": game.home_team,
            "status": game.status
        },
        "predictions": [prediction_to_dict(p) for p in predictions],
        "count": len(predictions)
    }


@router.get("/top")
async def get_top_predictions(
    min_confidence: float = Query(0.6, ge=0.0, le=1.0),
    stat_type: Optional[str] = Query(None),
    days_ahead: int = Query(7, ge=1, le=30),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get high-confidence predictions for upcoming games.

    Args:
        min_confidence: Minimum confidence threshold (0.0 to 1.0)
        stat_type: Filter by stat type (points, rebounds, assists, etc.)
        days_ahead: How many days ahead to look
        limit: Maximum number of predictions to return
    """
    start_date = date.today()
    end_date = start_date + timedelta(days=days_ahead)

    query = (
        db.query(Prediction)
        .join(Game)
        .filter(
            Prediction.confidence >= min_confidence,
            Game.game_date >= start_date,
            Game.game_date <= end_date
        )
        .order_by(Prediction.confidence.desc())
    )

    if stat_type:
        query = query.filter(Prediction.stat_type == stat_type.lower())

    predictions = query.limit(limit).all()

    return {
        "filters": {
            "min_confidence": min_confidence,
            "stat_type": stat_type,
            "date_range": f"{start_date} to {end_date}"
        },
        "predictions": [prediction_to_dict(p) for p in predictions],
        "count": len(predictions)
    }


@router.get("/recent")
async def get_recent_predictions(
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Get recently generated predictions.

    Args:
        hours: How many hours back to look
        limit: Maximum number of predictions to return
    """
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)

    predictions = (
        db.query(Prediction)
        .filter(Prediction.created_at >= cutoff_time)
        .order_by(Prediction.created_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "since": cutoff_time.isoformat(),
        "predictions": [prediction_to_dict(p) for p in predictions],
        "count": len(predictions)
    }


@router.get("/stat-types")
async def get_stat_types(db: Session = Depends(get_db)):
    """
    Get available stat types with prediction counts.
    """
    from sqlalchemy import func

    stat_types = (
        db.query(Prediction.stat_type, func.count(Prediction.id).label("count"))
        .group_by(Prediction.stat_type)
        .order_by(func.count(Prediction.id).desc())
        .all()
    )

    return {
        "stat_types": [
            {"type": st[0], "predictions_count": st[1]}
            for st in stat_types
        ]
    }


@router.post("/generate/upcoming")
async def generate_predictions_for_upcoming_games(
    days_ahead: int = Query(7, ge=1, le=30, description="Number of days ahead to generate predictions for"),
    stat_types: str = Query("points,rebounds,assists,threes", description="Comma-separated list of stat types"),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    Generate predictions for all upcoming games.

    Uses statistical heuristics based on player position and league averages
    to generate predicted values for player props.

    Args:
        days_ahead: How many days ahead to generate predictions for
        stat_types: Comma-separated stat types (points, rebounds, assists, threes)

    Returns:
        Summary of predictions generated
    """
    # Parse stat types
    stat_type_list = [s.strip() for s in stat_types.split(",")]

    # Get upcoming games
    start_date = date.today()
    end_date = start_date + timedelta(days=days_ahead)

    upcoming_games = (
        db.query(Game)
        .filter(
            Game.game_date >= start_date,
            Game.game_date <= end_date,
            Game.status == "scheduled"
        )
        .all()
    )

    if not upcoming_games:
        return {
            "message": "No upcoming games found",
            "predictions_generated": 0,
            "games_processed": 0
        }

    prediction_service = PredictionService(db)
    total_predictions = 0
    games_with_predictions = 0
    errors = []

    for game in upcoming_games:
        try:
            logger.info(f"Generating predictions for game {game.external_id}: {game.away_team} @ {game.home_team}")

            predictions = prediction_service.generate_predictions_for_game(
                game_id=str(game.id),
                stat_types=stat_type_list
            )

            if predictions:
                games_with_predictions += 1
                total_predictions += len(predictions)

        except Exception as e:
            logger.error(f"Error generating predictions for game {game.external_id}: {e}")
            errors.append({
                "game_id": game.external_id,
                "error": str(e)
            })

    return {
        "message": f"Generated predictions for {games_with_predictions} upcoming games",
        "predictions_generated": total_predictions,
        "games_processed": len(upcoming_games),
        "games_with_predictions": games_with_predictions,
        "stat_types": stat_type_list,
        "errors": errors
    }
