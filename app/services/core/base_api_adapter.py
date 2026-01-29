"""
Base API Adapter for sport-specific data sources.

This module provides a common base class and sport configuration for
creating adapters that fetch data from various external APIs (ESPN, NBA.com, etc.).

The base adapter provides:
- Shared retry logic with exponential backoff
- Common data normalization patterns
- Sport-specific configuration framework
- Database helpers for upsert operations

Usage:
    from app.services.core.base_api_adapter import SportAdapter, SPORT_CONFIG

    # Use config mode for existing sports
    nba_adapter = SportAdapter(sport_id="nba", db=db)
    games = await nba_adapter.fetch_games()

    # Or extend for custom adapters
    class CustomAdapter(BaseAPIAdapter):
        def __init__(self, db: Session):
            super().__init__(db, sport_id="custom")

    adapter = CustomAdapter(db)
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
import httpx
import uuid
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.logging import get_logger

logger = get_logger(__name__)


# Sport configuration for API adapters
# This configuration can be extended as new sports are added
SPORT_CONFIG = {
    'nba': {
        'name': 'NBA',
        'espn_league': 'nba',
        'espn_endpoint': 'nba',  # For ESPN API calls
        'team_count': 30,
        'season_format': 'YYYY-YY',  # e.g., "2025-26"
        'current_season': '2025-26',
        'api_base_url': 'https://cdn.nba.com/static/json/liveData/scoreboard/',
        'scoreboard_file': 'todaysScoreboard_00.json',
        'game_id_format': 'string',  # nba_game_id is string like "0022400001"
        'team_id_type': 'integer',  # nba_team_id is int
        'status_map': {
            0: 'scheduled',
            1: 'scheduled',  # Pre-game
            2: 'in_progress',
            3: 'finished'
        }
    },
    'nfl': {
        'name': 'NFL',
        'espn_league': 'nfl',
        'espn_endpoint': 'nfl',
        'team_count': 32,
        'season_format': 'YYYY',  # e.g., "2025"
        'current_season': '2025',
        'api_base_url': None,  # To be implemented
        'scoreboard_file': None,
        'game_id_format': 'string',
        'team_id_type': 'integer',
        'status_map': {}
    },
    'mlb': {
        'name': 'MLB',
        'espn_league': 'mlb',
        'espn_endpoint': 'mlb',
        'team_count': 30,
        'season_format': 'YYYY',
        'current_season': '2025',
        'api_base_url': None,
        'scoreboard_file': None,
        'game_id_format': 'string',
        'team_id_type': 'integer',
        'status_map': {}
    },
    'nhl': {
        'name': 'NHL',
        'espn_league': 'nhl',
        'espn_endpoint': 'nhl',
        'team_count': 32,
        'season_format': 'YYYY',
        'current_season': '2025',
        'api_base_url': None,
        'scoreboard_file': None,
        'game_id_format': 'string',
        'team_id_type': 'integer',
        'status_map': {}
    }
}


class BaseAPIAdapter:
    """
    Base class for API adapters that fetch data from external sports APIs.

    This class provides common functionality for:
    - Retry logic with exponential backoff
    - Game upsert operations
    - Status mapping
    - Team mapping lookups

    Sport-specific adapters should extend this class and implement
    the abstract methods for their particular data source.

    Attributes:
        db: Database session
        sport_id: Sport identifier (nba, nfl, mlb, nhl)
        config: Sport configuration dict
    """

    def __init__(self, db: Session, sport_id: str = "nba"):
        """
        Initialize the base API adapter.

        Args:
            db: SQLAlchemy database session
            sport_id: Sport identifier (must exist in SPORT_CONFIG)
        """
        if sport_id not in SPORT_CONFIG:
            raise ValueError(f"Unknown sport_id: {sport_id}. Must be one of: {list(SPORT_CONFIG.keys())}")

        self.db = db
        self.sport_id = sport_id
        self.config = SPORT_CONFIG[sport_id]

    def get_config(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value for the current sport.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value
        """
        return self.config.get(key, default)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException))
    )
    async def _fetch_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str
    ) -> Dict:
        """
        Internal method to fetch data with retry logic.

        Args:
            client: HTTP client
            url: URL to fetch

        Returns:
            Parsed JSON response

        Raises:
            httpx.HTTPStatusError: On HTTP errors
            httpx.RequestError: On network errors
            httpx.TimeoutException: On timeout
        """
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

    async def fetch_with_retry(
        self,
        url: str,
        timeout: float = 30.0
    ) -> Optional[Dict]:
        """
        Fetch data from URL with retry logic.

        A convenience wrapper around _fetch_with_retry that creates
        its own HTTP client.

        Args:
            url: URL to fetch
            timeout: Request timeout in seconds

        Returns:
            Parsed JSON response or None if all retries fail
        """
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                return await self._fetch_with_retry(client, url)
        except Exception as e:
            logger.error(f"Failed to fetch {url} after retries: {e}")
            return None

    def infer_game_status(self, game_date: datetime, game_duration_hours: int = 3) -> str:
        """
        Infer game status based on game date relative to now.

        Args:
            game_date: Game datetime
            game_duration_hours: Approximate game length in hours

        Returns:
            Game status: scheduled, in_progress, or finished
        """
        now = datetime.utcnow()
        game_end = game_date + timedelta(hours=game_duration_hours)

        if now < game_date:
            return "scheduled"
        elif game_date <= now <= game_end:
            return "in_progress"
        else:
            return "finished"

    def map_status_code(self, status_code: int) -> str:
        """
        Map API-specific status code to standard status values.

        Args:
            status_code: API status code

        Returns:
            Standard status string (scheduled, in_progress, finished, unknown)
        """
        status_map = self.get_config('status_map', {})
        return status_map.get(status_code, "unknown")

    def upsert_game(
        self,
        game_data: Dict[str, Any],
        game_model_class
    ) -> None:
        """
        Create or update a Game record in the database.

        This method uses a check-then-insert pattern with proper handling
        for race conditions.

        Args:
            game_data: Normalized game data dict with keys:
                - id: External game ID
                - game_date: Game datetime
                - away_team: Away team abbreviation
                - home_team: Home team abbreviation
                - season: Season year (int)
                - status: Game status
            game_model_class: SQLAlchemy Game model class
        """
        from sqlalchemy import IntegrityError

        now = datetime.utcnow()

        # Check if game exists
        existing = game_model_class.query.filter(
            game_model_class.external_id == game_data['id']
        ).first()

        if existing:
            # Update existing game
            existing.status = game_data.get('status', existing.status)
            existing.updated_at = now

            # Update scores if provided
            if 'home_score' in game_data:
                existing.home_score = game_data['home_score']
            if 'away_score' in game_data:
                existing.away_score = game_data['away_score']

            logger.debug(f"Updated game {game_data['id']}: {game_data['away_team']} @ {game_data['home_team']}")
        else:
            # Create new game
            new_game = game_model_class(
                id=str(uuid.uuid4()),
                external_id=game_data['id'],
                id_source=self.sport_id,
                game_date=game_data['game_date'],
                away_team=game_data['away_team'],
                home_team=game_data['home_team'],
                season=game_data['season'],
                status=game_data.get('status', 'scheduled'),
                home_score=game_data.get('home_score'),
                away_score=game_data.get('away_score'),
                created_at=now,
                updated_at=now
            )
            self.db.add(new_game)
            logger.info(f"Created game {game_data['id']}: {game_data['away_team']} @ {game_data['home_team']} on {game_data['game_date']}")

    def get_team_mapping_by_abbreviation(
        self,
        abbreviation: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get team mapping by abbreviation.

        Args:
            abbreviation: 3-letter team abbreviation

        Returns:
            Team mapping dict with keys:
            - nba_team_id (if applicable)
            - abbreviation
            - full_name
            - odds_api_name
            - odds_api_key
        """
        from app.models import TeamMapping

        # Try the sport-specific column first
        id_column = f"{self.sport_id}_abbreviation"

        mapping = self.db.query(TeamMapping).filter(
            getattr(TeamMapping, id_column) == abbreviation
        ).first()

        if mapping:
            return {
                f'{self.sport_id}_team_id': getattr(mapping, f'{self.sport_id}_team_id'),
                'abbreviation': getattr(mapping, 'nba_abbreviation'),
                'full_name': getattr(mapping, 'nba_full_name'),
                'city': getattr(mapping, 'nba_city'),
                'odds_api_name': mapping.odds_api_name,
                'odds_api_key': mapping.odds_api_key
            }

        # Fallback to nba_abbreviation (for backward compatibility)
        mapping = self.db.query(TeamMapping).filter(
            TeamMapping.nba_abbreviation == abbreviation
        ).first()

        if mapping:
            return {
                'nba_team_id': mapping.nba_team_id,
                'abbreviation': mapping.nba_abbreviation,
                'full_name': mapping.nba_full_name,
                'city': mapping.nba_city,
                'odds_api_name': mapping.odds_api_name,
                'odds_api_key': mapping.odds_api_key
            }

        return None

    async def close(self):
        """
        Close any open connections or resources.

        Override in subclasses if needed.
        """
        pass


class SportAdapter(BaseAPIAdapter):
    """
    Generic sport adapter using configuration-driven approach.

    This adapter provides a simplified way to fetch data for sports
    that follow common patterns, using configuration instead of
    code duplication.

    For sports with unique data patterns, create a subclass that
    extends BaseAPIAdapter and overrides the necessary methods.
    """

    def __init__(
        self,
        db: Session,
        sport_id: str,
        api_service=None
    ):
        """
        Initialize the sport adapter.

        Args:
            db: Database session
            sport_id: Sport identifier (nba, nfl, mlb, nhl)
            api_service: Optional API service instance for data fetching
        """
        super().__init__(db, sport_id)
        self.api_service = api_service

    async def fetch_games(
        self,
        lookback_days: int = 7,
        lookahead_days: int = 14,
        season: str = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch games for this sport.

        This is a placeholder implementation. Subclasses should override
        this method with sport-specific logic.

        Args:
            lookback_days: Days to look back
            lookahead_days: Days to look ahead
            season: Season string

        Returns:
            List of normalized game dicts
        """
        logger.warning(f"fetch_games not implemented for sport {self.sport_id}")
        return []

    async def fetch_player_stats(
        self,
        player_id: str,
        games_limit: int = 50,
        season: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch player statistics.

        This is a placeholder implementation. Subclasses should override
        this method with sport-specific logic.

        Args:
            player_id: Player ID (sport-specific format)
            games_limit: Number of games to average
            season: Season string

        Returns:
            Normalized player stats dict or None
        """
        logger.warning(f"fetch_player_stats not implemented for sport {self.sport_id}")
        return None

    async def fetch_boxscore(
        self,
        game_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch boxscore for a specific game.

        This is a placeholder implementation. Subclasses should override
        this method with sport-specific logic.

        Args:
            game_id: Game ID (sport-specific format)

        Returns:
            Boxscore data or None
        """
        logger.warning(f"fetch_boxscore not implemented for sport {self.sport_id}")
        return None


def get_sport_adapter(
    db: Session,
    sport_id: str = "nba"
) -> BaseAPIAdapter:
    """
    Factory function to get a sport adapter.

    This function returns the appropriate adapter for the given sport.
    Currently only NBA has a full implementation, but other sports can
    be added by extending BaseAPIAdapter.

    Args:
        db: Database session
        sport_id: Sport identifier

    Returns:
        Sport adapter instance

    Raises:
        ValueError: If sport_id is not supported

    Example:
        >>> adapter = get_sport_adapter(db, "nba")
        >>> games = await adapter.fetch_games()
    """
    # Import here to avoid circular dependency
    from app.services.sync.adapters.nba_api_adapter import NbaApiAdapter

    # For now, only NBA has a full implementation
    if sport_id == "nba":
        return NbaApiAdapter(db)
    else:
        # For other sports, return the config-based adapter
        # (which will need to be extended with actual API calls)
        return SportAdapter(db, sport_id=sport_id)
