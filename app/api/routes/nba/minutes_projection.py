"""
Minutes Projection API endpoints for enhanced player minutes forecasting.

These endpoints provide improved minutes projections that factor in:
- Game context (rest days, importance, back-to-back)
- Foul trouble risk (historical foul rate impacts minutes)
- Coach rotation patterns (how coaches distribute minutes)
- Score differential impact (game script affects rotations)

Key improvement: Instead of "starter = 30 minutes", we calculate dynamic
minutes based on multiple contextual factors.

Example:
Old: Starter → 30.0 minutes (fixed)
New: Starter, well-rested, no foul history → 31.5 minutes
New: Starter, back-to-back, high foul risk → 26.2 minutes
"""
import logging
from typing import List, Optional, Dict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.nba.models import Game, Player, ExpectedLineup
from app.services.nba.minutes_projection_service import MinutesProjectionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/minutes-projection", tags=["nba-minutes-projection"])


class MinutesProjectionRequest(BaseModel):
    """Request model for batch minutes projection."""
    game_id: str
    player_ids: List[str]
    verbose: bool = False


@router.get("/player/{player_id}/game/{game_id}")
async def get_player_minutes_projection(
    player_id: str,
    game_id: str,
    verbose: bool = Query(False, description="Include detailed factor breakdown"),
    db: Session = Depends(get_db)
):
    """
    Get enhanced minutes projection for a single player.

    Returns projected minutes with optional factor breakdown showing
    how each contextual factor affects the projection.

    Example breakdown:
    - Base minutes: 30.0 (starter role)
    - Game context: ×1.02 (well-rested, important game)
    - Foul trouble: ×0.98 (medium foul risk)
    - Coach pattern: ×1.00 (normal rotation)
    - Game script: ×1.00 (neutral)
    - Injury context: ×1.05 (2 teammates out)
    - Final: 30.0 × 1.02 × 0.98 × 1.00 × 1.00 × 1.05 = 31.5 minutes
    """
    service = MinutesProjectionService(db)

    # Verify player exists
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Verify game exists
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    projection = service.project_minutes(
        player_id=player_id,
        game_id=game_id,
        verbose=verbose
    )

    if "error" in projection:
        raise HTTPException(status_code=400, detail=projection["error"])

    return projection


@router.get("/game/{game_id}")
async def get_game_minutes_projections(
    game_id: str,
    verbose: bool = Query(False, description="Include detailed factor breakdowns"),
    db: Session = Depends(get_db)
):
    """
    Get enhanced minutes projections for all players in a game.

    Returns projected minutes sorted by minutes (descending), making it
    easy to see which players are expected to play the most.

    Use this to:
    - Identify which players will see significant minutes changes
    - Adjust predictions based on realistic playing time
    - Spot value in bench players getting extra run
    """
    service = MinutesProjectionService(db)

    # Verify game exists
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Get all players with expected lineups for this game
    lineups = db.query(ExpectedLineup).filter(
        ExpectedLineup.game_id == game_id
    ).all()

    player_ids = [lineup.player_id for lineup in lineups]

    if not player_ids:
        return {
            "game_id": game_id,
            "game_date": game.game_date,
            "away_team": game.away_team,
            "home_team": game.home_team,
            "projections": [],
            "total": 0
        }

    projections = service.batch_project_minutes(
        game_id=game_id,
        player_ids=player_ids,
        verbose=verbose
    )

    # Get player names
    players = db.query(Player).filter(
        Player.id.in_(player_ids)
    ).all()
    player_names = {p.id: p.name for p in players}

    # Format response
    formatted_projections = []
    for proj in projections:
        if not isinstance(proj, dict):
            continue

        formatted = {
            "player_id": proj.get("player_id"),
            "player_name": player_names.get(proj.get("player_id"), "Unknown"),
            "projected_minutes": proj.get("projected_minutes"),
            "confidence": proj.get("confidence")
        }

        if verbose:
            formatted["factors"] = proj.get("factors", {})

        formatted_projections.append(formatted)

    # Separate by team
    away_projections = [p for p in formatted_projections if p.get("player_id") in [l.player_id for l in lineups if l.team == game.away_team]]
    home_projections = [p for p in formatted_projections if p.get("player_id") in [l.player_id for l in lineups if l.team == game.home_team]]

    return {
        "game_id": game_id,
        "game_date": game.game_date,
        "away_team": game.away_team,
        "home_team": game.home_team,
        "away_projections": away_projections,
        "home_projections": home_projections,
        "total": len(formatted_projections)
    }


@router.get("/compare/{player_id}/game/{game_id}")
async def compare_minutes_projections(
    player_id: str,
    game_id: str,
    db: Session = Depends(get_db)
):
    """
    Compare improved vs simple (base) minutes projection.

    Shows the value add of the enhanced minutes projection model by
    displaying how much the projection changed when applying contextual
    factors.

    Useful for:
    - Validating the improvement over simple models
    - Understanding which factors affect minutes most
    - Identifying players with high minute variance
    """
    service = MinutesProjectionService(db)

    # Verify entities exist
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    comparison = service.get_minutes_comparison(player_id, game_id)

    if "error" in comparison:
        raise HTTPException(status_code=400, detail=comparison["error"])

    return comparison


@router.get("/foul-risk/{player_id}")
async def get_foul_trouble_risk(
    player_id: str,
    games_back: int = Query(20, description="Number of recent games to analyze", ge=5, le=50),
    db: Session = Depends(get_db)
):
    """
    Get foul trouble risk analysis for a player.

    Players with high foul trouble risk see fewer minutes and more
    volatility in their playing time.

    Risk levels:
    - HIGH: Average 5+ fouls or foul out rate ≥25% → 8% minutes reduction
    - MEDIUM: Average 3.5+ fouls or foul out rate ≥15% → 4% minutes reduction
    - LOW: Average 2.5+ fouls → 1% minutes reduction
    - MINIMAL: Below 2.5 fouls average → no reduction

    Args:
        player_id: Player ID to analyze
        games_back: Games to analyze for historical data

    Returns:
        Foul risk analysis with minutes penalty
    """
    from app.services.nba.minutes_projection_service import FoulTroubleAnalyzer

    # Verify player exists
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    risk = FoulTroubleAnalyzer.calculate_foul_risk(player_id, db, games_back)

    return {
        "player_id": player_id,
        "player_name": player.name,
        "team": player.team,
        "games_analyzed": risk.get("games_analyzed", 0),
        "risk_level": risk.get("risk_level", "unknown"),
        "avg_fouls": risk.get("avg_fouls"),
        "foul_out_rate": risk.get("foul_out_rate"),
        "minutes_penalty": risk.get("minutes_penalty", 1.0),
        "interpretation": _get_foul_risk_interpretation(risk)
    }


def _get_foul_risk_interpretation(risk: Dict) -> str:
    """Get human-readable interpretation of foul risk."""
    level = risk.get("risk_level", "unknown")
    foul_out_rate = risk.get("foul_out_rate", 0)

    if level == "high":
        return "High risk of foul trouble - expect 8% fewer minutes, high variance"
    elif level == "medium":
        return "Moderate foul risk - expect 4% fewer minutes, some variance"
    elif level == "low":
        return "Low foul risk - minimal impact on minutes"
    elif level == "minimal":
        return "Very low foul risk - unlikely to affect minutes"
    else:
        return "Insufficient data to assess foul risk"


@router.get("/team/{team}/rotation-pattern")
async def get_team_rotation_pattern(
    team: str,
    recent_games: int = Query(20, description="Recent games to analyze", ge=5, le=50),
    db: Session = Depends(get_db)
):
    """
    Get team rotation pattern analysis.

    Shows how the coach distributes minutes based on game context:
- Blowouts (15+ point diff): More bench players see action
- Close games (<5 point diff): Tighter rotations, stars play more
- Normal games: Standard rotation patterns

    Useful for understanding:
    - How many players typically see action
    - Which players benefit from blowouts
    - Coach's tendency to rest starters

    Args:
        team: Team abbreviation (e.g., "LAL", "BOS")
        recent_games: Number of recent games to analyze

    Returns:
        Rotation pattern statistics
    """
    from app.services.nba.minutes_projection_service import CoachRotationAnalyzer

    # Validate team format
    if len(team) != 3 or not team.isalpha():
        raise HTTPException(
            status_code=400,
            detail="Invalid team format. Use 3-letter abbreviation (e.g., LAL, BOS)"
        )

    pattern = CoachRotationAnalyzer.get_coach_rotation_pattern(team, db, recent_games)

    if "error" in pattern:
        return {
            "team": team,
            "error": pattern["error"],
            "note": "No recent game data found for analysis"
        }

    return {
        "team": team,
        "games_analyzed": pattern.get("total_games", 0),
        "blowout_games": pattern.get("blowout_count", 0),
        "close_games": pattern.get("close_game_count", 0),
        "normal_games": pattern.get("normal_count", 0),
        "rotation_patterns": {
            "blowout_rotation_players": pattern.get("blowout_rotation_players"),
            "close_game_rotation_players": pattern.get("close_game_rotation_players"),
            "avg_rotation_players": pattern.get("avg_rotation_players")
        },
        "interpretation": _get_rotation_interpretation(pattern)
    }


def _get_rotation_interpretation(pattern: Dict) -> str:
    """Get human-readable rotation pattern interpretation."""
    blowout_count = pattern.get("blowout_count", 0)
    close_count = pattern.get("close_game_count", 0)
    total = pattern.get("total_games", 0)

    if total == 0:
        return "No data available"

    blowout_pct = (blowout_count / total) * 100 if total > 0 else 0

    if blowout_pct >= 40:
        return "High blowout rate - expect deep rotations, bench players see more minutes"
    elif blowout_pct >= 25:
        return "Moderate blowout rate - some expanded rotations"
    elif close_count >= total * 0.5:
        return "Many close games - tight rotations, starters play more"
    else:
        return "Mixed game contexts - standard rotations expected"


@router.post("/batch")
async def batch_project_minutes(
    request: MinutesProjectionRequest,
    db: Session = Depends(get_db)
):
    """
    Batch project minutes for multiple players in a game.

    Efficiently calculates minutes projections for multiple players
    in a single API call. Useful for:
    - Updating predictions for all players in a game
    - Pre-game minutes analysis
    - Lineup optimization

    Request body:
    {
        "game_id": "uuid",
        "player_ids": ["uuid1", "uuid2", ...],
        "verbose": false
    }
    """
    service = MinutesProjectionService(db)

    # Verify game exists
    game = db.query(Game).filter(Game.id == request.game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    projections = service.batch_project_minutes(
        game_id=request.game_id,
        player_ids=request.player_ids,
        verbose=request.verbose
    )

    # Get player names
    players = db.query(Player).filter(
        Player.id.in_(request.player_ids)
    ).all()
    player_names = {p.id: p.name for p in players}

    # Format response
    formatted = []
    for proj in projections:
        if isinstance(proj, dict) and "error" not in proj:
            formatted.append({
                "player_id": proj.get("player_id"),
                "player_name": player_names.get(proj.get("player_id"), "Unknown"),
                "projected_minutes": proj.get("projected_minutes"),
                "confidence": proj.get("confidence")
            })

    return {
        "game_id": request.game_id,
        "total_players": len(request.player_ids),
        "projections": formatted
    }


@router.get("/upcoming-analysis")
async def analyze_upcoming_minutes(
    hours_ahead: int = Query(24, description="Analyze games within N hours", ge=1, le=72),
    min_minute_change: float = Query(2.0, description="Minimum minute change to flag", ge=0.5),
    db: Session = Depends(get_db)
):
    """
    Analyze upcoming games for significant minutes projection changes.

    Identifies players whose enhanced minutes projection differs
    significantly from the simple base minutes, indicating potential
    prediction adjustments needed.

    Example:
    - Player X: Base 30 min, Enhanced 26 min (-4 min)
    - Player Y: Base 14 min, Enhanced 20 min (+6 min)
    → Both players need prediction adjustments

    Args:
        hours_ahead: Hours ahead to look
        min_minute_change: Minimum minute difference to flag

    Returns:
        List of players with significant minute changes
    """
    service = MinutesProjectionService(db)

    from datetime import timedelta

    cutoff_time = datetime.now(datetime.UTC) + timedelta(hours=hours_ahead)

    # Get upcoming games
    games = db.query(Game).filter(
        and_(
            Game.status == 'scheduled',
            Game.game_date <= cutoff_time,
            Game.game_date >= datetime.now(datetime.UTC)
        )
    ).order_by(Game.game_date).limit(10).all()

    significant_changes = []

    for game in games:
        # Get lineups
        lineups = db.query(ExpectedLineup).filter(
            ExpectedLineup.game_id == game.id
        ).all()

        for lineup in lineups:
            # Get comparison
            comparison = service.get_minutes_comparison(lineup.player_id, game.id)

            if "error" not in comparison:
                diff = comparison.get("difference", 0)

                if abs(diff) >= min_minute_change:
                    significant_changes.append({
                        "game_id": game.id,
                        "game_date": game.game_date,
                        "player_id": comparison["player_id"],
                        "player_name": comparison["player_name"],
                        "base_minutes": comparison["base_minutes"],
                        "improved_minutes": comparison["improved_minutes"],
                        "difference": diff,
                        "confidence": comparison["confidence"],
                        "factors": comparison.get("factors_applied", [])
                    })

    # Sort by absolute difference
    significant_changes.sort(
        key=lambda x: abs(x["difference"]),
        reverse=True
    )

    return {
        "hours_ahead": hours_ahead,
        "min_minute_change": min_minute_change,
        "games_analyzed": len(games),
        "significant_changes": significant_changes,
        "total_changes": len(significant_changes)
    }
