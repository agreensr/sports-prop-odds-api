"""
Parlay API Routes.

Provides endpoints for generating and retrieving parlay bets.
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.services.core.parlay_service import ParlayService

router = APIRouter(prefix="/api/parlays", tags=["parlays"])


@router.get("/same-game/{game_id}")
async def get_same_game_parlays(
    game_id: str,
    min_confidence: float = Query(0.65, ge=0.0, le=1.0, description="Minimum confidence score"),
    min_ev: float = Query(0.08, ge=0.0, le=1.0, description="Minimum expected value"),
    max_legs: int = Query(4, ge=2, le=4, description="Maximum number of legs"),
    db: Session = Depends(get_db)
):
    """
    Get same-game parlays optimized for Top 50 players.

    Higher confidence threshold (0.65) and EV threshold (0.08) for
    more selective, higher-quality parlays.
    """
    service = ParlayService(db)
    parlays = service.generate_same_game_parlays_optimized(
        game_id=game_id,
        min_confidence=min_confidence,
        max_legs=max_legs,
        min_ev=min_ev
    )
    return {
        "parlays": parlays,
        "count": len(parlays),
        "game_id": game_id,
        "filters": {
            "min_confidence": min_confidence,
            "min_ev": min_ev,
            "max_legs": max_legs
        }
    }


@router.get("/cross-game")
async def get_cross_game_parlays(
    days_ahead: int = Query(1, ge=1, le=7, description="Days ahead to look for games"),
    min_confidence: float = Query(0.65, ge=0.0, le=1.0, description="Minimum confidence score"),
    min_ev: float = Query(0.08, ge=0.0, le=1.0, description="Minimum expected value"),
    db: Session = Depends(get_db)
):
    """
    Get 2-leg parlays across different games.

    Independent events (no correlation penalty) across different games.
    """
    service = ParlayService(db)
    parlays = service.generate_cross_game_parlays(
        days_ahead=days_ahead,
        min_confidence=min_confidence,
        min_ev=min_ev
    )
    return {
        "parlays": parlays,
        "count": len(parlays),
        "filters": {
            "days_ahead": days_ahead,
            "min_confidence": min_confidence,
            "min_ev": min_ev
        }
    }


@router.get("/combo")
async def get_combo_parlays(
    days_ahead: int = Query(1, ge=1, le=7, description="Days ahead to look for games"),
    min_ev: float = Query(0.10, ge=0.0, le=1.0, description="Minimum expected value"),
    db: Session = Depends(get_db)
):
    """
    Get 4-leg combo parlays.

    Combines two 2-leg parlays into higher-payout 4-leg combo parlays.
    """
    service = ParlayService(db)
    parlays = service.generate_combo_parlays(
        days_ahead=days_ahead,
        min_ev=min_ev
    )
    return {
        "parlays": parlays,
        "count": len(parlays),
        "filters": {
            "days_ahead": days_ahead,
            "min_ev": min_ev
        }
    }


@router.get("/")
async def list_parlays(
    parlay_type: str = Query(None, description="Filter by parlay type (same_game, multi_game)"),
    min_ev: float = Query(None, ge=0.0, le=1.0, description="Filter by minimum EV"),
    min_confidence: float = Query(None, ge=0.0, le=1.0, description="Filter by minimum confidence"),
    game_id: str = Query(None, description="Filter by specific game ID"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results to return"),
    db: Session = Depends(get_db)
):
    """
    List parlays from database with optional filtering.
    """
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
        "count": len(parlays),
        "filters": {
            "parlay_type": parlay_type,
            "min_ev": min_ev,
            "min_confidence": min_confidence,
            "game_id": game_id
        }
    }


@router.get("/{parlay_id}")
async def get_parlay_details(
    parlay_id: str,
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific parlay.
    """
    service = ParlayService(db)
    parlay = service.get_parlay_details(parlay_id)

    if not parlay:
        raise HTTPException(status_code=404, detail="Parlay not found")

    return parlay
