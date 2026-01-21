"""
Accuracy routes for prediction performance tracking.

Provides access to accuracy metrics, model drift detection, and
prediction resolution status.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.accuracy_service import AccuracyService
from app.services.boxscore_import_service import BoxscoreImportService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/accuracy", tags=["accuracy"])


@router.get("/overall")
async def get_overall_accuracy(
    model_version: Optional[str] = Query(None, description="Filter by model version (e.g., '1.0.0')"),
    days_back: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db: Session = Depends(get_db)
):
    """
    Get overall accuracy metrics across all stat types.

    Returns:
        - total_predictions: Total predictions in period
        - resolved_count: Number of predictions with actual results
        - mae: Mean Absolute Error (lower is better)
        - rmse: Root Mean Square Error (lower is better)
        - win_rate: Percentage of correct OVER/UNDER recommendations
        - recommendation_breakdown: Metrics for OVER vs UNDER
    """
    try:
        service = AccuracyService(db)
        metrics = service.calculate_overall_metrics(
            model_version=model_version,
            days_back=days_back
        )
        return metrics
    except Exception as e:
        logger.error(f"Error calculating overall accuracy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-stat-type")
async def get_accuracy_by_stat_type(
    model_version: Optional[str] = Query(None, description="Filter by model version"),
    days_back: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db: Session = Depends(get_db)
):
    """
    Get accuracy metrics broken down by stat type.

    Returns separate metrics for points, rebounds, assists, threes, etc.
    """
    try:
        service = AccuracyService(db)
        metrics = service.calculate_metrics_by_stat_type(
            model_version=model_version,
            days_back=days_back
        )
        return {
            "model_version": model_version,
            "days_back": days_back,
            "stat_types": metrics
        }
    except Exception as e:
        logger.error(f"Error calculating stat type accuracy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timeline")
async def get_accuracy_timeline(
    model_version: Optional[str] = Query(None, description="Filter by model version"),
    days_back: int = Query(30, ge=1, le=365, description="Total time period to analyze"),
    window_days: int = Query(1, ge=1, le=7, description="Size of each time window in days"),
    db: Session = Depends(get_db)
):
    """
    Get accuracy metrics over time for trend analysis.

    Useful for:
    - Visualizing performance trends
    - Detecting gradual model drift
    - Identifying sudden performance changes

    Returns a list of time-ordered metric snapshots.
    """
    try:
        service = AccuracyService(db)
        timeline = service.get_accuracy_timeline(
            model_version=model_version,
            days_back=days_back,
            window_days=window_days
        )
        return {
            "model_version": model_version,
            "days_back": days_back,
            "window_days": window_days,
            "timeline": timeline
        }
    except Exception as e:
        logger.error(f"Error getting accuracy timeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/drift-check")
async def check_model_drift(
    model_version: Optional[str] = Query(None, description="Filter by model version"),
    baseline_days: int = Query(30, ge=7, le=365, description="Baseline period size in days"),
    recent_days: int = Query(7, ge=1, le=30, description="Recent period size in days"),
    threshold: float = Query(0.10, ge=0.01, le=0.50, description="Drift detection threshold (e.g., 0.10 = 10%)"),
    db: Session = Depends(get_db)
):
    """
    Check for model performance drift.

    Compares recent performance to baseline and alerts if degradation
    exceeds the specified threshold.

    Alerts on:
    - MAE increase (predictions becoming less accurate)
    - RMSE increase (larger errors)
    - Win rate decrease (fewer correct recommendations)

    Returns:
        - drift_detected: Boolean indicating if drift was detected
        - baseline: Metrics from baseline period
        - recent: Metrics from recent period
        - changes: Percentage changes for each metric
        - alerts: List of alert messages if drift detected
    """
    try:
        service = AccuracyService(db)
        drift_result = service.detect_model_drift(
            model_version=model_version,
            baseline_days=baseline_days,
            recent_days=recent_days,
            threshold=threshold
        )
        return drift_result
    except Exception as e:
        logger.error(f"Error checking model drift: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/best-worst")
async def get_best_worst_predictions(
    model_version: Optional[str] = Query(None, description="Filter by model version"),
    days_back: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    limit: int = Query(10, ge=1, le=50, description="Number of results per category"),
    db: Session = Depends(get_db)
):
    """
    Get the best and worst predictions based on error magnitude.

    Useful for:
    - Understanding prediction outliers
    - Identifying patterns in good/bad predictions
    - Debugging model issues

    Returns:
        - best: Predictions with lowest error (most accurate)
        - worst: Predictions with highest error (least accurate)
    """
    try:
        service = AccuracyService(db)
        results = service.get_best_and_worst_predictions(
            model_version=model_version,
            days_back=days_back,
            limit=limit
        )
        return results
    except Exception as e:
        logger.error(f"Error getting best/worst predictions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-player")
async def get_accuracy_by_player(
    min_predictions: int = Query(5, ge=1, le=50, description="Minimum predictions to include player"),
    days_back: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db: Session = Depends(get_db)
):
    """
    Get accuracy metrics grouped by player.

    Shows which players the model predicts best/worst for.
    Only includes players with at least min_predictions resolved predictions.
    """
    try:
        service = AccuracyService(db)
        metrics = service.get_accuracy_by_player(
            min_predictions=min_predictions,
            days_back=days_back
        )
        return {
            "min_predictions": min_predictions,
            "days_back": days_back,
            "players": metrics
        }
    except Exception as e:
        logger.error(f"Error getting accuracy by player: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resolution-status")
async def get_resolution_status(db: Session = Depends(get_db)):
    """
    Get overall prediction resolution status.

    Returns:
        - total_predictions: Total predictions in database
        - resolved_predictions: Predictions with actual results
        - unresolved_predictions: Predictions still waiting for game results
        - resolution_rate: Percentage of predictions resolved
        - over_recommendations: Breakdown for OVER recommendations
        - under_recommendations: Breakdown for UNDER recommendations
        - win_rate: Overall win rate
    """
    try:
        service = BoxscoreImportService(db)
        status = service.get_resolution_status()
        return status
    except Exception as e:
        logger.error(f"Error getting resolution status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/unresolved-games")
async def get_unresolved_games(
    hours_back: int = Query(48, ge=1, le=168, description="Hours back to look"),
    db: Session = Depends(get_db)
):
    """
    Get list of completed games that haven't been resolved yet.

    Useful for:
    - Identifying games that need boxscore import
    - Monitoring resolution pipeline health
    - Finding missing data

    Returns list of games with:
        - id: Game database UUID
        - external_id: NBA.com game ID
        - away_team, home_team: Team abbreviations
        - game_date: ISO format datetime
        - unresolved_predictions: Count of unresolved predictions
    """
    try:
        service = BoxscoreImportService(db)
        games = service.get_unresolved_games(hours_back=hours_back)
        return {
            "hours_back": hours_back,
            "games": games,
            "count": len(games)
        }
    except Exception as e:
        logger.error(f"Error getting unresolved games: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resolve/{game_id}")
async def resolve_game_predictions(
    game_id: str,
    background_tasks: BackgroundTasks,
    dry_run: bool = Query(False, description="Simulate without making changes"),
    db: Session = Depends(get_db)
):
    """
    Manually trigger resolution of predictions for a specific game.

    Fetches boxscore from NBA API and resolves predictions with actual results.

    Use dry_run=True to test without making database changes.

    Returns resolution results including:
        - predictions_resolved: Number of predictions resolved
        - player_stats_created: New PlayerStats records created
        - player_stats_updated: Existing PlayerStats records updated
        - errors: Any errors encountered
    """
    try:
        service = BoxscoreImportService(db)

        if dry_run:
            result = await service.resolve_predictions_for_game(game_id, dry_run=True)
            return {
                "message": "Dry run complete - no changes made",
                "dry_run": True,
                **result
            }
        else:
            # Run in background
            def resolve_task():
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        service.resolve_predictions_for_game(game_id, dry_run=False)
                    )
                    db.commit()
                    logger.info(f"Background resolution complete: {result}")
                finally:
                    loop.close()

            background_tasks.add_task(resolve_task)

            return {
                "message": f"Resolution started for game {game_id}",
                "game_id": game_id
            }

    except Exception as e:
        logger.error(f"Error resolving game {game_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resolve-recent")
async def resolve_recent_predictions(
    hours_back: int = Query(48, ge=1, le=168, description="Hours back to look for completed games"),
    dry_run: bool = Query(False, description="Simulate without making changes"),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    Manually trigger resolution of predictions for recent completed games.

    Fetches boxscores for all completed games within the time window
    and resolves predictions with actual results.

    Use dry_run=True to test without making database changes.

    Returns resolution summary.
    """
    try:
        service = BoxscoreImportService(db)

        if dry_run:
            result = await service.resolve_predictions_for_completed_games(
                hours_back=hours_back,
                dry_run=True
            )
            return {
                "message": "Dry run complete - no changes made",
                "dry_run": True,
                **result
            }
        else:
            # Run in background
            def resolve_task():
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        service.resolve_predictions_for_completed_games(
                            hours_back=hours_back,
                            dry_run=False
                        )
                    )
                    db.commit()
                    logger.info(f"Background resolution complete: {result}")
                finally:
                    loop.close()

            background_tasks.add_task(resolve_task)

            return {
                "message": f"Resolution started for games in last {hours_back} hours",
                "hours_back": hours_back
            }

    except Exception as e:
        logger.error(f"Error resolving recent predictions: {e}")
        raise HTTPException(status_code=500, detail=str(e))
