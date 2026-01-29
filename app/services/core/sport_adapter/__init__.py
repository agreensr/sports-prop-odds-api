"""
Base Sport Adapter for Multi-Sport Support.

This module provides a unified adapter interface for all sports,
eliminating code duplication while maintaining sport-specific flexibility.

The adapter pattern provides:
1. Single source of truth for sport configuration
2. Consistent API across all sports
3. Easy addition of new sports
4. Centralized position and stat type management

Usage:
    from app.services.core.sport_adapter import SportAdapter
    from app.models import Player, Game

    nba_adapter = SportAdapter("nba", db_session)
    games = await nba_adapter.fetch_upcoming_games()
    players = await nba_adapter.fetch_roster(team="BOS")
"""
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.models import Player, Game
from app.services.core.sport_adapter.config import (
    get_sport_config,
    get_position_averages,
    get_espn_sport_path,
    get_recommendation_threshold,
    get_variance_percent,
    supports_per_36_stats,
    get_active_field_value,
    get_active_field_is_boolean,
    is_stat_relevant_for_position,
    get_primary_stat_for_position,
    get_default_stat_types,
    get_cache_ttl,
    SPORT_CONFIGS,
    POSITION_AVERAGES,
    NBA_CONFIG,
    NFL_CONFIG,
    MLB_CONFIG,
    NHL_CONFIG,
)
from app.core.logging import get_logger
from app.utils.timezone import is_in_season

logger = get_logger(__name__)


class SportAdapter:
    """
    Unified sport adapter for all sports (NBA, NFL, MLB, NHL).

    This adapter provides a consistent interface for:
    - Fetching data from external APIs (ESPN, Odds API)
    - Managing sport-specific data transformations
    - Handling position and stat type logic

    All sport-specific behavior is driven by configuration rather than
    code duplication, making it easy to add new sports.

    Args:
        sport_id: Sport identifier ('nba', 'nfl', 'mlb', 'nhl')
        db: Database session for queries
    """

    def __init__(self, sport_id: str, db: Session):
        """
        Initialize the sport adapter.

        Args:
            sport_id: Sport identifier ('nba', 'nfl', 'mlb', 'nhl')
            db: Database session
        """
        self.sport_id = sport_id.lower()
        self.db = db
        self.config = get_sport_config(self.sport_id)

    # ========================================================================
    # PROPERTIES (Convenience access to config)
    # ========================================================================

    @property
    def name(self) -> str:
        """Sport display name."""
        return self.config.name

    @property
    def abbreviation(self) -> str:
        """Sport abbreviation."""
        return self.config.abbreviation

    @property
    def espn_sport_path(self) -> str:
        """ESPN API path for this sport."""
        return self.config.espn_sport_path

    @property
    def odds_api_sport(self) -> str:
        """The Odds API sport key."""
        return self.config.odds_api_sport

    @property
    def recommendation_threshold(self) -> float:
        """Min confidence for OVER/UNDER recommendation."""
        return self.config.recommendation_threshold

    @property
    def variance_percent(self) -> int:
        """Variance to apply to predictions."""
        return self.config.variance_percent

    @property
    def supports_per_36_stats(self) -> bool:
        """Whether this sport uses per-36 stats."""
        return self.config.supports_per_36_stats

    @property
    def active_field_is_boolean(self) -> bool:
        """Whether active field is boolean."""
        return self.config.active_field_is_boolean

    @property
    def active_field_value(self) -> str:
        """Value for active players."""
        return self.config.active_field_value

    # ========================================================================
    # POSITION METHODS
    # ========================================================================

    def get_positions(self) -> Dict[str, Dict]:
        """
        Get all positions for this sport.

        Returns:
            Dictionary mapping position abbreviations to position info
        """
        return {
            abbr: {
                "abbreviation": pos.abbreviation,
                "name": pos.name,
                "primary_stat": pos.primary_stat,
                "stat_types": pos.stat_types,
            }
            for abbr, pos in self.config.positions.items()
        }

    def get_position_config(self, position: str) -> Optional[Dict]:
        """Get configuration for a specific position."""
        pos = self.config.positions.get(position.upper())
        if pos:
            return {
                "abbreviation": pos.abbreviation,
                "name": pos.name,
                "primary_stat": pos.primary_stat,
                "stat_types": pos.stat_types,
            }
        return None

    def get_position_averages(
        self,
        position: str,
        stat_types: Optional[List[str]] = None
    ) -> Dict[str, float]:
        """
        Get fallback position averages.

        Args:
            position: Position abbreviation
            stat_types: Optional list of stat types to filter

        Returns:
            Dictionary of stat_type -> average_value
        """
        averages = get_position_averages(self.sport_id, position)

        if stat_types:
            return {k: v for k, v in averages.items() if k in stat_types}
        return averages

    def is_stat_relevant_for_position(
        self,
        position: str,
        stat_type: str
    ) -> bool:
        """Check if a stat type is relevant for a position."""
        return is_stat_relevant_for_position(self.sport_id, position, stat_type)

    def get_primary_stat(self, position: str) -> Optional[str]:
        """Get the primary stat for a position."""
        return get_primary_stat_for_position(self.sport_id, position)

    def get_default_stat_types(self) -> List[str]:
        """Get default stat types for predictions."""
        return get_default_stat_types(self.sport_id)

    # ========================================================================
    # CACHE TTL METHODS
    # ========================================================================

    def get_cache_ttl(self) -> int:
        """
        Get appropriate cache TTL based on season status.

        Returns:
            Cache TTL in seconds
        """
        in_season = is_in_season(self.sport_id)
        return get_cache_ttl(self.sport_id, in_season)

    # ========================================================================
    # ACTIVE PLAYER QUERY HELPERS
    # ========================================================================

    def get_active_player_filter(self) -> Dict[str, Any]:
        """
        Get filter for active players for this sport.

        Returns:
            Dictionary with filter key and value
        """
        if self.active_field_is_boolean:
            return {"active": True}
        else:
            return {"status": self.active_field_value}

    def format_active_filter(self, field_name: str = "active") -> str:
        """
        Format an active filter for SQL queries.

        Args:
            field_name: Field name to use (default: "active")

        Returns:
            Filter string or value
        """
        if self.active_field_is_boolean:
            return f"{field_name} = true"
        else:
            return f"{field_name} = '{self.active_field_value}'"

    # ========================================================================
    # DATA FETCHING METHODS
    # ========================================================================

    async def fetch_upcoming_games(self, days_ahead: int = 7) -> List[Game]:
        """
        Fetch upcoming games from ESPN API.

        Args:
            days_ahead: Number of days ahead to fetch

        Returns:
            List of Game objects
        """
        from app.services.core.espn_service import ESPNApiService

        service = ESPNApiService(cache_ttl=self.get_cache_ttl())
        path = self.espn_sport_path

        # ESPN scores endpoint provides games
        url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"

        try:
            async with service._get_client() as client:
                response = await client.get(url)
                response.raise_for_status()

            data = response.json()

            games = []
            for event in data.get("events", []):
                # Parse game data
                game_date = self._parse_espn_datetime(event.get("date"))
                competitors = event.get("competitors", [])

                if len(competitors) >= 2:
                    away = competitors[0].get("team", {})
                    home = competitors[1].get("team", {})

                    # Check if game exists
                    existing = self.db.query(Game).filter(
                        Game.sport_id == self.sport_id,
                        Game.game_date >= game_date - timedelta(hours=1),
                        Game.away_team == away.get("abbreviation"),
                        Game.home_team == home.get("abbreviation")
                    ).first()

                    if existing:
                        games.append(existing)
                    else:
                        # Would create game here in full implementation
                        pass

            return games

        except Exception as e:
            logger.error(f"Error fetching {self.sport_id} games: {e}")
            return []

    async def fetch_team_roster(
        self,
        team: str,
        team_id: Optional[str] = None
    ) -> List[Player]:
        """
        Fetch team roster from ESPN API.

        Args:
            team: Team abbreviation
            team_id: ESPN team ID (optional)

        Returns:
            List of Player objects
        """
        from app.services.core.espn_service import ESPNApiService

        service = ESPNApiService(cache_ttl=self.get_cache_ttl())
        path = self.espn_sport_path

        if team_id:
            url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/teams/{team_id}"
        else:
            # Would need to look up team ID first
            url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/teams"

        try:
            async with service._get_client() as client:
                response = await client.get(url)
                response.raise_for_status()

            data = response.json()
            team_data = data.get("team", {})
            athletes = team_data.get("athletes", [])

            players = []
            for athlete in athletes:
                # Parse player data
                player_data = self._parse_athlete_data(athlete, team)
                if player_data:
                    players.append(player_data)

            return players

        except Exception as e:
            logger.error(f"Error fetching {self.sport_id} roster for {team}: {e}")
            return []

    def _parse_espn_datetime(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse ESPN datetime string to datetime object."""
        if not date_str:
            return None
        try:
            # ESPN dates are in ISO format with UTC timezone
            from datetime import timezone
            utc_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            # Return naive datetime for database
            return utc_datetime.replace(tzinfo=None)
        except Exception:
            return None

    def _parse_athlete_data(self, athlete: Dict, team: str) -> Optional[Dict]:
        """
        Parse athlete data from ESPN API.

        Args:
            athlete: ESPN athlete data
            team: Team abbreviation

        Returns:
            Dictionary with player data
        """
        # Implementation would be sport-specific based on data structure
        # This is a placeholder showing the pattern
        return {
            "name": athlete.get("displayName"),
            "team": team,
            "position": athlete.get("position", {}).get("abbreviation"),
            "jersey": athlete.get("jersey"),
            # ... more fields
        }

    # ========================================================================
    # PREDICTION HELPERS
    # ========================================================================

    def apply_variance_to_prediction(
        self,
        predicted_value: float,
        stat_type: str,
        position: Optional[str] = None
    ) -> float:
        """
        Apply sport-specific variance to a predicted value.

        Args:
            predicted_value: Base predicted value
            stat_type: Type of stat
            position: Player position (optional)

        Returns:
            Adjusted value with variance applied
        """
        variance = self.variance_percent / 100
        variance_amount = predicted_value * variance
        return predicted_value + variance_amount

    def should_recommend_over(
        self,
        predicted_value: float,
        bookmaker_line: float,
        confidence: float
    ) -> bool:
        """
        Determine if OVER should be recommended based on sport threshold.

        Args:
            predicted_value: Predicted value
            bookmaker_line: Bookmaker line
            confidence: Model confidence

        Returns:
            True if OVER should be recommended
        """
        # Must have sufficient confidence
        if confidence < self.recommendation_threshold:
            return False

        # Predicted value must exceed line by margin
        margin = predicted_value - bookmaker_line
        return margin > 0

    # ========================================================================
    # UTILITY METHODS
    # ========================================================================

    def get_sport_summary(self) -> Dict[str, Any]:
        """
        Get a summary of this sport's configuration.

        Returns:
            Dictionary with sport info
        """
        return {
            "sport_id": self.sport_id,
            "name": self.name,
            "abbreviation": self.abbreviation,
            "espn_path": self.espn_sport_path,
            "odds_api_sport": self.odds_api_sport,
            "recommendation_threshold": self.recommendation_threshold,
            "variance_percent": self.variance_percent,
            "supports_per_36_stats": self.supports_per_36_stats,
            "positions": list(self.config.positions.keys()),
            "default_stat_types": self.config.default_stat_types,
        }

    def __repr__(self) -> str:
        return f"SportAdapter(sport_id='{self.sport_id}', name='{self.name}')"


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_sport_adapter(sport_id: str, db: Session) -> SportAdapter:
    """
    Factory function to create a sport adapter.

    This is the recommended way to create adapters in application code.

    Args:
        sport_id: Sport identifier ('nba', 'nfl', 'mlb', 'nhl')
        db: Database session

    Returns:
        Configured SportAdapter instance

    Raises:
        ValueError: If sport_id is not recognized

    Example:
        from app.services.core.sport_adapter import create_sport_adapter
        from app.core.database import SessionLocal

        db = SessionLocal()
        nba_adapter = create_sport_adapter("nba", db)
        games = await nba_adapter.fetch_upcoming_games()
        db.close()
    """
    return SportAdapter(sport_id, db)


# =============================================================================
# CONVENIENCE EXPORTS
# =============================================================================

__all__ = [
    "SportAdapter",
    "create_sport_adapter",
    # Config functions
    "get_sport_config",
    "get_position_averages",
    "get_espn_sport_path",
    "get_recommendation_threshold",
    "get_variance_percent",
    "supports_per_36_stats",
    "get_active_field_value",
    "get_active_field_is_boolean",
    "is_stat_relevant_for_position",
    "get_primary_stat_for_position",
    "get_default_stat_types",
    "get_cache_ttl",
    # Config data
    "SPORT_CONFIGS",
    "POSITION_AVERAGES",
    "NBA_CONFIG",
    "NFL_CONFIG",
    "MLB_CONFIG",
    "NHL_CONFIG",
]
