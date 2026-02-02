"""
Single Bets API routes.

Provides endpoints for:
- Getting daily single bet recommendations
- Filtering by sport, date, confidence, edge
- Getting bet statistics

Base path: /api/single-bets
"""
import logging
from datetime import date, datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.services.core.single_bet_service import (
    SingleBetService,
    SingleBet,
    get_single_bet_service
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/single-bets", tags=["single-bets"])


# ==================== RESPONSE MODELS ====================

class BetRecommendationModel(str):
    """Bet recommendation type."""
    OVER = "OVER"
    UNDER = "UNDER"


class SingleBetResponse(BaseModel):
    """Single bet response model."""
    id: str
    sport_id: str = Field(..., description="Sport identifier (nba, nfl, mlb, nhl)")
    player_name: str
    team: str = Field(..., description="Team abbreviation")
    opponent: str = Field(..., description="Opponent team abbreviation")
    game_date: datetime = Field(..., description="Game date/time in Central Time (CST/CDT)")
    stat_type: str = Field(..., description="Stat type (points, rebounds, etc.)")
    predicted_value: float
    bookmaker_line: float
    recommendation: str = Field(..., description="OVER or UNDER")
    bookmaker_name: str
    odds_american: int = Field(..., description="American odds (e.g., -110, +150)")
    odds_decimal: float = Field(..., description="Decimal odds (e.g., 1.91, 2.50)")
    confidence: float = Field(..., ge=0, le=1, description="Win probability (0-1)")
    edge_percent: float = Field(..., description="Edge over market (%)")
    ev_percent: float = Field(..., description="Expected value (%)")
    priority_score: float = Field(..., description="Priority for ranking")
    created_at: datetime = Field(..., description="Creation timestamp in Central Time (CST/CDT)")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "sport_id": "nba",
                "player_name": "Luka Doncic",
                "team": "DAL",
                "opponent": "LAL",
                "game_date": "2026-01-27T19:00:00",
                "stat_type": "points",
                "predicted_value": 35.2,
                "bookmaker_line": 33.5,
                "recommendation": "OVER",
                "bookmaker_name": "draftkings",
                "odds_american": -110,
                "odds_decimal": 1.91,
                "confidence": 0.68,
                "edge_percent": 7.2,
                "ev_percent": 13.5,
                "priority_score": 9.18,
                "created_at": "2026-01-27T14:00:00"
            }
        }


class DailyBetsResponse(BaseModel):
    """Response model for daily bets."""
    date: date
    total_bets: int
    bets: List[SingleBetResponse]
    summary: dict = Field(..., description="Summary statistics")


class BetStatsResponse(BaseModel):
    """Response model for bet statistics."""
    total_bets: int
    by_sport: dict
    avg_confidence: float
    avg_edge: float
    avg_ev: float


# ==================== ERROR RESPONSES ====================

class ErrorResponse(BaseModel):
    """Error response model."""
    error: str
    detail: Optional[str] = None


# ==================== ENDPOINTS ====================

@router.get("/daily", response_model=DailyBetsResponse)
async def get_daily_bets(
    target_date: Optional[str] = Query(
        None,
        description="Target date (YYYY-MM-DD format, default: today)"
    ),
    sport_id: Optional[str] = Query(
        None,
        description="Filter by sport (nba, nfl, mlb, nhl)"
    ),
    limit: Optional[int] = Query(
        10,
        ge=1,
        le=20,
        description="Max number of bets to return"
    ),
    db: Session = Depends(get_db)
) -> DailyBetsResponse:
    """
    Get daily single bet recommendations.

    Returns the top single bets for the target date, ranked by
    expected value × confidence.

    **Business Rules**:
    - Max 10 bets per day
    - Min 60% confidence
    - Min 5% edge
    - Max 3 bets per game
    """
    try:
        # Parse target date
        if target_date:
            try:
                parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid date format. Use YYYY-MM-DD."
                )
        else:
            parsed_date = date.today()

        # Get service
        service = get_single_bet_service(db)

        # Generate bets
        bets = service.generate_daily_bets(
            target_date=parsed_date,
            sport_id=sport_id
        )

        # Apply limit
        if limit and limit < len(bets):
            bets = bets[:limit]

        # Convert to response models
        bet_responses = [
            SingleBetResponse(
                id=bet.id,
                sport_id=bet.sport_id,
                player_name=bet.player_name,
                team=bet.team,
                opponent=bet.opponent,
                game_date=bet.game_date,
                stat_type=bet.stat_type,
                predicted_value=bet.predicted_value,
                bookmaker_line=bet.bookmaker_line,
                recommendation=bet.recommendation.value,
                bookmaker_name=bet.bookmaker_name,
                odds_american=bet.odds_american,
                odds_decimal=bet.odds_decimal,
                confidence=bet.confidence,
                edge_percent=bet.edge_percent,
                ev_percent=bet.ev_percent,
                priority_score=bet.priority_score,
                created_at=bet.created_at
            )
            for bet in bets
        ]

        # Calculate summary
        summary = _calculate_summary(bets)

        return DailyBetsResponse(
            date=parsed_date,
            total_bets=len(bet_responses),
            bets=bet_responses,
            summary=summary
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting daily bets: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error generating daily bets: {str(e)}"
        )


@router.get("/bets", response_model=List[SingleBetResponse])
async def get_bets(
    sport_id: Optional[str] = Query(None, description="Filter by sport"),
    days: int = Query(7, ge=1, le=30, description="Days to look back"),
    min_confidence: float = Query(0.60, ge=0, le=1, description="Min confidence"),
    min_edge: float = Query(5.0, description="Min edge (%)"),
    limit: int = Query(50, ge=1, le=100, description="Max results"),
    db: Session = Depends(get_db)
) -> List[SingleBetResponse]:
    """
    Get recent single bets with optional filters.

    Returns a list of recent single bets that match the specified criteria.
    """
    try:
        service = get_single_bet_service(db)

        # Get bets
        if sport_id:
            bets = service.get_bets_by_sport(sport_id, days)
        else:
            # Get all sports (run for each sport and combine)
            all_bets = []
            for sport in ['nba', 'nfl', 'mlb', 'nhl']:
                sport_bets = service.get_bets_by_sport(sport, days)
                all_bets.extend(sport_bets)
            bets = all_bets

        # Apply filters
        filtered_bets = [
            bet for bet in bets
            if bet.confidence >= min_confidence and bet.edge_percent >= min_edge
        ]

        # Sort by priority and limit
        filtered_bets.sort(key=lambda b: b.priority_score, reverse=True)
        filtered_bets = filtered_bets[:limit]

        # Convert to response models
        return [
            SingleBetResponse(
                id=bet.id,
                sport_id=bet.sport_id,
                player_name=bet.player_name,
                team=bet.team,
                opponent=bet.opponent,
                game_date=bet.game_date,
                stat_type=bet.stat_type,
                predicted_value=bet.predicted_value,
                bookmaker_line=bet.bookmaker_line,
                recommendation=bet.recommendation.value,
                bookmaker_name=bet.bookmaker_name,
                odds_american=bet.odds_american,
                odds_decimal=bet.odds_decimal,
                confidence=bet.confidence,
                edge_percent=bet.edge_percent,
                ev_percent=bet.ev_percent,
                priority_score=bet.priority_score,
                created_at=bet.created_at
            )
            for bet in filtered_bets
        ]

    except Exception as e:
        logger.error(f"Error getting bets: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting bets: {str(e)}"
        )


@router.get("/stats", response_model=BetStatsResponse)
async def get_bet_stats(
    days: int = Query(7, ge=1, le=30, description="Days to look back"),
    db: Session = Depends(get_db)
) -> BetStatsResponse:
    """
    Get statistics for single bets.

    Returns aggregate statistics for recent bets across all sports.
    """
    try:
        service = get_single_bet_service(db)

        # Get all recent bets
        all_bets = []
        for sport in ['nba', 'nfl', 'mlb', 'nhl']:
            sport_bets = service.get_bets_by_sport(sport, days)
            all_bets.extend(sport_bets)

        if not all_bets:
            return BetStatsResponse(
                total_bets=0,
                by_sport={},
                avg_confidence=0.0,
                avg_edge=0.0,
                avg_ev=0.0
            )

        # Calculate stats
        by_sport = {}
        for sport in ['nba', 'nfl', 'mlb', 'nhl']:
            sport_bets = [b for b in all_bets if b.sport_id == sport]
            if sport_bets:
                by_sport[sport] = {
                    "count": len(sport_bets),
                    "avg_confidence": sum(b.confidence for b in sport_bets) / len(sport_bets),
                    "avg_edge": sum(b.edge_percent for b in sport_bets) / len(sport_bets),
                    "avg_ev": sum(b.ev_percent for b in sport_bets) / len(sport_bets),
                }

        total_bets = len(all_bets)
        avg_confidence = sum(b.confidence for b in all_bets) / total_bets
        avg_edge = sum(b.edge_percent for b in all_bets) / total_bets
        avg_ev = sum(b.ev_percent for b in all_bets) / total_bets

        return BetStatsResponse(
            total_bets=total_bets,
            by_sport=by_sport,
            avg_confidence=round(avg_confidence, 3),
            avg_edge=round(avg_edge, 2),
            avg_ev=round(avg_ev, 2)
        )

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting stats: {str(e)}"
        )


@router.get("/display")
async def get_display_bets(
    target_date: Optional[str] = Query(None, description="Target date (YYYY-MM-DD)"),
    sport_id: Optional[str] = Query(None, description="Filter by sport"),
    db: Session = Depends(get_db)
) -> dict:
    """
    Get bets formatted for display (plain text format).

    Useful for sending notifications or displaying in simple interfaces.
    """
    try:
        # Parse target date
        if target_date:
            parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
        else:
            parsed_date = date.today()

        service = get_single_bet_service(db)
        bets = service.generate_daily_bets(
            target_date=parsed_date,
            sport_id=sport_id
        )

        display_text = service.format_bets_for_display(bets)

        return {
            "date": parsed_date.isoformat(),
            "sport": sport_id or "all",
            "count": len(bets),
            "display": display_text
        }

    except Exception as e:
        logger.error(f"Error getting display bets: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting display bets: {str(e)}"
        )


# ==================== UTILITY FUNCTIONS ====================

def _calculate_summary(bets: List[SingleBet]) -> dict:
    """Calculate summary statistics for a list of bets."""
    if not bets:
        return {
            "avg_confidence": 0.0,
            "avg_edge": 0.0,
            "avg_ev": 0.0,
            "by_sport": {}
        }

    # Overall averages
    avg_confidence = sum(b.confidence for b in bets) / len(bets)
    avg_edge = sum(b.edge_percent for b in bets) / len(bets)
    avg_ev = sum(b.ev_percent for b in bets) / len(bets)

    # By sport
    by_sport = {}
    for sport in ['nba', 'nfl', 'mlb', 'nhl']:
        sport_bets = [b for b in bets if b.sport_id == sport]
        if sport_bets:
            by_sport[sport] = {
                "count": len(sport_bets),
                "avg_confidence": round(sum(b.confidence for b in sport_bets) / len(sport_bets), 3),
                "avg_edge": round(sum(b.edge_percent for b in sport_bets) / len(sport_bets), 2),
            }

    return {
        "avg_confidence": round(avg_confidence, 3),
        "avg_edge": round(avg_edge, 2),
        "avg_ev": round(avg_ev, 2),
        "by_sport": by_sport
    }
