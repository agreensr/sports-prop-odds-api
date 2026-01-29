"""
Enhanced Parlay API routes.

Provides endpoints for:
- Getting daily 2-leg parlay recommendations from top single bets
- Filtering by sport, date, EV
- Getting parlay statistics

Base path: /api/parlays-v2
"""
import logging
from datetime import date, datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.services.core.enhanced_parlay_service import (
    EnhancedParlayService,
    ParlayBet,
    get_enhanced_parlay_service
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/parlays-v2", tags=["parlays-v2"])


# ==================== RESPONSE MODELS ====================

class ParlayLegModel(BaseModel):
    """Parlay leg response model."""
    player_id: str
    player_name: str
    team: str
    opponent: str
    game_date: datetime = Field(..., description="Game date/time in Central Time (CST/CDT)")
    stat_type: str
    predicted_value: float
    line: float
    recommendation: str
    bookmaker_name: str
    odds_american: int
    odds_decimal: float
    confidence: float
    edge_percent: float
    ev_percent: float


class ParlayResponse(BaseModel):
    """Parlay response model."""
    id: str
    parlay_type: str = Field(..., description="Same-game or cross-game")
    legs: List[ParlayLegModel]
    total_legs: int
    calculated_odds: int
    decimal_odds: float
    implied_probability: float
    ev_percent: float
    confidence_score: float
    correlation_score: float
    created_at: datetime


class DailyParlaysResponse(BaseModel):
    """Response model for daily parlays."""
    date: date
    total_parlays: int
    parlays: List[ParlayResponse]
    summary: dict


# ==================== ENDPOINTS ====================

@router.get("/daily", response_model=DailyParlaysResponse)
async def get_daily_parlays(
    target_date: Optional[str] = Query(
        None,
        description="Target date (YYYY-MM-DD format, default: today)"
    ),
    sport_id: Optional[str] = Query(
        None,
        description="Filter by sport (nba, nfl, mlb, nhl)"
    ),
    limit: Optional[int] = Query(
        5,
        ge=1,
        le=20,
        description="Max number of parlays to return"
    ),
    db: Session = Depends(get_db)
) -> DailyParlaysResponse:
    """
    Get daily 2-leg parlay recommendations from top single bets.

    **Business Rules:**
    - Generated from top 10 single bets
    - 2-leg parlays ONLY
    - Same-game and cross-game allowed
    - Min 8% EV
    - Max 5 parlays per day
    - Ranked by EV

    **Example Parlay:**
    - Leg 1: Luka Doncic Points OVER 33.5
    - Leg 2: LeBron James Assists OVER 6.5
    - Combined odds: +265
    - EV: 15%
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
        service = get_enhanced_parlay_service(db)

        # Generate parlays
        parlays = service.generate_daily_parlays(
            target_date=parsed_date,
            sport_id=sport_id
        )

        # Apply limit
        if limit and limit < len(parlays):
            parlays = parlays[:limit]

        # Convert to response models
        parlay_responses = []
        for parlay in parlays:
            legs = [
                ParlayLegModel(**leg) for leg in parlay.legs
            ]
            parlay_responses.append(
                ParlayResponse(
                    id=parlay.id,
                    parlay_type=parlay.parlay_type,
                    legs=legs,
                    total_legs=parlay.total_legs,
                    calculated_odds=parlay.calculated_odds,
                    decimal_odds=parlay.decimal_odds,
                    implied_probability=parlay.implied_probability,
                    ev_percent=parlay.ev_percent,
                    confidence_score=parlay.confidence_score,
                    correlation_score=parlay.correlation_score,
                    created_at=parlay.created_at
                )
            )

        # Calculate summary
        summary = _calculate_summary(parlays)

        return DailyParlaysResponse(
            date=parsed_date,
            total_parlays=len(parlay_responses),
            parlays=parlay_responses,
            summary=summary
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting daily parlays: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error generating daily parlays: {str(e)}"
        )


@router.get("/display")
async def get_display_parlays(
    target_date: Optional[str] = Query(None, description="Target date (YYYY-MM-DD)"),
    sport_id: Optional[str] = Query(None, description="Filter by sport"),
    db: Session = Depends(get_db)
) -> dict:
    """
    Get parlays formatted for display (plain text format).

    Useful for sending notifications or displaying in simple interfaces.
    """
    try:
        # Parse target date
        if target_date:
            parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
        else:
            parsed_date = date.today()

        service = get_enhanced_parlay_service(db)
        parlays = service.generate_daily_parlays(
            target_date=parsed_date,
            sport_id=sport_id
        )

        display_text = service.format_parlays_for_display(parlays)

        return {
            "date": parsed_date.isoformat(),
            "sport": sport_id or "all",
            "count": len(parlays),
            "display": display_text
        }

    except Exception as e:
        logger.error(f"Error getting display parlays: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting display parlays: {str(e)}"
        )


@router.get("/stats")
async def get_parlay_stats(
    days: int = Query(7, ge=1, le=30, description="Days to look back"),
    db: Session = Depends(get_db)
) -> dict:
    """
    Get statistics for generated parlays.

    Returns aggregate statistics for recent parlays.
    """
    try:
        service = get_enhanced_parlay_service(db)

        # Generate parlays for each day and collect stats
        all_parlays = []
        for day_offset in range(days):
            target_date = date.today() - timedelta(days=day_offset)
            day_parlays = service.generate_daily_parlays(target_date=target_date)
            all_parlays.extend(day_parlays)

        if not all_parlays:
            return {
                "total_parlays": 0,
                "avg_ev": 0.0,
                "avg_confidence": 0.0,
                "by_type": {"same_game": {"count": 0}, "cross_game": {"count": 0}}
            }

        # Calculate stats
        same_game = [p for p in all_parlays if p.parlay_type == "same_game"]
        cross_game = [p for p in all_parlays if p.parlay_type == "cross_game"]

        return {
            "total_parlays": len(all_parlays),
            "avg_ev": round(sum(p.ev_percent for p in all_parlays) / len(all_parlays), 2),
            "avg_confidence": round(sum(p.confidence_score for p in all_parlays) / len(all_parlays), 3),
            "by_type": {
                "same_game": {
                    "count": len(same_game),
                    "avg_ev": round(sum(p.ev_percent for p in same_game) / len(same_game), 2) if same_game else 0
                },
                "cross_game": {
                    "count": len(cross_game),
                    "avg_ev": round(sum(p.ev_percent for p in cross_game) / len(cross_game), 2) if cross_game else 0
                }
            }
        }

    except Exception as e:
        logger.error(f"Error getting parlay stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting parlay stats: {str(e)}"
        )


# ==================== UTILITY FUNCTIONS ====================

def _calculate_summary(parlays: List[ParlayBet]) -> dict:
    """Calculate summary statistics for a list of parlays."""
    if not parlays:
        return {
            "avg_ev": 0.0,
            "avg_confidence": 0.0,
            "avg_odds": 0,
            "by_type": {"same_game": 0, "cross_game": 0}
        }

    # Overall averages
    avg_ev = sum(p.ev_percent for p in parlays) / len(parlays)
    avg_confidence = sum(p.confidence_score for p in parlays) / len(parlays)
    avg_odds = sum(p.calculated_odds for p in parlays) / len(parlays)

    # By type
    same_game_count = sum(1 for p in parlays if p.parlay_type == "same_game")
    cross_game_count = sum(1 for p in parlays if p.parlay_type == "cross_game")

    return {
        "avg_ev": round(avg_ev, 2),
        "avg_confidence": round(avg_confidence, 3),
        "avg_odds": round(avg_odds),
        "by_type": {
            "same_game": same_game_count,
            "cross_game": cross_game_count
        }
    }
