"""
Betting manager API routes for PMAGENT.

Provides endpoints for:
- Daily betting cards across all sports
- Bankroll tracking
- Performance summaries
"""
import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.betting.project_manager import ProjectManagerAgent, get_project_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/betting", tags=["betting_manager"])


class BankrollUpdate(BaseModel):
    """Request model for bankroll updates."""
    profit_loss: float
    note: Optional[str] = None


@router.get("/card")
async def get_daily_betting_card(
    days_ahead: int = Query(1, ge=0, le=7, description="Days ahead to look"),
    db: Session = Depends(get_db)
):
    """
    Get today's betting card across all sports.

    Aggregates high-confidence predictions from NBA and NHL,
    calculates Kelly bet sizes, and organizes into straights and parlays.

    Returns:
        {
            "date": "2025-01-30",
            "bankroll": {...},
            "straight_bets": [...],
            "two_leg_parlays": [...],
            "three_leg_parlays": [...],
            "summary": {...}
        }
    """
    pm = get_project_manager(db)
    card = pm.get_daily_betting_card(days_ahead=days_ahead)

    return card


@router.get("/bankroll")
async def get_bankroll_status(db: Session = Depends(get_db)):
    """
    Get current bankroll status and growth progress.

    Returns:
        {
            "current": 500.00,
            "starting": 500.00,
            "target": 5000.00,
            "growth_percent": 0.0,
            "growth_needed": 4500.00,
            "unit_size": 10.0
        }
    """
    pm = get_project_manager(db)

    unit_size = pm.get_unit_size()

    return {
        "current": round(pm.current_bankroll, 2),
        "starting": round(pm.starting_bankroll, 2),
        "target": round(pm.target_bankroll, 2),
        "growth_needed": round(pm.target_bankroll - pm.current_bankroll, 2),
        "growth_percent": round(
            (pm.current_bankroll / pm.starting_bankroll - 1) * 100
            if pm.starting_bankroll > 0 else 0,
            1
        ),
        "unit_size": unit_size,
        "max_bet_percent": pm.max_bet_percent * 100
    }


@router.put("/bankroll")
async def update_bankroll(
    update: BankrollUpdate,
    db: Session = Depends(get_db)
):
    """
    Update bankroll after settled bets.

    Args:
        update: BankrollUpdate with profit_loss amount

    Returns:
        Updated bankroll info
    """
    pm = get_project_manager(db)
    result = pm.update_bankroll(update.profit_loss)

    logger.info(
        f"Bankroll updated: ${result['previous_bankroll']:.2f} -> "
        f"${result['current_bankroll']:.2f} "
        f"({update.profit_loss:+.2f})"
    )

    return result


@router.get("/performance")
async def get_performance_summary(
    days_back: int = Query(30, ge=1, le=365, description="Days to analyze"),
    db: Session = Depends(get_db)
):
    """
    Get performance metrics by sport and confidence tier.

    Args:
        days_back: Number of days to analyze

    Returns:
        Performance summary with win rate, ROI, P/L by category
    """
    pm = get_project_manager(db)
    performance = pm.get_performance_summary(days_back=days_back)

    return performance


@router.get("/strategy")
async def get_betting_strategy(db: Session = Depends(get_db)):
    """
    Get current betting strategy based on bankroll.

    Returns unit sizing, allocation, and rules.
    """
    pm = get_project_manager(db)
    unit_size = pm.get_unit_size()

    # Calculate allocation based on bankroll
    bankroll = pm.current_bankroll

    if bankroll < 750:
        max_daily_risk = 50.0  # 10%
        straight_bet = 10.0
        two_leg_parlay = 10.0
        three_leg_parlay = 5.0
    elif bankroll < 1000:
        max_daily_risk = 60.0  # 8%
        straight_bet = 15.0
        two_leg_parlay = 10.0
        three_leg_parlay = 5.0
    elif bankroll < 2000:
        max_daily_risk = 80.0  # 8%
        straight_bet = 20.0
        two_leg_parlay = 15.0
        three_leg_parlay = 5.0
    elif bankroll < 3000:
        max_daily_risk = 125.0  # 6%
        straight_bet = 25.0
        two_leg_parlay = 20.0
        three_leg_parlay = 10.0
    else:
        max_daily_risk = 150.0  # 5%
        straight_bet = 30.0
        two_leg_parlay = 25.0
        three_leg_parlay = 10.0

    return {
        "bankroll": round(bankroll, 2),
        "unit_size": unit_size,
        "max_daily_risk": round(max_daily_risk, 2),
        "max_daily_risk_percent": round((max_daily_risk / bankroll) * 100, 1) if bankroll > 0 else 0,
        "allocation": {
            "straight_bets": {
                "percent": 70,
                "wager": straight_bet
            },
            "two_leg_parlays": {
                "percent": 20,
                "wager": two_leg_parlay,
                "max_parlays": 5
            },
            "three_leg_parlays": {
                "percent": 10,
                "wager": three_leg_parlay,
                "max_parlays": 2
            }
        },
        "confidence_thresholds": {
            "min_confidence": pm.min_confidence,
            "parlay_2leg_min": 0.75,
            "parlay_3leg_min": 0.80
        }
    }
