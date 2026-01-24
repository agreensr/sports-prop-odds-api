"""NBA API adapter for normalizing data from nba_api_service.

This adapter wraps the existing NbaApiService and provides a consistent
interface for the sync orchestrator.

Data transformation:
- Raw nba_api data → Normalized game format for matching
- Uses nba_game_id format (e.g., "0022400001")
- Includes team IDs (numeric) for matching
"""
import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.services.nba.nba_api_service import NbaApiService
from app.models.nba.models import Player, Game as NBAGame

logger = logging.getLogger(__name__)


class NbaApiAdapter:
    """
    Adapter for nba_api data source.

    Wraps existing NbaApiService and transforms data into
    normalized format expected by the sync orchestrator.
    """

    def __init__(self, db: Session):
        """
        Initialize the NBA API adapter.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self.nba_service = NbaApiService(db=db)

    async def fetch_games(
        self,
        lookback_days: int = 7,
        lookahead_days: int = 14,
        season: str = "2025-26"
    ) -> List[Dict[str, Any]]:
        """
        Fetch games from nba_api.

        Since nba_api doesn't have a direct "list games" endpoint,
        we'll need to use the scoreboard endpoint or fetch from
        the games table in our database.

        For now, we return games from our database that fall within
        the date range, enriched with nba_api team IDs.

        Args:
            lookback_days: Days to look back
            lookahead_days: Days to look ahead
            season: NBA season

        Returns:
            List of normalized game dicts
        """
        from app.models.nba.models import TeamMapping

        # Calculate date range
        start_date = date.today() - timedelta(days=lookback_days)
        end_date = date.today() + timedelta(days=lookahead_days)

        # Fetch games from our database
        games = self.db.query(NBAGame).filter(
            NBAGame.game_date >= datetime.combine(start_date, datetime.min.time()),
            NBAGame.game_date <= datetime.combine(end_date, datetime.max.time()),
            NBAGame.id_source == 'nba'
        ).all()

        # Enrich with team IDs from team_mappings
        result = []
        for game in games:
            # Get team IDs
            home_team = self.db.query(TeamMapping).filter(
                TeamMapping.nba_abbreviation == game.home_team
            ).first()

            away_team = self.db.query(TeamMapping).filter(
                TeamMapping.nba_abbreviation == game.away_team
            ).first()

            if not home_team or not away_team:
                logger.warning(
                    f"Team mapping not found for game {game.external_id}: "
                    f"{game.away_team} @ {game.home_team}"
                )
                continue

            result.append({
                'id': game.external_id,  # nba_game_id
                'game_date': game.game_date,
                'home_team': game.home_team,
                'away_team': game.away_team,
                'home_team_id': home_team.nba_team_id,
                'away_team_id': away_team.nba_team_id,
                'season': game.season,
                'status': game.status
            })

        logger.info(f"Fetched {len(result)} games from nba_api (via database)")
        return result

    async def fetch_player_stats(
        self,
        nba_player_id: int,
        games_limit: int = 50,
        season: str = "2025-26"
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch player statistics from nba_api.

        Args:
            nba_player_id: nba_api numeric player ID
            games_limit: Number of recent games
            season: NBA season

        Returns:
            Normalized player stats dict or None
        """
        stats = await self.nba_service.get_player_season_averages(
            player_nba_api_id=nba_player_id,
            games_limit=games_limit,
            season=season
        )

        if not stats:
            return None

        return {
            'nba_player_id': nba_player_id,
            'games_count': stats['games_count'],
            'points_per_36': stats['points_per_36'],
            'rebounds_per_36': stats['rebounds_per_36'],
            'assists_per_36': stats['assists_per_36'],
            'threes_per_36': stats['threes_per_36'],
            'avg_minutes': stats['avg_minutes'],
            'last_game_date': stats['last_game_date']
        }

    async def fetch_boxscore(
        self,
        nba_game_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch boxscore for a specific game.

        Args:
            nba_game_id: nba_api game ID

        Returns:
            Boxscore data or None
        """
        # This would use the nba_api boxscore endpoint
        # For now, return None as this is a placeholder
        # In production, you'd implement:
        # from nba_api.stats.endpoints import boxscoretraditionalv2
        logger.warning(f"Boxscore fetch not implemented for game {nba_game_id}")
        return None

    async def sync_all_player_stats(
        self,
        games_limit: int = 50,
        season: str = "2025-26"
    ) -> Dict[str, int]:
        """
        Sync all active player stats.

        Args:
            games_limit: Number of games to average
            season: NBA season

        Returns:
            Sync results dict
        """
        return await self.nba_service.sync_all_active_players(
            games_limit=games_limit,
            season=season
        )

    def get_player_by_nba_id(self, nba_player_id: int) -> Optional[Player]:
        """
        Get player from database by nba_api ID.

        Args:
            nba_player_id: nba_api numeric player ID

        Returns:
            Player instance or None
        """
        return self.db.query(Player).filter(
            Player.nba_api_id == nba_player_id
        ).first()

    def get_team_mapping(self, abbreviation: str) -> Optional[Dict[str, Any]]:
        """
        Get team mapping by abbreviation.

        Args:
            abbreviation: 3-letter team abbreviation

        Returns:
            Team mapping dict or None
        """
        from app.models.nba.models import TeamMapping

        mapping = self.db.query(TeamMapping).filter(
            TeamMapping.nba_abbreviation == abbreviation
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
