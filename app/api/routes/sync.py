"""Sync API routes for data synchronization health and management.

Provides endpoints for:
- Sync health monitoring
- Manual sync triggers
- Reviewing unmatched games
- Querying matched data
"""
import logging
from datetime import date, datetime
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.sync.orchestrator import SyncOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])


def get_orchestrator(db: Session = Depends(get_db)) -> SyncOrchestrator:
    """Dependency to get sync orchestrator instance."""
    return SyncOrchestrator(db)


@router.get("/status")
async def get_sync_status(
    orchestrator: SyncOrchestrator = Depends(get_orchestrator)
) -> Dict:
    """
    Get overall sync health status dashboard.

    Returns aggregated status from all sync jobs including:
    - Health status (healthy, degraded, unhealthy)
    - Last sync times for each job type
    - Success/error counts
    - Unmatched games count
    - Low confidence matches count
    """
    return orchestrator.get_sync_status()


@router.get("/matched-games")
async def get_matched_games(
    game_date: Optional[date] = Query(None, description="Filter by specific date"),
    orchestrator: SyncOrchestrator = Depends(get_orchestrator)
) -> Dict:
    """
    Get games with verified nba+odds mapping.

    Args:
        game_date: Optional date filter

    Returns:
        List of matched games with confidence scores
    """
    games = orchestrator.get_matched_games(game_date=game_date)

    return {
        'count': len(games),
        'games': games
    }


@router.get("/players/{identifier}")
async def get_player_resolved(
    identifier: str,
    source: str = Query('odds_api', description="Source of the player name"),
    db: Session = Depends(get_db)
) -> Dict:
    """
    Get player with resolved identity across APIs.

    Uses the PlayerResolver to find the canonical nba_player_id
    for any player name from any source.

    Args:
        identifier: Player name or ID to resolve
        source: Source of the identifier (odds_api, espn, etc.)

    Returns:
        Player resolution info or error if not found
    """
    from app.services.sync.matchers.player_resolver import PlayerResolver

    resolver = PlayerResolver(db)

    # Try to resolve the player
    result = await resolver.resolve_player(
        player_name=identifier,
        source=source
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Player '{identifier}' not found in {source}"
        )

    return result


@router.post("/games")
async def trigger_sync_games(
    lookback_days: int = Query(7, ge=0, le=30, description="Days to look back"),
    lookahead_days: int = Query(14, ge=0, le=30, description="Days to look ahead"),
    background_tasks: BackgroundTasks = None,
    orchestrator: SyncOrchestrator = Depends(get_orchestrator)
) -> Dict:
    """
    Manually trigger sync for games.

    This will:
    1. Fetch games from nba_api
    2. Fetch odds from odds_api
    3. Match games via GameMatcher
    4. Store results in game_mappings

    For large syncs, consider running in background.

    Args:
        lookback_days: How many days back to sync
        lookahead_days: How many days ahead to sync

    Returns:
        Sync results with counts
    """
    try:
        results = await orchestrator.sync_games(
            lookback_days=lookback_days,
            lookahead_days=lookahead_days
        )

        return {
            'message': 'Games sync completed',
            'results': results
        }

    except Exception as e:
        logger.error(f"Manual games sync failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Games sync failed: {str(e)}"
        )


@router.post("/odds")
async def trigger_sync_odds(
    days: int = Query(7, ge=0, le=30, description="Days ahead to fetch"),
    background_tasks: BackgroundTasks = None,
    orchestrator: SyncOrchestrator = Depends(get_orchestrator)
) -> Dict:
    """
    Manually trigger sync for odds.

    Fetches current odds from The Odds API and caches them.

    Args:
        days: Number of days ahead to fetch

    Returns:
        Sync results
    """
    try:
        results = await orchestrator.sync_odds(days=days)

        return {
            'message': 'Odds sync completed',
            'results': results
        }

    except Exception as e:
        logger.error(f"Manual odds sync failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Odds sync failed: {str(e)}"
        )


@router.post("/player-stats")
async def trigger_sync_player_stats(
    games_limit: int = Query(50, ge=10, le=100, description="Number of games to average"),
    background_tasks: BackgroundTasks = None,
    orchestrator: SyncOrchestrator = Depends(get_orchestrator)
) -> Dict:
    """
    Manually trigger sync for player stats.

    Fetches per-36 stats for all active players from nba_api
    and caches them in player_season_stats table.

    Args:
        games_limit: Number of games to average

    Returns:
        Sync results
    """
    try:
        results = await orchestrator.sync_player_stats(games_limit=games_limit)

        return {
            'message': 'Player stats sync completed',
            'results': results
        }

    except Exception as e:
        logger.error(f"Manual player stats sync failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Player stats sync failed: {str(e)}"
        )


@router.post("/reconcile")
async def trigger_reconcile(
    limit: int = Query(100, ge=1, le=500, description="Max games to process"),
    background_tasks: BackgroundTasks = None,
    orchestrator: SyncOrchestrator = Depends(get_orchestrator)
) -> Dict:
    """
    Manually trigger match reconciliation.

    Re-attempts to match games that previously failed to match.

    Args:
        limit: Maximum number of games to process

    Returns:
        Reconciliation results
    """
    try:
        results = await orchestrator.reconcile_matches(limit=limit)

        return {
            'message': 'Reconciliation completed',
            'results': results
        }

    except Exception as e:
        logger.error(f"Manual reconciliation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Reconciliation failed: {str(e)}"
        )


@router.get("/queue")
async def get_manual_review_queue(
    orchestrator: SyncOrchestrator = Depends(get_orchestrator)
) -> Dict:
    """
    Get games and players requiring manual review.

    Returns:
        Lists of unmatched games and low confidence matches
    """
    return orchestrator.get_manual_review_queue()


@router.post("/validate-game/{game_id}")
async def validate_game_mapping(
    game_id: str,
    db: Session = Depends(get_db)
) -> Dict:
    """
    Validate that a game has properly matched data.

    Checks if the game mapping exists and meets confidence threshold.

    Args:
        game_id: The game ID (nba_game_id or odds_event_id)

    Returns:
        Validation result
    """
    from app.models.nba.models import GameMapping

    # Try to find by nba_game_id or odds_event_id
    mapping = db.query(GameMapping).filter(
        (GameMapping.nba_game_id == game_id) |
        (GameMapping.odds_event_id == game_id)
    ).first()

    if not mapping:
        return {
            'valid': False,
            'message': f'No mapping found for game_id {game_id}',
            'game_id': game_id
        }

    # Check confidence threshold
    is_valid = mapping.match_confidence >= 0.85 and mapping.status == 'matched'

    return {
        'valid': is_valid,
        'game_id': game_id,
        'nba_game_id': mapping.nba_game_id,
        'odds_event_id': mapping.odds_event_id,
        'match_confidence': float(mapping.match_confidence),
        'match_method': mapping.match_method,
        'status': mapping.status,
        'last_validated_at': mapping.last_validated_at.isoformat() if mapping.last_validated_at else None
    }
