"""
The Odds API service for fetching betting odds.

This service provides access to betting odds from bookmakers including:
- Game odds (moneyline, spread, totals)
- Player props odds (points, rebounds, assists, etc.)

Free Tier: 500 requests/month
Strategy: Aggressive caching to minimize usage
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import httpx

logger = logging.getLogger(__name__)

# The Odds API base URL
THE_ODDS_API_BASE = "https://api.the-odds-api.com/v4"


class OddsApiService:
    """
    The Odds API service for betting odds.

    Free Tier: 500 requests/month (~16/day)
    Strategy: Aggressive caching to minimize usage
    """

    def __init__(self, api_key: str, cache_ttl: int = 600):
        """
        Initialize The Odds API service.

        Args:
            api_key: The Odds API key
            cache_ttl: Default cache TTL in seconds (default: 10 minutes)
        """
        self.api_key = api_key
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, tuple] = {}  # key -> (data, expiry)
        self._lock = asyncio.Lock()
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            timeout = httpx.Timeout(30.0)
            limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
            self._client = httpx.AsyncClient(
                timeout=timeout,
                limits=limits,
                headers=self._get_headers()
            )
        return self._client

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with API key."""
        return {
            "Content-Type": "application/json",
            "X-Application": "sports-bet-ai-api"
        }

    def _get_cache_key(self, endpoint: str, **kwargs) -> str:
        """Generate cache key from endpoint name and parameters."""
        params = ",".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
        return f"{endpoint}:{params}" if params else endpoint

    async def _get_cached(self, key: str) -> Optional[any]:
        """Get data from cache if valid."""
        async with self._lock:
            if key in self._cache:
                data, expiry = self._cache[key]
                if datetime.now() < expiry:
                    return data
                else:
                    del self._cache[key]
        return None

    async def _set_cache(self, key: str, data: any, ttl: Optional[int] = None):
        """Set data in cache with TTL."""
        ttl = ttl or self.cache_ttl
        expiry = datetime.now() + timedelta(seconds=ttl)
        async with self._lock:
            self._cache[key] = (data, expiry)

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # Game Odds Methods

    async def get_upcoming_games_with_odds(
        self,
        days_ahead: int = 7
    ) -> List[Dict]:
        """
        Fetch upcoming NBA games with odds.

        Args:
            days_ahead: Number of days ahead to fetch (default: 7)

        Returns:
            List of games with odds data
        """
        cache_key = self._get_cache_key("upcoming_games", days=days_ahead)
        cached = await self._get_cached(cache_key)
        if cached:
            return cached

        try:
            client = await self._get_client()

            # Fetch odds for h2h (moneyline), spreads, and totals
            all_games = {}

            for market in ["h2h", "spreads", "totals"]:
                params = {
                    "apiKey": self.api_key,
                    "days": days_ahead,
                    "market": market,
                    "regions": "us"
                }

                response = await client.get(
                    f"{THE_ODDS_API_BASE}/sports/basketball_nba/odds",
                    params=params
                )
                response.raise_for_status()

                data = response.json()

                # Merge games by ID
                for game in data:
                    game_id = game.get("id")
                    if game_id not in all_games:
                        all_games[game_id] = {
                            "id": game_id,
                            "sport_key": game.get("sport_key"),
                            "sport_title": game.get("sport_title"),
                            "commence_time": game.get("commence_time"),
                            "home_team": game.get("home_team"),
                            "away_team": game.get("away_team"),
                            "bookmakers": []
                        }

                    # Add bookmaker data
                    for bookmaker in game.get("bookmakers", []):
                        all_games[game_id]["bookmakers"].append({
                            "key": bookmaker.get("key"),
                            "title": bookmaker.get("title"),
                            "last_update": bookmaker.get("last_update"),
                            "markets": bookmaker.get("markets", [])
                        })

            # Convert to list and cache
            result = list(all_games.values())

            # Cache for 10 minutes (odds change frequently)
            await self._set_cache(cache_key, result, ttl=600)

            return result

        except Exception as e:
            logger.error(f"Error fetching NBA game odds: {e}")
            return []

    async def get_event_player_props(
        self,
        event_id: str
    ) -> Dict:
        """
        Fetch player props for specific NBA game.

        Args:
            event_id: The Odds API event ID

        Returns:
            Player props data by market
        """
        cache_key = self._get_cache_key("player_props", event_id=event_id)
        cached = await self._get_cached(cache_key)
        if cached:
            return cached

        try:
            client = await self._get_client()

            # Fetch player props for different markets
            markets = ["player_points", "player_rebounds", "player_assists", "player_threes"]
            result = {
                "event_id": event_id,
                "markets": {}
            }

            for market in markets:
                params = {
                    "apiKey": self.api_key,
                    "event": event_id,
                    "market": market,
                    "regions": "us"
                }

                response = await client.get(
                    f"{THE_ODDS_API_BASE}/sports/basketball_nba/events/{event_id}/odds",
                    params=params
                )

                if response.status_code == 200:
                    data = response.json()
                    result["markets"][market] = data
                else:
                    logger.warning(f"Failed to fetch {market} for event {event_id}: {response.status_code}")
                    result["markets"][market] = []

            # Cache for 5 minutes (player props change frequently)
            await self._set_cache(cache_key, result, ttl=300)

            return result

        except Exception as e:
            logger.error(f"Error fetching NBA player props for event {event_id}: {e}")
            return {
                "event_id": event_id,
                "markets": {}
            }

    async def get_quota_status(self) -> Dict:
        """
        Get remaining API quota for the month.

        Returns:
            Quota information
        """
        try:
            client = await self._get_client()

            # Make a simple request to check quota - need valid parameters
            params = {
                "apiKey": self.api_key,
                "sport": "basketball_nba"
            }
            response = await client.get(
                f"{THE_ODDS_API_BASE}/sports/basketball_nba/scores",
                params=params
            )
            response.raise_for_status()

            # Check rate limit headers
            remaining = response.headers.get("x-requests-remaining", "unknown")

            return {
                "remaining_requests": remaining,
                "status": "active" if remaining != "0" else "exceeded"
            }

        except Exception as e:
            logger.error(f"Error checking quota status: {e}")
            return {
                "remaining_requests": "unknown",
                "status": "error"
            }


# Singleton instance
_odds_service: Optional[OddsApiService] = None


def get_odds_service(api_key: str) -> OddsApiService:
    """Get or create OddsApiService singleton."""
    global _odds_service
    if _odds_service is None:
        _odds_service = OddsApiService(api_key=api_key)
    return _odds_service
