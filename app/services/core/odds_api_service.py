"""
The Odds API service for fetching betting odds.

This service provides access to betting odds from bookmakers including:
- Game odds (moneyline, spread, totals)
- Player props odds (points, rebounds, assists, etc.)

Paid Plan: 20,000 requests/month (~666/day)
Quota Tracking: Response headers x-requests-remaining, x-requests-used
"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.logging import get_logger
from app.services.core.circuit_breaker import odds_api_breaker, CircuitBreakerError

logger = get_logger(__name__)

# The Odds API base URL
THE_ODDS_API_BASE = "https://api.the-odds-api.com/v4"


class OddsApiService:
    """
    The Odds API service for betting odds.

    Paid Plan: 20,000 requests/month (~666/day)
    Quota Tracking: Captures x-requests-remaining and x-requests-used headers

    Cache TTL is dynamic based on sport season status for better data freshness
    during active seasons and better performance during offseason.
    """

    def __init__(self, api_key: str, cache_ttl: Optional[int] = None, default_sport: str = "nba"):
        """
        Initialize The Odds API service.

        Args:
            api_key: The Odds API key
            cache_ttl: Override cache TTL in seconds. If None, uses dynamic
                      TTL based on season status (10 min season, 24h offseason).
            default_sport: Default sport for season-aware TTL (default: 'nba')
        """
        if cache_ttl is None:
            from app.core.config import get_dynamic_cache_ttl
            cache_ttl = get_dynamic_cache_ttl(default_sport)

        self.api_key = api_key
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, tuple] = {}  # key -> (data, expiry)
        self._lock = asyncio.Lock()
        self._client: Optional[httpx.AsyncClient] = None

        # Quota tracking (from response headers)
        self._requests_remaining: Optional[int] = None
        self._requests_used: Optional[int] = None
        self._quota_last_updated: Optional[datetime] = None

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

    def _update_quota_from_headers(self, response: httpx.Response):
        """
        Update quota tracking from response headers.

        The Odds API returns:
        - x-requests-remaining: Requests left in current billing period
        - x-requests-used: Requests used in current billing period

        Args:
            response: HTTP response object
        """
        try:
            remaining = response.headers.get('x-requests-remaining')
            used = response.headers.get('x-requests-used')

            if remaining:
                self._requests_remaining = int(remaining)
            if used:
                self._requests_used = int(used)

            self._quota_last_updated = datetime.now()

            logger.info(
                f"The Odds API Quota: {self._requests_remaining} remaining, "
                f"{self._requests_used} used"
            )

            # Alert thresholds: Monthly quota is 20,000 requests
            # - WARNING when < 20% remaining (< 4000 requests)
            # - ERROR when < 5% remaining (< 1000 requests)
            if self._requests_remaining is not None:
                if self._requests_remaining < 1000:
                    logger.error(
                        f"CRITICAL: Odds API quota critically low! "
                        f"Only {self._requests_remaining} requests remaining (< 5%). "
                        f"Consider upgrading plan or reducing usage."
                    )
                elif self._requests_remaining < 4000:
                    logger.warning(
                        f"WARNING: Odds API quota running low. "
                        f"{self._requests_remaining} requests remaining (< 20%)."
                    )

            # Update Prometheus metrics
            try:
                from app.core.metrics import update_odds_api_quota
                if self._requests_remaining is not None and self._requests_used is not None:
                    update_odds_api_quota(
                        remaining=self._requests_remaining,
                        used=self._requests_used,
                        monthly_quota=20000
                    )
            except ImportError:
                # Metrics module not available - skip
                pass

        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse quota headers: {e}")

    def get_quota_status(self) -> Dict:
        """
        Get current quota status.

        Returns:
            Dict with remaining/used requests and last update time
        """
        return {
            "requests_remaining": self._requests_remaining,
            "requests_used": self._requests_used,
            "last_updated": self._quota_last_updated.isoformat() if self._quota_last_updated else None,
            "monthly_quota": 20000,
            "quota_percentage": round(
                (self._requests_used / 20000 * 100) if self._requests_used else 0, 2
            )
        }

    # Game Odds Methods

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    @odds_api_breaker
    async def _fetch_games_with_breaker(
        self,
        days_ahead: int,
        client: httpx.AsyncClient
    ) -> List[Dict]:
        """
        Internal method to fetch games - wrapped with circuit breaker.

        Args:
            days_ahead: Number of days ahead to fetch
            client: HTTP client

        Returns:
            List of games with odds data
        """
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

            # Track quota from response headers
            self._update_quota_from_headers(response)

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

        return list(all_games.values())

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

            # Call through circuit breaker
            result = await self._fetch_games_with_breaker(days_ahead, client)

            # Cache for 10 minutes (odds change frequently)
            await self._set_cache(cache_key, result, ttl=600)

            return result

        except CircuitBreakerError:
            logger.warning("Odds API circuit breaker is OPEN - returning empty list")
            return []
        except Exception as e:
            logger.error(f"Error fetching NBA game odds: {e}")
            return []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    @odds_api_breaker
    async def _fetch_player_props_with_breaker(
        self,
        event_id: str,
        player_props_markets: str,
        client: httpx.AsyncClient
    ) -> tuple[Dict, int]:
        """
        Internal method to fetch player props - wrapped with circuit breaker.

        Args:
            event_id: The Odds API event ID
            player_props_markets: Comma-separated list of markets
            client: HTTP client

        Returns:
            Tuple of (data dict, status code)
        """
        params = {
            "apiKey": self.api_key,
            "markets": player_props_markets,
            "regions": "us"
        }

        response = await client.get(
            f"{THE_ODDS_API_BASE}/sports/basketball_nba/events/{event_id}/odds",
            params=params
        )

        # Track quota from response headers
        self._update_quota_from_headers(response)

        status_code = response.status_code
        data = response.json() if status_code == 200 else {}

        return (data, status_code)

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

        # IMPORTANT: Request ALL player props markets in ONE API call
        # Using 'markets' (plural) with comma-separated list instead of 'market' (singular)
        # This prevents the API from returning fallback h2h markets when player props aren't available
        player_props_markets = "player_points,player_rebounds,player_assists,player_threes"

        try:
            client = await self._get_client()

            # Call through circuit breaker
            data, status_code = await self._fetch_player_props_with_breaker(
                event_id, player_props_markets, client
            )

            if status_code == 200:
                # Structure the response with markets keyed by market type
                # The API returns a single game object with all requested markets
                result = {
                    "event_id": event_id,
                    "markets": player_props_markets,
                    "data": data  # Store the full game response
                }

                # Log what markets were actually returned
                returned_markets = set()
                for bm in data.get("bookmakers", []):
                    for market in bm.get("markets", []):
                        returned_markets.add(market.get("key"))

                logger.info(f"Fetched player props for event {event_id}: returned markets = {list(returned_markets)}")

                # Cache for 5 minutes (player props change frequently)
                await self._set_cache(cache_key, result, ttl=300)

                return result
            else:
                logger.warning(f"Failed to fetch player props for event {event_id}: {status_code}")
                return {
                    "event_id": event_id,
                    "markets": player_props_markets,
                    "data": {"bookmakers": []}
                }

        except CircuitBreakerError:
            logger.warning(f"Odds API circuit breaker is OPEN for event {event_id} - returning empty player props")
            return {
                "event_id": event_id,
                "markets": player_props_markets,
                "data": {"bookmakers": []}
            }
        except Exception as e:
            logger.error(f"Error fetching NBA player props for event {event_id}: {e}")
            return {
                "event_id": event_id,
                "markets": "",
                "data": {"bookmakers": []}
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
