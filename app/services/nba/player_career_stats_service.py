"""
Player Career Stats Service for fetching player career statistics from NBA.com.

This service uses the nba_api package to fetch:
- Player career stats by season (SeasonTotalsRegularSeason)
- Season-level aggregated statistics
- Last N games performance breakdown

Key features:
- Uses playercareerstats endpoint for season-level data
- Filters for specific season (2025-26)
- Provides career totals and season averages
- Integrates with existing player database

Data Flow:
    nba_api playercareerstats → PlayerCareerStatsService → Database/Telegram Notification
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from app.models import Player

logger = logging.getLogger(__name__)

# Default season
DEFAULT_SEASON = "2025-26"

# Rate limiting settings
REQUEST_DELAY_SECONDS = 1.0
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2.0


class PlayerCareerStatsService:
    """
    Service for fetching player career statistics from NBA.com via nba_api.

    Provides season-level career stats including:
    - Season totals (GP, PTS, REB, AST, FG3M)
    - Career totals across all seasons
    - Per-game averages
    """

    def __init__(self, db: Session):
        """
        Initialize Player Career Stats service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self._nba_api = None  # Lazy load nba_api

    @property
    def nba_api(self):
        """Lazy load nba_api package."""
        if self._nba_api is None:
            try:
                from nba_api.stats.endpoints import playercareerstats
                self._nba_api = {
                    'playercareerstats': playercareerstats
                }
                logger.info("nba_api playercareerstats loaded successfully")
            except ImportError as e:
                logger.error(f"Failed to import nba_api playercareerstats: {e}")
                self._nba_api = None
        return self._nba_api

    async def get_player_career_stats(
        self,
        player_nba_api_id: int,
        season: str = DEFAULT_SEASON,
        retries: int = 0
    ) -> Optional[Dict]:
        """
        Fetch player career stats from nba_api with retry logic.

        Args:
            player_nba_api_id: Player's nba_api numeric ID (nba_api_id in our DB)
            season: NBA season (default: 2025-26)
            retries: Current retry count (for internal use)

        Returns:
            Dict with career stats or None if fetch fails:
            {
                'player_id': int,
                'season': str,
                'team_id': int,
                'team_abbr': str,
                'player_age': int,
                'games_played': int,
                'games_started': int,
                'minutes': float,
                'points': int,
                'rebounds': int,
                'assists': int,
                'threes': int,
                'points_per_game': float,
                'rebounds_per_game': float,
                'assists_per_game': float,
                'threes_per_game': float
            }
        """
        if not self.nba_api:
            logger.error("nba_api package not available")
            return None

        # Add delay before request to avoid rate limiting
        await asyncio.sleep(REQUEST_DELAY_SECONDS)

        try:
            from nba_api.stats.endpoints import playercareerstats

            # Fetch career stats using numeric nba_api_id
            career_stats = playercareerstats.PlayerCareerStats(
                player_id=player_nba_api_id,
                per_mode36='PerGame'
            )

            # Get data frames
            data_frames = career_stats.get_data_frames()

            if not data_frames or len(data_frames) == 0:
                logger.warning(f"No career stats found for nba_api_id {player_nba_api_id}")
                return None

            # SeasonTotalsRegularSeason is at index 0
            season_totals_df = data_frames[0]

            if season_totals_df.empty:
                logger.warning(f"No season totals found for nba_api_id {player_nba_api_id}")
                return None

            # Filter for the requested season
            # SEASON_ID is in format "2025-26" or "22025" depending on the endpoint
            season_row = season_totals_df[
                (season_totals_df['SEASON_ID'].astype(str) == season) |
                (season_totals_df['SEASON_ID'].astype(str).str.contains(season.split('-')[0]))
            ]

            if season_row.empty:
                logger.warning(
                    f"No stats found for season {season} (SEASON_ID starting with {season_id_prefix}) "
                    f"for nba_api_id {player_nba_api_id}"
                )
                return None

            # Get the first matching row (most recent team if player was traded)
            row = season_row.iloc[0]

            stats = {
                'player_id': player_nba_api_id,
                'season': season,
                'team_id': row.get('TEAM_ID'),
                'team_abbr': row.get('TEAM_ABBREVIATION'),
                'player_age': row.get('PLAYER_AGE'),
                'games_played': int(row.get('GP', 0)),
                'games_started': int(row.get('GS', 0)),
                'minutes': float(row.get('MIN', 0)),
                'points': int(row.get('PTS', 0)),
                'rebounds': int(row.get('REB', 0)),
                'assists': int(row.get('AST', 0)),
                'threes': int(row.get('FG3M', 0)),
                'field_goals_made': int(row.get('FGM', 0)),
                'field_goals_attempted': int(row.get('FGA', 0)),
                'fg_pct': float(row.get('FG_PCT', 0)),
                'threes_attempted': int(row.get('FG3A', 0)),
                'threes_pct': float(row.get('FG3_PCT', 0)),
                'offensive_rebounds': int(row.get('OREB', 0)),
                'defensive_rebounds': int(row.get('DREB', 0)),
            }

            # Calculate per-game averages
            gp = stats['games_played']
            if gp > 0:
                stats['points_per_game'] = round(stats['points'] / gp, 2)
                stats['rebounds_per_game'] = round(stats['rebounds'] / gp, 2)
                stats['assists_per_game'] = round(stats['assists'] / gp, 2)
                stats['threes_per_game'] = round(stats['threes'] / gp, 2)
            else:
                stats['points_per_game'] = 0.0
                stats['rebounds_per_game'] = 0.0
                stats['assists_per_game'] = 0.0
                stats['threes_per_game'] = 0.0

            logger.info(
                f"Fetched career stats for nba_api_id {player_nba_api_id} "
                f"({stats['team_abbr']}) season {season}: "
                f"{stats['points_per_game']} PTS, {stats['rebounds_per_game']} REB, "
                f"{stats['assists_per_game']} AST, {stats['threes_per_game']} 3PM"
            )

            return stats

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
                return await self.get_player_career_stats(
                    player_nba_api_id=player_nba_api_id,
                    season=season,
                    retries=retries + 1
                )
            else:
                logger.error(f"Error fetching career stats for nba_api_id {player_nba_api_id}: {e}")
                return None

    async def get_last_10_games_stats(
        self,
        player_nba_api_id: int,
        season: str = DEFAULT_SEASON,
        retries: int = 0
    ) -> Optional[List[Dict]]:
        """
        Fetch player's last 10 games stats from nba_api using playergamelog.

        Note: While PlayerCareerStats provides season totals, for last N games
        we need to use PlayerGameLog endpoint which provides individual game data.

        Args:
            player_nba_api_id: Player's nba_api numeric ID
            season: NBA season (default: 2025-26)
            retries: Current retry count

        Returns:
            List of game stat dictionaries or None if fetch fails:
            [
                {
                    'game_date': date,
                    'matchup': str,
                    'points': int,
                    'rebounds': int,
                    'assists': int,
                    'threes': int,
                    'minutes': float
                },
                ...
            ]
        """
        # Import the existing nba_api_service which has game log functionality
        from app.services.nba.nba_api_service import NbaApiService

        nba_service = NbaApiService(self.db)

        # Fetch last 10 games
        game_logs = await nba_service.get_player_game_logs(
            player_nba_api_id=player_nba_api_id,
            games_limit=10,
            season=season
        )

        if not game_logs:
            logger.warning(f"No game logs found for nba_api_id {player_nba_api_id}")
            return None

        logger.info(f"Fetched last {len(game_logs)} games for nba_api_id {player_nba_api_id}")
        return game_logs

    async def get_player_stats_summary(
        self,
        player_nba_api_id: int,
        season: str = DEFAULT_SEASON
    ) -> Optional[Dict]:
        """
        Get complete player stats summary including career totals and last 10 games.

        This is the main method that combines both career stats and recent games.

        Args:
            player_nba_api_id: Player's nba_api numeric ID
            season: NBA season

        Returns:
            Dict with complete stats summary or None:
            {
                'player_id': int,
                'season': str,
                'career_stats': {...},  # Season totals from playercareerstats
                'last_10_games': [...],  # Last 10 games from playergamelog
                'last_10_avg': {
                    'points': float,
                    'rebounds': float,
                    'assists': float,
                    'threes': float
                }
            }
        """
        # Get career stats for the season
        career_stats = await self.get_player_career_stats(player_nba_api_id, season)

        if not career_stats:
            logger.warning(f"No career stats available for nba_api_id {player_nba_api_id}")
            return None

        # Get last 10 games
        last_10_games = await self.get_last_10_games_stats(player_nba_api_id, season)

        # Calculate last 10 games average
        last_10_avg = None
        if last_10_games:
            total_points = sum(g['points'] for g in last_10_games)
            total_rebounds = sum(g['rebounds'] for g in last_10_games)
            total_assists = sum(g['assists'] for g in last_10_games)
            total_threes = sum(g['threes'] for g in last_10_games)

            last_10_avg = {
                'points': round(total_points / len(last_10_games), 2),
                'rebounds': round(total_rebounds / len(last_10_games), 2),
                'assists': round(total_assists / len(last_10_games), 2),
                'threes': round(total_threes / len(last_10_games), 2)
            }

        return {
            'player_id': player_nba_api_id,
            'season': season,
            'career_stats': career_stats,
            'last_10_games': last_10_games or [],
            'last_10_avg': last_10_avg
        }

    async def sync_all_active_players_career_stats(
        self,
        season: str = DEFAULT_SEASON
    ) -> Dict[str, int]:
        """
        Sync career stats for all active players in the database.

        This is used for batch fetching career stats data.

        Args:
            season: NBA season

        Returns:
            Dict with sync results
        """
        players = self.db.query(Player).filter(
            Player.active == True,
            Player.nba_api_id.isnot(None)
        ).all()

        success_count = 0
        error_count = 0
        no_data_count = 0

        results = []

        for player in players:
            try:
                stats = await self.get_player_stats_summary(
                    player.nba_api_id,
                    season
                )

                if stats:
                    results.append({
                        'player_name': player.name,
                        'player_id': player.nba_api_id,
                        'stats': stats
                    })
                    success_count += 1
                else:
                    no_data_count += 1

            except Exception as e:
                logger.error(f"Error syncing career stats for {player.name}: {e}")
                error_count += 1

        return {
            'total': len(players),
            'success': success_count,
            'no_data': no_data_count,
            'errors': error_count,
            'results': results
        }
