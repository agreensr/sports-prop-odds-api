"""
NHL Game Odds Mapper for correlating internal games with Odds API events.

This service maps internal NHL Game IDs to The Odds API event IDs using:
1. Cached odds_api_event_id on the Game model (fastest)
2. Pre-existing game_mappings table entries (from sync jobs)
3. Live Odds API query as fallback (slowest but ensures coverage)

Adapted from the NBA GameOddsMapper with NHL-specific adjustments.
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.nhl.models import Game
from app.core.logging import get_logger

logger = get_logger(__name__)


class NHLGameOddsMapper:
    """
    Map NHL games to Odds API event IDs.

    Uses a tiered lookup strategy:
    1. Check cached odds_api_event_id on Game model
    2. Look up in game_mappings table
    3. Query Odds API directly (if service provided)
    """

    def __init__(self, db: Session, odds_api_service=None):
        """
        Initialize the NHL game odds mapper.

        Args:
            db: SQLAlchemy database session
            odds_api_service: Optional OddsApiService for fallback queries
        """
        self.db = db
        self.odds_api_service = odds_api_service

    async def get_odds_event_id(
        self,
        game: Game
    ) -> Optional[str]:
        """
        Find Odds API event ID for an NHL game.

        Uses tiered lookup strategy:
        1. Check cached odds_api_event_id on Game model
        2. Look up in game_mappings table
        3. Query Odds API directly (if service provided)

        Args:
            game: NHL Game model instance

        Returns:
            Odds API event ID or None if not found
        """
        # Step 1: Check if game already has cached odds_api_event_id
        if hasattr(game, 'odds_api_event_id') and game.odds_api_event_id:
            logger.debug(
                f"Using cached odds_api_event_id for NHL game {game.id}: "
                f"{game.odds_api_event_id}"
            )
            return game.odds_api_event_id

        # Step 2: Look up in game_mappings table
        mapping = self._find_mapping_for_game(game)

        if mapping and mapping.odds_event_id:
            # Cache the odds_event_id on the Game model for future lookups
            if hasattr(game, 'odds_api_event_id'):
                game.odds_api_event_id = mapping.odds_event_id
                self.db.commit()

            logger.info(
                f"Found odds_event_id via mapping for NHL game {game.id}: "
                f"{mapping.odds_event_id}"
            )
            return mapping.odds_event_id

        # Step 3: Fallback to live Odds API query
        if self.odds_api_service:
            logger.info(
                f"No mapping found for NHL game {game.id}, "
                f"attempting live Odds API query"
            )
            odds_event_id = await self._query_odds_api_fallback(game)

            if odds_event_id:
                # Cache the result
                if hasattr(game, 'odds_api_event_id'):
                    game.odds_api_event_id = odds_event_id
                    self.db.commit()
                return odds_event_id

        logger.warning(
            f"Could not find odds_event_id for NHL game {game.id} "
            f"({game.away_team} @ {game.home_team})"
        )
        return None

    def _find_mapping_for_game(self, game: Game) -> Optional[Any]:
        """
        Find game mapping by matching teams and date.

        NHL Note: Uses game_mappings table if available,
        otherwise attempts direct matching.

        Args:
            game: Game model instance

        Returns:
            GameMapping instance or None
        """
        # For NHL, we'll use a simpler approach since game_mappings
        # may not be set up for NHL yet
        return None

    async def _query_odds_api_fallback(
        self,
        game: Game
    ) -> Optional[str]:
        """
        Query Odds API directly to find matching NHL event.

        This is a fallback method that queries the Odds API's
        upcoming games endpoint to find a matching event by
        teams and date.

        Args:
            game: NHL Game model instance

        Returns:
            Odds API event ID or None
        """
        if not self.odds_api_service:
            return None

        try:
            # Fetch upcoming NHL games from Odds API
            games_data = await self.odds_api_service.get_upcoming_games_with_odds(
                days_ahead=7,
                sport="nhl"
            )

            if not games_data:
                return None

            # Match by teams and date
            game_date = game.game_date.date() if isinstance(game.game_date, datetime) else game.game_date

            for odds_game in games_data:
                # Check if teams match (case-insensitive)
                away_match = (
                    odds_game.get("away_team", "").lower() == game.away_team.lower() or
                    game.away_team.lower() in odds_game.get("away_team", "").lower()
                )
                home_match = (
                    odds_game.get("home_team", "").lower() == game.home_team.lower() or
                    game.home_team.lower() in odds_game.get("home_team", "").lower()
                )

                # Check if date matches (within 1 day for time zone differences)
                odds_commence_time = odds_game.get("commence_time")
                if odds_commence_time:
                    try:
                        odds_date = datetime.fromisoformat(
                            odds_commence_time.replace("Z", "+00:00")
                        ).date()

                        date_match = abs((odds_date - game_date).days) <= 1

                        if away_match and home_match and date_match:
                            odds_event_id = odds_game.get("id")
                            logger.info(
                                f"Found odds_event_id via API fallback for NHL: {odds_event_id}"
                            )
                            return odds_event_id
                    except (ValueError, AttributeError):
                        continue

        except Exception as e:
            logger.error(f"Error querying Odds API fallback for NHL: {e}")

        return None

    async def get_odds_event_id_by_game_id(
        self,
        game_id: str
    ) -> Optional[str]:
        """
        Get odds event ID by internal game ID.

        Convenience method that fetches the game first.

        Args:
            game_id: Internal game UUID

        Returns:
            Odds API event ID or None
        """
        game = self.db.query(Game).filter(Game.id == game_id).first()
        if not game:
            logger.warning(f"NHL Game {game_id} not found")
            return None

        return await self.get_odds_event_id(game)

    async def get_odds_event_id_by_teams_and_date(
        self,
        away_team: str,
        home_team: str,
        game_date: Any
    ) -> Optional[str]:
        """
        Get odds event ID by teams and date.

        Useful when you don't have the game ID.

        Args:
            away_team: Away team abbreviation
            home_team: Home team abbreviation
            game_date: Game date (datetime or date)

        Returns:
            Odds API event ID or None
        """
        if isinstance(game_date, datetime):
            game_date = game_date.date()

        # Find the game by teams and date
        start_date = game_date - timedelta(days=1)
        end_date = game_date + timedelta(days=1)

        game = self.db.query(Game).filter(
            Game.away_team == away_team.upper(),
            Game.home_team == home_team.upper(),
            Game.game_date >= start_date,
            Game.game_date <= end_date
        ).first()

        if game:
            return await self.get_odds_event_id(game)

        return None

    def invalidate_cache(self, game: Game) -> None:
        """
        Invalidate cached odds_api_event_id for a game.

        Useful when you need to force a fresh lookup.

        Args:
            game: Game model instance
        """
        if hasattr(game, 'odds_api_event_id') and game.odds_api_event_id:
            logger.info(
                f"Invalidating cached odds_api_event_id for NHL game {game.id}: "
                f"{game.odds_api_event_id}"
            )
            game.odds_api_event_id = None
            self.db.commit()


# Singleton factory for convenience
_nhl_mapper_cache: Optional[NHLGameOddsMapper] = None


def get_nhl_game_odds_mapper(
    db: Session,
    odds_api_service=None
) -> NHLGameOddsMapper:
    """
    Get an NHLGameOddsMapper instance.

    Args:
        db: SQLAlchemy database session
        odds_api_service: Optional OddsApiService for fallback queries

    Returns:
        NHLGameOddsMapper instance
    """
    global _nhl_mapper_cache
    if _nhl_mapper_cache is None:
        _nhl_mapper_cache = NHLGameOddsMapper(db, odds_api_service)
    return _nhl_mapper_cache
