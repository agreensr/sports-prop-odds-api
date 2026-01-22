"""
Bet tracking API routes for managing placed bets and results.
"""
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.bet_tracking_service import BetTrackingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bets", tags=["bets"])


# Request/Response models
class BetLegCreate(BaseModel):
    """Leg data for creating a bet."""
    player_name: str
    player_team: str
    stat_type: str
    selection: str
    line: Optional[float] = None
    special_bet: Optional[str] = None
    predicted_value: Optional[float] = None
    model_confidence: Optional[float] = None
    recommendation: Optional[str] = None


class CreateBetRequest(BaseModel):
    """Request to create a new placed bet."""
    sportsbook: str = Field(..., description="Sportsbook name (FanDuel, DraftKings, etc.)")
    bet_id: str = Field(..., description="Bet ID from sportsbook")
    bet_type: str = Field(..., description="Bet type (same_game_parlay, multi_game_parlay, straight)")
    matchup: str = Field(..., description="Game matchup (e.g., IND @ BOS)")
    game_date: str = Field(..., description="Game date/time (ISO format)")
    wager_amount: float = Field(..., gt=0, description="Amount wagered")
    total_charged: float = Field(..., gt=0, description="Total charged including fees")
    odds: int = Field(..., description="American odds (+760, +333, etc.)")
    to_win: float = Field(..., description="Potential profit")
    total_payout: float = Field(..., description="Total potential return")
    placed_at: str = Field(..., description="When bet was placed (ISO format)")
    legs: List[BetLegCreate] = Field(..., min_items=1, description="Bet legs")
    game_id: Optional[str] = Field(None, description="Game ID from our database")


class UpdateBetResultRequest(BaseModel):
    """Request to update bet results."""
    status: str = Field(..., description="New status (won, lost, push, cashed_out)")
    actual_payout: Optional[float] = Field(None, description="Actual amount received")
    leg_results: Optional[List[dict]] = Field(None, description="Leg results with leg_id, result, actual_value")


class PlacedBetResponse(BaseModel):
    """Response for a placed bet."""
    id: str
    sportsbook: str
    bet_id: str
    bet_type: str
    matchup: str
    game_date: str
    wager_amount: float
    total_charged: float
    odds: int
    to_win: float
    total_payout: float
    status: str
    cash_out_value: Optional[float]
    actual_payout: Optional[float]
    profit_loss: Optional[float]
    placed_at: str
    settled_at: Optional[str]
    legs: Optional[List[dict]] = None


class BetListResponse(BaseModel):
    """Response containing multiple bets."""
    bets: List[PlacedBetResponse]
    count: int


@router.post("/", response_model=dict)
async def create_placed_bet(
    request: CreateBetRequest,
    db: Session = Depends(get_db)
):
    """
    Create a new placed bet record.

    Use this to track bets placed on sportsbooks like FanDuel or DraftKings.
    """
    try:
        service = BetTrackingService(db)

        # Parse dates
        game_date = datetime.fromisoformat(request.game_date.replace('Z', '+00:00'))
        placed_at = datetime.fromisoformat(request.placed_at.replace('Z', '+00:00'))

        # Convert legs to dict format
        legs_data = []
        for leg in request.legs:
            legs_data.append({
                'player_name': leg.player_name,
                'player_team': leg.player_team,
                'stat_type': leg.stat_type,
                'selection': leg.selection,
                'line': leg.line,
                'special_bet': leg.special_bet,
                'predicted_value': leg.predicted_value,
                'model_confidence': leg.model_confidence,
                'recommendation': leg.recommendation
            })

        bet_id = service.create_placed_bet(
            sportsbook=request.sportsbook,
            bet_id=request.bet_id,
            bet_type=request.bet_type,
            matchup=request.matchup,
            game_date=game_date,
            wager_amount=request.wager_amount,
            total_charged=request.total_charged,
            odds=request.odds,
            to_win=request.to_win,
            total_payout=request.total_payout,
            placed_at=placed_at,
            legs=legs_data,
            game_id=request.game_id
        )

        return {
            'message': 'Bet created successfully',
            'bet_id': bet_id
        }
    except Exception as e:
        logger.error(f"Error creating bet: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=BetListResponse)
async def get_placed_bets(
    sportsbook: Optional[str] = Query(None, description="Filter by sportsbook"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    db: Session = Depends(get_db)
):
    """Get placed bets with optional filtering."""
    try:
        service = BetTrackingService(db)
        bets = service.get_placed_bets(
            sportsbook=sportsbook,
            status=status,
            limit=limit
        )

        return {
            'bets': bets,
            'count': len(bets)
        }
    except Exception as e:
        logger.error(f"Error retrieving bets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_bet_summary(db: Session = Depends(get_db)):
    """Get summary statistics of placed bets."""
    try:
        service = BetTrackingService(db)
        summary = service.get_bet_summary()
        return summary
    except Exception as e:
        logger.error(f"Error retrieving bet summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{bet_id}", response_model=PlacedBetResponse)
async def get_bet_details(
    bet_id: str,
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific bet."""
    try:
        service = BetTrackingService(db)
        bet = service.get_bet_details(bet_id)

        if not bet:
            raise HTTPException(status_code=404, detail=f"Bet {bet_id} not found")

        return bet
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving bet details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{bet_id}/result")
async def update_bet_result(
    bet_id: str,
    request: UpdateBetResultRequest,
    db: Session = Depends(get_db)
):
    """Update bet result after game completion."""
    try:
        service = BetTrackingService(db)
        success = service.update_bet_result(
            bet_id=bet_id,
            status=request.status,
            actual_payout=request.actual_payout,
            leg_results=request.leg_results
        )

        if not success:
            raise HTTPException(status_code=404, detail=f"Bet {bet_id} not found")

        return {
            'message': f'Bet {bet_id} updated to {request.status}'
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating bet result: {e}")
        raise HTTPException(status_code=500, detail=str(e))
