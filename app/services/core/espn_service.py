"""
ESPN API Service for multi-sport data fetching.

This service provides access to ESPN's public API endpoints for:
- News and injury updates
- Game scores and schedules
- Team information and rosters
- Player statistics

ESPN API is used as a SECONDARY data source:
- Primary: The Odds API (games, odds, player props)
- Secondary: ESPN API (news, scores, teams)
- Tertiary: Sport-specific APIs (nba_api, nfl_data_py)

ESPN API Endpoints:
- Base URL: https://site.api.espn.com/apis/site/v2/sports/
- Documentation: Unofficial, community-maintained

Sports Supported:
- basketball/nba (NBA)
- football/nfl (NFL)
- baseball/mlb (MLB)
- hockey/nhl (NHL)

Rate Limits: No official limits, but be respectful

Timezone: All datetimes returned in Central Time (CST/CDT)
"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import httpx
from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential

from app.utils.timezone import utc_to_central
from app.core.logging import get_logger
from app.services.core.circuit_breaker import espn_api_breaker, CircuitBreakerError

logger = get_logger(__name__)

# ESPN API base URLs
ESPN_BASE_URL = "https://site.api.espn.com/apis/site/v2/sports"
ESPN_BASE_V3_URL = "https://sports.core.api.espn.com/v3/sports"

# Sport mappings
ESPN_SPORT_PATHS = {
    'nba': 'basketball/nba',
    'nfl': 'football/nfl',
    'mlb': 'baseball/mlb',
    'nhl': 'hockey/nhl',
}


class ESPNApiService:
    """
    ESPN API service for fetching sports data.

    This service handles:
    - News and injury updates
    - Game scores and schedules
    - Team information
    - Player rosters

    Cache TTL is dynamic based on sport season status:
    - Active season: Shorter TTL for fresh data
    - Offseason: Longer TTL (24 hours) for performance

    Usage:
        service = ESPNApiService()
        news = await service.get_news('nba')
        scores = await service.get_scores('nba', '20260127')
        teams = await service.get_teams('nba')
    """

    def __init__(self, cache_ttl: Optional[int] = None, default_sport: str = "nba"):
        """
        Initialize ESPN API service.

        Args:
            cache_ttl: Override cache TTL in seconds. If None, uses dynamic
                      TTL based on season status.
            default_sport: Default sport for season-aware TTL (default: 'nba')
        """
        if cache_ttl is None:
            from app.core.config import get_dynamic_cache_ttl
            cache_ttl = get_dynamic_cache_ttl(default_sport)

        self.cache_ttl = cache_ttl
        self._cache: Dict[str, tuple] = {}  # key -> (data, expiry)
        self._client: Optional[httpx.AsyncClient] = None
        self._default_sport = default_sport

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            timeout = httpx.Timeout(30.0)
            limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
            self._client = httpx.AsyncClient(
                timeout=timeout,
                limits=limits,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                    "Accept": "application/json",
                }
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_cache_key(self, endpoint: str, **kwargs) -> str:
        """Generate cache key."""
        params = ",".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
        return f"{endpoint}:{params}" if params else endpoint

    async def _get_cached(self, key: str) -> Optional[Any]:
        """Get data from cache if valid."""
        if key in self._cache:
            data, expiry = self._cache[key]
            if datetime.now() < expiry:
                return data
            else:
                del self._cache[key]
        return None

    async def _set_cache(self, key: str, data: Any, ttl: Optional[int] = None):
        """Set data in cache with TTL."""
        ttl = ttl or self.cache_ttl
        expiry = datetime.now() + timedelta(seconds=ttl)
        self._cache[key] = (data, expiry)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    @espn_api_breaker
    async def _fetch_with_breaker(self, url: str, client: httpx.AsyncClient) -> Dict:
        """
        Internal method to fetch data - wrapped with circuit breaker.

        Args:
            url: Full API URL
            client: HTTP client

        Returns:
            Parsed JSON response
        """
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

    async def _fetch(self, url: str, use_cache: bool = True) -> Dict:
        """
        Fetch data from ESPN API.

        Args:
            url: Full API URL
            use_cache: Whether to use cache (default: True)

        Returns:
            Parsed JSON response
        """
        cache_key = self._get_cache_key(url)

        if use_cache:
            cached = await self._get_cached(cache_key)
            if cached:
                return cached

        try:
            client = await self._get_client()
            data = await self._fetch_with_breaker(url, client)
            await self._set_cache(cache_key, data)
            return data
        except CircuitBreakerError:
            logger.warning(f"ESPN API circuit breaker is OPEN for {url} - returning empty dict")
            return {}

    # ==================== NEWS ENDPOINTS ====================

    async def get_news(
        self,
        sport_id: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get recent news for a sport.

        Args:
            sport_id: Sport identifier ('nba', 'nfl', 'mlb', 'nhl')
            limit: Maximum number of articles

        Returns:
            List of news articles with title, description, link, published_date
        """
        sport_path = ESPN_SPORT_PATHS.get(sport_id)
        if not sport_path:
            logger.warning(f"Unsupported sport: {sport_id}")
            return []

        url = f"{ESPN_BASE_URL}/{sport_path}/news"

        try:
            data = await self._fetch(url)

            articles = []
            for item in data.get('articles', [])[:limit]:
                article = {
                    'title': item.get('headline'),
                    'description': item.get('description'),
                    'link': item.get('links', {}).get('web', {}).get('href'),
                    'published_date': self._parse_espn_date(item.get('published')),
                    'type': item.get('type', 'news'),
                    'source': 'espn',
                }
                articles.append(article)

            logger.info(f"Fetched {len(articles)} news articles for {sport_id}")
            return articles

        except Exception as e:
            logger.error(f"Error fetching news for {sport_id}: {e}")
            return []

    async def get_daily_injuries(
        self,
        sport_id: str,
        date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get injury report for a specific date.

        Note: ESPN doesn't have a dedicated injuries endpoint.
        This method scrapes news articles for injury-related content.

        Args:
            sport_id: Sport identifier ('nba', 'nfl', 'mlb', 'nhl')
            date: Date to fetch injuries for (default: today)

        Returns:
            List of injury-related articles
        """
        # Get news and filter for injury-related content
        news = await self.get_news(sport_id, limit=50)

        # Filter for injury-related keywords
        injury_keywords = [
            'injury', 'injured', 'out', 'questionable',
            'day-to-day', 'sidelined', 'hurt', 'status'
        ]

        injury_news = []
        for article in news:
            title = article.get('title', '').lower()
            description = article.get('description', '').lower()

            if any(keyword in title or keyword in description for keyword in injury_keywords):
                article['tags'] = ['injury']
                injury_news.append(article)

        logger.info(f"Found {len(injury_news)} injury-related articles for {sport_id}")
        return injury_news

    # ==================== SCORES ENDPOINTS ====================

    async def get_scores(
        self,
        sport_id: str,
        date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get game scores for a specific date.

        Args:
            sport_id: Sport identifier ('nba', 'nfl', 'mlb', 'nhl')
            date: Date in YYYYMMDD format (default: today)

        Returns:
            List of games with scores, status, teams
        """
        sport_path = ESPN_SPORT_PATHS.get(sport_id)
        if not sport_path:
            logger.warning(f"Unsupported sport: {sport_id}")
            return []

        # Default to today if no date provided
        if not date:
            date = datetime.now().strftime('%Y%m%d')

        url = f"{ESPN_BASE_URL}/{sport_path}/scoreboard?dates={date}"

        try:
            data = await self._fetch(url)

            games = []
            for event in data.get('events', []):
                # Handle different API structures
                # NBA/NFL/MLB: competitors are at event level
                # NHL: competitors are at competitions[0] level
                competitors_list = event.get('competitors', [])
                if not competitors_list and event.get('competitions'):
                    # NHL structure - get competitors from first competition
                    competitions = event.get('competitions', [])
                    if competitions and len(competitions) > 0:
                        competitors_list = competitions[0].get('competitors', [])

                game = {
                    'id': event.get('id'),
                    'name': event.get('name'),
                    'short_name': event.get('shortName'),
                    'date': self._parse_espn_date(event.get('date')),
                    'status': self._parse_game_status(event.get('status', {})),
                    'competitors': self._parse_competitors(competitors_list),
                }
                games.append(game)

            logger.info(f"Fetched {len(games)} games for {sport_id} on {date}")
            return games

        except Exception as e:
            logger.error(f"Error fetching scores for {sport_id}: {e}")
            return []

    async def get_scoreboard(
        self,
        sport_id: str,
        date: Optional[str] = None,
        include_scheduled: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get scoreboard for a specific date with optional scheduled games.

        This is the primary method for fetching game schedules.
        Returns ALL games including scheduled (pre-game), in-progress, and final.

        Args:
            sport_id: Sport identifier ('nba', 'nfl', 'mlb', 'nhl')
            date: Date in YYYYMMDD format (default: today)
            include_scheduled: Include pre-game/scheduled games (default: True)

        Returns:
            List of games with detailed information:
            - id: ESPN game ID
            - name: Game name (e.g., "Lakers at Celtics")
            - date: Game datetime (parsed to Central Time)
            - status: Game status ('scheduled', 'in_progress', 'final')
            - home_abbr: Home team abbreviation
            - away_abbr: Away team abbreviation
            - home_name: Home team full name
            - away_name: Away team full name
        """
        sport_path = ESPN_SPORT_PATHS.get(sport_id)
        if not sport_path:
            logger.warning(f"Unsupported sport: {sport_id}")
            return []

        # Default to today if no date provided
        if not date:
            date = datetime.now().strftime('%Y%m%d')

        url = f"{ESPN_BASE_URL}/{sport_path}/scoreboard?dates={date}"

        try:
            data = await self._fetch(url, use_cache=False)  # Don't cache for fresh schedule data

            games = []
            for event in data.get('events', []):
                # Parse status to get state
                status_data = event.get('status', {})
                state = status_data.get('state', 'pre')

                # Skip scheduled games if not requested
                if state == 'pre' and not include_scheduled:
                    continue

                # Get competitors from competitions structure
                competitions = event.get('competitions', [])
                if competitions and len(competitions) > 0:
                    comp = competitions[0]
                    competitors_list = comp.get('competitors', [])
                else:
                    competitors_list = event.get('competitors', [])

                # Parse home/away teams
                home_team = None
                away_team = None

                for team in competitors_list:
                    team_data = team.get('team', {})
                    is_home = team.get('homeAway') == 'home'

                    parsed = {
                        'id': team_data.get('id'),
                        'name': team_data.get('displayName'),
                        'abbreviation': team_data.get('abbreviation'),
                        'logo': team_data.get('logo'),
                        'score': team.get('score'),
                    }

                    if is_home:
                        home_team = parsed
                    else:
                        away_team = parsed

                if not home_team or not away_team:
                    continue

                game = {
                    'id': event.get('id'),
                    'name': event.get('name'),
                    'short_name': event.get('shortName'),
                    'date': self._parse_espn_date(event.get('date')),
                    'status': state,
                    'home_abbr': home_team.get('abbreviation'),
                    'away_abbr': away_team.get('abbreviation'),
                    'home_name': home_team.get('name'),
                    'away_name': away_team.get('name'),
                    'home_score': home_team.get('score'),
                    'away_score': away_team.get('score'),
                }
                games.append(game)

            logger.info(f"Fetched {len(games)} games for {sport_id} on {date} (include_scheduled={include_scheduled})")
            return games

        except Exception as e:
            logger.error(f"Error fetching scoreboard for {sport_id}: {e}")
            return []

    async def get_upcoming_games(
        self,
        sport_id: str,
        days_ahead: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Get upcoming scheduled games for the next N days.

        This is ideal for fetching the full schedule of future games.

        Args:
            sport_id: Sport identifier ('nba', 'nfl', 'mlb', 'nhl')
            days_ahead: Number of days to look ahead (default: 7)

        Returns:
            List of upcoming games with full details
        """
        all_games = []
        base_date = datetime.now()

        for day in range(days_ahead):
            target_date = base_date + timedelta(days=day)
            date_str = target_date.strftime('%Y%m%d')

            games = await self.get_scoreboard(
                sport_id=sport_id,
                date=date_str,
                include_scheduled=True
            )

            # Filter to only scheduled games (pre-game state)
            scheduled = [g for g in games if g.get('status') == 'pre']
            all_games.extend(scheduled)

        logger.info(f"Fetched {len(all_games)} upcoming {sport_id} games (next {days_ahead} days)")
        return all_games

    # ==================== TEAM ENDPOINTS ====================

    async def get_teams(self, sport_id: str) -> List[Dict[str, Any]]:
        """
        Get all teams for a sport.

        Args:
            sport_id: Sport identifier ('nba', 'nfl', 'mlb', 'nhl')

        Returns:
            List of teams with id, name, abbreviation, logo
        """
        sport_path = ESPN_SPORT_PATHS.get(sport_id)
        if not sport_path:
            logger.warning(f"Unsupported sport: {sport_id}")
            return []

        url = f"{ESPN_BASE_URL}/{sport_path}/teams"

        try:
            data = await self._fetch(url)

            teams = []
            for team in data.get('sports', [{}])[0].get('leagues', [{}])[0].get('teams', []):
                team_data = team.get('team', {})
                team_info = {
                    'id': team_data.get('id'),
                    'uid': team_data.get('uid'),
                    'name': team_data.get('name'),
                    'display_name': team_data.get('displayName'),
                    'abbreviation': team_data.get('abbreviation'),
                    'logo': team_data.get('logo'),
                    'color': team_data.get('color'),
                    'venue': self._parse_venue(team_data.get('venue', {})),
                }
                teams.append(team_info)

            logger.info(f"Fetched {len(teams)} teams for {sport_id}")
            return teams

        except Exception as e:
            logger.error(f"Error fetching teams for {sport_id}: {e}")
            return []

    async def get_team_roster(
        self,
        sport_id: str,
        team_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get roster for a specific team.

        Args:
            sport_id: Sport identifier ('nba', 'nfl', 'mlb', 'nhl')
            team_id: ESPN team ID

        Returns:
            List of players with id, name, position, jersey number
        """
        sport_path = ESPN_SPORT_PATHS.get(sport_id)
        if not sport_path:
            logger.warning(f"Unsupported sport: {sport_id}")
            return []

        url = f"{ESPN_BASE_URL}/{sport_path}/teams/{team_id}"

        try:
            data = await self._fetch(url)

            # Navigate to roster data
            team_data = data.get('team', {})
            athletes = team_data.get('athletes', [])

            roster = []
            for athlete in athletes:
                player = {
                    'id': athlete.get('id'),
                    'uid': athlete.get('uid'),
                    'name': athlete.get('displayName'),
                    'first_name': athlete.get('firstName'),
                    'last_name': athlete.get('lastName'),
                    'position': athlete.get('position', {}).get('abbreviation'),
                    'jersey': athlete.get('jersey'),
                    'status': athlete.get('status'),
                    'headshot': athlete.get('headshot'),
                }
                roster.append(player)

            logger.info(f"Fetched {len(roster)} players for team {team_id}")
            return roster

        except Exception as e:
            logger.error(f"Error fetching roster for {team_id}: {e}")
            return []

    # ==================== PLAYER ENDPOINTS ====================

    async def get_player_stats(
        self,
        sport_id: str,
        player_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get statistics for a specific player.

        Args:
            sport_id: Sport identifier ('nba', 'nfl', 'mlb', 'nhl')
            player_id: ESPN player ID

        Returns:
            Player statistics dictionary
        """
        sport_path = ESPN_SPORT_PATHS.get(sport_id)
        if not sport_path:
            logger.warning(f"Unsupported sport: {sport_id}")
            return None

        url = f"{ESPN_BASE_URL}/{sport_path}/athletes/{player_id}"

        try:
            data = await self._fetch(url)

            athlete = data.get('athlete', {})
            stats = {
                'id': athlete.get('id'),
                'name': athlete.get('displayName'),
                'position': athlete.get('position', {}).get('abbreviation'),
                'stats': self._parse_player_stats(athlete.get('stats', [])),
            }

            return stats

        except Exception as e:
            logger.error(f"Error fetching stats for player {player_id}: {e}")
            return None

    # ==================== BOXSCORE ENDPOINTS ====================

    async def get_boxscore(
        self,
        sport_id: str,
        espn_game_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get boxscore data for a specific game.

        Fetches player stats from ESPN's summary endpoint which includes
        complete boxscore data for finished games.

        Args:
            sport_id: Sport identifier ('nba', 'nfl', 'mlb', 'nhl')
            espn_game_id: ESPN game ID (integer)

        Returns:
            Dictionary with:
            - GAME_ID: ESPN game ID
            - PlayerStats: List of player stat dicts with keys:
                - PLAYER_ID: ESPN player ID
                - PTS: Points scored
                - REB: Rebounds
                - AST: Assists
                - FG3M: Three-pointers made
                - MIN: Minutes played
        """
        sport_path = ESPN_SPORT_PATHS.get(sport_id)
        if not sport_path:
            logger.warning(f"Unsupported sport: {sport_id}")
            return None

        url = f"{ESPN_BASE_URL}/{sport_path}/summary?event={espn_game_id}"

        try:
            data = await self._fetch(url, use_cache=False)  # Don't cache boxscores

            boxscore = data.get('boxscore', {})
            players = boxscore.get('players', [])

            if not players:
                logger.warning(f"No boxscore data for game {espn_game_id}")
                return None

            player_stats = []

            # ESPN boxscore has teams in 'players' array
            for team_data in players:
                statistics = team_data.get('statistics', [])
                if not statistics:
                    continue

                # First element has the column definitions and athletes
                stat_entry = statistics[0]
                athletes = stat_entry.get('athletes', [])

                for athlete_data in athletes:
                    # Skip players who didn't play
                    if athlete_data.get('didNotPlay', False):
                        continue

                    athlete = athlete_data.get('athlete', {})
                    player_id = athlete.get('id', '')

                    # Get stats from values array
                    # ESPN format: [MIN, PTS, FG, 3PT, FT, REB, AST, TO, STL, BLK, OREB, DREB, PF, +/-]
                    values = athlete_data.get('stats', [])

                    # Parse 3PT format "made-attempted" to get just made
                    threes_raw = values[3] if len(values) > 3 else "0-0"
                    try:
                        threes_made = int(threes_raw.split('-')[0]) if threes_raw and '-' in threes_raw else 0
                    except (ValueError, IndexError):
                        threes_made = 0

                    player_stats.append({
                        'PLAYER_ID': str(player_id),
                        'PTS': values[1] if len(values) > 1 else None,
                        'REB': values[5] if len(values) > 5 else None,
                        'AST': values[6] if len(values) > 6 else None,
                        'FG3M': threes_made,
                        'MIN': values[0] if len(values) > 0 else None,
                    })

            result = {
                'GAME_ID': str(espn_game_id),
                'PlayerStats': player_stats
            }

            logger.info(f"Fetched boxscore for {espn_game_id}: {len(player_stats)} players")
            return result

        except Exception as e:
            logger.error(f"Error fetching boxscore for game {espn_game_id}: {e}")
            return None

    # ==================== UTILITY METHODS ====================

    @staticmethod
    def _parse_espn_date(date_str: Optional[str]) -> Optional[datetime]:
        """
        Parse ESPN date string to datetime in UTC.

        ESPN dates are in ISO format with timezone (e.g., "2025-01-28T19:00:00Z").
        This method parses and returns UTC datetime for database storage.

        Note: Previously converted to Central Time, but this caused display issues.
        Games are now stored in UTC and converted to display timezone (EST/CT) when shown.
        """
        if not date_str:
            return None
        try:
            # ESPN dates are in ISO format with UTC timezone
            # Return as naive UTC datetime (without tzinfo) for database storage
            utc_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            # Strip timezone info for database storage (naive datetime assumed to be UTC)
            return utc_datetime.replace(tzinfo=None)
        except Exception:
            return None

    @staticmethod
    def _parse_game_status(status: Dict) -> str:
        """Parse game status to simplified form."""
        state = status.get('state', 'pre')
        detail = status.get('detail', '')

        if state == 'pre':
            return 'scheduled'
        elif state == 'in':
            return 'in_progress'
        elif state == 'post':
            return 'final'
        else:
            return state

    @staticmethod
    def _parse_competitors(competitors: List[Dict]) -> Dict[str, Any]:
        """Parse competitors array to home/away teams."""
        home = None
        away = None

        for team in competitors:
            team_data = team.get('team', {})
            is_home = team.get('homeAway') == 'home'

            parsed = {
                'id': team_data.get('id'),
                'name': team_data.get('displayName'),
                'abbreviation': team_data.get('abbreviation'),
                'logo': team_data.get('logo'),
                'score': team.get('score'),
                'winner': team.get('winner'),
            }

            if is_home:
                home = parsed
            else:
                away = parsed

        return {'home': home, 'away': away}

    @staticmethod
    def _parse_venue(venue: Dict) -> Dict[str, Any]:
        """Parse venue information."""
        return {
            'name': venue.get('name'),
            'city': venue.get('address', {}).get('city'),
            'state': venue.get('address', {}).get('state'),
            'capacity': venue.get('capacity'),
        }

    @staticmethod
    def _parse_player_stats(stats: List[Dict]) -> Dict[str, Any]:
        """Parse player stats array to dictionary."""
        stats_dict = {}

        for stat in stats:
            name = stat.get('name', '')
            value = stat.get('value')

            if name and value is not None:
                stats_dict[name] = value

        return stats_dict


# Convenience functions
async def get_espn_service() -> ESPNApiService:
    """Get or create ESPN API service instance."""
    return ESPNApiService()
