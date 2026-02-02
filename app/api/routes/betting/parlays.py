"""
Parlay-specific API routes for PMAGENT.

Provides endpoints for:
- Getting available parlays
- Building custom parlays
- Parlay performance tracking
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.betting.parlay_builder import ParlayBuilder, get_parlay_builder
from app.services.betting.project_manager import get_project_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/betting", tags=["parlays"])


class CustomParlayRequest(BaseModel):
    """Request model for custom parlay building."""
    player_ids: List[str]
    stat_types: List[str]
    wager: Optional[float] = None


@router.get("/parlays")
async def get_available_parlays(
    days_ahead: int = Query(1, ge=0, le=7, description="Days ahead to look"),
    min_confidence: float = Query(0.75, ge=0.5, le=1.0, description="Min confidence per leg"),
    db: Session = Depends(get_db)
):
    """
    Get available 2-leg and 3-leg parlays for today.

    Returns:
        {
            "two_leg_parlays": [...],
            "three_leg_parlays": [...],
            "summary": {...}
        }
    """
    pm = get_project_manager(db)
    card = pm.get_daily_betting_card(days_ahead=days_ahead)

    # Filter by confidence if specified
    two_legs = card.get("two_leg_parlays", [])
    three_legs = card.get("three_leg_parlays", [])

    if min_confidence > 0.75:
        two_legs = [
            p for p in two_legs
            if p.get("combined_confidence", 0) >= min_confidence
        ]
        three_legs = [
            p for p in three_legs
            if p.get("combined_confidence", 0) >= min_confidence
        ]

    return {
        "date": card.get("date"),
        "two_leg_parlays": two_legs,
        "three_leg_parlays": three_legs,
        "summary": {
            "two_leg_count": len(two_legs),
            "three_leg_count": len(three_legs),
            "total_parlays": len(two_legs) + len(three_legs),
            "total_wager": sum(p["wager"] for p in two_legs) + sum(p["wager"] for p in three_legs)
        }
    }


@router.get("/parlays/correlation-matrix")
async def get_correlation_matrix():
    """
    Get the correlation matrix used for parlay building.

    Returns correlation coefficients for different stat combinations.
    Higher values indicate better correlation for parlays.
    """
    builder = ParlayBuilder()

    matrix = []
    for (stat1, stat2), correlation in builder.CORRELATION_MATRIX.items():
        matrix.append({
            "stat1": stat1,
            "stat2": stat2,
            "correlation": correlation,
            "recommendation": "excellent" if correlation >= 0.8 else
                            "good" if correlation >= 0.6 else
                            "moderate" if correlation >= 0.4 else "low"
        })

    # Sort by correlation
    matrix.sort(key=lambda x: x["correlation"], reverse=True)

    return {
        "correlation_matrix": matrix,
        "notes": [
            "Same-player parlays have highest correlation",
            "Same-team parlays have moderate correlation",
            "Cross-team parlays have low correlation (avoid unless high confidence)"
        ]
    }


@router.get("/parlays/limits")
async def get_parlay_limits(db: Session = Depends(get_db)):
    """
    Get daily parlay betting limits and counts.

    Returns current limits and remaining parlay slots.
    """
    builder = get_parlay_builder()
    limits = builder.get_parlay_count_limits()

    return {
        "limits": limits,
        "wager_amounts": {
            "two_leg": builder.two_leg_wager,
            "three_leg": builder.three_leg_wager
        },
        "rules": [
            "2-leg parlays: Min 75% confidence per leg, max 5 per day",
            "3-leg parlays: Min 80% confidence per leg, max 2 per day",
            "Prefer same-player parlays (highest correlation)",
            "All 3-leg parlay legs must be different players"
        ]
    }


@router.get("/parlays/performance")
async def get_parlay_performance(
    days_back: int = Query(30, ge=1, le=365, description="Days to analyze"),
    db: Session = Depends(get_db)
):
    """
    Get parlay performance metrics.

    Returns win rate, ROI, and P/L specifically for parlays.
    """
    # TODO: Query from placed_bets table
    return {
        "period_days": days_back,
        "two_leg": {
            "total_bets": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "roi": 0.0,
            "profit_loss": 0.0
        },
        "three_leg": {
            "total_bets": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "roi": 0.0,
            "profit_loss": 0.0
        }
    }
