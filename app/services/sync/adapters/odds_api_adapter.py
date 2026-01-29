"""Odds API adapter for normalizing data from odds_api_service.

This adapter wraps the existing OddsApiService and provides a consistent
interface for the sync orchestrator.

Data transformation:
- Raw The Odds API data → Normalized game format for matching
- Uses odds_event_id format (e.g., "abc123def456")
- Includes team names (strings) for matching
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.core.odds_api_service import get_odds_service

logger = logging.getLogger(__name__)


class OddsApiAdapter:
    """
    Adapter for The Odds API data source.

    Wraps existing OddsApiService and transforms data into
    normalized format expected by the sync orchestrator.
    """

    def __init__(self, db: Session, api_key: Optional[str] = None):
        """
        Initialize the Odds API adapter.

        Args:
            db: SQLAlchemy database session
            api_key: The Odds API key (defaults to settings)
        """
        self.db = db
        self.api_key = api_key or settings.THE_ODDS_API_KEY
        self.odds_service = get_odds_service(self.api_key)

    async def fetch_odds(
        self,
        upcoming_only: bool = True,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Fetch odds from The Odds API.

        Args:
            upcoming_only: Only fetch upcoming games
            days: Number of days ahead to fetch

        Returns:
            List of normalized odds game dicts
        """
        try:
            games = await self.odds_service.get_upcoming_games_with_odds(days_ahead=days)

            result = []
            for game in games:
                # Parse commence_time
                commence_time = None
                if game.get('commence_time'):
                    if isinstance(game['commence_time'], str):
                        commence_time = datetime.fromisoformat(
                            game['commence_time'].replace('Z', '+00:00')
                        )
                    else:
                        commence_time = game['commence_time']

                result.append({
                    'id': game.get('id'),  # odds_event_id
                    'sport_key': game.get('sport_key'),
                    'sport_title': game.get('sport_title'),
                    'commence_time': commence_time,
                    'home_team': game.get('home_team'),
                    'away_team': game.get('away_team'),
                    'bookmakers': game.get('bookmakers', [])
                })

            logger.info(f"Fetched {len(result)} games from The Odds API")
            return result

        except Exception as e:
            logger.error(f"Error fetching odds: {e}")
            return []

    async def fetch_player_props(
        self,
        odds_event_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch player props for a specific game.

        Args:
            odds_event_id: The Odds API event ID

        Returns:
            Player props data or None
        """
        try:
            result = await self.odds_service.get_event_player_props(odds_event_id)
            return result
        except Exception as e:
            logger.error(f"Error fetching player props for {odds_event_id}: {e}")
            return None

    async def normalize_player_props(
        self,
        props_data: Dict[str, Any]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Normalize player props data into a structured format.

        Args:
            props_data: Raw player props from get_event_player_props

        Returns:
            Dict with stat_type as key and list of player props as value
        """
        result = {
            'points': [],
            'rebounds': [],
            'assists': [],
            'threes': []
        }

        if not props_data or 'data' not in props_data:
            return result

        for bookmaker in props_data['data'].get('bookmakers', []):
            bookmaker_key = bookmaker.get('key')
            bookmaker_title = bookmaker.get('title')

            for market in bookmaker.get('markets', []):
                market_key = market.get('key')  # player_points, player_rebounds, etc.

                # Map market key to our stat type
                stat_type = None
                if market_key == 'player_points':
                    stat_type = 'points'
                elif market_key == 'player_rebounds':
                    stat_type = 'rebounds'
                elif market_key == 'player_assists':
                    stat_type = 'assists'
                elif market_key == 'player_threes':
                    stat_type = 'threes'

                if not stat_type:
                    continue

                for outcome in market.get('outcomes', []):
                    player_name = outcome.get('description')
                    line = outcome.get('point')
                    price = outcome.get('price')

                    # Determine over/under from outcome name
                    selection = None
                    name_lower = outcome.get('name', '').lower()
                    if 'over' in name_lower:
                        selection = 'OVER'
                    elif 'under' in name_lower:
                        selection = 'UNDER'

                    if player_name and line is not None:
                        result[stat_type].append({
                            'player_name': player_name,
                            'line': line,
                            'selection': selection,
                            'price': price,
                            'bookmaker_key': bookmaker_key,
                            'bookmaker_title': bookmaker_title
                        })

        return result

    def get_team_mapping_by_odds_name(
        self,
        odds_team_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get team mapping by The Odds API team name.

        Args:
            odds_team_name: Team name from The Odds API

        Returns:
            Team mapping dict or None
        """
        from app.models import TeamMapping

        mapping = self.db.query(TeamMapping).filter(
            TeamMapping.odds_api_name == odds_team_name
        ).first()

        if not mapping:
            return None

        return {
            'nba_team_id': mapping.nba_team_id,
            'abbreviation': mapping.nba_abbreviation,
            'full_name': mapping.nba_full_name,
            'city': mapping.nba_city,
            'odds_api_name': mapping.odds_api_name,
            'odds_api_key': mapping.odds_api_key
        }

    async def close(self):
        """Close the odds service connection."""
        await self.odds_service.close()
