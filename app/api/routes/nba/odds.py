"""
Odds API routes for fetching betting odds from bookmakers.

Provides endpoints for:
- Game odds (moneyline, spread, totals)
- Player props odds
- Updating predictions with odds pricing
"""
import logging
import uuid
import os
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.services.core.odds_api_service import get_odds_service
from app.services.data_sources.odds_mapper import OddsMapper
from app.models.nba.models import Game, GameOdds, Player, Prediction

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/odds", tags=["odds"])

# Get API key from config (which loads from .env)
def get_odds_api_key() -> str:
    """Get Odds API key from settings."""
    return settings.THE_ODDS_API_KEY or os.getenv("THE_ODDS_API_KEY", "")


def prediction_to_dict_with_odds(pred: Prediction) -> dict:
    """Convert Prediction model to dictionary with odds pricing."""
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
            "date": pred.game.game_date.isoformat(),
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
        "over_price": pred.over_price,
        "under_price": pred.under_price,
        "odds_fetched_at": pred.odds_fetched_at.isoformat() if pred.odds_fetched_at else None,
        "odds_last_updated": pred.odds_last_updated.isoformat() if pred.odds_last_updated else None
    }


@router.get("/quota")
async def get_quota_status(db: Session = Depends(get_db)):
    """
    Get remaining API quota for The Odds API.

    Returns information about monthly request usage.
    """
    api_key = get_odds_api_key()
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="The Odds API key not configured. Set THE_ODDS_API_KEY environment variable."
        )

    try:
        service = get_odds_service(api_key)
        quota = await service.get_quota_status()

        return {
            "service": "the-odds-api",
            "quota": quota
        }
    except Exception as e:
        logger.error(f"Error checking quota status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fetch/game-odds")
async def fetch_game_odds(
    days_ahead: int = Query(default=7, ge=1, le=14, description="Days ahead to fetch"),
    db: Session = Depends(get_db)
):
    """
    Fetch NBA game odds from bookmakers.

    - **days_ahead**: Number of days ahead to fetch (default: 7, max: 14)

    Fetches moneyline, spread, and totals odds for upcoming NBA games.
    """
    api_key = get_odds_api_key()
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="The Odds API key not configured. Set THE_ODDS_API_KEY environment variable."
        )

    try:
        service = get_odds_service(api_key)
        mapper = OddsMapper(db)

        # Fetch game odds
        games_data = await service.get_upcoming_games_with_odds(days_ahead)

        added = 0
        updated = 0
        errors = []

        for game_data in games_data:
            try:
                # Find or create game - first try external_id, then try team+date matching
                game = mapper.find_game_by_external_id(game_data["id"])

                if not game:
                    # Try to find existing game by team names and date
                    now = datetime.utcnow()
                    away_team_abbr = mapper._team_name_to_abbrev(game_data["away_team"])
                    home_team_abbr = mapper._team_name_to_abbrev(game_data["home_team"])
                    commence_time = datetime.fromisoformat(game_data["commence_time"].replace("Z", "+00:00"))

                    # Apply The Odds API 10-minute offset correction
                    commence_time = commence_time - timedelta(minutes=10)

                    game = mapper.find_game_by_teams(home_team_abbr, away_team_abbr, commence_time)

                    if game:
                        # Update existing game's external_id to match The Odds API
                        game.external_id = game_data["id"]
                        game.updated_at = now
                        logger.info(f"Updated game {away_team_abbr} @ {home_team_abbr} with Odds API external_id: {game_data['id']}")
                    else:
                        # Create new game
                        game = Game(
                            id=str(uuid.uuid4()),
                            external_id=game_data["id"],
                            id_source="odds_api",
                            game_date=commence_time,
                            away_team=away_team_abbr,
                            home_team=home_team_abbr,
                            season=commence_time.year,
                            status="scheduled",
                            created_at=now,
                            updated_at=now
                        )
                        db.add(game)
                        db.flush()

                # Map and insert odds
                game_odds_list = mapper.map_game_odds(game_data, game)

                for game_odds in game_odds_list:
                    # Check if odds already exist
                    existing = db.query(GameOdds).filter(
                        GameOdds.game_id == game.id,
                        GameOdds.bookmaker_key == game_odds.bookmaker_key
                    ).first()

                    if existing:
                        # Update existing odds
                        existing.home_moneyline = game_odds.home_moneyline
                        existing.away_moneyline = game_odds.away_moneyline
                        existing.home_spread_point = game_odds.home_spread_point
                        existing.home_spread_price = game_odds.home_spread_price
                        existing.away_spread_point = game_odds.away_spread_point
                        existing.away_spread_price = game_odds.away_spread_price
                        existing.totals_point = game_odds.totals_point
                        existing.over_price = game_odds.over_price
                        existing.under_price = game_odds.under_price
                        existing.last_update = game_odds.last_update
                        updated += 1
                    else:
                        # Add new odds
                        db.add(game_odds)
                        added += 1

            except Exception as e:
                logger.error(f"Error processing game {game_data.get('id')}: {e}")
                errors.append(f"{game_data.get('id')}: {str(e)}")

        db.commit()

        return {
            "status": "success",
            "games_processed": len(games_data),
            "odds_added": added,
            "odds_updated": updated,
            "errors": errors,
            "total_odds": added + updated
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error fetching game odds: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fetch/player-props/{game_id}")
async def fetch_player_props_for_game(
    game_id: str,
    db: Session = Depends(get_db)
):
    """
    Fetch player props odds for a specific NBA game.

    - **game_id**: The Odds API event ID

    Fetches player props odds for points, rebounds, assists, and threes.
    Updates existing predictions with odds pricing.
    """
    api_key = get_odds_api_key()
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="The Odds API key not configured. Set THE_ODDS_API_KEY environment variable."
        )

    try:
        service = get_odds_service(api_key)
        mapper = OddsMapper(db)

        # Find game by external ID
        game = mapper.find_game_by_external_id(game_id)

        if not game:
            raise HTTPException(status_code=404, detail=f"Game {game_id} not found in database")

        # Fetch player props
        props_data = await service.get_event_player_props(game_id)

        # Map to prediction updates
        updates = await mapper.map_player_props_to_predictions(props_data, game)

        updated = 0
        errors = []

        # Bookmaker priority (highest first) - FanDuel only
        BOOKMAKER_PRIORITY = ["FanDuel"]
        for update_data in updates:
            try:
                prediction = db.query(Prediction).filter(
                    Prediction.id == update_data["prediction_id"]
                ).first()

                if prediction:
                    new_bookmaker = update_data.get("bookmaker_name")
                    current_bookmaker = prediction.bookmaker_name

                    # Only update if:
                    # 1. No existing bookmaker, OR
                    # 2. New bookmaker is higher priority than current, OR
                    # 3. Same bookmaker (update missing Over/Under prices)
                    should_update = False
                    if current_bookmaker is None:
                        should_update = True
                    elif new_bookmaker == current_bookmaker:
                        # Same bookmaker - update to fill in missing Over/Under prices
                        should_update = True
                    elif new_bookmaker in BOOKMAKER_PRIORITY and current_bookmaker in BOOKMAKER_PRIORITY:
                        new_priority = BOOKMAKER_PRIORITY.index(new_bookmaker)
                        current_priority = BOOKMAKER_PRIORITY.index(current_bookmaker)
                        should_update = new_priority < current_priority

                    if should_update:
                        # Only update prices if they're not None (preserve existing prices)
                        if update_data.get("over_price") is not None:
                            prediction.over_price = update_data.get("over_price")
                        if update_data.get("under_price") is not None:
                            prediction.under_price = update_data.get("under_price")

                        # Update bookmaker info
                        prediction.bookmaker_line = update_data.get("bookmaker_line")
                        prediction.bookmaker_name = new_bookmaker

                        prediction.odds_last_updated = update_data.get("odds_last_updated")

                        if not prediction.odds_fetched_at:
                            prediction.odds_fetched_at = update_data.get("odds_last_updated")

                        prediction.updated_at = datetime.utcnow()
                        updated += 1

            except Exception as e:
                logger.error(f"Error updating prediction {update_data.get('prediction_id')}: {e}")
                errors.append(f"{update_data.get('prediction_id')}: {str(e)}")

        db.commit()

        # Count total predictions for this game
        total_predictions = db.query(Prediction).filter(
            Prediction.game_id == game.id
        ).count()

        # Count predictions with odds
        predictions_with_odds = db.query(Prediction).filter(
            Prediction.game_id == game.id,
            Prediction.over_price.isnot(None)
        ).count()

        # Parse markets string into list
        markets_str = props_data.get("markets", "")
        markets_list = markets_str.split(",") if markets_str else []

        return {
            "status": "success",
            "game_id": game_id,
            "predictions_updated": updated,
            "total_predictions": total_predictions,
            "predictions_with_odds": predictions_with_odds,
            "markets_fetched": markets_list,
            "errors": errors
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error fetching player props: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/predictions/update-odds")
async def update_prediction_odds(
    days_ahead: int = Query(default=1, ge=1, le=7, description="Days ahead to update"),
    db: Session = Depends(get_db)
):
    """
    Update predictions with latest odds pricing for upcoming games.

    - **days_ahead**: Number of days ahead to update (default: 1)

    Fetches player props odds for games in the next N days and updates
    existing predictions with over/under pricing.
    """
    api_key = get_odds_api_key()
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="The Odds API key not configured. Set THE_ODDS_API_KEY environment variable."
        )

    try:
        service = get_odds_service(api_key)
        mapper = OddsMapper(db)

        # Get upcoming games with predictions
        from datetime import timedelta
        start_date = datetime.utcnow()
        end_date = start_date + timedelta(days=days_ahead)

        games = db.query(Game).filter(
            Game.game_date >= start_date,
            Game.game_date <= end_date,
            Game.id_source == "nba",
            Game.status == "scheduled"
        ).all()

        total_updated = 0
        games_processed = 0
        errors = []

        # Bookmaker priority (highest first) - FanDuel only
        BOOKMAKER_PRIORITY = ["FanDuel"]
        try:
                for game in games:
                    props_data = await service.get_event_player_props(game.external_id)

                    # Map to prediction updates
                    updates = await mapper.map_player_props_to_predictions(props_data, game)

                    for update_data in updates:
                        prediction = db.query(Prediction).filter(
                            Prediction.id == update_data["prediction_id"]
                        ).first()

                        if prediction:
                            new_bookmaker = update_data.get("bookmaker_name")
                            current_bookmaker = prediction.bookmaker_name

                            # Only update if:
                            # 1. No existing bookmaker, OR
                            # 2. New bookmaker is higher priority than current, OR
                            # 3. Same bookmaker (update missing Over/Under prices)
                            should_update = False
                            if current_bookmaker is None:
                                should_update = True
                            elif new_bookmaker == current_bookmaker:
                                # Same bookmaker - update to fill in missing Over/Under prices
                                should_update = True
                            elif new_bookmaker in BOOKMAKER_PRIORITY and current_bookmaker in BOOKMAKER_PRIORITY:
                                new_priority = BOOKMAKER_PRIORITY.index(new_bookmaker)
                                current_priority = BOOKMAKER_PRIORITY.index(current_bookmaker)
                                should_update = new_priority < current_priority

                            if should_update:
                                # Only update prices if they're not None
                                if update_data.get("over_price") is not None:
                                    prediction.over_price = update_data.get("over_price")
                                if update_data.get("under_price") is not None:
                                    prediction.under_price = update_data.get("under_price")

                                prediction.bookmaker_line = update_data.get("bookmaker_line")
                                prediction.bookmaker_name = new_bookmaker
                            prediction.odds_last_updated = update_data.get("odds_last_updated")

                            if not prediction.odds_fetched_at:
                                prediction.odds_fetched_at = update_data.get("odds_last_updated")

                            prediction.updated_at = datetime.utcnow()
                            total_updated += 1

                games_processed += 1

        except Exception as e:
                logger.error(f"Error processing game {game.external_id}: {e}")
                errors.append(f"{game.external_id}: {str(e)}")

        return {
            "status": "success",
            "games_processed": games_processed,
            "predictions_updated": total_updated,
            "errors": errors
        }

    except Exception as e:
        logger.error(f"Error updating prediction odds: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/game/{game_id}")
async def get_game_odds(
    game_id: str,
    db: Session = Depends(get_db)
):
    """
    Get odds for a specific game.

    - **game_id**: Database game UUID

    Returns all bookmaker odds for the specified game.
    """
    try:
        game = db.query(Game).filter(Game.id == game_id).first()

        if not game:
            raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

        # Get all odds for this game
        odds = db.query(GameOdds).filter(
            GameOdds.game_id == game_id
        ).order_by(GameOdds.last_update.desc()).all()

        return {
            "game": {
                "id": str(game.id),
                "external_id": game.external_id,
                "date": game.game_date.isoformat(),
                "away_team": game.away_team,
                "home_team": game.home_team,
                "status": game.status
            },
            "odds": [
                {
                    "id": str(odds.id),
                    "bookmaker_key": odds.bookmaker_key,
                    "bookmaker_title": odds.bookmaker_title,
                    "home_moneyline": odds.home_moneyline,
                    "away_moneyline": odds.away_moneyline,
                    "home_spread_point": odds.home_spread_point,
                    "home_spread_price": odds.home_spread_price,
                    "away_spread_point": odds.away_spread_point,
                    "away_spread_price": odds.away_spread_price,
                    "totals_point": odds.totals_point,
                    "over_price": odds.over_price,
                    "under_price": odds.under_price,
                    "last_update": odds.last_update.isoformat()
                }
                for odds in odds
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting game odds: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predictions/with-odds")
async def get_predictions_with_odds(
    min_confidence: float = Query(default=0.5, ge=0, le=1),
    limit: int = Query(default=20, ge=1, le=100),
    has_odds_only: bool = Query(default=False, description="Only return predictions with odds pricing"),
    db: Session = Depends(get_db)
):
    """
    Get predictions with odds pricing information.

    - **min_confidence**: Minimum confidence threshold (default: 0.5)
    - **limit**: Maximum predictions to return (default: 20)
    - **has_odds_only**: Only return predictions that have odds pricing (default: false)

    Returns predictions with over/under pricing from bookmakers.
    """
    try:
        query = db.query(Prediction).join(Player).join(Game).filter(
            Player.id_source == "nba",
            Prediction.confidence >= min_confidence
        )

        if has_odds_only:
            query = query.filter(Prediction.over_price.isnot(None))

        predictions = query.order_by(Prediction.confidence.desc()).limit(limit).all()

        return {
            "predictions": [prediction_to_dict_with_odds(p) for p in predictions],
            "count": len(predictions),
            "min_confidence": min_confidence,
            "has_odds_only": has_odds_only
        }

    except Exception as e:
        logger.error(f"Error fetching predictions with odds: {e}")
        raise HTTPException(status_code=500, detail=str(e))
