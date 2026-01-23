"""
Data fetching routes using HYBRID APPROACH (The Odds API + Sport APIs).

HYBRID ARCHITECTURE:
- The Odds API: Game schedule and betting odds (primary schedule source)
- Sport-specific APIs (NBA, NFL, etc.): Player statistics and historical data

This approach provides:
- Accurate scheduling with proper timezone handling
- Consistent multi-sport support
- Rich player statistics for ML predictions
"""
import asyncio
import logging
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session

from app.models.nba.models import Game, Player, Prediction
from app.services.nba.nba_service import NBAService
from app.services.core.odds_api_service import get_odds_service
from app.services.data_sources.odds_mapper import OddsMapper
from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data", tags=["data"])

# Get API key from environment
ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY", "")


@router.post("/fetch/upcoming")
async def fetch_upcoming_games(
    background_tasks: BackgroundTasks,
    days_ahead: int = 7,
    use_cache: bool = True,
    db: Session = Depends(get_db)
):
    """
    Fetch upcoming NBA games using NBA API.

    Fetches games from NBA.com scoreboard with caching.
    Falls back to cached database data if API is unavailable.

    Args:
        days_ahead: Number of days ahead to fetch (default: 7)
        use_cache: If True, return cached data on timeout (default: True)

    Returns:
        Message with games fetched or cached
    """
    try:
        nba_service = NBAService(cache_ttl=300)

        games_fetched = 0
        games_cached = 0
        errors = []

        # Fetch games for each day
        for day_offset in range(days_ahead):
            game_date = date.today() + timedelta(days=day_offset)

            try:
                logger.info(f"Fetching games for {game_date}")

                # Get scoreboard from NBA API (with caching)
                games = await nba_service.get_scoreboard(game_date)

                if not games:
                    logger.warning(f"No games found for {game_date}")
                    # Try to get cached games from database
                    cached_games = (
                        db.query(Game)
                        .filter(
                            Game.game_date >= game_date,
                            Game.game_date < game_date + timedelta(days=1)
                        )
                        .all()
                    )
                    if cached_games:
                        games_cached += len(cached_games)
                        logger.info(f"Using {len(cached_games)} cached games for {game_date}")
                    continue

                # Import games into database
                for game_data in games:
                    # Skip games with missing team abbreviations
                    away_team = game_data.get("VISITOR_TEAM_ABBREVIATION", "")
                    home_team = game_data.get("HOME_TEAM_ABBREVIATION", "")
                    if not away_team or not home_team:
                        logger.warning(f"Skipping game {game_data.get('GAME_ID')} - missing team abbreviations")
                        continue

                    existing_game = (
                        db.query(Game)
                        .filter(Game.external_id == game_data["GAME_ID"])
                        .first()
                    )

                    # Parse game datetime - NBA service now returns UTC directly
                    game_date_str = game_data["GAME_DATE"]

                    try:
                        # Parse ISO format datetime (already in UTC from NBA service)
                        # The NBA service returns naive UTC datetime like "2026-01-24T00:00:00"
                        # We need to interpret this as UTC explicitly, not local time
                        game_datetime_parsed = datetime.fromisoformat(game_date_str)
                        # Make it timezone-aware as UTC, then make it naive for database storage
                        # This ensures it's stored correctly as UTC
                        game_datetime = game_datetime_parsed.replace(tzinfo=timezone.utc).replace(tzinfo=None)
                    except (ValueError, KeyError) as e:
                        logger.warning(f"Could not parse game date {game_date_str}: {e}")
                        # Fallback: try parsing as naive datetime
                        try:
                            game_datetime = datetime.strptime(game_date_str, "%Y-%m-%dT%H:%M:%S")
                        except:
                            game_datetime = datetime.utcnow()

                    if existing_game:
                        # Update existing game
                        # Note: away_score and home_score are not stored in Game model
                        existing_game.status = game_data.get("GAME_STATUS", "scheduled")
                        existing_game.game_date = game_datetime
                    else:
                        # Create new game
                        # Determine season from game date (NBA season spans calendar years)
                        # Games from Oct-Dec belong to next year's season, games from Jan-Jun belong to current year's season
                        game_year = game_datetime.year
                        if game_datetime.month >= 10:
                            season = game_year + 1
                        else:
                            season = game_year

                        new_game = Game(
                            id=str(uuid.uuid4()),
                            external_id=game_data["GAME_ID"],
                            id_source="nba",
                            game_date=game_datetime,
                            away_team=away_team,
                            home_team=home_team,
                            # Note: away_score and home_score are not stored in Game model
                            status=game_data.get("GAME_STATUS", "scheduled"),
                            season=season,
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow()
                        )
                        db.add(new_game)

                    games_fetched += 1

                db.commit()

            except asyncio.TimeoutError:
                logger.error(f"Timeout fetching games for {game_date}")
                errors.append(f"Timeout for {game_date}")

                # Fall back to cached games
                if use_cache:
                    cached_games = (
                        db.query(Game)
                        .filter(
                            Game.game_date >= game_date,
                            Game.game_date < game_date + timedelta(days=1)
                        )
                        .all()
                    )
                    games_cached += len(cached_games)

            except Exception as e:
                logger.error(f"Error fetching games for {game_date}: {e}")
                errors.append(f"{game_date}: {str(e)}")
                # Rollback to clear any failed state
                db.rollback()

        return {
            "message": "Success with fallback to cached data",
            "games_fetched": games_fetched,
            "games_cached": games_cached,
            "errors": errors
        }

    except Exception as e:
        logger.error(f"Error in fetch_upcoming: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching upcoming games: {str(e)}"
        )


@router.post("/fetch/from-odds")
async def fetch_games_from_odds(
    days_ahead: int = 7,
    db: Session = Depends(get_db)
):
    """
    Fetch upcoming games from The Odds API (HYBRID APPROACH).

    This is the PRIMARY method for fetching games in the hybrid architecture.
    The Odds API becomes the single source of truth for game schedule.

    Benefits:
    - No timezone issues (Odds API uses proper ISO timestamps)
    - Only games with betting markets (relevant for predictions)
    - Consistent format across all sports (NBA, NFL, NHL, MLB)

    Workflow:
    1. Fetch schedule from The Odds API
    2. Create/update Game records in database
    3. Use sport-specific APIs for player statistics (separate endpoint)

    Args:
        days_ahead: Number of days ahead to fetch (default: 7)

    Returns:
        Summary of games created/updated
    """
    try:
        odds_service = get_odds_service(ODDS_API_KEY)
        odds_mapper = OddsMapper(db)

        # Fetch upcoming games from The Odds API
        schedule_data = await odds_service.get_upcoming_games_with_odds()

        if not schedule_data:
            return {
                "message": "No upcoming games found from The Odds API",
                "created": 0,
                "updated": 0,
                "total": 0
            }

        # Create/update Game records
        result = odds_mapper.create_games_from_odds_schedule(schedule_data)

        return {
            "message": f"Successfully synced game schedule from The Odds API",
            "created": result["created"],
            "updated": result["updated"],
            "skipped": result["skipped"],
            "total": result["created"] + result["updated"],
            "errors": result["errors"]
        }

    except Exception as e:
        logger.error(f"Error in fetch_from_odds: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching games from The Odds API: {str(e)}"
        )


@router.post("/fetch/players")
async def fetch_players_from_nba(
    background_tasks: BackgroundTasks,
    season: str = "2024-25",
    db: Session = Depends(get_db)
):
    """
    Fetch all NBA players from NBA.com and import into database.

    Uses nba_api to fetch all active NBA players with caching.
    Ensures players are available for predictions.

    Args:
        season: NBA season in "YYYY-YY" format (default: "2024-25")

    Returns:
        Import statistics
    """
    try:
        nba_service = NBAService(cache_ttl=86400)  # 24 hour cache for players

        players_data = await nba_service.get_all_players(season=season)

        imported = 0
        updated = 0
        errors = []

        for player_data in players_data:
            try:
                existing_player = (
                    db.query(Player)
                    .filter(Player.external_id == player_data["PERSON_ID"])
                    .first()
                )

                if existing_player:
                    # Update existing player
                    existing_player.name = player_data["DISPLAY_FIRST_LAST"]
                    existing_player.team = player_data.get("TEAM_ABBREVIATION", "")
                    existing_player.active = player_data.get("ROSTERSTATUS", 1) == 1
                    existing_player.id_source = "nba"
                    existing_player.updated_at = datetime.utcnow()
                    updated += 1
                else:
                    # Create new player
                    new_player = Player(
                        id=str(uuid.uuid4()),
                        external_id=player_data["PERSON_ID"],
                        id_source="nba",
                        name=player_data["DISPLAY_FIRST_LAST"],
                        team=player_data.get("TEAM_ABBREVIATION", ""),
                        position="",  # Not available in all players endpoint
                        active=player_data.get("ROSTERSTATUS", 1) == 1,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    db.add(new_player)
                    imported += 1

            except Exception as e:
                logger.error(f"Error importing player {player_data.get('PERSON_ID')}: {e}")
                errors.append(f"{player_data.get('DISPLAY_FIRST_LAST', 'Unknown')}: {str(e)}")

        db.commit()

        return {
            "message": "Player import complete from NBA.com",
            "imported": imported,
            "updated": updated,
            "errors": errors
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error in fetch_players: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching players from NBA: {str(e)}"
        )


@router.get("/status")
async def get_data_status(db: Session = Depends(get_db)):
    """
    Get current database status and statistics.
    """
    player_count = db.query(Player).count()
    game_count = db.query(Game).count()
    prediction_count = db.query(Prediction).count()

    # Get upcoming games count
    upcoming_games = (
        db.query(Game)
        .filter(Game.game_date >= date.today())
        .count()
    )

    # Get recent predictions count
    recent_predictions = (
        db.query(Prediction)
        .filter(Prediction.created_at >= datetime.utcnow() - timedelta(hours=24))
        .count()
    )

    return {
        "database": {
            "players": player_count,
            "games": game_count,
            "predictions": prediction_count,
            "upcoming_games": upcoming_games,
            "recent_predictions_24h": recent_predictions
        },
        "status": "healthy"
    }


@router.post("/clear-cache")
async def clear_nba_cache():
    """
    Clear the NBA API cache.

    This forces the next request to fetch fresh data from NBA.com.
    """
    nba_service = NBAService()
    await nba_service.clear_cache()
    return {
        "message": "NBA API cache cleared"
    }


@router.post("/fetch/single-game/{nba_game_id}")
async def fetch_single_game(
    nba_game_id: str,
    db: Session = Depends(get_db)
):
    """
    Fetch box score for a single game by NBA game ID.

    Useful for manually updating a specific game's data.
    """
    try:
        nba_service = NBAService()

        boxscore = await nba_service.get_boxscore(nba_game_id)

        if not boxscore or not boxscore.get("PLAYER_STATS"):
            raise HTTPException(
                status_code=404,
                detail=f"Game {nba_game_id} not found on NBA.com"
            )

        # Update game status based on boxscore availability
        existing_game = (
            db.query(Game)
            .filter(Game.external_id == nba_game_id)
            .first()
        )

        if existing_game:
            # Game is likely in progress or final if boxscore exists
            existing_game.status = "final" if existing_game.status != "in_progress" else existing_game.status
            existing_game.updated_at = datetime.utcnow()
            db.commit()

            return {
                "message": "Game box score updated successfully",
                "game": {
                    "nba_id": nba_game_id,
                    "player_stats_count": len(boxscore.get("PLAYER_STATS", [])),
                    "home_team": existing_game.home_team,
                    "away_team": existing_game.away_team
                }
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Game {nba_game_id} not found in database. Fetch upcoming games first."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching game {nba_game_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching game: {str(e)}"
        )


@router.post("/fix/game-dates")
async def fix_game_dates(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """
    Fix game dates by deleting games in date range and re-fetching with correct timezone conversion.

    Use this when timezone conversion issues have caused games to be stored with incorrect UTC dates.

    Args:
        start_date: Start date to fix (inclusive)
        end_date: End date to fix (inclusive)

    Returns:
        Summary of deleted games and re-fetched games
    """
    try:
        # Count games to be deleted
        games_to_delete = (
            db.query(Game)
            .filter(
                Game.game_date >= start_date,
                Game.game_date < end_date + timedelta(days=1)
            )
            .all()
        )

        deleted_count = len(games_to_delete)

        if deleted_count == 0:
            return {
                "message": "No games found in date range",
                "deleted": 0,
                "refetched": 0
            }

        # Delete games (cascade will handle related records)
        for game in games_to_delete:
            db.delete(game)

        db.commit()
        logger.info(f"Deleted {deleted_count} games from {start_date} to {end_date}")

        # Re-fetch games for each day in the range
        nba_service = NBAService(cache_ttl=0)  # Disable cache
        games_refetched = 0
        errors = []

        current_date = start_date
        while current_date <= end_date:
            try:
                logger.info(f"Re-fetching games for {current_date}")
                games = await nba_service.get_scoreboard(current_date)

                if games:
                    for game_data in games:
                        away_team = game_data.get("VISITOR_TEAM_ABBREVIATION", "")
                        home_team = game_data.get("HOME_TEAM_ABBREVIATION", "")
                        if not away_team or not home_team:
                            continue

                        # NBA service now returns UTC datetime directly
                        game_date_str = game_data["GAME_DATE"]

                        try:
                            # Parse ISO format datetime (already in UTC from NBA service)
                            # The NBA service returns naive UTC datetime like "2026-01-24T00:00:00"
                            # We need to interpret this as UTC explicitly, not local time
                            game_datetime_parsed = datetime.fromisoformat(game_date_str)
                            # Make it timezone-aware as UTC, then make it naive for database storage
                            # This ensures it's stored correctly as UTC
                            game_datetime = game_datetime_parsed.replace(tzinfo=timezone.utc).replace(tzinfo=None)
                        except (ValueError, KeyError) as e:
                            logger.warning(f"Could not parse game date {game_date_str}: {e}")
                            continue

                        # Check if game already exists (shouldn't after deletion)
                        existing_game = (
                            db.query(Game)
                            .filter(Game.external_id == game_data["GAME_ID"])
                            .first()
                        )

                        if existing_game:
                            existing_game.status = game_data.get("GAME_STATUS", "scheduled")
                            existing_game.game_date = game_datetime
                        else:
                            game_year = game_datetime.year
                            if game_datetime.month >= 10:
                                season = game_year + 1
                            else:
                                season = game_year

                            new_game = Game(
                                id=str(uuid.uuid4()),
                                external_id=game_data["GAME_ID"],
                                id_source="nba",
                                game_date=game_datetime,
                                away_team=away_team,
                                home_team=home_team,
                                status=game_data.get("GAME_STATUS", "scheduled"),
                                season=season,
                                created_at=datetime.utcnow(),
                                updated_at=datetime.utcnow()
                            )
                            db.add(new_game)

                        games_refetched += 1

                    db.commit()

            except Exception as e:
                logger.error(f"Error re-fetching games for {current_date}: {e}")
                errors.append(f"{current_date}: {str(e)}")

            current_date += timedelta(days=1)

        return {
            "message": f"Fixed games from {start_date} to {end_date}",
            "deleted": deleted_count,
            "refetched": games_refetched,
            "errors": errors
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error in fix_game_dates: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fixing game dates: {str(e)}"
        )
