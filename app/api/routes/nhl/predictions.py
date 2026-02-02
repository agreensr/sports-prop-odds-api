"""
NHL Prediction routes with enhanced model support.

Provides access to AI-generated NHL player prop predictions with odds pricing
from bookmakers.
"""
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request
from sqlalchemy.orm import Session

from app.models.nhl.models import Player, Game, Prediction
from app.core.database import get_db
from app.core.config import settings
from app.services.nhl.prediction_service import PredictionService
from app.services.core.odds_api_service import get_odds_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["nhl_predictions"])


def nhl_prediction_to_dict(pred: Prediction) -> dict:
    """Convert NHL Prediction model to dictionary."""
    return {
        "id": str(pred.id),
        "player": {
            "id": str(pred.player.id),
            "nhl_id": pred.player.nhl_id,
            "name": pred.player.name,
            "team": pred.player.team,
            "position": pred.player.position
        },
        "game": {
            "id": str(pred.game.id),
            "nhl_id": pred.game.nhl_id,
            "date": pred.game.game_date.isoformat(),
            "away_team": pred.game.away_team,
            "home_team": pred.game.home_team,
            "status": pred.game.status
        },
        "stat_type": pred.stat_type,
        "predicted_value": pred.predicted_value,
        "bookmaker_line": pred.bookmaker_line,
        "recommendation": pred.recommendation,
        "confidence": pred.confidence,
        "model_version": pred.model_version,
        "created_at": pred.created_at.isoformat()
    }


@router.get("/player/{player_id}")
async def get_nhl_player_predictions(
    player_id: str,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get NHL predictions for a player by database UUID.

    Args:
        player_id: Player database UUID
        limit: Maximum number of predictions to return

    Returns:
        Player info with list of predictions
    """
    player = db.query(Player).filter(Player.id == player_id).first()

    if not player:
        try:
            player_uuid = UUID(player_id)
            player = db.query(Player).filter(Player.id == str(player_uuid)).first()
        except ValueError:
            pass

    if not player:
        raise HTTPException(status_code=404, detail=f"Player {player_id} not found")

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
            "name": player.name,
            "team": player.team,
            "position": player.position
        },
        "predictions": [nhl_prediction_to_dict(p) for p in predictions],
        "count": len(predictions)
    }


@router.get("/game/{game_id}")
async def get_nhl_game_predictions(
    game_id: str,
    db: Session = Depends(get_db)
):
    """
    Get all NHL predictions for a specific game by database UUID.

    Args:
        game_id: Game database UUID

    Returns:
        Game info with list of predictions
    """
    game = db.query(Game).filter(Game.id == game_id).first()

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
            "date": game.game_date.isoformat(),
            "away_team": game.away_team,
            "home_team": game.home_team,
            "status": game.status
        },
        "predictions": [nhl_prediction_to_dict(p) for p in predictions],
        "count": len(predictions)
    }


@router.get("/teams/{away_team}/{home_team}")
async def get_nhl_predictions_by_team_names(
    away_team: str,
    home_team: str,
    db: Session = Depends(get_db)
):
    """
    Get NHL predictions for a game by team abbreviations (case-insensitive).

    Args:
        away_team: Away team abbreviation
        home_team: Home team abbreviation

    Returns:
        Game info with list of predictions
    """
    from sqlalchemy import or_

    away_team = away_team.upper()
    home_team = home_team.upper()

    game = (
        db.query(Game)
        .filter(
            or_(
                (Game.away_team == away_team) & (Game.home_team == home_team),
                (Game.away_team == home_team) & (Game.home_team == away_team)
            ),
            Game.game_date >= datetime.now() - timedelta(days=1)
        )
        .order_by(Game.game_date.desc())
        .first()
    )

    if not game:
        raise HTTPException(
            status_code=404,
            detail=f"Game between {away_team} and {home_team} not found"
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
            "date": game.game_date.isoformat(),
            "away_team": game.away_team,
            "home_team": game.home_team,
            "status": game.status
        },
        "predictions": [nhl_prediction_to_dict(p) for p in predictions],
        "count": len(predictions)
    }


@router.get("/top")
async def get_top_nhl_predictions(
    min_confidence: float = Query(0.6, ge=0.0, le=1.0),
    stat_type: Optional[str] = Query(None),
    days_ahead: int = Query(1, ge=0, le=30),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get high-confidence NHL predictions for upcoming games.

    Args:
        min_confidence: Minimum confidence threshold (0.0 to 1.0)
        stat_type: Filter by stat type (goals, assists, points, shots)
        days_ahead: How many days ahead to look
        limit: Maximum number of predictions to return

    Returns:
        Filtered list of predictions
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
        "predictions": [nhl_prediction_to_dict(p) for p in predictions],
        "count": len(predictions)
    }


@router.get("/stat-types")
async def get_nhl_stat_types(db: Session = Depends(get_db)):
    """
    Get available NHL stat types with prediction counts.

    Returns:
        List of stat types with prediction counts
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


# ============================================================================
# ENHANCED NHL PREDICTIONS WITH REAL ODDS API INTEGRATION
# ============================================================================

@router.get("/enhanced/game/{game_id}")
async def get_enhanced_nhl_predictions(
    game_id: str,
    stat_types: str = Query("goals,assists,points,shots", description="Comma-separated stat types"),
    bookmaker: str = Query("draftkings", description="Preferred bookmaker"),
    db: Session = Depends(get_db)
):
    """
    Get enhanced NHL predictions with REAL odds from Odds API.

    This endpoint uses the Enhanced NHL Prediction Service which:
    1. Fetches real-time bookmaker lines from The Odds API
    2. Compares AI projections to actual lines
    3. Provides OVER/UNDER/PASS recommendations based on edge

    Args:
        game_id: Game database UUID
        stat_types: Comma-separated stat types (goals, assists, points, shots)
        bookmaker: Preferred bookmaker for line data

    Returns:
        List of enhanced predictions with real line data
    """
    from app.services.nhl.enhanced_prediction_service import EnhancedNHLPredictionService

    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        try:
            game_uuid = UUID(game_id)
            game = db.query(Game).filter(Game.id == str(game_uuid)).first()
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid game ID format: {game_id}")

    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

    stat_type_list = [s.strip() for s in stat_types.split(",") if s.strip()]

    # Initialize odds service if API key is available
    odds_service = None
    if settings.THE_ODDS_API_KEY:
        try:
            odds_service = get_odds_service(settings.THE_ODDS_API_KEY, sport="nhl")
            logger.info("Odds API service initialized for NHL enhanced predictions")
        except Exception as e:
            logger.warning(f"Failed to initialize odds service: {e}")

    # Initialize enhanced prediction service
    prediction_service = EnhancedNHLPredictionService(
        db=db,
        odds_api_service=odds_service
    )

    # Generate predictions
    predictions = prediction_service.generate_prop_predictions(
        game_id=game_id,
        stat_types=stat_type_list,
        bookmaker=bookmaker
    )

    return {
        "game": {
            "id": str(game.id),
            "date": game.game_date.isoformat(),
            "away_team": game.away_team,
            "home_team": game.home_team,
            "status": game.status
        },
        "odds_source": "live" if odds_service else "estimated",
        "predictions": predictions,
        "count": len(predictions),
        "stat_types": stat_type_list
    }


@router.post("/enhanced/generate")
async def generate_enhanced_nhl_predictions(
    days_ahead: int = Query(7, ge=1, le=30, description="Number of days ahead"),
    stat_types: str = Query("goals,assists,points,shots", description="Comma-separated stat types"),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    Generate enhanced NHL predictions with REAL odds for upcoming games.

    This endpoint:
    1. Finds all upcoming NHL games
    2. Fetches real-time odds from The Odds API
    3. Generates AI projections
    4. Compares projections to lines to find edges

    Args:
        days_ahead: How many days ahead to generate predictions for
        stat_types: Comma-separated stat types

    Returns:
        Summary of enhanced predictions generated
    """
    from app.services.nhl.enhanced_prediction_service import EnhancedNHLPredictionService

    stat_type_list = [s.strip() for s in stat_types.split(",") if s.strip()]

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
            "message": "No upcoming NHL games found",
            "predictions_generated": 0,
            "games_processed": 0,
            "odds_source": "none"
        }

    # Initialize odds service
    odds_service = None
    odds_source = "estimated"

    if settings.THE_ODDS_API_KEY:
        try:
            odds_service = get_odds_service(settings.THE_ODDS_API_KEY, sport="nhl")
            odds_source = "live"
            logger.info("Odds API service initialized for NHL predictions")
        except Exception as e:
            logger.warning(f"Failed to initialize odds service: {e}")

    # Initialize enhanced prediction service
    prediction_service = EnhancedNHLPredictionService(
        db=db,
        odds_api_service=odds_service
    )

    # Generate predictions
    all_predictions = []
    games_with_predictions = 0
    total_predictions = 0
    errors = []

    for game in upcoming_games:
        try:
            logger.info(
                f"Generating enhanced NHL predictions for game {game.id}: "
                f"{game.away_team} @ {game.home_team}"
            )

            predictions = prediction_service.generate_prop_predictions(
                game_id=str(game.id),
                stat_types=stat_type_list
            )

            if predictions:
                games_with_predictions += 1
                total_predictions += len(predictions)
                all_predictions.extend(predictions)

        except Exception as e:
            logger.error(
                f"Error generating enhanced NHL predictions for game {game.id}: {e}"
            )
            errors.append({
                "game_id": str(game.id),
                "error": str(e)
            })

    return {
        "message": f"Generated enhanced NHL predictions for {games_with_predictions} upcoming games",
        "predictions_generated": total_predictions,
        "games_processed": len(upcoming_games),
        "games_with_predictions": games_with_predictions,
        "stat_types": stat_type_list,
        "odds_source": odds_source,
        "errors": errors
    }
