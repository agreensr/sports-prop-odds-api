"""
NBA.com data service using nba_api library (minimal version).

This service provides access to official NBA.com data including:
- Player rosters and information

The nba_api library is maintained and provides reliable access to NBA.com endpoints.
"""
import asyncio
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional
import logging
from pydantic import BaseModel

logger = logging.getLogger(__name__)

try:
    from nba_api.stats.endpoints import commonallplayers, scoreboardv2
    NBA_API_AVAILABLE = True
except ImportError:
    logger.warning("nba_api not installed. Run: pip install nba_api>=1.4.1")
    NBA_API_AVAILABLE = False


class CacheEntry:
    """Simple cache entry with TTL."""
    def __init__(self, data: any, valid_until: datetime):
        self.data = data
        self.valid_until = valid_until

    def is_valid(self) -> bool:
        """Check if cache entry is still valid."""
        return datetime.now() < self.valid_until


class NBAPlayer(BaseModel):
    """NBA player data model."""
    id: str  # NBA.com PERSON_ID
    name: str  # DISPLAY_FIRST_LAST
    team: str  # TEAM_ABBREVIATION
    position: Optional[str] = None
    jersey_number: Optional[int] = None
    active: bool = True


class NBAGame(BaseModel):
    """NBA game data model."""
    id: str  # NBA.com GAME_ID
    game_date: date
    away_team: str  # Team tricode
    home_team: str  # Team tricode
    away_score: Optional[int] = None
    home_score: Optional[int] = None
    status: str  # scheduled, in_progress, final


class NBAService:
    """
    NBA.com data service using nba_api library.

    Provides cached access to NBA.com endpoints with configurable TTL.
    All methods are async but wrap the synchronous nba_api calls.
    """

    def __init__(self, cache_ttl: int = 300):
        """
        Initialize NBA service.

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

    async def get_all_players(self, season: str = "2024-25") -> List[Dict]:
        """
        Fetch all active NBA players.

        Endpoint: commonallplayers.CommonAllPlayers
        Cost: 1 API call
        Cache: 24 hours

        Args:
            season: NBA season in "YYYY-YY" format (default: "2024-25")

        Returns:
            List of player dictionaries with keys:
            - PERSON_ID: NBA.com player ID
            - DISPLAY_FIRST_LAST: Full name
            - TEAM_ABBREVIATION: Team code
            - ROSTERSTATUS: 1 = active, 0 = inactive
        """
        if not NBA_API_AVAILABLE:
            logger.error("NBA API not available")
            return []

        cache_key = self._get_cache_key("all_players", season=season)
        cached = await self._get_cached(cache_key)
        if cached:
            return cached

        try:
            # Run blocking call in thread pool
            loop = asyncio.get_event_loop()
            players_data = await loop.run_in_executor(
                None,
                lambda: commonallplayers.CommonAllPlayers(
                    league_id='00',
                    season=season,
                    is_only_current_season=1  # Only current players
                ).get_dict()
            )

            # Extract player list
            players = players_data.get('resultSets', [{}])[0].get('rowSet', [])

            # Transform to list of dicts
            result = []
            headers = players_data.get('resultSets', [{}])[0].get('headers', [])
            for row in players:
                player_dict = dict(zip(headers, row))
                result.append({
                    'PERSON_ID': str(player_dict.get('PERSON_ID', '')),
                    'DISPLAY_FIRST_LAST': player_dict.get('DISPLAY_FIRST_LAST', ''),
                    'TEAM_ABBREVIATION': player_dict.get('TEAM_ABBREVIATION', ''),
                    'ROSTERSTATUS': player_dict.get('ROSTERSTATUS', 1)
                })

            # Cache for 24 hours
            await self._set_cache(cache_key, result, ttl=86400)
            return result

        except Exception as e:
            logger.error(f"Error fetching NBA players: {e}")
            return []

    async def get_scoreboard(self, game_date: date) -> List[Dict]:
        """
        Fetch NBA games scoreboard for a specific date.

        Endpoint: scoreboardv2.ScoreboardV2
        Cost: 1 API call
        Cache: 5 minutes (game lines change frequently)

        Args:
            game_date: Date to fetch games for

        Returns:
            List of game dictionaries with keys:
            - GAME_ID: NBA.com game ID
            - GAME_DATE: Game datetime in ISO format
            - VISITOR_TEAM_ABBREVIATION: Away team code
            - HOME_TEAM_ABBREVIATION: Home team code
            - PTS_VISITOR: Away team score (if game started/finished)
            - PTS_HOME: Home team score (if game started/finished)
            - GAME_STATUS: Game status (1=upcoming, 2=in progress, 3=final)
        """
        if not NBA_API_AVAILABLE:
            logger.error("NBA API not available")
            return []

        # Format date for NBA API (MM/DD/YYYY)
        game_date_str = game_date.strftime("%m/%d/%Y")
        cache_key = self._get_cache_key("scoreboard", date=game_date_str)
        cached = await self._get_cached(cache_key)
        if cached:
            logger.info(f"Using cached scoreboard for {game_date}")
            return cached

        try:
            # Run blocking call in thread pool
            loop = asyncio.get_event_loop()
            scoreboard_data = await loop.run_in_executor(
                None,
                lambda: scoreboardv2.ScoreboardV2(
                    game_date=game_date_str,
                    league_id="00",
                    day_offset=0
                ).get_dict()
            )

            # Extract game header data
            result_sets = scoreboard_data.get('resultSets', [])
            if not result_sets:
                logger.warning(f"No games found for {game_date}")
                return []

            # GameHeader is typically the first result set
            game_headers = result_sets[0].get('rowSet', [])
            headers = result_sets[0].get('headers', [])

            # Transform to list of dicts in expected format
            result = []
            for row in game_headers:
                game_dict = dict(zip(headers, row))

                # Extract team abbreviations from GAMECODE (format: YYYYMMDD/AWAYHOME)
                # Example: "20260120/PHXPHI" means PHX @ PHI
                gamecode = game_dict.get('GAMECODE', '')
                away_abbr = ''
                home_abbr = ''
                if '/' in gamecode:
                    teams_part = gamecode.split('/')[-1]
                    if len(teams_part) >= 6:
                        away_abbr = teams_part[:3]
                        home_abbr = teams_part[3:6]

                # Map NBA API status to our status values
                # NBA API: 1 = scheduled/pre-game, 2 = in progress, 3 = final
                nba_status = game_dict.get('GAME_STATUS_ID', 1)
                if nba_status == 3:
                    game_status = "final"
                elif nba_status == 2:
                    game_status = "in_progress"
                else:
                    game_status = "scheduled"

                # Build game datetime from GAME_DATE_EST
                game_date_str_api = game_dict.get('GAME_DATE_EST', '')

                # Parse the game date/time
                try:
                    # Format is typically "YYYY-MM-DDTHH:MM:SS"
                    # NBA API returns this in Eastern Time (no timezone marker)
                    base_datetime = game_date_str_api.replace('T', ' ')

                    # Parse as naive datetime (Eastern Time), then localize and convert to UTC
                    from datetime import timezone, timedelta
                    naive_dt = datetime.strptime(base_datetime, "%Y-%m-%d %H:%M:%S")
                    eastern = timezone(timedelta(hours=-5))  # EST is UTC-5
                    game_datetime = naive_dt.replace(tzinfo=eastern).astimezone(timezone.utc)
                except Exception as e:
                    logger.warning(f"Error parsing game datetime for {game_dict.get('GAME_ID')}: {e}")
                    # Fall back to the passed date at noon
                    game_datetime = datetime.combine(game_date, datetime.min.time()).replace(hour=12, tzinfo=datetime.now().astimezone().tzinfo)

                result.append({
                    'GAME_ID': str(game_dict.get('GAME_ID', '')),
                    'GAME_DATE': game_datetime.isoformat(),
                    'VISITOR_TEAM_ABBREVIATION': away_abbr,
                    'HOME_TEAM_ABBREVIATION': home_abbr,
                    'PTS_VISITOR': None,  # Not in scoreboard, needs boxscore
                    'PTS_HOME': None,  # Not in scoreboard, needs boxscore
                    'GAME_STATUS': game_status
                })

            logger.info(f"Fetched {len(result)} games for {game_date}")

            # Cache for 5 minutes
            await self._set_cache(cache_key, result, ttl=300)
            return result

        except Exception as e:
            logger.error(f"Error fetching NBA scoreboard for {game_date}: {e}")
            return []

    async def get_boxscore(self, game_id: str) -> Dict:
        """Placeholder for boxscore - returns empty dict."""
        logger.warning("get_boxscore not yet implemented")
        return {}

    async def get_schedule(self, season: str = "2024-25") -> List[Dict]:
        """Placeholder for schedule - returns empty list."""
        logger.warning("get_schedule not yet implemented")
        return []

    async def get_team_roster(self, team_id: str, season: str = "2024-25") -> List[Dict]:
        """Placeholder for roster - returns empty list."""
        logger.warning("get_team_roster not yet implemented")
        return []
