"""
Historical Odds API Routes.

Provides endpoints for:
- Hit rate queries (how often players hit their lines)
- Batch hit rate retrieval (for multiple players)
- Historical odds backfill triggers
- Comprehensive player reports

Hit rates are used to weight prediction confidence based on
historical performance against betting lines.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.nba.historical_odds_service import HistoricalOddsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/historical-odds", tags=["historical-odds"])


class BatchHitRateRequest(BaseModel):
    """Request model for batch hit rate queries."""
    player_ids: List[str]
    stat_types: List[str]
    games_back: int = 10


@router.get("/hit-rate/{player_id}")
async def get_player_hit_rate(
    player_id: str,
    stat_type: str = Query(..., description="Stat type: points, rebounds, assists, threes"),
    bookmaker: Optional[str] = Query(None, description="Filter by bookmaker (FanDuel, DraftKings, etc.)"),
    games_back: int = Query(10, description="Number of recent games to analyze", ge=1, le=50),
    starters_only: bool = Query(True, description="Only include games as starter"),
    db: Session = Depends(get_db)
):
    """
    Get hit rate for a player.

    Returns hit rate data showing how often player hits OVER.

    Example response:
    ```json
    {
        "hit_rate": 0.667,
        "total_games": 12,
        "over_hits": 8,
        "under_hits": 3,
        "pushes": 1,
        "sample_size_adjective": "moderate"
    }
    ```

    Example: "LeBron James has hit his assist over/under 8 out of 12 games (66.7%)"
    """
    if stat_type not in ["points", "rebounds", "assists", "threes"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid stat_type: {stat_type}. Must be one of: points, rebounds, assists, threes"
        )

    service = HistoricalOddsService(db)
    hit_rate_data = service.get_player_hit_rate(
        player_id=player_id,
        stat_type=stat_type,
        bookmaker_name=bookmaker,
        games_back=games_back,
        starters_only=starters_only
    )

    return hit_rate_data


@router.post("/batch-hit-rates")
async def get_batch_hit_rates(
    request: BatchHitRateRequest,
    db: Session = Depends(get_db)
):
    """
    Get hit rates for multiple players at once.

    Useful for generating predictions for multiple players.

    Example request:
    ```json
    {
        "player_ids": ["uuid1", "uuid2", "uuid3"],
        "stat_types": ["points", "assists"],
        "games_back": 10
    }
    ```

    Returns nested dict with hit rates for each player/stat combination.
    """
    if len(request.player_ids) > 50:
        raise HTTPException(
            status_code=400,
            detail="Cannot query more than 50 players at once"
        )

    if len(request.stat_types) > 4:
        raise HTTPException(
            status_code=400,
            detail="Cannot query more than 4 stat types at once"
        )

    service = HistoricalOddsService(db)
    hit_rates = service.get_batch_hit_rates(
        player_ids=request.player_ids,
        stat_types=request.stat_types,
        games_back=request.games_back
    )

    return hit_rates


@router.post("/backfill")
async def trigger_backfill(
    games_limit: int = Query(5, description="Max games to process", ge=1, le=20),
    starters_only: bool = Query(True, description="Only capture odds for starters"),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    Trigger historical odds backfill.

    Fetches odds from completed games and resolves with actual results.
    Runs in the background if background_tasks provided.

    This endpoint should be called periodically (e.g., via cron) to
    populate historical odds data for hit rate calculation.
    """
    service = HistoricalOddsService(db)

    if background_tasks:
        # Run in background
        background_tasks.add_task(service.backfill_recent_games, games_limit, starters_only)
        return {
            "message": "Backfill started in background",
            "games_limit": games_limit
        }

    # Run synchronously (for testing)
    result = await service.backfill_recent_games(games_limit=games_limit, starters_only=starters_only)

    return {
        "message": "Backfill complete",
        "result": result
    }


@router.get("/player-report/{player_id}")
async def get_player_report(
    player_id: str,
    games_back: int = Query(10, description="Number of recent games", ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Get comprehensive hit rate report for a player.

    Returns hit rates for all stat types (points, rebounds, assists, threes).

    Example response:
    ```json
    {
        "player_id": "uuid",
        "games_back": 10,
        "hit_rates": {
            "points": {"hit_rate": 0.667, "total_games": 12, "over_hits": 8, ...},
            "rebounds": {"hit_rate": 0.500, "total_games": 10, "over_hits": 5, ...},
            "assists": {"hit_rate": 0.800, "total_games": 15, "over_hits": 12, ...},
            "threes": {"hit_rate": 0.400, "total_games": 10, "over_hits": 4, ...}
        }
    }
    ```
    """
    service = HistoricalOddsService(db)
    report = service.get_player_report(player_id=player_id, games_back=games_back)

    return report


@router.post("/capture/{game_id}")
async def capture_game_odds(
    game_id: str,
    starters_only: bool = Query(True, description="Only capture odds for starters"),
    db: Session = Depends(get_db)
):
    """
    Capture odds snapshots for a specific game.

    Fetches player props from The Odds API and stores them
    as historical odds snapshots.

    Typically called:
    - Pre-game: To capture opening odds
 - Post-game: As part of backfill process
    """
    from app.models import Game

    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

    service = HistoricalOddsService(db)
    result = await service.batch_capture_game_odds(
        game_id=game_id,
        starters_only=starters_only
    )

    return {
        "game_id": game_id,
        "game": f"{game.away_team} @ {game.home_team}",
        "captured": result.get("captured", 0),
        "errors": result.get("errors", 0)
    }


@router.post("/resolve/{game_id}")
async def resolve_game_snapshots(
    game_id: str,
    db: Session = Depends(get_db)
):
    """
    Resolve odds snapshots for a game with actual results.

    Updates snapshots with hit_result (OVER, UNDER, PUSH) based on
    actual boxscore statistics.

    Should be called after games are completed and boxscores are available.
    """
    from app.models import Game

    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

    service = HistoricalOddsService(db)
    result = service.resolve_snapshots_for_game(game_id=game_id)

    return {
        "game_id": game_id,
        "game": f"{game.away_team} @ {game.home_team}",
        "resolved": result.get("resolved", 0),
        "errors": result.get("errors", 0)
    }


@router.get("/stats")
async def get_historical_odds_stats(
    db: Session = Depends(get_db)
):
    """
    Get statistics about historical odds data.

    Returns counts of snapshots, resolution rates, and data coverage.
    """
    from app.models import HistoricalOddsSnapshot
    from sqlalchemy import func

    # Total snapshots
    total_snapshots = db.query(HistoricalOddsSnapshot).count()

    # Resolved snapshots
    resolved_snapshots = db.query(HistoricalOddsSnapshot).filter(
        HistoricalOddsSnapshot.hit_result.isnot(None)
    ).count()

    # Unresolved snapshots
    unresolved_snapshots = total_snapshots - resolved_snapshots

    # Breakdown by hit result
    hit_results = db.query(
        HistoricalOddsSnapshot.hit_result,
        func.count(HistoricalOddsSnapshot.id)
    ).filter(
        HistoricalOddsSnapshot.hit_result.isnot(None)
    ).group_by(HistoricalOddsSnapshot.hit_result).all()

    hit_result_counts = {result[0]: result[1] for result in hit_results}

    # Breakdown by stat type
    stat_types = db.query(
        HistoricalOddsSnapshot.stat_type,
        func.count(HistoricalOddsSnapshot.id)
    ).group_by(HistoricalOddsSnapshot.stat_type).all()

    stat_type_counts = {stat[0]: stat[1] for stat in stat_types}

    # Breakdown by bookmaker
    bookmakers = db.query(
        HistoricalOddsSnapshot.bookmaker_name,
        func.count(HistoricalOddsSnapshot.id)
    ).group_by(HistoricalOddsSnapshot.bookmaker_name).all()

    bookmaker_counts = {bm[0]: bm[1] for bm in bookmakers}

    return {
        "total_snapshots": total_snapshots,
        "resolved_snapshots": resolved_snapshots,
        "unresolved_snapshots": unresolved_snapshots,
        "resolution_rate": round(resolved_snapshots / total_snapshots, 3) if total_snapshots > 0 else 0,
        "hit_results": hit_result_counts,
        "stat_types": stat_type_counts,
        "bookmakers": bookmaker_counts
    }
