"""
Enhanced NBA Data Service using nba_api.

Provides comprehensive access to player stats, season averages,
per-36 stats, game logs, and roster information.
"""
import asyncio
import logging
import uuid
from typing import Dict, List
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.nba.models import Player, PlayerSeasonStats
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Convenience constants
CURRENT_SEASON = settings.CURRENT_SEASON
NBA_API_REQUEST_DELAY = settings.NBA_API_REQUEST_DELAY


class NbaDataService:
    """Comprehensive NBA data service using nba_api."""

    def __init__(self, db: Session):
        self.db = db

    async def fetch_all_player_stats(
        self,
        season: str = CURRENT_SEASON,
        per_mode: str = "PerGame",
        measure_type: str = "Base"
    ) -> List[Dict]:
        """
        Fetch all player stats using LeagueDashPlayerStats.

        This is the PRIMARY method for getting player data.
        Returns per-game or per-36 minute statistics for all players.

        Args:
            season: Season string (e.g., "2024-25")
            per_mode: "PerGame" or "Per36"
            measure_type: "Base", "Advanced", etc.

        Returns:
            List of player stat dictionaries
        """
        try:
            from nba_api.stats.endpoints import leaguedashplayerstats

            await asyncio.sleep(NBA_API_REQUEST_DELAY)

            stats = leaguedashplayerstats.LeagueDashPlayerStats(
                season=season,
                season_type_all_star='Regular Season',
                measure_type_detailed_defense=measure_type,
                per_mode_detailed=per_mode,
                plus_minus='N',
                pace_adjust='N',
                rank='N'
            )

            df = stats.get_data_frames()[0] if stats.get_data_frames() else None

            if df is None or df.empty:
                logger.warning(f"No player stats returned for {season}")
                return []

            return df.to_dict('records')

        except Exception as e:
            logger.error(f"Error fetching player stats: {e}")
            return []

    async def fetch_player_per_36(self, season: str = CURRENT_SEASON) -> List[Dict]:
        """
        Fetch per-36 minute stats for all players.

        Per-36 stats normalize for playing time, allowing fair
        comparisons between bench players and starters.

        Args:
            season: Season string (e.g., "2024-25")

        Returns:
            List of player stat dictionaries
        """
        return await self.fetch_all_player_stats(
            season=season,
            per_mode='Per36',
            measure_type='Base'
        )

    async def fetch_player_advanced_stats(self, season: str = CURRENT_SEASON) -> List[Dict]:
        """
        Fetch advanced stats for all players.

        Includes offensive rating, defensive rating, usage rate, etc.

        Args:
            season: Season string (e.g., "2024-25")

        Returns:
            List of player stat dictionaries
        """
        return await self.fetch_all_player_stats(
            season=season,
            per_mode='PerGame',
            measure_type='Advanced'
        )

    async def update_player_season_stats(self, season: str = CURRENT_SEASON) -> Dict:
        """
        Update PlayerSeasonStats table with fresh per-36 data.

        This is the main sync method for player stats. It fetches
        per-36 minute stats from nba_api and updates the database.

        Args:
            season: Season string (e.g., "2024-25")

        Returns:
            Dictionary with sync results
        """
        logger.info(f"Starting player stats sync for {season}...")

        players_data = await self.fetch_player_per_36(season=season)

        if not players_data:
            return {"status": "error", "message": "No data from API"}

        updated = created = errors = 0

        for player_data in players_data:
            try:
                nba_api_id = player_data.get('PLAYER_ID')
                player = self.db.query(Player).filter(
                    Player.nba_api_id == nba_api_id
                ).first()

                if not player:
                    player_name = player_data.get('PLAYER_NAME')
                    player = self.db.query(Player).filter(
                        Player.name == player_name
                    ).first()
                    if player:
                        player.nba_api_id = nba_api_id

                if not player:
                    continue

                stats = self.db.query(PlayerSeasonStats).filter(
                    PlayerSeasonStats.player_id == player.id,
                    PlayerSeasonStats.season == season
                ).first()

                stats_dict = {
                    'games_count': player_data.get('GP', 0),
                    'points_per_36': player_data.get('PTS', 0.0),
                    'rebounds_per_36': player_data.get('REB', 0.0),
                    'assists_per_36': player_data.get('AST', 0.0),
                    'threes_per_36': player_data.get('FG3M', 0.0),
                    'avg_minutes': player_data.get('MIN', 0.0),
                }

                if stats:
                    for key, value in stats_dict.items():
                        setattr(stats, key, value)
                    updated += 1
                else:
                    stats = PlayerSeasonStats(
                        id=str(uuid.uuid4()),
                        player_id=player.id,
                        season=season,
                        **stats_dict,
                        fetched_at=datetime.now(timezone.utc),
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc)
                    )
                    self.db.add(stats)
                    created += 1

            except Exception as e:
                logger.error(f"Error processing player: {e}")
                errors += 1

        self.db.commit()

        return {
            "status": "success",
            "season": season,
            "created": created,
            "updated": updated,
            "errors": errors,
            "total": created + updated
        }

    async def get_player_stats_by_team(
        self,
        team_abbr: str,
        season: str = CURRENT_SEASON
    ) -> List[Dict]:
        """
        Get stats for all players on a specific team.

        Args:
            team_abbr: 3-letter team abbreviation (e.g., "LAL")
            season: Season string (e.g., "2024-25")

        Returns:
            List of player stat dictionaries
        """
        all_stats = await self.fetch_player_per_36(season=season)

        return [
            stat for stat in all_stats
            if stat.get('TEAM_ABBREVIATION') == team_abbr
        ]

    async def get_league_leaders(
        self,
        stat: str = 'PTS',
        season: str = CURRENT_SEASON,
        top_n: int = 50
    ) -> List[Dict]:
        """
        Get league leaders for a specific stat.

        Args:
            stat: Stat category (PTS, REB, AST, FG3M, etc.)
            season: Season string (e.g., "2024-25")
            top_n: Number of top players to return

        Returns:
            List of player stat dictionaries sorted by stat
        """
        all_stats = await self.fetch_player_per_36(season=season)

        # Filter to players with minimum games (e.g., 10 games)
        qualified = [
            s for s in all_stats
            if s.get('GP', 0) >= 10
        ]

        # Sort by stat (descending)
        sorted_stats = sorted(
            qualified,
            key=lambda x: x.get(stat, 0),
            reverse=True
        )

        return sorted_stats[:top_n]
