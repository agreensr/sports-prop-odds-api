"""
Prediction routes with NBA.com external_id lookup support.

Provides access to AI-generated player prop predictions with odds pricing
from bookmakers.
"""
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request
from sqlalchemy.orm import Session, joinedload
from slowapi import Limiter

from app.models import Player, Game, Prediction, Base
from app.core.database import get_db
from app.core.config import settings
from app.services.nba.prediction_service import PredictionService
from app.services.core.odds_api_service import get_odds_service
from app.utils.timezone import format_game_time_eastern, utc_to_eastern

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/predictions", tags=["predictions"])

# Rate limiter - will be accessed via request.state
def get_limiter(request: Request) -> Limiter:
    """Get the rate limiter from app state."""
    return request.app.state.limiter


def check_request_limit(limiter: Limiter, request: Request, limit: str) -> tuple:
    """
    Check rate limit for the request.

    Note: This is a no-op wrapper. The actual rate limiting should be
    handled by @limiter.limit() decorators on route handlers.

    Returns an empty tuple for compatibility with existing code.
    """
    # No-op for now - rate limiting should be handled by decorators on the routes
    return ()


def prediction_to_dict(pred: Prediction) -> dict:
    """Convert Prediction model to dictionary with odds pricing and Eastern time."""
    # Convert game UTC time to Eastern Time for display
    eastern_time = utc_to_eastern(pred.game.game_date)

    return {
        "id": str(pred.id),
        "player": {
            "id": str(pred.player.id),
            "external_id": pred.player.external_id,
            "name": pred.player.name,
            "team": pred.player.team,
            "position": pred.player.position
        },
        "game": {
            "id": str(pred.game.id),
            "external_id": pred.game.external_id,
            "date_utc": pred.game.game_date.isoformat(),
            "date_est": eastern_time.isoformat(),
            "date_display": format_game_time_eastern(pred.game.game_date),
            "away_team": pred.game.away_team,
            "home_team": pred.game.home_team,
            "status": pred.game.status
        },
        "stat_type": pred.stat_type,
        "predicted_value": pred.predicted_value,
        "bookmaker_line": pred.bookmaker_line,
        "bookmaker_name": pred.bookmaker_name,
        "recommendation": pred.recommendation,
        "confidence": pred.confidence,
        "model_version": pred.model_version,
        # Odds pricing fields
        "over_price": pred.over_price,
        "under_price": pred.under_price,
        "odds_fetched_at": pred.odds_fetched_at.isoformat() if pred.odds_fetched_at else None,
        "odds_last_updated": pred.odds_last_updated.isoformat() if pred.odds_last_updated else None,
        "created_at": pred.created_at.isoformat()
    }


@router.get("/player/{player_id}")
async def get_player_predictions(
    request: Request,
    player_id: str,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get predictions for a player by database UUID.

    Rate limit: 10 requests per minute.

    Note: This is the original endpoint that requires the internal database UUID.
    For NBA.com ID lookup, use /api/predictions/player/nba/{nba_id}
    """
    # Apply rate limit for prediction endpoints
    limiter = get_limiter(request)
    check_request_limit(limiter, request, "10/minute")  # Rate limit check (no-op, use decorators instead)
    # Try exact match first (database stores IDs as VARCHAR, may have mixed formats)
    player = db.query(Player).filter(Player.id == player_id).first()

    # If not found and input looks like UUID, try the stringified version
    if not player:
        try:
            player_uuid = UUID(player_id)
            player = db.query(Player).filter(Player.id == str(player_uuid)).first()
        except ValueError:
            pass  # Not a UUID format, skip to external_id lookup

    # If still not found, try external_id as fallback
    if not player:
        logger.info(f"Player ID {player_id} not found, trying external_id lookup")
        player = db.query(Player).filter(Player.external_id == player_id).first()

    if not player:
        raise HTTPException(
            status_code=404,
            detail=f"Player {player_id} not found. Use /api/predictions/player/nba/{{nba_id}} for NBA.com ID lookup"
        )

    # OPTIMIZED: Eager load player and game to avoid N+1 queries
    predictions = (
        db.query(Prediction)
        .options(joinedload(Prediction.player), joinedload(Prediction.game))
        .filter(Prediction.player_id == player.id)
        .order_by(Prediction.created_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "player": {
            "id": str(player.id),
            "external_id": player.external_id,
            "name": player.name,
            "team": player.team,
            "position": player.position
        },
        "predictions": [prediction_to_dict(p) for p in predictions],
        "count": len(predictions)
    }


@router.get("/player/nba/{nba_id}")
async def get_player_predictions_by_nba_id(
    request: Request,
    nba_id: str,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get predictions for a player by NBA.com external_id.

    Rate limit: 10 requests per minute.

    Users can query using NBA.com player IDs (e.g., "2544" for LeBron James).

    Example: /api/predictions/player/nba/2544
    """
    # Apply rate limit for prediction endpoints
    limiter = get_limiter(request)
    check_request_limit(limiter, request, "10/minute")  # Rate limit check (no-op, use decorators instead)
    player = db.query(Player).filter(Player.external_id == nba_id).first()

    if not player:
        # Provide helpful error message
        raise HTTPException(
            status_code=404,
            detail=f"Player with NBA ID {nba_id} not found in database. "
                   f"The player may not have been imported from NBA.com yet. "
                   f"Use /api/players/search to find players."
        )

    # OPTIMIZED: Eager load player and game to avoid N+1 queries
    predictions = (
        db.query(Prediction)
        .options(joinedload(Prediction.player), joinedload(Prediction.game))
        .filter(Prediction.player_id == player.id)
        .order_by(Prediction.created_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "player": {
            "id": str(player.id),
            "external_id": player.external_id,
            "name": player.name,
            "team": player.team,
            "position": player.position
        },
        "predictions": [prediction_to_dict(p) for p in predictions],
        "count": len(predictions)
    }


@router.get("/game/{game_id}")
async def get_game_predictions(
    request: Request,
    game_id: str,
    db: Session = Depends(get_db)
):
    """
    Get all predictions for a specific game by database UUID.

    Rate limit: 10 requests per minute.
    """
    # Apply rate limit for prediction endpoints
    limiter = get_limiter(request)
    check_request_limit(limiter, request, "10/minute")  # Rate limit check (no-op, use decorators instead)
    # Try exact match first (database stores IDs as VARCHAR, may have mixed formats)
    game = db.query(Game).filter(Game.id == game_id).first()

    # If not found and input looks like UUID, try the stringified version
    if not game:
        try:
            game_uuid = UUID(game_id)
            game = db.query(Game).filter(Game.id == str(game_uuid)).first()
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid game ID format: {game_id}")

    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

    # OPTIMIZED: Eager load player and game to avoid N+1 queries
    predictions = (
        db.query(Prediction)
        .options(joinedload(Prediction.player), joinedload(Prediction.game))
        .filter(Prediction.game_id == game.id)
        .order_by(Prediction.confidence.desc())
        .all()
    )

    return {
        "game": {
            "id": str(game.id),
            "external_id": game.external_id,
            "date": game.game_date.isoformat(),
            "away_team": game.away_team,
            "home_team": game.home_team,
            "status": game.status
        },
        "predictions": [prediction_to_dict(p) for p in predictions],
        "count": len(predictions)
    }


@router.get("/game/nba/{nba_game_id}")
async def get_game_predictions_by_nba_id(
    request: Request,
    nba_game_id: str,
    db: Session = Depends(get_db)
):
    """
    Get all predictions for a game by NBA.com game ID.

    Rate limit: 10 requests per minute.

    Example: /api/predictions/game/nba/0022400001
    """
    # Apply rate limit for prediction endpoints
    limiter = get_limiter(request)
    check_request_limit(limiter, request, "10/minute")  # Rate limit check (no-op, use decorators instead)
    game = db.query(Game).filter(Game.external_id == nba_game_id).first()

    if not game:
        raise HTTPException(
            status_code=404,
            detail=f"Game with NBA ID {nba_game_id} not found in database"
        )

    # OPTIMIZED: Eager load player and game to avoid N+1 queries
    predictions = (
        db.query(Prediction)
        .options(joinedload(Prediction.player), joinedload(Prediction.game))
        .filter(Prediction.game_id == game.id)
        .order_by(Prediction.confidence.desc())
        .all()
    )

    return {
        "game": {
            "id": str(game.id),
            "external_id": game.external_id,
            "date": game.game_date.isoformat(),
            "away_team": game.away_team,
            "home_team": game.home_team,
            "status": game.status
        },
        "predictions": [prediction_to_dict(p) for p in predictions],
        "count": len(predictions)
    }


@router.get("/teams/{away_team}/{home_team}")
async def get_predictions_by_team_names(
    request: Request,
    away_team: str,
    home_team: str,
    db: Session = Depends(get_db)
):
    """
    Get predictions for a game by team abbreviations (case-insensitive).

    Rate limit: 10 requests per minute.

    Finds the most recent upcoming game matching the specified teams.
    Supports partial team name matching and various abbreviations.

    Example: /api/predictions/teams/LAL/BOS or /api/predictions/teams/lakers/celtics
    """
    # Apply rate limit for prediction endpoints
    limiter = get_limiter(request)
    check_request_limit(limiter, request, "10/minute")  # Rate limit check (no-op, use decorators instead)

    from sqlalchemy import or_

    # Normalize team names to uppercase
    away_team = away_team.upper()
    home_team = home_team.upper()

    # Team name mapping for common aliases
    TEAM_ALIASES = {
        "LAL": ["LAL", "LAKERS", "LOS ANGELES LAKERS", "LA LAKERS"],
        "BOS": ["BOS", "CELTICS", "BOSTON CELTICS"],
        "GSW": ["GSW", "WARRIORS", "GOLDEN STATE WARRIORS", "DUBS"],
        "MIA": ["MIA", "HEAT", "MIAMI HEAT"],
        "NYK": ["NYK", "KNICKS", "NEW YORK KNICKS", "NY"],
        "BKN": ["BKN", "NETS", "BROOKLYN NETS"],
        "PHI": ["PHI", "76ERS", "SIXERS", "PHILADELPHIA 76ERS"],
        "MIL": ["MIL", "BUCKS", "MILWAUKEE BUCKS"],
        "PHX": ["PHX", "SUNS", "PHOENIX SUNS"],
        "DAL": ["DAL", "MAVERICKS", "DALLAS MAVERICKS", "MAVS"],
        "LAC": ["LAC", "CLIPPERS", "LA CLIPPERS", "LOS ANGELES CLIPPERS"],
        "DEN": ["DEN", "NUGGETS", "DENVER NUGGETS"],
        "CLE": ["CLE", "CAVALIERS", "CLEVELAND CAVALIERS", "CAVS"],
        "TOR": ["TOR", "RAPTORS", "TORONTO RAPTORS"],
        "HOU": ["HOU", "ROCKETS", "HOUSTON ROCKETS"],
        "SAS": ["SAS", "SPURS", "SAN ANTONIO SPURS"],
        "IND": ["IND", "PACERS", "INDIANA PACERS"],
        "CHI": ["CHI", "BULLS", "CHICAGO BULLS"],
        "DET": ["DET", "PISTONS", "DETROIT PISTONS"],
        "ORL": ["ORL", "MAGIC", "ORLANDO MAGIC"],
        "ATL": ["ATL", "HAWKS", "ATLANTA HAWKS"],
        "CHA": ["CHA", "HORNETS", "CHARLOTTE HORNETS"],
        "WAS": ["WAS", "WIZARDS", "WASHINGTON WIZARDS"],
        "SAC": ["SAC", "KINGS", "SACRAMENTO KINGS"],
        "POR": ["POR", "TRAIL BLAZERS", "BLAZERS", "PORTLAND TRAIL BLAZERS"],
        "OKC": ["OKC", "THUNDER", "OKLAHOMA CITY THUNDER"],
        "MIN": ["MIN", "TIMBERWOLVES", "MINNESOTA TIMBERWOLVES", "WOLVES"],
        "UTA": ["UTA", "JAZZ", "UTAH JAZZ"],
        "MEM": ["MEM", "GRIZZLIES", "MEMPHIS GRIZZLIES"],
        "NOP": ["NOP", "PELICANS", "NEW ORLEANS PELICANS"],
        "SFO": ["SFO", "KINGS", "SACRAMENTO KINGS"],
    }

    # Normalize aliases to official abbreviations
    def normalize_team_name(team_input: str) -> str:
        team_input = team_input.upper()
        for official, aliases in TEAM_ALIASES.items():
            if team_input in aliases or team_input == official:
                return official
        return team_input  # Return as-is if no alias found

    away_team = normalize_team_name(away_team)
    home_team = normalize_team_name(home_team)

    # Find the most recent upcoming game for these teams
    game = (
        db.query(Game)
        .filter(
            or_(
                # away_team @ home_team
                (Game.away_team == away_team) & (Game.home_team == home_team),
                # home_team @ away_team (reverse order)
                (Game.away_team == home_team) & (Game.home_team == away_team)
            ),
            Game.game_date >= datetime.now() - timedelta(days=1)  # Include recent games
        )
        .order_by(Game.game_date.desc())
        .first()
    )

    if not game:
        raise HTTPException(
            status_code=404,
            detail=f"Game between {away_team} and {home_team} not found. "
                   f"Check team abbreviations or try /api/games to see upcoming games."
        )

    # OPTIMIZED: Eager load player and game to avoid N+1 queries
    predictions = (
        db.query(Prediction)
        .options(joinedload(Prediction.player), joinedload(Prediction.game))
        .filter(Prediction.game_id == game.id)
        .order_by(Prediction.confidence.desc())
        .all()
    )

    return {
        "game": {
            "id": str(game.id),
            "external_id": game.external_id,
            "date": game.game_date.isoformat(),
            "away_team": game.away_team,
            "home_team": game.home_team,
            "status": game.status
        },
        "predictions": [prediction_to_dict(p) for p in predictions],
        "count": len(predictions)
    }


@router.get("/top")
async def get_top_predictions(
    request: Request,
    min_confidence: float = Query(0.6, ge=0.0, le=1.0),
    stat_type: Optional[str] = Query(None),
    days_ahead: int = Query(1, ge=0, le=30),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get high-confidence predictions for upcoming games.

    Rate limit: 10 requests per minute.

    Args:
        min_confidence: Minimum confidence threshold (0.0 to 1.0)
        stat_type: Filter by stat type (points, rebounds, assists, etc.)
        days_ahead: How many days ahead to look (default: 1 = today only)
        limit: Maximum number of predictions to return
    """
    # Apply rate limit for prediction endpoints
    limiter = get_limiter(request)
    check_request_limit(limiter, request, "10/minute")  # Rate limit check (no-op, use decorators instead)

    # Use Central Time for date filtering (games in CST)
    from datetime import datetime, timezone, timedelta
    from app.utils.timezone import EASTERN_STANDARD_OFFSET, UTC

    # Get current time in Eastern Time
    now_utc = datetime.now(UTC)
    # EST is UTC-5
    now_eastern = now_utc + timedelta(hours=-5)
    # Convert to naive datetime for easier manipulation
    now_eastern_naive = now_eastern.replace(tzinfo=None)

    # Start of today in Eastern Time
    start_of_today_eastern = now_eastern_naive.replace(hour=0, minute=0, second=0, microsecond=0)

    # For today only (days_ahead=0), use end of today in Eastern Time
    # For days_ahead >= 1, include that many full days
    if days_ahead == 0:
        end_date_eastern = now_eastern_naive.replace(hour=23, minute=59, second=59, microsecond=999999)
    else:
        # Add days to today in Eastern Time
        end_date_eastern = (start_of_today_eastern + timedelta(days=days_ahead)).replace(hour=23, minute=59, second=59, microsecond=999999)

    # Convert Eastern Time boundaries to UTC for database comparison
    # EST is UTC-5, so to convert EST to UTC: add 5 hours
    start_date_utc = start_of_today_eastern + timedelta(hours=5)
    end_date_utc = end_date_eastern + timedelta(hours=5)

    # Make timezone-aware for comparison
    start_date_utc = start_date_utc.replace(tzinfo=timezone.utc)
    end_date_utc = end_date_utc.replace(tzinfo=timezone.utc)

    # OPTIMIZED: Eager load player and game to avoid N+1 queries
    query = (
        db.query(Prediction)
        .options(joinedload(Prediction.player), joinedload(Prediction.game))
        .join(Game)
        .filter(
            Prediction.confidence >= min_confidence,
            Game.game_date >= start_date_utc,
            Game.game_date <= end_date_utc
        )
        .order_by(Prediction.confidence.desc())
    )

    if stat_type:
        query = query.filter(Prediction.stat_type == stat_type.lower())

    predictions = query.limit(limit).all()

    return {
        "filters": {
            "min_confidence": min_confidence,
            "stat_type": stat_type,
            "date_range": f"{start_of_today_eastern.strftime('%Y-%m-%d')} to {end_date_eastern.strftime('%Y-%m-%d')}",
            "timezone": "Central Time (CST)"
        },
        "predictions": [prediction_to_dict(p) for p in predictions],
        "count": len(predictions)
    }


@router.get("/recent")
async def get_recent_predictions(
    request: Request,
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Get recently generated predictions.

    Rate limit: 10 requests per minute.

    Args:
        hours: How many hours back to look
        limit: Maximum number of predictions to return
    """
    # Apply rate limit for prediction endpoints
    limiter = get_limiter(request)
    check_request_limit(limiter, request, "10/minute")  # Rate limit check (no-op, use decorators instead)
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)

    # OPTIMIZED: Eager load player and game to avoid N+1 queries
    predictions = (
        db.query(Prediction)
        .options(joinedload(Prediction.player), joinedload(Prediction.game))
        .filter(Prediction.created_at >= cutoff_time)
        .order_by(Prediction.created_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "since": cutoff_time.isoformat(),
        "predictions": [prediction_to_dict(p) for p in predictions],
        "count": len(predictions)
    }


@router.get("/stat-types")
async def get_stat_types(request: Request, db: Session = Depends(get_db)):
    """
    Get available stat types with prediction counts.

    Rate limit: 60 requests per minute (general endpoint).
    """
    # Apply general rate limit
    limiter = get_limiter(request)
    check_request_limit(limiter, request, "60/minute")  # Rate limit check (no-op, use decorators instead)
    from sqlalchemy import func

    stat_types = (
        db.query(Prediction.stat_type, func.count(Prediction.id).label("count"))
        .group_by(Prediction.stat_type)
        .order_by(func.count(Prediction.id).desc())
        .all()
    )

    return {
        "stat_types": [
            {"type": st[0], "predictions_count": st[1]}
            for st in stat_types
        ]
    }


@router.post("/generate/upcoming")
async def generate_predictions_for_upcoming_games(
    days_ahead: int = Query(7, ge=1, le=30, description="Number of days ahead to generate predictions for"),
    stat_types: str = Query("points,rebounds,assists,threes", description="Comma-separated list of stat types"),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    Generate predictions for all upcoming games.

    Uses statistical heuristics based on player position and league averages
    to generate predicted values for player props.

    Args:
        days_ahead: How many days ahead to generate predictions for
        stat_types: Comma-separated stat types (points, rebounds, assists, threes)

    Returns:
        Summary of predictions generated
    """
    # Parse stat types
    stat_type_list = [s.strip() for s in stat_types.split(",")]

    # Get upcoming games
    start_date = date.today()
    end_date = start_date + timedelta(days=days_ahead)

    upcoming_games = (
        db.query(Game)
        .filter(
            Game.game_date >= start_date,
            Game.game_date <= end_date,
            Game.status == "scheduled"
        )
        .all()
    )

    if not upcoming_games:
        return {
            "message": "No upcoming games found",
            "predictions_generated": 0,
            "games_processed": 0
        }

    prediction_service = PredictionService(db)
    total_predictions = 0
    games_with_predictions = 0
    errors = []

    for game in upcoming_games:
        try:
            logger.info(f"Generating predictions for game {game.external_id}: {game.away_team} @ {game.home_team}")

            predictions = prediction_service.generate_predictions_for_game(
                game_id=str(game.id),
                stat_types=stat_type_list
            )

            if predictions:
                games_with_predictions += 1
                total_predictions += len(predictions)

        except Exception as e:
            logger.error(f"Error generating predictions for game {game.external_id}: {e}")
            errors.append({
                "game_id": game.external_id,
                "error": str(e)
            })

    return {
        "message": f"Generated predictions for {games_with_predictions} upcoming games",
        "predictions_generated": total_predictions,
        "games_processed": len(upcoming_games),
        "games_with_predictions": games_with_predictions,
        "stat_types": stat_type_list,
        "errors": errors
    }


# ============================================================================
# ENHANCED PREDICTIONS WITH REAL ODDS API INTEGRATION
# ============================================================================

@router.get("/enhanced/game/{game_id}")
async def get_enhanced_predictions_for_game(
    request: Request,
    game_id: str,
    stat_types: str = Query("points,rebounds,assists,threes", description="Comma-separated stat types"),
    bookmaker: str = Query("draftkings", description="Preferred bookmaker"),
    db: Session = Depends(get_db)
):
    """
    Get enhanced predictions with REAL odds from Odds API.

    This endpoint uses the Enhanced Prediction Service which:
    1. Fetches real-time bookmaker lines from The Odds API
    2. Compares AI projections to actual lines
    3. Provides OVER/UNDER/PASS recommendations based on edge

    Rate limit: 10 requests per minute.

    Args:
        game_id: Game database UUID
        stat_types: Comma-separated stat types (points, rebounds, assists, threes)
        bookmaker: Preferred bookmaker for line data

    Returns:
        List of enhanced predictions with real line data
    """
    from app.services.nba.enhanced_prediction_service import EnhancedPredictionService

    # Try exact match first
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        try:
            game_uuid = UUID(game_id)
            game = db.query(Game).filter(Game.id == str(game_uuid)).first()
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid game ID format: {game_id}")

    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

    # Parse stat types
    stat_type_list = [s.strip() for s in stat_types.split(",") if s.strip()]

    # Initialize odds service if API key is available
    odds_service = None
    if settings.THE_ODDS_API_KEY:
        try:
            odds_service = get_odds_service(settings.THE_ODDS_API_KEY)
            logger.info("Odds API service initialized for enhanced predictions")
        except Exception as e:
            logger.warning(f"Failed to initialize odds service: {e}")

    # Initialize enhanced prediction service
    prediction_service = EnhancedPredictionService(
        db=db,
        odds_api_service=odds_service
    )

    # Generate predictions
    predictions = prediction_service.generate_prop_predictions(
        game_id=game_id,
        stat_types=stat_type_list,
        bookmaker=bookmaker
    )

    # Get game info for response
    eastern_time = utc_to_eastern(game.game_date)

    return {
        "game": {
            "id": str(game.id),
            "external_id": game.external_id,
            "date_utc": game.game_date.isoformat(),
            "date_est": eastern_time.isoformat(),
            "date_display": format_game_time_eastern(game.game_date),
            "away_team": game.away_team,
            "home_team": game.home_team,
            "status": game.status
        },
        "odds_source": "live" if odds_service else "estimated",
        "predictions": predictions,
        "count": len(predictions),
        "stat_types": stat_type_list
    }


@router.post("/enhanced/generate")
async def generate_enhanced_predictions(
    request: Request,
    days_ahead: int = Query(7, ge=1, le=30, description="Number of days ahead"),
    stat_types: str = Query("points,rebounds,assists,threes", description="Comma-separated stat types"),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    Generate enhanced predictions with REAL odds for upcoming games.

    This endpoint:
    1. Finds all upcoming games
    2. Fetches real-time odds from The Odds API
    3. Generates AI projections
    4. Compares projections to lines to find edges

    Rate limit: 5 requests per hour (due to external API usage).

    Args:
        days_ahead: How many days ahead to generate predictions for
        stat_types: Comma-separated stat types

    Returns:
        Summary of enhanced predictions generated
    """
    from app.services.nba.enhanced_prediction_service import EnhancedPredictionService

    # Parse stat types
    stat_type_list = [s.strip() for s in stat_types.split(",") if s.strip()]

    # Get upcoming games
    start_date = date.today()
    end_date = start_date + timedelta(days=days_ahead)

    upcoming_games = (
        db.query(Game)
        .filter(
            Game.game_date >= start_date,
            Game.game_date <= end_date,
            Game.status == "scheduled"
        )
        .all()
    )

    if not upcoming_games:
        return {
            "message": "No upcoming games found",
            "predictions_generated": 0,
            "games_processed": 0,
            "odds_source": "none"
        }

    # Initialize odds service if API key is available
    odds_service = None
    odds_source = "estimated"

    if settings.THE_ODDS_API_KEY:
        try:
            odds_service = get_odds_service(settings.THE_ODDS_API_KEY)
            odds_source = "live"
            logger.info("Odds API service initialized for enhanced predictions")
        except Exception as e:
            logger.warning(f"Failed to initialize odds service: {e}")

    # Initialize enhanced prediction service
    prediction_service = EnhancedPredictionService(
        db=db,
        odds_api_service=odds_service
    )

    # Generate predictions for each game
    all_predictions = []
    games_with_predictions = 0
    total_predictions = 0
    errors = []

    for game in upcoming_games:
        try:
            logger.info(
                f"Generating enhanced predictions for game {game.external_id}: "
                f"{game.away_team} @ {game.home_team}"
            )

            predictions = prediction_service.generate_prop_predictions(
                game_id=str(game.id),
                stat_types=stat_type_list
            )

            if predictions:
                games_with_predictions += 1
                total_predictions += len(predictions)
                all_predictions.extend(predictions)

        except Exception as e:
            logger.error(
                f"Error generating enhanced predictions for game {game.external_id}: {e}"
            )
            errors.append({
                "game_id": game.external_id,
                "error": str(e)
            })

    return {
        "message": f"Generated enhanced predictions for {games_with_predictions} upcoming games",
        "predictions_generated": total_predictions,
        "games_processed": len(upcoming_games),
        "games_with_predictions": games_with_predictions,
        "stat_types": stat_type_list,
        "odds_source": odds_source,
        "errors": errors
    }


# ============================================================================
# ENSEMBLE PREDICTIONS WITH ML, CALIBRATION & DYNAMIC WEIGHTING
# ============================================================================


# ============================================================================
# ENSEMBLE PREDICTIONS WITH ML, CALIBRATION & DYNAMIC WEIGHTING  
# ============================================================================

@router.get("/ensemble/player/{player_id}")
async def get_ensemble_prediction_for_player(
    request: Request,
    player_id: str,
    game_id: str,
    stat_type: str = Query("points", description="Stat type to predict"),
    db: Session = Depends(get_db)
):
    from app.services.nba.ensemble_prediction_service import create_ensemble_service
    from app.services.nba.calibration_service import CalibrationService
    
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        player = db.query(Player).filter(Player.external_id == player_id).first()
        if not player:
            raise HTTPException(status_code=404, detail=f"Player {player_id} not found")
    
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")
    
    ensemble = create_ensemble_service(db)
    calibration = CalibrationService(db)
    player_tier = calibration.get_player_tier(player_id)
    
    result = ensemble.predict(player_id, game_id, stat_type)
    
    result["player"] = {
        "id": str(player.id),
        "external_id": player.external_id,
        "name": player.name,
        "team": player.team,
        "position": player.position
    }
    
    result["game"] = {
        "id": str(game.id),
        "external_id": game.external_id,
        "date_utc": game.game_date.isoformat(),
        "away_team": game.away_team,
        "home_team": game.home_team,
        "status": game.status
    }
    
    result["player_tier"] = player_tier
    result["model_version"] = "ensemble-v1.0"
    
    return result


@router.get("/ensemble/game/{game_id}")
async def get_ensemble_predictions_for_game(
    request: Request,
    game_id: str,
    stat_types: str = Query("points,rebounds,assists,threes"),
    min_confidence: float = Query(0.50, ge=0.0, le=1.0),
    db: Session = Depends(get_db)
):
    from app.services.nba.ensemble_prediction_service import create_ensemble_service
    from app.services.nba.calibration_service import CalibrationService, PLAYER_TIERS
    from sqlalchemy import or_
    
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        try:
            game_uuid = UUID(game_id)
            game = db.query(Game).filter(Game.id == str(game_uuid)).first()
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid game ID: {game_id}")
    
    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")
    
    stat_type_list = [s.strip().lower() for s in stat_types.split(",") if s.strip()]
    
    players = (
        db.query(Player)
        .filter(
            or_(
                Player.team == game.away_team,
                Player.team == game.home_team
            ),
            Player.active == True
        )
        .all()
    )
    
    if not players:
        return {
            "game": {
                "id": str(game.id),
                "external_id": game.external_id,
                "away_team": game.away_team,
                "home_team": game.home_team
            },
            "predictions": [],
            "count": 0
        }
    
    ensemble = create_ensemble_service(db)
    calibration = CalibrationService(db)
    
    all_predictions = []
    
    for player in players:
        for stat_type in stat_type_list:
            try:
                result = ensemble.predict(str(player.id), str(game.id), stat_type)
                
                if result["confidence"] >= min_confidence:
                    result["player"] = {
                        "id": str(player.id),
                        "external_id": player.external_id,
                        "name": player.name,
                        "team": player.team,
                        "position": player.position
                    }
                    
                    player_tier = calibration.get_player_tier(str(player.id))
                    result["player_tier"] = player_tier
                    result["tier_description"] = PLAYER_TIERS[player_tier]["description"]
                    result["game_id"] = str(game.id)
                    result["stat_type"] = stat_type
                    
                    all_predictions.append(result)
                    
            except Exception as e:
                logger.debug(f"Error: {e}")
                continue
    
    all_predictions.sort(key=lambda x: x["confidence"], reverse=True)
    
    return {
        "game": {
            "id": str(game.id),
            "external_id": game.external_id,
            "date_utc": game.game_date.isoformat(),
            "away_team": game.away_team,
            "home_team": game.home_team,
            "status": game.status
        },
        "filters": {
            "stat_types": stat_type_list,
            "min_confidence": min_confidence
        },
        "predictions": all_predictions,
        "count": len(all_predictions),
        "model_version": "ensemble-v1.0"
    }


@router.get("/ensemble/top")
async def get_top_ensemble_predictions(
    request: Request,
    min_confidence: float = Query(0.60, ge=0.0, le=1.0),
    stat_type: Optional[str] = Query(None),
    days_ahead: int = Query(1, ge=0, le=7),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db)
):
    from app.services.nba.ensemble_prediction_service import create_ensemble_service
    from app.services.nba.calibration_service import CalibrationService, PLAYER_TIERS
    from datetime import timezone, timedelta
    from sqlalchemy import or_
    
    now_utc = datetime.now(timezone.utc)
    end_date_utc = now_utc + timedelta(days=days_ahead)
    
    upcoming_games = (
        db.query(Game)
        .filter(
            Game.game_date >= now_utc,
            Game.game_date <= end_date_utc,
            Game.status == "scheduled"
        )
        .all()
    )
    
    if not upcoming_games:
        return {
            "filters": {
                "min_confidence": min_confidence,
                "stat_type": stat_type,
                "days_ahead": days_ahead
            },
            "predictions": [],
            "count": 0
        }
    
    ensemble = create_ensemble_service(db)
    calibration = CalibrationService(db)
    
    stat_types = [stat_type] if stat_type else ["points", "rebounds", "assists", "threes"]
    
    all_predictions = []
    
    for game in upcoming_games:
        players = (
            db.query(Player)
            .filter(
                or_(
                    Player.team == game.away_team,
                    Player.team == game.home_team
                ),
                Player.active == True
            )
            .all()
        )
        
        for player in players:
            for stat in stat_types:
                try:
                    result = ensemble.predict(str(player.id), str(game.id), stat)
                    
                    if result["confidence"] >= min_confidence:
                        result["player"] = {
                            "id": str(player.id),
                            "external_id": player.external_id,
                            "name": player.name,
                            "team": player.team,
                            "position": player.position
                        }
                        
                        eastern_time = utc_to_eastern(game.game_date)
                        result["game"] = {
                            "id": str(game.id),
                            "external_id": game.external_id,
                            "date_utc": game.game_date.isoformat(),
                            "date_display": format_game_time_eastern(game.game_date),
                            "away_team": game.away_team,
                            "home_team": game.home_team
                        }
                        
                        player_tier = calibration.get_player_tier(str(player.id))
                        result["player_tier"] = player_tier
                        result["tier_description"] = PLAYER_TIERS[player_tier]["description"]
                        
                        all_predictions.append(result)
                        
                except Exception as e:
                    logger.debug(f"Error: {e}")
                    continue
    
    all_predictions.sort(key=lambda x: x["confidence"], reverse=True)
    top_predictions = all_predictions[:limit]
    
    return {
        "filters": {
            "min_confidence": min_confidence,
            "stat_type": stat_type,
            "days_ahead": days_ahead
        },
        "predictions": top_predictions,
        "count": len(top_predictions),
        "model_version": "ensemble-v1.0"
    }


@router.get("/ensemble/info")
async def get_ensemble_info(request: Request, db: Session = Depends(get_db)):
    from app.services.nba.ensemble_prediction_service import create_ensemble_service
    from app.services.nba.calibration_service import CalibrationService, PLAYER_TIERS, STAT_CALIBRATION
    from app.services.nba.xgboost_prediction_service import FEATURE_COLUMNS
    
    ensemble = create_ensemble_service(db)
    calibration = CalibrationService(db)
    
    return {
        "ensemble": ensemble.get_ensemble_info(),
        "player_tiers": {
            tier: {
                "min_pts_per_36": config["min_pts_per_36"],
                "calibration": config["calibration_multiplier"],
                "confidence_boost": config["confidence_boost"],
                "description": config["description"]
            }
            for tier, config in PLAYER_TIERS.items()
        },
        "stat_calibration": STAT_CALIBRATION,
        "xgboost_features": FEATURE_COLUMNS,
        "calibration_target": "<5% ECE",
        "research_basis": "Walsh and Joshi (2024): Calibration-based ROI +34.69% vs accuracy-based -35.17%"
    }
