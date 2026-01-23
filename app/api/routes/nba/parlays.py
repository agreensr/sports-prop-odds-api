"""
Parlay routes for NBA player prop betting.

Provides endpoints for generating same-game and multi-game parlays
with correlation analysis and expected value calculations.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.nba.models import Parlay
from app.core.database import get_db
from app.services.core.parlay_service import ParlayService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/parlays", tags=["parlays"])


# Response models for API documentation
class ParlayGameInfo(BaseModel):
    """Game information for a parlay leg."""
    id: str
    matchup: str
    date_utc: str
    date_central: str
    date_display: str
    status: str


class ParlayLegResponse(BaseModel):
    """Individual leg in a parlay."""
    leg_order: int
    player: str
    team: str
    stat_type: str
    selection: str
    line: Optional[float]
    predicted_value: float
    odds: float  # Changed to float to support both American and decimal odds
    confidence: float
    correlation_with_parlay: Optional[float]
    game: Optional[ParlayGameInfo] = None


class ParlayResponse(BaseModel):
    """Generated parlay bet."""
    id: str
    parlay_type: str
    calculated_odds: int
    implied_probability: float
    expected_value: float
    expected_value_percent: float
    confidence_score: float
    total_legs: int
    correlation_score: Optional[float]
    created_at: str
    legs: Optional[List[ParlayLegResponse]] = None


class ParlayListResponse(BaseModel):
    """Response containing multiple parlays."""
    parlays: List[ParlayResponse]
    count: int


class GenerateParlaysResponse(BaseModel):
    """Response from parlay generation."""
    message: str
    parlays: List[dict]
    count: int


# ===== Generation Endpoints =====

@router.post("/generate/same-game/{game_id}", response_model=GenerateParlaysResponse)
async def generate_same_game_parlays(
    game_id: str,
    min_confidence: float = Query(0.60, ge=0.0, le=1.0, description="Minimum confidence for predictions"),
    max_legs: int = Query(3, ge=2, le=4, description="Maximum number of legs per parlay"),
    min_ev: float = Query(0.05, ge=-0.5, le=1.0, description="Minimum expected value (e.g., 0.05 = 5%)"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of parlays to return"),
    db: Session = Depends(get_db)
):
    """
    Generate same-game parlays with correlation analysis.

    Creates parlays combining:
    - Same-player correlated props (points+assists, points+threes)
    - Teammate correlated props (assists+points, rebounds+points)

    Correlation analysis boosts expected value calculations based on
    statistical relationships between stat types.

    Example: POST /api/parlays/generate/same-game/{game_id}?min_confidence=0.65&max_legs=3&min_ev=0.05
    """
    try:
        service = ParlayService(db)
        parlays = service.generate_same_game_parlays(
            game_id=game_id,
            min_confidence=min_confidence,
            max_legs=max_legs,
            min_ev=min_ev,
            limit=limit
        )

        return {
            "message": f"Generated {len(parlays)} same-game parlays",
            "parlays": parlays,
            "count": len(parlays)
        }
    except Exception as e:
        logger.error(f"Error generating same-game parlays: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate/multi-game", response_model=GenerateParlaysResponse)
async def generate_multi_game_parlays(
    days_ahead: int = Query(3, ge=1, le=7, description="Number of days ahead to look"),
    min_confidence: float = Query(0.60, ge=0.0, le=1.0, description="Minimum confidence for predictions"),
    max_legs: int = Query(3, ge=2, le=4, description="Maximum number of legs per parlay"),
    min_ev: float = Query(0.05, ge=-0.5, le=1.0, description="Minimum expected value"),
    games_per_parlay: int = Query(3, ge=2, le=5, description="Number of different games to combine"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of parlays to return"),
    db: Session = Depends(get_db)
):
    """
    Generate multi-game parlays across different teams/games.

    Combines top predictions from different games to create parlays.
    Uses conservative EV calculation (no correlation bonus) since
    games are independent events.

    Example: POST /api/parlays/generate/multi-game?days_ahead=3&min_confidence=0.60&min_ev=0.05
    """
    try:
        service = ParlayService(db)
        parlays = service.generate_multi_game_parlays(
            days_ahead=days_ahead,
            min_confidence=min_confidence,
            max_legs=max_legs,
            min_ev=min_ev,
            games_per_parlay=games_per_parlay,
            limit=limit
        )

        return {
            "message": f"Generated {len(parlays)} multi-game parlays",
            "parlays": parlays,
            "count": len(parlays)
        }
    except Exception as e:
        logger.error(f"Error generating multi-game parlays: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== Retrieval Endpoints =====

@router.get("/", response_model=ParlayListResponse)
async def get_parlays(
    parlay_type: Optional[str] = Query(None, description="Filter by parlay type: same_game or multi_game"),
    min_ev: Optional[float] = Query(None, ge=-0.5, le=1.0, description="Minimum expected value"),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0, description="Minimum confidence score"),
    game_id: Optional[str] = Query(None, description="Filter by specific game ID"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    db: Session = Depends(get_db)
):
    """
    Get parlays from database with optional filtering.

    Supports filtering by:
    - parlay_type: 'same_game' or 'multi_game'
    - min_ev: Minimum expected value
    - min_confidence: Minimum confidence score
    - game_id: Specific game ID

    Results are sorted by expected value (highest first).

    Example: GET /api/parlays/?parlay_type=same_game&min_ev=0.10&limit=20
    """
    try:
        service = ParlayService(db)
        parlays = service.get_parlays(
            parlay_type=parlay_type,
            min_ev=min_ev,
            min_confidence=min_confidence,
            game_id=game_id,
            limit=limit
        )

        return {
            "parlays": parlays,
            "count": len(parlays)
        }
    except Exception as e:
        logger.error(f"Error retrieving parlays: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/top-ev", response_model=ParlayListResponse)
async def get_top_ev_parlays(
    parlay_type: Optional[str] = Query(None, description="Filter by parlay type"),
    min_ev: float = Query(0.10, ge=0.0, le=1.0, description="Minimum expected value"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
    db: Session = Depends(get_db)
):
    """
    Get top expected value parlays.

    Returns the highest EV parlays, useful for identifying the best
    betting opportunities. Results are sorted by EV (highest first).

    Example: GET /api/parlays/top-ev?min_ev=0.15&limit=10
    """
    try:
        service = ParlayService(db)
        parlays = service.get_parlays(
            parlay_type=parlay_type,
            min_ev=min_ev,
            limit=limit
        )

        return {
            "parlays": parlays,
            "count": len(parlays)
        }
    except Exception as e:
        logger.error(f"Error retrieving top EV parlays: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{parlay_id}", response_model=ParlayResponse)
async def get_parlay_details(
    parlay_id: str,
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific parlay including all legs.

    Example: GET /api/parlays/{parlay_id}
    """
    try:
        service = ParlayService(db)
        parlay = service.get_parlay_details(parlay_id)

        if not parlay:
            raise HTTPException(status_code=404, detail=f"Parlay {parlay_id} not found")

        return parlay
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving parlay details: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    """
    Get top expected value parlays.

    Returns the highest EV parlays, useful for identifying the best
    betting opportunities. Results are sorted by EV (highest first).

    Example: GET /api/parlays/top-ev?min_ev=0.15&limit=10
    """
    try:
        service = ParlayService(db)
        parlays = service.get_parlays(
            parlay_type=parlay_type,
            min_ev=min_ev,
            limit=limit
        )

        return {
            "parlays": parlays,
            "count": len(parlays)
        }
    except Exception as e:
        logger.error(f"Error retrieving top EV parlays: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/game/{game_id}", response_model=ParlayListResponse)
async def get_game_parlays(
    game_id: str,
    parlay_type: Optional[str] = Query(None, description="Filter by parlay type"),
    min_ev: Optional[float] = Query(None, description="Minimum expected value"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    db: Session = Depends(get_db)
):
    """
    Get all parlays for a specific game.

    Returns both same-game parlays and parlays that include this game
    as part of multi-game combinations.

    Example: GET /api/parlays/game/{game_id}?parlay_type=same_game&min_ev=0.05
    """
    try:
        service = ParlayService(db)
        parlays = service.get_parlays(
            parlay_type=parlay_type,
            game_id=game_id,
            min_ev=min_ev,
            limit=limit
        )

        return {
            "parlays": parlays,
            "count": len(parlays)
        }
    except Exception as e:
        logger.error(f"Error retrieving game parlays: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== Maintenance Endpoints =====

@router.delete("/cleanup")
async def cleanup_old_parlays(
    days_old: int = Query(7, ge=1, le=30, description="Number of days to keep parlays"),
    db: Session = Depends(get_db)
):
    """
    Delete parlays older than specified number of days.

    Useful for database maintenance and keeping only relevant
    upcoming parlays.

    Example: DELETE /api/parlays/cleanup?days_old=7
    """
    try:
        service = ParlayService(db)
        deleted_count = service.cleanup_old_parlays(days_old=days_old)

        return {
            "message": f"Deleted {deleted_count} parlays older than {days_old} days",
            "deleted_count": deleted_count
        }
    except Exception as e:
        logger.error(f"Error cleaning up parlays: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/summary")
async def get_parlay_stats(
    db: Session = Depends(get_db)
):
    """
    Get summary statistics about generated parlays.

    Returns counts by type, average EV, and other useful metrics.

    Example: GET /api/parlays/stats/summary
    """
    try:
        from sqlalchemy import func

        total_count = db.query(Parlay).count()
        same_game_count = db.query(Parlay).filter(Parlay.parlay_type == "same_game").count()
        multi_game_count = db.query(Parlay).filter(Parlay.parlay_type == "multi_game").count()

        avg_ev = db.query(func.avg(Parlay.expected_value)).scalar()
        avg_confidence = db.query(func.avg(Parlay.confidence_score)).scalar()
        max_ev = db.query(func.max(Parlay.expected_value)).scalar()

        positive_ev_count = db.query(Parlay).filter(Parlay.expected_value > 0).count()

        return {
            "total_parlays": total_count,
            "by_type": {
                "same_game": same_game_count,
                "multi_game": multi_game_count
            },
            "average_expected_value": round(float(avg_ev), 4) if avg_ev else 0,
            "average_confidence": round(float(avg_confidence), 3) if avg_confidence else 0,
            "max_expected_value": round(float(max_ev), 4) if max_ev else 0,
            "positive_ev_count": positive_ev_count,
            "positive_ev_percentage": round((positive_ev_count / total_count * 100), 2) if total_count > 0 else 0
        }
    except Exception as e:
        logger.error(f"Error retrieving parlay stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
