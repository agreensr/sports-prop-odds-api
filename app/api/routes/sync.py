"""Sync API routes for data synchronization health and management.

Provides endpoints for:
- Scheduler control (start/stop/status)
- Sync health monitoring
- Manual sync triggers
- Reviewing unmatched games
- Querying matched data
- Triggering individual jobs
"""
import logging
from datetime import date, datetime
from typing import Dict, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.sync.orchestrator import SyncOrchestrator
from app.core.scheduler import get_scheduler

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


# ============================================================================
# SCHEDULER CONTROL ENDPOINTS
# ============================================================================

@router.get("/scheduler/status")
async def get_scheduler_status() -> Dict:
    """
    Get the current status of the automation scheduler.

    Returns:
        Scheduler status including running state and job list
    """
    scheduler = get_scheduler()

    if scheduler is None:
        return {
            'running': False,
            'message': 'Scheduler not initialized'
        }

    jobs = scheduler.scheduler.get_jobs() if scheduler.scheduler else []

    job_list = []
    for job in jobs:
        next_run = job.next_run_time
        job_list.append({
            'id': job.id,
            'name': job.name,
            'next_run': next_run.isoformat() if next_run else None,
            'trigger': str(job.trigger)
        })

    return {
        'running': scheduler.running,
        'jobs': job_list,
        'total_jobs': len(jobs)
    }


@router.post("/scheduler/start")
async def start_scheduler() -> Dict:
    """
    Start the automation scheduler.

    This will initialize all scheduled background tasks.

    Returns:
        Status message
    """
    from app.core.scheduler import start_scheduler

    if get_scheduler() is not None and get_scheduler().running:
        return {
            'message': 'Scheduler already running',
            'running': True
        }

    await start_scheduler()

    return {
        'message': 'Scheduler started successfully',
        'running': True
    }


@router.post("/scheduler/stop")
async def stop_scheduler() -> Dict:
    """
    Stop the automation scheduler.

    This will stop all scheduled background tasks.

    Returns:
        Status message
    """
    from app.core.scheduler import stop_scheduler

    if get_scheduler() is None or not get_scheduler().running:
        return {
            'message': 'Scheduler not running',
            'running': False
        }

    await stop_scheduler()

    return {
        'message': 'Scheduler stopped successfully',
        'running': False
    }


@router.post("/scheduler/jobs/trigger/{job_id}")
async def trigger_job(
    job_id: str,
    db: Session = Depends(get_db)
) -> Dict:
    """
    Manually trigger a scheduled job by ID.

    Available job IDs:
    - games_fetch: Fetch NBA games schedule
    - odds_fetch_game_time: Fetch odds (game hours)
    - odds_fetch_off_hours: Fetch odds (off hours)
    - player_stats_update: Update player stats
    - injury_fetch: Fetch injury data
    - lineup_fetch: Fetch lineup data
    - predictions_daily: Generate daily predictions
    - result_verification: Verify prediction results

    Args:
        job_id: The ID of the job to trigger

    Returns:
        Job execution result
    """
    scheduler = get_scheduler()

    if scheduler is None:
        raise HTTPException(
            status_code=400,
            detail='Scheduler not running. Start the scheduler first.'
        )

    # Find the job
    job = None
    for j in scheduler.scheduler.get_jobs():
        if j.id == job_id:
            job = j
            break

    if not job:
        raise HTTPException(
            status_code=404,
            detail=f'Job {job_id} not found'
        )

    # Trigger the job
    try:
        job.func()
        logger.info(f"✅ Manually triggered job: {job_id}")

        return {
            'message': f'Job {job_id} triggered successfully',
            'job_id': job_id,
            'job_name': job.name
        }

    except Exception as e:
        logger.error(f"❌ Failed to trigger job {job_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f'Job execution failed: {str(e)}'
        )


@router.get("/scheduler/jobs")
async def list_scheduled_jobs() -> Dict:
    """
    List all scheduled automation jobs with details.

    Returns:
        List of all scheduled jobs with their schedules and next run times
    """
    scheduler = get_scheduler()

    if scheduler is None:
        return {
            'running': False,
            'jobs': []
        }

    jobs = []

    for job in scheduler.scheduler.get_jobs():
        next_run = job.next_run_time

        # Parse trigger for human-readable schedule
        trigger_str = str(job.trigger)

        jobs.append({
            'id': job.id,
            'name': job.name,
            'trigger': trigger_str,
            'next_run': next_run.isoformat() if next_run else None,
            'last_run': None  # APScheduler doesn't track last run by default
        })

    return {
        'running': scheduler.running,
        'total_jobs': len(jobs),
        'jobs': jobs
    }


@router.get("/odds-api/quota")
async def get_odds_api_quota(db: Session = Depends(get_db)) -> Dict:
    """
    Get The Odds API quota status.

    Returns the current quota usage including:
    - requests_remaining: Requests left in current billing period
    - requests_used: Requests used in current billing period
    - monthly_quota: Total monthly quota (20,000 for paid plan)
    - quota_percentage: Percentage of quota used

    This endpoint makes a test API call to get fresh quota data.
    """
    from app.core.config import settings
    from app.services.core.odds_api_service import OddsApiService

    service = OddsApiService(api_key=settings.THE_ODDS_API_KEY)

    try:
        # Make a lightweight request to get fresh quota data
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.the-odds-api.com/v4/sports",
                params={"apiKey": settings.THE_ODDS_API_KEY},
                timeout=10.0
            )

            # Extract quota from headers
            remaining = response.headers.get('x-requests-remaining')
            used = response.headers.get('x-requests-used')

            if remaining and used:
                return {
                    "requests_remaining": int(remaining),
                    "requests_used": int(used),
                    "monthly_quota": 20000,
                    "quota_percentage": round((int(used) / 20000) * 100, 2),
                    "last_updated": datetime.utcnow().isoformat()
                }
            else:
                return {
                    "error": "Quota headers not found in response",
                    "status_code": response.status_code
                }
    except Exception as e:
        logger.error(f"Failed to fetch quota: {e}")
        return {
            "error": str(e),
            "message": "Failed to fetch quota from The Odds API"
        }

