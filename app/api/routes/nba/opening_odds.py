"""
Opening Odds API endpoints for tracking line movements and finding value.

These endpoints provide access to opening odds data and line movement analysis
to identify betting opportunities created by market inefficiencies.

Key Endpoints:
- GET /api/nba/opening-odds/game/{game_id} - Get opening vs current odds for a game
- GET /api/nba/opening-odds/value/{game_id} - Find value opportunities from line movements
- GET /api/nba/opening-odds/player/{player_id}/stats - Line movement statistics for a player
- POST /api/nba/opening-odds/capture - Capture opening odds for upcoming games
"""
import logging
from typing import List, Optional
from datetime import datetime, timedelta

# UTC timezone for Python < 3.11 compatibility
try:
    from datetime import UTC
except ImportError:
    from datetime import timezone
    UTC = timezone.utc

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.core.database import get_db
from app.models.nba.models import Game, HistoricalOddsSnapshot, Player
from app.services.nba.opening_odds_service import OpeningOddsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/opening-odds", tags=["nba-opening-odds"])


# Request/Response Models
class OpeningOddsCapture(BaseModel):
    """Request model for capturing opening odds."""
    game_id: str
    player_id: str
    stat_type: str
    bookmaker_name: str
    bookmaker_line: float
    over_price: Optional[float] = None
    under_price: Optional[float] = None
    was_starter: bool = False


@router.get("/game/{game_id}")
async def get_opening_vs_current_odds(
    game_id: str,
    player_id: Optional[str] = None,
    stat_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get opening odds compared to current odds for a game.

    Shows how lines have moved from opening to current, helping identify
    where the market has adjusted.

    Args:
        game_id: Game UUID
        player_id: Optional filter by player
        stat_type: Optional filter by stat type

    Returns:
        List of opening vs current odds comparisons
    """
    service = OpeningOddsService(db)

    # Verify game exists
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    comparisons = service.get_opening_vs_current_odds(game_id, player_id, stat_type)

    return {
        "game_id": game_id,
        "game_date": game.game_date,
        "away_team": game.away_team,
        "home_team": game.home_team,
        "comparisons": comparisons,
        "total": len(comparisons)
    }


@router.get("/value/{game_id}")
async def find_value_opportunities(
    game_id: str,
    min_movement: float = Query(2.0, description="Minimum line movement to consider", ge=0),
    hours_before_game: int = Query(24, description="Only consider games within N hours", ge=1, le=72),
    db: Session = Depends(get_db)
):
    """
    Find value opportunities created by line movements.

    Identifies situations where:
    1. The line has moved significantly (indicating market adjustment)
    2. Our prediction still shows an edge (indicating potential value)

    Examples:
    - Opening line: 23.5, Current: 25.5, Prediction: 26.0 (OVER)
      → Line moved toward prediction = stronger OVER signal

    - Opening line: 25.5, Current: 23.5, Prediction: 21.0 (UNDER)
      → Line moved toward prediction = stronger UNDER signal

    Args:
        game_id: Game UUID to analyze
        min_movement: Minimum line movement threshold (default: 2.0 points)
        hours_before_game: Only look at games within this many hours

    Returns:
        List of value opportunities sorted by value score
    """
    service = OpeningOddsService(db)

    # Verify game exists and is upcoming
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Check if game is in the appropriate time window
    hours_until_game = (game.game_date - datetime.now(UTC)).total_seconds() / 3600
    if hours_until_game > hours_before_game:
        raise HTTPException(
            status_code=400,
            detail=f"Game is {hours_until_game:.1f} hours away, "
                  f"only analyzing games within {hours_before_game} hours"
        )

    if hours_until_game < 0:
        raise HTTPException(
            status_code=400,
            detail="Game has already started"
        )

    opportunities = service.find_value_from_line_movements(
        game_id=game_id,
        min_movement=min_movement
    )

    return {
        "game_id": game_id,
        "game_date": game.game_date,
        "hours_until_game": hours_until_game,
        "min_movement_threshold": min_movement,
        "opportunities": opportunities,
        "total_opportunities": len(opportunities)
    }


@router.get("/player/{player_id}/stats")
async def get_player_line_movement_stats(
    player_id: str,
    stat_type: Optional[str] = None,
    last_n_games: int = Query(20, description="Number of recent games to analyze", ge=5, le=100),
    db: Session = Depends(get_db)
):
    """
    Get line movement statistics for a player.

    Shows historical data on how this player's lines typically move
    from opening to close, helping predict future line movements.

    Args:
        player_id: Player UUID
        stat_type: Optional filter by stat type
        last_n_games: Number of recent games to analyze

    Returns:
        Line movement statistics including averages, distribution, and patterns
    """
    service = OpeningOddsService(db)

    stats = service.get_line_movement_stats(
        player_id=player_id,
        stat_type=stat_type,
        last_n_games=last_n_games
    )

    if 'error' in stats:
        raise HTTPException(status_code=404, detail=stats['error'])

    return stats


@router.get("/upcoming")
async def list_games_with_opening_odds(
    hours_ahead: int = Query(48, description="Look ahead this many hours", ge=1, le=168),
    db: Session = Depends(get_db)
):
    """
    List upcoming games that have opening odds captured.

    Useful for identifying which games have opening odds data available
    for line movement analysis.

    Args:
        hours_ahead: How many hours ahead to look

    Returns:
        List of games with opening odds count
    """
    from app.models.nba.models import HistoricalOddsSnapshot

    cutoff_time = datetime.now(UTC) + timedelta(hours=hours_ahead)

    games = db.query(Game).filter(
        and_(
            Game.status == 'scheduled',
            Game.game_date <= cutoff_time,
            Game.game_date >= datetime.now(UTC)
        )
    ).order_by(Game.game_date).all()

    games_with_odds = []
    for game in games:
        # Count opening odds snapshots
        opening_count = db.query(HistoricalOddsSnapshot).filter(
            and_(
                HistoricalOddsSnapshot.game_id == game.id,
                HistoricalOddsSnapshot.is_opening_line == True
            )
        ).count()

        if opening_count > 0:
            games_with_odds.append({
                "game_id": game.id,
                "game_date": game.game_date,
                "away_team": game.away_team,
                "home_team": game.home_team,
                "opening_odds_count": opening_count
            })

    return {
        "hours_ahead": hours_ahead,
        "games_found": len(games_with_odds),
        "games": games_with_odds
    }


@router.post("/capture")
async def capture_opening_odds(
    odds: List[OpeningOddsCapture],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Capture opening odds for player props.

    This endpoint should be called when odds first become available
    (typically 24-48 hours before game time) to establish the opening line.

    Args:
        odds: List of opening odds to capture
        background_tasks: FastAPI background tasks

    Returns:
        Summary of captured opening odds
    """
    service = OpeningOddsService(db)

    captured = []
    skipped = []

    for odd in odds:
        # Verify game exists
        game = db.query(Game).filter(Game.id == odd.game_id).first()
        if not game:
            skipped.append({"odd": odd.model_dump(), "reason": "Game not found"})
            continue

        # Verify player exists
        from app.models.nba.models import Player
        player = db.query(Player).filter(Player.id == odd.player_id).first()
        if not player:
            skipped.append({"odd": odd.model_dump(), "reason": "Player not found"})
            continue

        # Capture opening odds
        snapshot = service.capture_opening_odds(
            game_id=odd.game_id,
            player_id=odd.player_id,
            stat_type=odd.stat_type,
            bookmaker_name=odd.bookmaker_name,
            bookmaker_line=odd.bookmaker_line,
            over_price=odd.over_price,
            under_price=odd.under_price,
            was_starter=odd.was_starter
        )

        if snapshot:
            captured.append({
                "snapshot_id": snapshot.id,
                "player": player.name,
                "stat_type": odd.stat_type,
                "bookmaker": odd.bookmaker_name,
                "line": odd.bookmaker_line
            })
        else:
            skipped.append({
                "odd": odd.model_dump(),
                "reason": "Opening odds already exist"
            })

    return {
        "captured": len(captured),
        "skipped": len(skipped),
        "captured_details": captured,
        "skipped_details": skipped
    }


@router.get("/top-movements")
async def get_top_line_movements(
    hours_ahead: int = Query(24, description="Look ahead this many hours", ge=1, le=72),
    min_movement: float = Query(1.5, description="Minimum movement to show", ge=0.5),
    limit: int = Query(20, description="Max results to return", ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get the biggest line movements across all upcoming games.

    Useful for quickly identifying which props have seen the most
    significant market adjustments.

    Args:
        hours_ahead: How many hours ahead to look
        min_movement: Minimum line movement threshold
        limit: Maximum results to return

    Returns:
        List of props with biggest line movements
    """
    from sqlalchemy import desc, and_

    cutoff_time = datetime.now(UTC) + timedelta(hours=hours_ahead)

    # Get all snapshots with line movement data
    query = db.query(
        HistoricalOddsSnapshot.id,
        HistoricalOddsSnapshot.game_id,
        HistoricalOddsSnapshot.player_id,
        HistoricalOddsSnapshot.stat_type,
        HistoricalOddsSnapshot.bookmaker_name,
        HistoricalOddsSnapshot.bookmaker_line,
        HistoricalOddsSnapshot.line_movement,
        HistoricalOddsSnapshot.snapshot_time
    ).join(
        Game,
        HistoricalOddsSnapshot.game_id == Game.id
    ).filter(
        and_(
            Game.status == 'scheduled',
            Game.game_date <= cutoff_time,
            Game.game_date >= datetime.now(UTC),
            HistoricalOddsSnapshot.line_movement != 0
        )
    )

    # Filter by minimum movement
    if min_movement > 0:
        query = query.filter(
            HistoricalOddsSnapshot.line_movement >= min_movement
        )

    query = query.order_by(desc(HistoricalOddsSnapshot.line_movement)).limit(limit)

    snapshots = query.all()

    movements = []
    for snap in snapshots:
        player = db.query(HistoricalOddsSnapshot.player).filter(
            HistoricalOddsSnapshot.id == snap.player_id
        ).first()

        movements.append({
            "game_id": snap.game_id,
            "player": player.name if player else "Unknown",
            "player_id": snap.player_id,
            "team": player.team if player else "",
            "stat_type": snap.stat_type,
            "bookmaker": snap.bookmaker_name,
            "current_line": snap.bookmaker_line,
            "line_movement": snap.line_movement,
            "last_update": snap.snapshot_time
        })

    return {
        "hours_ahead": hours_ahead,
        "min_movement": min_movement,
        "movements": movements,
        "total": len(movements)
    }
