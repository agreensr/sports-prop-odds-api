"""NBA API adapter for normalizing data from nba_api_service.

This adapter wraps the existing NbaApiService and provides a consistent
interface for the sync orchestrator.

Data transformation:
- Raw nba_api data → Normalized game format for matching
- Uses nba_game_id format (e.g., "0022400001")
- Includes team IDs (numeric) for matching

Live Data Source:
- NBA.com scoreboard API: https://cdn.nba.com/static/json/liveData/scoreboard/
"""
import logging
import httpx
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
import uuid
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.services.nba.nba_api_service import NbaApiService
from app.models import Player, Game as NBAGame, TeamMapping

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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException))
    )
    async def _fetch_nba_scoreboard_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str
    ) -> Dict:
        """
        Internal method to fetch NBA scoreboard with retry logic.

        Args:
            client: HTTP client
            url: Scoreboard URL

        Returns:
            Parsed JSON response
        """
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

    async def fetch_games(
        self,
        lookback_days: int = 7,
        lookahead_days: int = 14,
        season: str = "2025-26"
    ) -> List[Dict[str, Any]]:
        """
        Fetch games from NBA.com todaysScoreboard API.

        The NBA's todaysScoreboard endpoint is the only reliable public endpoint
        that provides current and upcoming games. It returns games for today.

        Args:
            lookback_days: Days to look back (not fully supported due to API limits)
            lookahead_days: Days to look ahead (not fully supported due to API limits)
            season: NBA season (for display purposes)

        Returns:
            List of normalized game dicts
        """
        all_games = []
        base_url = "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                data = await self._fetch_nba_scoreboard_with_retry(client, base_url)

            # Extract games from scoreboard
            scoreboard = data.get("scoreboard", {})
            games_data = scoreboard.get("games", [])
            game_date_str = scoreboard.get("gameDate", "")

            logger.info(f"Fetched {len(games_data)} games from NBA.com todaysScoreboard for {game_date_str}")

            for game in games_data:
                # Skip games that don't have proper data
                if not game.get("gameId") or not game.get("homeTeam") or not game.get("awayTeam"):
                    continue

                # Parse game time
                game_time_utc = None

                if "gameTimeUTC" in game:
                    try:
                        game_time_utc = datetime.fromisoformat(
                            game["gameTimeUTC"].replace("Z", "+00:00")
                        )
                    except (ValueError, KeyError):
                        pass

                # Build game data dict
                game_data = {
                    'id': game["gameId"],  # nba_game_id
                    'game_date': game_time_utc or datetime.utcnow(),
                    'home_team': game["homeTeam"]["teamTricode"],
                    'away_team': game["awayTeam"]["teamTricode"],
                    'home_team_id': game["homeTeam"]["teamId"],
                    'away_team_id': game["awayTeam"]["teamId"],
                    'season': season,
                    'status': self._map_game_status(game.get("gameStatus", 0)),
                    'home_score': game["homeTeam"].get("score", 0),
                    'away_score': game["awayTeam"].get("score", 0),
                }

                all_games.append(game_data)

        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP error fetching games: {e}")
        except Exception as e:
            logger.error(f"Error fetching games from NBA.com: {e}")
            import traceback
            traceback.print_exc()

        logger.info(f"Fetched {len(all_games)} total games from NBA.com todaysScoreboard")

        # Create or update Game records in database
        for game_data in all_games:
            self._upsert_game(game_data)

        self.db.commit()

        return all_games

    def _infer_game_status(self, game_date: datetime) -> str:
        """
        Infer game status based on game date relative to now.

        Args:
            game_date: Game datetime

        Returns:
            Game status: scheduled, in_progress, or finished
        """
        now = datetime.utcnow()
        game_duration_hours = 3  # Approximate NBA game length

        game_end = game_date + timedelta(hours=game_duration_hours)

        if now < game_date:
            return "scheduled"
        elif game_date <= now <= game_end:
            return "in_progress"
        else:
            return "finished"

    def _upsert_game(self, game_data: Dict[str, Any]) -> None:
        """
        Create or update a Game record in the database.

        Args:
            game_data: Normalized game data dict
        """
        # Check if game exists
        existing = self.db.query(NBAGame).filter(
            NBAGame.external_id == game_data['id']
        ).first()

        # Extract season from game_data (e.g., "2025-26" -> 2025)
        season_int = int(game_data['season'].split('-')[0]) if '-' in game_data['season'] else 2025

        now = datetime.utcnow()

        if existing:
            # Update existing game
            existing.status = game_data['status']
            existing.updated_at = now
            logger.debug(f"Updated game {game_data['id']}: {game_data['away_team']} @ {game_data['home_team']}")
        else:
            # Create new game
            new_game = NBAGame(
                id=str(uuid.uuid4()),
                external_id=game_data['id'],
                id_source='nba',
                game_date=game_data['game_date'],
                away_team=game_data['away_team'],
                home_team=game_data['home_team'],
                season=season_int,
                status=game_data['status'],
                created_at=now,
                updated_at=now
            )
            self.db.add(new_game)
            logger.info(f"Created game {game_data['id']}: {game_data['away_team']} @ {game_data['home_team']} on {game_data['game_date']}")

    def _map_game_status(self, nba_status: int) -> str:
        """Map NBA game status to our status values."""
        status_map = {
            0: "scheduled",  # Not started
            1: "scheduled",  # Scheduled/pre-game
            2: "in_progress",  # In progress
            3: "finished",  # Finished
        }
        return status_map.get(nba_status, "unknown")

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
        from app.models import TeamMapping

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
