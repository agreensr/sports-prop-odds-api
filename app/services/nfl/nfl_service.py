"""
NFL data service for fetching player and game data.

This service provides access to NFL data including:
- Player rosters and information
- Game schedules and results
- Team information

Uses nfl_data_py library for reliable NFL data access.
"""
import asyncio
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional
import logging
from pydantic import BaseModel
import random
from datetime import datetime, timedelta

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    pd = None
    PANDAS_AVAILABLE = False
    logger.warning("pandas not installed - NFL data fetching will be limited")

logger = logging.getLogger(__name__)

try:
    import nfl_data_py as nfl
    NFL_API_AVAILABLE = True
except ImportError:
    logger.warning("nfl_data_py not installed. Run: pip install nfl_data_py")
    NFL_API_AVAILABLE = False


class CacheEntry:
    """Simple cache entry with TTL."""
    def __init__(self, data: any, valid_until: datetime):
        self.data = data
        self.valid_until = valid_until

    def is_valid(self) -> bool:
        """Check if cache entry is still valid."""
        return datetime.now() < self.valid_until


class NFLPlayer(BaseModel):
    """NFL player data model."""
    id: str  # NFL.com player ID or GSIS ID
    name: str  # Full name
    team: str  # Team abbreviation
    position: Optional[str] = None
    jersey_number: Optional[int] = None
    active: bool = True


class NFLGame(BaseModel):
    """NFL game data model."""
    id: str  # Game ID
    game_date: date
    away_team: str  # Team abbreviation
    home_team: str  # Team abbreviation
    away_score: Optional[int] = None
    home_score: Optional[int] = None
    status: str  # scheduled, in_progress, final


class NFLService:
    """
    NFL data service using nfl_data_py library.

    Provides cached access to NFL data with configurable TTL.
    All methods are async but wrap the synchronous nfl_data_py calls.
    """

    def __init__(self, cache_ttl: int = 300):
        """
        Initialize NFL service.

        Args:
            cache_ttl: Default cache TTL in seconds (default: 5 minutes)
        """
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()

    def _get_cache_key(self, endpoint: str, **kwargs) -> str:
        """Generate cache key from endpoint name and parameters."""
        params = ",".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
        return f"{endpoint}:{params}" if params else endpoint

    async def _get_cached(self, key: str) -> Optional[any]:
        """Get data from cache if valid."""
        async with self._lock:
            entry = self._cache.get(key)
            if entry and entry.is_valid():
                return entry.data
        return None

    async def _set_cache(self, key: str, data: any, ttl: Optional[int] = None):
        """Set data in cache with TTL."""
        ttl = ttl or self.cache_ttl
        valid_until = datetime.now() + timedelta(seconds=ttl)
        async with self._lock:
            self._cache[key] = CacheEntry(data, valid_until)

    async def clear_cache(self):
        """Clear all cached data."""
        async with self._lock:
            self._cache.clear()

    async def get_cache_stats(self) -> Dict[str, any]:
        """Get cache statistics."""
        async with self._lock:
            total = len(self._cache)
            valid = sum(1 for e in self._cache.values() if e.is_valid())
            return {
                "total_entries": total,
                "valid_entries": valid,
                "expired_entries": total - valid
            }

    async def get_all_players(self, season: int = 2024) -> List[Dict]:
        """
        Fetch all active NFL players for a given season.

        Args:
            season: NFL season year (default: 2024)

        Returns:
            List of player dictionaries with keys:
            - player_id: NFL.com player ID or GSIS ID
            - player_name: Full name
            - team: Team abbreviation
            - position: Player position
            - jersey_number: Jersey number
        """
        if not NFL_API_AVAILABLE:
            logger.error("NFL API not available")
            return []
        if not PANDAS_AVAILABLE:
            logger.error("Pandas not available")
            return []

        cache_key = self._get_cache_key("all_players", season=season)
        cached = await self._get_cached(cache_key)
        if cached:
            return cached

        try:
            # Run blocking call in thread pool
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(
                None,
                lambda: nfl.import_weekly_rosters([season])
            )

            if df.empty:
                logger.warning(f"No NFL players found for season {season}")
                return []

            # Get unique players
            df_unique = df.drop_duplicates(subset=['player_id', 'player_name'])

            # Transform to list of dicts
            result = []
            for _, row in df_unique.iterrows():
                result.append({
                    'player_id': str(row.get('player_id', '')),
                    'player_name': row.get('player_name', ''),
                    'team': row.get('team', ''),
                    'position': row.get('position', ''),
                    'jersey_number': int(row.get('jersey_number', 0)) if pd.notna(row.get('jersey_number')) else None
                })

            # Cache for 24 hours
            await self._set_cache(cache_key, result, ttl=86400)
            return result

        except Exception as e:
            logger.error(f"Error fetching NFL players: {e}")
            return []

    async def get_schedule(self, season: int = 2024) -> List[Dict]:
        """
        Fetch NFL schedule for a given season.

        Args:
            season: NFL season year (default: 2024)

        Returns:
            List of game dictionaries
        """
        if not NFL_API_AVAILABLE:
            logger.error("NFL API not available")
            return []
        if not PANDAS_AVAILABLE:
            logger.error("Pandas not available")
            return []

        cache_key = self._get_cache_key("schedule", season=season)
        cached = await self._get_cached(cache_key)
        if cached:
            return cached

        try:
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(
                None,
                lambda: nfl.import_schedules([season])
            )

            if df.empty:
                logger.warning(f"No NFL schedule found for season {season}")
                return []

            # Transform to list of dicts
            result = []
            for _, row in df.iterrows():
                result.append({
                    'game_id': str(row.get('game_id', '')),
                    'season': int(row.get('season', season)),
                    'week': int(row.get('week', 0)),
                    'game_date': row.get('game_date', ''),
                    'away_team': row.get('away_team', ''),
                    'home_team': row.get('home_team', ''),
                    'away_score': int(row.get('away_score', 0)) if pd.notna(row.get('away_score')) else None,
                    'home_score': int(row.get('home_score', 0)) if pd.notna(row.get('home_score')) else None,
                    'status': row.get('game_status', 'scheduled')
                })

            # Cache for 1 hour
            await self._set_cache(cache_key, result, ttl=3600)
            return result

        except Exception as e:
            logger.error(f"Error fetching NFL schedule: {e}")
            return []

    async def search_players(self, name: str, season: int = 2024, limit: int = 10) -> List[Dict]:
        """
        Search for NFL players by name.

        Args:
            name: Player name or partial name
            season: NFL season year (default: 2024)
            limit: Maximum results to return

        Returns:
            List of matching player dictionaries
        """
        players = await self.get_all_players(season)

        # Filter by name (case-insensitive partial match)
        name_lower = name.lower()
        matches = [
            p for p in players
            if name_lower in p.get('player_name', '').lower()
        ]

        return matches[:limit]
