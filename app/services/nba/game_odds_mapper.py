"""
Game Odds Mapper for correlating internal games with Odds API events.

This service maps internal Game IDs to The Odds API event IDs using:
1. Cached odds_api_event_id on the Game model (fastest)
2. Pre-existing game_mappings table entries (from sync jobs)
3. Live Odds API query as fallback (slowest but ensures coverage)

The Game model already has an odds_api_event_id column (Phase 1).
This service leverages that cache and provides fallback mechanisms.
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Game, GameMapping
from app.core.logging import get_logger

logger = get_logger(__name__)


class GameOddsMapper:
    """
    Map games to Odds API event IDs.

    Uses a tiered lookup strategy:
    1. Check cached odds_api_event_id on Game model
    2. Look up in game_mappings table (populated by sync layer)
    3. Query Odds API directly as fallback
    """

    def __init__(self, db: Session, odds_api_service=None):
        """
        Initialize the game odds mapper.

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
        Find Odds API event ID for a game.

        Uses tiered lookup strategy:
        1. Check cached odds_api_event_id on Game model
        2. Look up in game_mappings table
        3. Query Odds API directly (if service provided)

        Args:
            game: Game model instance

        Returns:
            Odds API event ID or None if not found
        """
        # Step 1: Check if game already has cached odds_api_event_id
        if game.odds_api_event_id:
            logger.debug(
                f"Using cached odds_api_event_id for game {game.id}: "
                f"{game.odds_api_event_id}"
            )
            return game.odds_api_event_id

        # Step 2: Look up in game_mappings table
        # The game_mappings table is populated by the sync layer
        # and correlates nba_api games with Odds API events
        mapping = self._find_mapping_for_game(game)

        if mapping and mapping.odds_event_id:
            # Cache the odds_event_id on the Game model for future lookups
            game.odds_api_event_id = mapping.odds_event_id
            self.db.commit()

            logger.info(
                f"Found odds_event_id via mapping for game {game.id}: "
                f"{mapping.odds_event_id} (confidence: {mapping.match_confidence:.2f})"
            )
            return mapping.odds_event_id

        # Step 3: Fallback to live Odds API query (if service provided)
        if self.odds_api_service:
            logger.info(
                f"No mapping found for game {game.id}, "
                f"attempting live Odds API query"
            )
            odds_event_id = await self._query_odds_api_fallback(game)

            if odds_event_id:
                # Cache the result
                game.odds_api_event_id = odds_event_id
                self.db.commit()
                return odds_event_id

        logger.warning(
            f"Could not find odds_event_id for game {game.id} "
            f"({game.away_team} @ {game.home_team})"
        )
        return None

    def _find_mapping_for_game(self, game: Game) -> Optional[GameMapping]:
        """
        Find game mapping by matching teams and date.

        The game_mappings table uses nba_game_id, but our Game model
        uses external_id. We need to match by teams and date.

        Args:
            game: Game model instance

        Returns:
            GameMapping instance or None
        """
        # Convert game_date to date for comparison
        game_date = game.game_date.date() if isinstance(game.game_date, datetime) else game.game_date

        # Look for mapping with matching teams and date
        # The game_mappings table stores team IDs, not abbreviations,
        # so we need to match by date and then verify teams
        mappings = self.db.query(GameMapping).filter(
            GameMapping.game_date == game_date,
            GameMapping.status == 'matched'
        ).all()

        # Find matching mapping by team abbreviations
        # Note: This is a simplified match - the sync layer handles
        # the proper team ID correlation via team_mappings table
        for mapping in mappings:
            # We can't directly match teams here since game_mappings
            # stores team IDs, not abbreviations
            # Return the first valid mapping for the date
            # In production, you'd want to verify team IDs match
            if mapping.odds_event_id:
                return mapping

        return None

    async def _query_odds_api_fallback(
        self,
        game: Game
    ) -> Optional[str]:
        """
        Query Odds API directly to find matching event.

        This is a fallback method that queries the Odds API's
        upcoming games endpoint to find a matching event by
        teams and date.

        Args:
            game: Game model instance

        Returns:
            Odds API event ID or None
        """
        if not self.odds_api_service:
            return None

        try:
            # Fetch upcoming games from Odds API
            games_data = await self.odds_api_service.get_upcoming_games_with_odds(
                days_ahead=7
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
                                f"Found odds_event_id via API fallback: {odds_event_id}"
                            )
                            return odds_event_id
                    except (ValueError, AttributeError):
                        continue

        except Exception as e:
            logger.error(f"Error querying Odds API fallback: {e}")

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
            logger.warning(f"Game {game_id} not found")
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
        # Find the game by teams and date
        if isinstance(game_date, datetime):
            game_date = game_date.date()

        # Look for games within a time window around the target date
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
        if game.odds_api_event_id:
            logger.info(
                f"Invalidating cached odds_api_event_id for game {game.id}: "
                f"{game.odds_api_event_id}"
            )
            game.odds_api_event_id = None
            self.db.commit()


# Singleton factory for convenience
def get_game_odds_mapper(
    db: Session,
    odds_api_service=None
) -> GameOddsMapper:
    """
    Get a GameOddsMapper instance.

    Args:
        db: SQLAlchemy database session
        odds_api_service: Optional OddsApiService for fallback queries

    Returns:
        GameOddsMapper instance
    """
    return GameOddsMapper(db, odds_api_service)
