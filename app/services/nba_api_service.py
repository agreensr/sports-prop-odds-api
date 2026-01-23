"""
NBA API Service for fetching player statistics from NBA.com.

This service uses the nba_api package to fetch:
- Player game logs (last N games for a player)
- Player season averages (per-36 stats)
- Team matchup stats (offensive/defensive ratings)

Key benefits for prediction accuracy:
- Uses player's actual recent performance instead of position averages
- Provides per-36 stats for minutes-based predictions
- Caches results to avoid rate limiting and improve performance

Data Flow:
    nba_api → NbaApiService → Cache → Database (player_season_stats) → PredictionService
"""
import asyncio
import logging
import time
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
import uuid

from app.models.models import Player, PlayerSeasonStats

logger = logging.getLogger(__name__)

# Default season (adjust based on current date)
DEFAULT_SEASON = "2025-26"

# Rate limiting settings
REQUEST_DELAY_SECONDS = 1.0  # Delay between requests to avoid rate limiting
MAX_RETRIES = 3  # Maximum number of retries for timeout errors
RETRY_DELAY_SECONDS = 2.0  # Initial retry delay (doubles each retry)


class NbaApiService:
    """
    Service for fetching player statistics from NBA.com via nba_api.

    Provides per-36 stats for predictions by:
    1. Fetching player game logs (last N games)
    2. Calculating per-36 averages
    3. Caching in database for 24-hour TTL
    """

    def __init__(self, db: Session, cache_ttl_hours: int = 24):
        """
        Initialize NBA API service.

        Args:
            db: SQLAlchemy database session
            cache_ttl_hours: Cache TTL in hours (default: 24)
        """
        self.db = db
        self.cache_ttl_hours = cache_ttl_hours
        self._nba_api = None  # Lazy load nba_api

    @property
    def nba_api(self):
        """Lazy load nba_api package."""
        if self._nba_api is None:
            try:
                from nba_api.stats.static import players
                from nba_api.stats.endpoints import playergamelog, leaguedashteamstats
                self._nba_api = {
                    'players': players,
                    'playergamelog': playergamelog,
                    'leaguedashteamstats': leaguedashteamstats
                }
                logger.info("nba_api package loaded successfully")
            except ImportError as e:
                logger.error(f"Failed to import nba_api: {e}")
                logger.error("Install with: pip install nba_api")
                self._nba_api = None
        return self._nba_api

    async def get_player_game_logs(
        self,
        player_nba_api_id: int,
        games_limit: int = 50,
        season: str = DEFAULT_SEASON,
        retries: int = 0
    ) -> Optional[List[Dict]]:
        """
        Fetch player game logs from nba_api with retry logic and delays.

        Args:
            player_nba_api_id: Player's nba_api numeric ID (nba_api_id in our DB)
            games_limit: Number of recent games to fetch (default: 50)
            season: NBA season (default: 2025-26)
            retries: Current retry count (for internal use)

        Returns:
            List of game log dictionaries or None if fetch fails
        """
        if not self.nba_api:
            logger.error("nba_api package not available")
            return None

        # Add delay before request to avoid rate limiting
        await asyncio.sleep(REQUEST_DELAY_SECONDS)

        try:
            from nba_api.stats.endpoints import playergamelog

            # Fetch game logs using numeric nba_api_id
            gamelog = playergamelog.PlayerGameLog(
                player_id=player_nba_api_id,
                season=season,
                season_type_all_star='Regular Season'
            )

            # Get data frames
            df = gamelog.get_data_frames()[0] if gamelog.get_data_frames() else None

            if df is None or df.empty:
                logger.warning(f"No game logs found for nba_api_id {player_nba_api_id}")
                return None

            # Take the last N games
            recent_games = df.tail(games_limit)

            # Convert to list of dictionaries
            games = []
            for _, row in recent_games.iterrows():
                games.append({
                    'game_date': datetime.strptime(row['GAME_DATE'], '%b %d, %Y').date(),
                    'minutes': self._parse_minutes(row.get('MIN', '0')),
                    'points': row.get('PTS', 0),
                    'rebounds': row.get('REB', 0),
                    'assists': row.get('AST', 0),
                    'threes': row.get('FG3M', 0),
                })

            logger.debug(f"Fetched {len(games)} game logs for nba_api_id {player_nba_api_id}")
            return games

        except Exception as e:
            error_str = str(e)
            # Check if it's a timeout error (retryable)
            is_timeout = 'timeout' in error_str.lower() or 'timed out' in error_str.lower()

            if is_timeout and retries < MAX_RETRIES:
                retry_delay = RETRY_DELAY_SECONDS * (2 ** retries)  # Exponential backoff
                logger.warning(
                    f"Timeout error for nba_api_id {player_nba_api_id} "
                    f"(attempt {retries + 1}/{MAX_RETRIES}), retrying in {retry_delay}s..."
                )
                await asyncio.sleep(retry_delay)
                return await self.get_player_game_logs(
                    player_nba_api_id=player_nba_api_id,
                    games_limit=games_limit,
                    season=season,
                    retries=retries + 1
                )
            else:
                logger.error(f"Error fetching game logs for nba_api_id {player_nba_api_id}: {e}")
                return None

    def _parse_minutes(self, min_str) -> float:
        """
        Parse minutes (int, float, or string "MM:SS") to float minutes.

        Args:
            min_str: Minutes as int (31), float (31.5), or "MM:SS" string ("25:30")

        Returns:
            Minutes as float (e.g., 25.5)
        """
        if min_str is None:
            return 0.0

        # Handle numeric types directly
        if isinstance(min_str, (int, float)):
            return float(min_str)

        # Handle string types
        if isinstance(min_str, str):
            min_str = min_str.strip()
            if not min_str:
                return 0.0

            try:
                parts = min_str.split(':')
                if len(parts) == 2:
                    minutes = int(parts[0])
                    seconds = int(parts[1])
                    return minutes + (seconds / 60.0)
                return float(min_str)
            except (ValueError, AttributeError):
                return 0.0

        return 0.0

    async def get_player_season_averages(
        self,
        player_nba_api_id: int,
        games_limit: int = 50,
        season: str = DEFAULT_SEASON
    ) -> Optional[Dict]:
        """
        Calculate player season averages (per-36) from recent games.

        This is the primary method for predictions - returns per-36 stats
        that can be multiplied by projected minutes.

        Args:
            player_nba_api_id: Player's nba_api numeric ID
            games_limit: Number of recent games to average (default: 15)
            season: NBA season

        Returns:
            Dict with per-36 stats or None if unavailable:
            {
                'games_count': int,
                'points_per_36': float,
                'rebounds_per_36': float,
                'assists_per_36': float,
                'threes_per_36': float,
                'avg_minutes': float,
                'last_game_date': date
            }
        """
        # Check cache first - find player by nba_api_id
        player = self.db.query(Player).filter(
            Player.nba_api_id == player_nba_api_id
        ).first()

        if player:
            cached = self.db.query(PlayerSeasonStats).filter(
                PlayerSeasonStats.player_id == player.id,
                PlayerSeasonStats.season == season,
                PlayerSeasonStats.fetched_at >= datetime.now() - timedelta(hours=self.cache_ttl_hours)
            ).first()

            if cached:
                logger.info(f"Using cached stats for nba_api_id {player_nba_api_id}")
                return {
                    'games_count': cached.games_count,
                    'points_per_36': cached.points_per_36,
                    'rebounds_per_36': cached.rebounds_per_36,
                    'assists_per_36': cached.assists_per_36,
                    'threes_per_36': cached.threes_per_36,
                    'avg_minutes': cached.avg_minutes,
                    'last_game_date': cached.last_game_date
                }

        # Fetch from nba_api
        game_logs = await self.get_player_game_logs(player_nba_api_id, games_limit, season)

        if not game_logs:
            logger.warning(f"No game logs available for nba_api_id {player_nba_api_id}")
            return None

        # Calculate averages
        total_minutes = sum(g['minutes'] for g in game_logs)
        games_with_minutes = sum(1 for g in game_logs if g['minutes'] > 0)

        if games_with_minutes == 0:
            logger.warning(f"No games with minutes for nba_api_id {player_nba_api_id}")
            return None

        avg_minutes = total_minutes / len(game_logs)

        # Calculate per-36 stats (only from games where player played)
        total_points = sum(g['points'] for g in game_logs if g['minutes'] > 0)
        total_rebounds = sum(g['rebounds'] for g in game_logs if g['minutes'] > 0)
        total_assists = sum(g['assists'] for g in game_logs if g['minutes'] > 0)
        total_threes = sum(g['threes'] for g in game_logs if g['minutes'] > 0)

        total_minutes_played = sum(g['minutes'] for g in game_logs if g['minutes'] > 0)

        if total_minutes_played == 0:
            return None

        stats = {
            'games_count': len(game_logs),
            'points_per_36': round(total_points * 36.0 / total_minutes_played, 2),
            'rebounds_per_36': round(total_rebounds * 36.0 / total_minutes_played, 2),
            'assists_per_36': round(total_assists * 36.0 / total_minutes_played, 2),
            'threes_per_36': round(total_threes * 36.0 / total_minutes_played, 2),
            'avg_minutes': round(avg_minutes, 1),
            'last_game_date': max(g['game_date'] for g in game_logs)
        }

        # Cache in database
        if player:
            self._cache_season_stats(player.id, season, stats)

        logger.debug(f"Calculated per-36 stats for nba_api_id {player_nba_api_id}: {stats}")
        return stats

    def _cache_season_stats(self, player_id: str, season: str, stats: Dict) -> None:
        """
        Cache player season stats in database.

        Args:
            player_id: Player ID
            season: NBA season
            stats: Stats dictionary from get_player_season_averages
        """
        try:
            # Check for existing entry
            existing = self.db.query(PlayerSeasonStats).filter(
                PlayerSeasonStats.player_id == player_id,
                PlayerSeasonStats.season == season
            ).first()

            now = datetime.now()

            if existing:
                # Update existing
                existing.games_count = stats['games_count']
                existing.points_per_36 = stats['points_per_36']
                existing.rebounds_per_36 = stats['rebounds_per_36']
                existing.assists_per_36 = stats['assists_per_36']
                existing.threes_per_36 = stats['threes_per_36']
                existing.avg_minutes = stats['avg_minutes']
                existing.last_game_date = stats['last_game_date']
                existing.fetched_at = now
                existing.updated_at = now
            else:
                # Create new entry
                season_stats = PlayerSeasonStats(
                    id=str(uuid.uuid4()),
                    player_id=player_id,
                    season=season,
                    games_count=stats['games_count'],
                    points_per_36=stats['points_per_36'],
                    rebounds_per_36=stats['rebounds_per_36'],
                    assists_per_36=stats['assists_per_36'],
                    threes_per_36=stats['threes_per_36'],
                    avg_minutes=stats['avg_minutes'],
                    last_game_date=stats['last_game_date'],
                    fetched_at=now,
                    created_at=now,
                    updated_at=now
                )
                self.db.add(season_stats)

            self.db.commit()
            logger.debug(f"Cached season stats for player {player_id}")

        except Exception as e:
            logger.error(f"Error caching season stats: {e}")
            self.db.rollback()

    async def get_team_matchup_stats(
        self,
        team_abbr: str,
        season: str = DEFAULT_SEASON
    ) -> Optional[Dict]:
        """
        Get team offensive/defensive ratings for matchup context.

        Args:
            team_abbr: Team abbreviation (e.g., "BOS", "LAL")
            season: NBA season

        Returns:
            Dict with team ratings or None if unavailable
        """
        if not self.nba_api:
            return None

        try:
            from nba_api.stats.endpoints import leaguedashteamstats

            # Fetch team stats
            team_stats = leaguedashteamstats.LeagueDashTeamStats(
                season=season,
                measure_type="Base",
                per_mode="PerGame",
                plus_minus="N",
                pace_adjust="N",
                rank="N",
                outcome="",
                location="",
                month="0",
                season_segment="",
                date_from="",
                date_to="",
                opponent_team_id="0",
                vs_conference="",
                vs_division=""
            )

            df = team_stats.get_data_frames()[0] if team_stats.get_data_frames() else None

            if df is None or df.empty:
                return None

            # Find the team
            team_row = df[df['TEAM_ABBREVIATION'] == team_abbr]

            if team_row.empty:
                logger.warning(f"Team {team_abbr} not found in nba_api")
                return None

            row = team_row.iloc[0]

            return {
                'offensive_rating': row.get('OFF_RATING', 0),
                'defensive_rating': row.get('DEF_RATING', 0),
                'pace': row.get('PACE', 0),
                'pts_per_game': row.get('PTS', 0),
                'reb_per_game': row.get('REB', 0),
                'ast_per_game': row.get('AST', 0),
            }

        except Exception as e:
            logger.error(f"Error fetching team stats for {team_abbr}: {e}")
            return None

    async def sync_all_active_players(
        self,
        games_limit: int = 50,
        season: str = DEFAULT_SEASON
    ) -> Dict[str, int]:
        """
        Sync season stats for all active players.

        This is used by the scheduled sync script to pre-fetch
        player stats and cache them in the database.

        Args:
            games_limit: Number of games to average
            season: NBA season

        Returns:
            Dict with sync results
        """
        players = self.db.query(Player).filter(
            Player.active == True,
            Player.nba_api_id.isnot(None)  # Only sync players with nba_api_id
        ).all()

        success_count = 0
        error_count = 0
        no_data_count = 0

        for player in players:
            try:
                stats = await self.get_player_season_averages(
                    player.nba_api_id,
                    games_limit,
                    season
                )

                if stats:
                    success_count += 1
                else:
                    no_data_count += 1

            except Exception as e:
                logger.error(f"Error syncing stats for {player.name}: {e}")
                error_count += 1

        return {
            'total': len(players),
            'success': success_count,
            'no_data': no_data_count,
            'errors': error_count
        }
