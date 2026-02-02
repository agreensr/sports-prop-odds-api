"""
NFL prediction routes.

Provides access to AI-generated NFL player prop predictions with odds pricing
from bookmakers.
"""
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_
from slowapi import Limiter

from app.models.nfl.models import Player, Game, Prediction, Base
from app.core.database import get_db
from app.services.nfl.nfl_service import NFLService, NFL_API_AVAILABLE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nfl", tags=["nfl"])

# Initialize NFL service
nfl_service = NFLService()

# Rate limiter - will be accessed via request.state
def get_limiter(request: Request) -> Limiter:
    """Get the rate limiter from app state."""
    return request.app.state.limiter


def prediction_to_dict(pred: Prediction) -> dict:
    """Convert Prediction model to dictionary with odds pricing."""
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
            "date": pred.game.game_date.isoformat(),
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
        "over_price": pred.over_price,
        "under_price": pred.under_price,
        "implied_probability": pred.implied_probability
    }


@router.get("/health")
async def nfl_health():
    """NFL service health check."""
    cache_stats = await nfl_service.get_cache_stats()
    return {
        "status": "healthy" if NFL_API_AVAILABLE else "degraded",
        "service": "nfl",
        "cache": cache_stats
    }


@router.get("/players")
async def get_nfl_players(
    name: Optional[str] = None,
    season: int = Query(default=2024, description="NFL season"),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get NFL players with optional name search.

    - **name**: Filter by player name (partial match, case-insensitive)
    - **season**: NFL season year (default: 2024)
    - **limit**: Maximum number of results (default: 50)
    """
    try:
        if name:
            # Search by name using NFL service
            players = await nfl_service.search_players(name, season, limit)
            return {"players": players, "count": len(players)}
        else:
            # Get all players for season from database
            query = db.query(Player).filter(Player.id_source == "nfl")
            players = query.limit(limit).all()
            return {
                "players": [
                    {
                        "id": str(p.id),
                        "external_id": p.external_id,
                        "name": p.name,
                        "team": p.team,
                        "position": p.position
                    }
                    for p in players
                ],
                "count": len(players)
            }
    except Exception as e:
        logger.error(f"Error fetching NFL players: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predictions/player/{player_id}")
async def get_nfl_player_predictions(
    request: Request,
    player_id: str,
    min_confidence: float = Query(default=0.5, ge=0, le=1),
    db: Session = Depends(get_db)
):
    """
    Get NFL player predictions with rate limiting.

    Rate limit: 10 requests per minute.
    """
    # Apply rate limit for prediction endpoints
    limiter = get_limiter(request)
    limiter.check_request_limit(request, "10/minute")[0]  # Raises RateLimitExceeded if over limit
    """
    Get NFL predictions for a specific player.

    - **player_id**: Player UUID or external ID
    - **min_confidence**: Minimum confidence threshold (default: 0.5)
    """
    try:
        # Try to find player by UUID or external_id
        player = db.query(Player).filter(
            or_(
                Player.id == player_id,
                Player.external_id == player_id
            ),
            Player.id_source == "nfl"
        ).first()

        if not player:
            raise HTTPException(status_code=404, detail=f"Player {player_id} not found")

        # Get predictions for this player
        query = db.query(Prediction).filter(
            Prediction.player_id == player.id,
            Prediction.confidence >= min_confidence
        ).order_by(Prediction.confidence.desc())

        predictions = query.all()

        return {
            "player": {
                "id": str(player.id),
                "external_id": player.external_id,
                "name": player.name,
                "team": player.team
            },
            "predictions": [prediction_to_dict(p) for p in predictions],
            "count": len(predictions)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching NFL player predictions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predictions/top")
async def get_nfl_top_picks(
    min_confidence: float = Query(default=0.70, ge=0, le=1),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Get top NFL picks by confidence level.

    - **min_confidence**: Minimum confidence threshold (default: 0.70)
    - **limit**: Maximum number of predictions (default: 10)
    """
    try:
        # Get predictions for NFL players only
        query = db.query(Prediction).join(Player).filter(
            Player.id_source == "nfl",
            Prediction.confidence >= min_confidence
        ).order_by(Prediction.confidence.desc())

        predictions = query.limit(limit).all()

        return {
            "predictions": [prediction_to_dict(p) for p in predictions],
            "count": len(predictions),
            "min_confidence": min_confidence
        }
    except Exception as e:
        logger.error(f"Error fetching NFL top picks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/data/fetch/players")
async def fetch_nfl_players(
    season: int = Query(default=2024),
    db: Session = Depends(get_db)
):
    """
    Fetch NFL players from NFL.com and update database.

    - **season**: NFL season year (default: 2024)
    """
    try:
        players = await nfl_service.get_all_players(season)

        added = 0
        updated = 0

        for player_data in players:
            # Check if player exists
            existing = db.query(Player).filter(
                Player.external_id == player_data['player_id'],
                Player.id_source == "nfl"
            ).first()

            if existing:
                # Update existing player
                existing.name = player_data['player_name']
                existing.team = player_data['team']
                existing.position = player_data.get('position')
                existing.updated_at = datetime.utcnow()
                updated += 1
            else:
                # Create new player
                now = datetime.utcnow()
                new_player = Player(
                    id=str(uuid.uuid4()),
                    external_id=player_data['player_id'],
                    name=player_data['player_name'],
                    team=player_data['team'],
                    position=player_data.get('position'),
                    id_source="nfl",
                    active=True,
                    created_at=now,
                    updated_at=now
                )
                db.add(new_player)
                added += 1

        db.commit()

        return {
            "status": "success",
            "players_fetched": len(players),
            "players_added": added,
            "players_updated": updated
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error fetching NFL players: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/status")
async def get_nfl_data_status(db: Session = Depends(get_db)):
    """Get NFL database status."""
    try:
        player_count = db.query(Player).filter(Player.id_source == "nfl").count()
        game_count = db.query(Game).filter(Game.id_source == "nfl").count()
        prediction_count = db.query(Prediction).join(Player).filter(Player.id_source == "nfl").count()

        return {
            "sport": "nfl",
            "database": {
                "players": player_count,
                "games": game_count,
                "predictions": prediction_count
            },
            "status": "ready" if player_count > 0 else "no_data"
        }
    except Exception as e:
        logger.error(f"Error getting NFL data status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
