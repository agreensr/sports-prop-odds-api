"""
Injury tracking routes for NBA player prop predictions.

Provides access to injury data from ESPN and NBA official reports,
including injury context for prediction adjustments.
"""
import logging
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.models.nba.models import PlayerInjury, Player
from app.core.database import get_db
from app.services.nba.injury_service import InjuryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/injuries", tags=["injuries"])


class InjuryFetchResponse(BaseModel):
    """Response model for injury fetch operations."""
    success: bool
    message: str
    espn_count: int = 0
    nba_count: int = 0
    total_ingested: int = 0


def injury_to_dict(injury: PlayerInjury) -> dict:
    """Convert PlayerInjury model to dictionary."""
    return {
        "id": str(injury.id),
        "player": {
            "id": str(injury.player.id),
            "external_id": injury.player.external_id,
            "name": injury.player.name,
            "team": injury.player.team,
            "position": injury.player.position
        } if injury.player else None,
        "game_id": str(injury.game_id) if injury.game_id else None,
        "injury_type": injury.injury_type,
        "status": injury.status,
        "impact_description": injury.impact_description,
        "days_since_return": injury.days_since_return,
        "minutes_restriction": injury.minutes_restriction,
        "games_played_since_return": injury.games_played_since_return,
        "reported_date": injury.reported_date.isoformat() if injury.reported_date else None,
        "return_date": injury.return_date.isoformat() if injury.return_date else None,
        "external_source": injury.external_source,
        "created_at": injury.created_at.isoformat(),
        "updated_at": injury.updated_at.isoformat()
    }


@router.get("/")
async def get_injuries(
    team: Optional[str] = Query(None, description="Filter by team abbreviation"),
    days: int = Query(7, ge=1, le=30, description="Number of days to look back"),
    status: Optional[str] = Query(None, description="Filter by injury status"),
    db: Session = Depends(get_db)
):
    """
    Get active injuries from the database.

    Query Parameters:
    - team: Filter by team abbreviation (e.g., BOS, LAL)
    - days: Number of days to look back (default: 7, max: 30)
    - status: Filter by status (out, doubtful, questionable, day-to-day, returning)

    Returns list of injury records with player information.
    """
    injury_service = InjuryService(db)

    # Build status filter list
    status_filter = None
    if status:
        status_filter = [status]

    injuries = injury_service.get_active_injuries(
        team=team,
        days=days,
        status_filter=status_filter
    )

    return {
        "count": len(injuries),
        "team_filter": team,
        "days": days,
        "status_filter": status,
        "injuries": [injury_to_dict(i) for i in injuries]
    }


@router.get("/player/{player_id}")
async def get_player_injuries(
    player_id: str,
    db: Session = Depends(get_db)
):
    """
    Get injury history for a specific player.

    Returns all injury records for the player from the past 30 days.
    """
    # Look up player
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        # Try external_id lookup
        player = db.query(Player).filter(Player.external_id == player_id).first()

    if not player:
        raise HTTPException(status_code=404, detail=f"Player {player_id} not found")

    # Get injuries for player
    cutoff_date = date.today() - timedelta(days=30)
    injuries = db.query(PlayerInjury).filter(
        PlayerInjury.player_id == player.id,
        PlayerInjury.reported_date >= cutoff_date
    ).order_by(PlayerInjury.reported_date.desc()).all()

    return {
        "player": {
            "id": str(player.id),
            "external_id": player.external_id,
            "name": player.name,
            "team": player.team,
            "position": player.position
        },
        "injury_count": len(injuries),
        "injuries": [injury_to_dict(i) for i in injuries]
    }


@router.get("/context/{player_id}")
async def get_player_injury_context(
    player_id: str,
    game_id: Optional[str] = Query(None, description="Game ID for context"),
    db: Session = Depends(get_db)
):
    """
    Get injury context for a player including teammate injuries.

    This is the primary endpoint for prediction adjustments.

    Returns:
    - self_injury: Player's own injury status
    - teammate_injuries: List of injured teammates (usage boost opportunity)
    - impact_score: Overall impact on prediction (-1.0 to +1.0)
    - minutes_projection: Adjusted minutes based on injury context
    - confidence_adjustment: Confidence modifier
    """
    # Verify player exists
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        # Try external_id lookup
        player = db.query(Player).filter(Player.external_id == player_id).first()

    if not player:
        raise HTTPException(status_code=404, detail=f"Player {player_id} not found")

    injury_service = InjuryService(db)
    context = injury_service.get_player_injury_context(player_id, game_id)

    return {
        "player": {
            "id": str(player.id),
            "name": player.name,
            "team": player.team
        },
        "game_id": game_id,
        **context
    }


@router.post("/fetch")
async def fetch_injuries(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Trigger manual fetch of injury data from external sources.

    Fetches from:
    1. ESPN NBA News API
    2. NBA Official Injury Report (via Firecrawl)

    Runs in background to avoid blocking the response.
    """
    async def fetch_task():
        """Background task to fetch injuries."""
        injury_service = InjuryService(db)

        try:
            # Fetch from ESPN
            espn_articles = await injury_service.fetch_espn_injury_news(limit=50)
            logger.info(f"Fetched {len(espn_articles)} injury articles from ESPN")

            # Fetch from NBA official
            nba_injuries = await injury_service.fetch_nba_official_report()
            logger.info(f"Fetched {len(nba_injuries)} injuries from NBA official report")

            # Combine and ingest
            all_injuries = []

            # Parse ESPN articles for injury data
            for article in espn_articles:
                # Simple extraction - would need more sophisticated parsing
                headline = article.get("headline", "")
                description = article.get("description", "")

                # Try to extract player name and injury info
                # This is simplified - production would use NLP
                all_injuries.append({
                    "player_name": _extract_player_name_from_text(headline),
                    "injury_type": _extract_injury_type(headline, description),
                    "status": _extract_status_from_text(headline, description),
                    "description": description,
                    "source": "espn"
                })

            # Add NBA official injuries
            all_injuries.extend(nba_injuries)

            # Ingest to database
            ingested = injury_service.ingest_injuries(all_injuries)
            logger.info(f"Ingested {ingested} injuries to database")

        except Exception as e:
            logger.error(f"Error in injury fetch background task: {e}")

    # Schedule background task
    background_tasks.add_task(fetch_task)

    return InjuryFetchResponse(
        success=True,
        message="Injury fetch started in background"
    )


def _extract_player_name_from_text(text: str) -> str:
    """Extract player name from text - simplified version."""
    # This would need proper NLP in production
    # For now, return empty string
    return ""


def _extract_injury_type(headline: str, description: str) -> str:
    """Extract injury type from text."""
    combined = f"{headline} {description}".lower()

    injury_types = ["ankle", "knee", "hamstring", "concussion", "illness",
                    "back", "finger", "shoulder", "foot", "hip"]

    for injury_type in injury_types:
        if injury_type in combined:
            return injury_type

    return "unknown"


def _extract_status_from_text(headline: str, description: str) -> str:
    """Extract injury status from text."""
    combined = f"{headline} {description}".lower()

    if "out" in combined and "questionable" not in combined:
        return "out"
    elif "doubtful" in combined:
        return "doubtful"
    elif "questionable" in combined:
        return "questionable"
    elif "day-to-day" in combined or "day to day" in combined:
        return "day-to-day"
    elif "returning" in combined or "activated" in combined:
        return "returning"
    else:
        return "questionable"  # Default


@router.get("/stats/summary")
async def get_injury_stats(
    days: int = Query(7, ge=1, le=30, description="Number of days to look back"),
    db: Session = Depends(get_db)
):
    """
    Get injury statistics summary.

    Returns counts by team and status for the specified time period.
    """
    cutoff_date = date.today() - timedelta(days=days)

    # Get all injuries in the period
    injuries = db.query(PlayerInjury).filter(
        PlayerInjury.reported_date >= cutoff_date
    ).all()

    # Group by status
    by_status: dict = {}
    for injury in injuries:
        status = injury.status
        if status not in by_status:
            by_status[status] = 0
        by_status[status] += 1

    # Group by team
    by_team: dict = {}
    for injury in injuries:
        if injury.player:
            team = injury.player.team
            if team not in by_team:
                by_team[team] = 0
            by_team[team] += 1

    return {
        "period_days": days,
        "total_injuries": len(injuries),
        "by_status": by_status,
        "by_team": by_team
    }
