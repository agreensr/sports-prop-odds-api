"""
Injury tracking service for NBA player prop predictions.

This service fetches injury data from multiple sources:
1. ESPN NBA News API - Real-time injury updates
2. NBA Official Injury Report (via Firecrawl) - Official status reports

The service calculates injury context including:
- Player's own injury status
- Teammate injuries (usage boost opportunities)
- Minutes restrictions for returning players
- Impact scores for prediction adjustments

Research-backed approach:
- Returning players maintain efficiency, only minutes are restricted
- Source: https://www.jssm.org/volume24/iss2/cap/jssm-24-363.pdf
- Minutes restrictions typically 15-25 minutes initially
"""
import asyncio
import re
import httpx
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
import logging
import uuid
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.models import PlayerInjury, Player, Game

logger = logging.getLogger(__name__)

# Firecrawl configuration
FIRECRAWL_BASE_URL = "http://89.117.150.95:3002"
NBA_INJURY_REPORT_URL = "https://official.nba.com/nba-injury-report-2025-26-season"

# ESPN NBA News API
ESPN_NEWS_API_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/news"

# Injury severity levels for impact calculation
INJURY_SEVERITY = {
    "out": 100,
    "out indefinitely": 95,
    "out for season": 100,
    "doubtful": 60,
    "questionable": 30,
    "day-to-day": 20,
    "probable": 10,
    "available": 0,
    "returning": -10,  # Negative means positive impact (returning to action)
}

# Injury-related keywords for filtering ESPN news
INJURY_KEYWORDS = [
    "injury", "injured", "out", "questionable", "doubtful",
    "day-to-day", "ruled out", "will not play", "will miss",
    "sidelined", "hamstring", "ankle", "knee", "concussion",
    "illness", "sick", "health", "protocols", "returning",
    "activated", "minutes restriction"
]


class CacheEntry:
    """Simple cache entry with TTL."""
    def __init__(self, data: any, valid_until: datetime):
        self.data = data
        self.valid_until = valid_until

    def is_valid(self) -> bool:
        """Check if cache entry is still valid."""
        return datetime.now() < self.valid_until


class InjuryContext(BaseModel):
    """Injury context for a player."""
    self_injury: Optional[Dict] = None  # Player's own injury status
    teammate_injuries: List[Dict] = []  # Injured teammates
    impact_score: float = 0.0  # Overall impact (-1.0 to +1.0)
    minutes_adjustment: Optional[int] = None  # Minutes to add/subtract
    confidence_adjustment: float = 0.0  # Confidence modifier


class InjuryService:
    """
    Injury tracking and context calculation service.

    Fetches injury data from ESPN and NBA official reports,
    stores in database, and provides context for predictions.
    """

    def __init__(self, db: Session, cache_ttl: int = 3600):
        """
        Initialize injury service.

        Args:
            db: SQLAlchemy database session
            cache_ttl: Default cache TTL in seconds (default: 1 hour for injuries)
        """
        self.db = db
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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException))
    )
    async def _fetch_espn_news_with_retry(self, client: httpx.AsyncClient) -> Dict:
        """
        Internal method to fetch ESPN news with retry logic.

        Args:
            client: HTTP client

        Returns:
            Parsed JSON response
        """
        response = await client.get(ESPN_NEWS_API_URL)
        response.raise_for_status()
        return response.json()

    async def fetch_espn_injury_news(self, limit: int = 50) -> List[Dict]:
        """
        Fetch injury-related news from ESPN NBA News API.

        Args:
            limit: Maximum number of articles to return

        Returns:
            List of injury-related news articles with:
            - id: Article ID
            - headline: Article title
            - description: Article summary
            - published: Published date
            - link: Article URL
        """
        cache_key = self._get_cache_key("espn_news", limit=limit)
        cached = await self._get_cached(cache_key)
        if cached:
            logger.info("Using cached ESPN injury news")
            return cached

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                data = await self._fetch_espn_news_with_retry(client)

            # Extract articles
            articles = data.get("articles", [])

            # Filter for injury-related content
            injury_articles = []
            for article in articles:
                headline = article.get("headline", "").lower()
                description = article.get("description", "").lower()

                # Check if any injury keyword is present
                if any(keyword in headline or keyword in description for keyword in INJURY_KEYWORDS):
                    injury_articles.append({
                        "id": article.get("id"),
                        "headline": article.get("headline"),
                        "description": article.get("description"),
                        "published": article.get("published"),
                        "link": article.get("links", {}).get("web", {}).get("href"),
                        "source": "espn"
                    })

                    if len(injury_articles) >= limit:
                        break

            logger.info(f"Fetched {len(injury_articles)} injury-related articles from ESPN")

            # Cache for 30 minutes (news updates frequently)
            await self._set_cache(cache_key, injury_articles, ttl=1800)
            return injury_articles

        except Exception as e:
            logger.error(f"Error fetching ESPN injury news: {e}")
            return []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException))
    )
    async def _fetch_firecrawl_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str
    ) -> Dict:
        """
        Internal method to fetch data from Firecrawl with retry logic.

        Args:
            client: HTTP client
            url: URL to scrape

        Returns:
            Parsed JSON response
        """
        payload = {"url": url}
        response = await client.post(
            f"{FIRECRAWL_BASE_URL}/v1/scrape",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        return response.json()

    async def fetch_nba_official_report(self) -> List[Dict]:
        """
        Fetch official NBA injury report via Firecrawl.

        Returns:
            List of injury entries with:
            - player_name: Player name
            - team: Team abbreviation
            - injury_type: Type of injury
            - status: Injury status
            - description: Additional details
        """
        cache_key = self._get_cache_key("nba_official_report")
        cached = await self._get_cached(cache_key)
        if cached:
            logger.info("Using cached NBA official injury report")
            return cached

        try:
            # Call Firecrawl API with retry logic
            async with httpx.AsyncClient(timeout=60.0) as client:
                data = await self._fetch_firecrawl_with_retry(
                    client,
                    NBA_INJURY_REPORT_URL
                )

            # Parse the scraped content
            content = data.get("data", {}).get("markdown", "")
            injury_list = self._parse_nba_injury_report(content)

            logger.info(f"Parsed {len(injury_list)} injuries from NBA official report")

            # Cache for 1 hour (official reports update every 15 min)
            await self._set_cache(cache_key, injury_list, ttl=3600)
            return injury_list

        except Exception as e:
            logger.error(f"Error fetching NBA official injury report: {e}")
            return []

    def _parse_nba_injury_report(self, content: str) -> List[Dict]:
        """
        Parse NBA injury report content into structured data.

        Args:
            content: Markdown content from NBA injury report

        Returns:
            List of parsed injury entries
        """
        injuries = []
        lines = content.split("\n")

        # Pattern to match injury entries
        # Format typically: "PLAYER NAME - Team - Injury Type - Status"
        injury_pattern = re.compile(
            r"([A-Z][A-Za-z\s\.]+?)\s*[-–]\s*([A-Z]{3})\s*[-–]\s*(.+?)\s*[-–]\s*(.+)$"
        )

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("|"):
                continue

            match = injury_pattern.match(line)
            if match:
                player_name = match.group(1).strip()
                team = match.group(2).strip()
                injury_type = match.group(3).strip()
                status = match.group(4).strip().lower()

                injuries.append({
                    "player_name": player_name,
                    "team": team,
                    "injury_type": injury_type,
                    "status": self._normalize_status(status),
                    "description": f"{injury_type} - {status}",
                    "source": "nba_official"
                })

        return injuries

    def _normalize_status(self, status: str) -> str:
        """
        Normalize injury status to standard values.

        Args:
            status: Raw status string

        Returns:
            Normalized status: out, doubtful, questionable, day-to-day, returning, available
        """
        status_lower = status.lower()

        if any(word in status_lower for word in ["out", "will not play", "ruled out"]):
            return "out"
        elif "doubtful" in status_lower:
            return "doubtful"
        elif "questionable" in status_lower:
            return "questionable"
        elif any(word in status_lower for word in ["day-to-day", "day to day", "dtd"]):
            return "day-to-day"
        elif any(word in status_lower for word in ["returning", "activated", "available"]):
            return "returning" if "returning" in status_lower else "available"
        elif "probable" in status_lower:
            return "available"
        else:
            return "questionable"  # Default to questionable

    def ingest_injuries(self, injuries: List[Dict]) -> int:
        """
        Store injury data in database.

        Args:
            injuries: List of injury entries to store

        Returns:
            Number of injuries stored
        """
        count = 0
        today = date.today()

        for injury_data in injuries:
            try:
                # Look up player by name
                player = self.db.query(Player).filter(
                    Player.name.ilike(f"%{injury_data['player_name']}%")
                ).first()

                if not player:
                    logger.debug(f"Player not found: {injury_data['player_name']}")
                    continue

                # Check if injury already exists for today
                existing = self.db.query(PlayerInjury).filter(
                    and_(
                        PlayerInjury.player_id == player.id,
                        PlayerInjury.reported_date == today,
                        PlayerInjury.status == injury_data['status']
                    )
                ).first()

                if existing:
                    # Update existing injury
                    existing.updated_at = datetime.now()
                    existing.impact_description = injury_data.get('description', existing.impact_description)
                else:
                    # Create new injury entry
                    injury = PlayerInjury(
                        id=str(uuid.uuid4()),
                        player_id=player.id,
                        injury_type=injury_data.get('injury_type'),
                        status=injury_data['status'],
                        impact_description=injury_data.get('description'),
                        reported_date=today,
                        external_source=injury_data.get('source', 'unknown'),
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    self.db.add(injury)
                    count += 1

            except Exception as e:
                logger.error(f"Error ingesting injury for {injury_data.get('player_name')}: {e}")

        try:
            self.db.commit()
            logger.info(f"Ingested {count} new injuries")
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error committing injuries: {e}")

        return count

    def get_active_injuries(
        self,
        team: Optional[str] = None,
        days: int = 7,
        status_filter: Optional[List[str]] = None
    ) -> List[PlayerInjury]:
        """
        Get active injuries from database.

        Args:
            team: Filter by team abbreviation
            days: Number of days to look back
            status_filter: List of statuses to include (default: all except available)

        Returns:
            List of active PlayerInjury records
        """
        cutoff_date = date.today() - timedelta(days=days)

        if status_filter is None:
            # Default: exclude "available" status
            status_filter = ["out", "doubtful", "questionable", "day-to-day", "returning"]

        query = self.db.query(PlayerInjury).filter(
            and_(
                PlayerInjury.reported_date >= cutoff_date,
                PlayerInjury.status.in_(status_filter)
            )
        )

        if team:
            # Join with players table to filter by team
            query = query.join(Player).filter(Player.team == team)

        return query.order_by(PlayerInjury.reported_date.desc()).all()

    def get_player_injury_context(
        self,
        player_id: str,
        game_id: Optional[str] = None
    ) -> Dict:
        """
        Get injury context for a player in a specific game.

        Returns:
            Dict with:
            - self_injury: Player's own injury status (if any)
            - teammate_injuries: List of injured teammates (usage boost opportunity)
            - impact_score: Calculated impact on prediction (-1.0 to +1.0)
            - minutes_projection: Adjusted minutes based on injury context
            - confidence_adjustment: Confidence modifier (-0.3 to +0.15)
        """
        # Get player info
        player = self.db.query(Player).filter(Player.id == player_id).first()
        if not player:
            return {
                "self_injury": None,
                "teammate_injuries": [],
                "impact_score": 0.0,
                "minutes_projection": None,
                "confidence_adjustment": 0.0
            }

        # Get player's own injury (recent reports)
        cutoff_date = date.today() - timedelta(days=7)
        self_injury = self.db.query(PlayerInjury).filter(
            and_(
                PlayerInjury.player_id == player_id,
                PlayerInjury.reported_date >= cutoff_date
            )
        ).order_by(PlayerInjury.reported_date.desc()).first()

        # Get teammate injuries (potential usage boost)
        if player.team:
            teammate_injuries = self.db.query(PlayerInjury).join(Player).filter(
                and_(
                    Player.team == player.team,
                    Player.id != player_id,
                    PlayerInjury.reported_date >= cutoff_date,
                    PlayerInjury.status.in_(["out", "doubtful", "questionable"])
                )
            ).all()
        else:
            teammate_injuries = []

        # Calculate impact score
        impact_score = 0.0
        minutes_projection = None
        confidence_adjustment = 0.0

        if self_injury:
            severity = INJURY_SEVERITY.get(self_injury.status, 0)
            impact_score = -severity / 100.0  # Negative impact for own injury

            # Calculate minutes based on status
            if self_injury.status == "out":
                minutes_projection = 0
                confidence_adjustment = -0.30
            elif self_injury.status == "doubtful":
                minutes_projection = 10
                confidence_adjustment = -0.20
            elif self_injury.status == "questionable":
                minutes_projection = 20
                confidence_adjustment = -0.15
            elif self_injury.status == "returning":
                # Use restricted minutes based on games played since return
                games_played = self_injury.games_played_since_return or 0
                minutes_projection = 18 + min(games_played * 2, 12)  # 18-30 minutes
                confidence_adjustment = -0.05  # Minor uncertainty
            elif self_injury.status == "day-to-day":
                minutes_projection = 25
                confidence_adjustment = -0.10

        # Add positive impact for teammate injuries (usage boost)
        if teammate_injuries:
            boost = min(len(teammate_injuries) * 0.03, 0.10)  # Max 10% boost
            impact_score += boost
            confidence_adjustment += min(len(teammate_injuries) * 0.02, 0.05)  # Max +0.05

        return {
            "self_injury": {
                "status": self_injury.status if self_injury else None,
                "injury_type": self_injury.injury_type if self_injury else None,
                "days_since_return": self_injury.days_since_return if self_injury else None,
                "games_played_since_return": self_injury.games_played_since_return if self_injury else None,
                "minutes_restriction": self_injury.minutes_restriction if self_injury else None,
            } if self_injury else None,
            "teammate_injuries": [
                {
                    "player_name": t.player.name,
                    "status": t.status,
                    "injury_type": t.injury_type
                }
                for t in teammate_injuries
            ],
            "impact_score": round(impact_score, 2),
            "minutes_projection": minutes_projection,
            "confidence_adjustment": round(confidence_adjustment, 2)
        }

    def calculate_minutes_restriction(
        self,
        days_since_return: int,
        games_played: int
    ) -> int:
        """
        Calculate minutes restriction based on return progression.

        Research-backed gradual increase:
        - Base: 18 minutes for returnees
        - +2 minutes per game played
        - Max: 30 minutes (normal starter minutes)

        Args:
            days_since_return: Days since player returned from injury
            games_played: Games played since return

        Returns:
            Recommended minutes restriction
        """
        base_restriction = 18
        increase = min(games_played * 2, 12)
        return min(base_restriction + increase, 30)

    def update_return_progression(self, player_id: str, games_played: int) -> bool:
        """
        Update a returning player's progression after playing a game.

        Args:
            player_id: Player ID
            games_played: Total games played since return

        Returns:
            True if updated successfully
        """
        try:
            injury = self.db.query(PlayerInjury).filter(
                and_(
                    PlayerInjury.player_id == player_id,
                    PlayerInjury.status == "returning"
                )
            ).first()

            if injury:
                injury.games_played_since_return = games_played
                injury.minutes_restriction = self.calculate_minutes_restriction(
                    injury.days_since_return or 0,
                    games_played
                )
                injury.updated_at = datetime.now()
                self.db.commit()
                return True

        except Exception as e:
            logger.error(f"Error updating return progression for {player_id}: {e}")
            self.db.rollback()

        return False

    def filter_by_injury_status(
        self,
        player_ids: List[str],
        exclude_statuses: Optional[List[str]] = None
    ) -> List[str]:
        """
        Filter out injured players from a list.

        CRITICAL: This is the main injury filtering method for predictions.
        Must be called BEFORE generating predictions to exclude unavailable players.

        Args:
            player_ids: List of player database UUIDs
            exclude_statuses: Injury statuses to exclude (default: out, doubtful, questionable)

        Returns:
            Filtered list of player IDs (healthy players only)

        Example:
            >>> healthy_ids = injury_service.filter_by_injury_status(player_ids)
            >>> print(f"Filtered: {len(player_ids)} → {len(healthy_ids)}")
        """
        if exclude_statuses is None:
            exclude_statuses = ["out", "doubtful", "questionable"]

        cutoff_date = date.today() - timedelta(days=7)

        # Normalize statuses to uppercase for case-insensitive comparison
        exclude_statuses_upper = [s.upper() for s in exclude_statuses]

        # Get active injuries for these players
        injured = self.db.query(PlayerInjury).filter(
            and_(
                PlayerInjury.player_id.in_(player_ids),
                PlayerInjury.reported_date >= cutoff_date,
                func.upper(PlayerInjury.status).in_(exclude_statuses_upper)
            )
        ).all()

        injured_ids = {injury.player_id for injury in injured}

        # Log filtered players with details
        for injury in injured:
            player = self.db.query(Player).filter(Player.id == injury.player_id).first()
            if player:
                logger.info(
                    f"Excluding {player.name} - status: {injury.status}, "
                    f"injury: {injury.injury_type}"
                )
            else:
                logger.info(f"Excluding player {injury.player_id} - status: {injury.status}")

        # Return only healthy players
        healthy_ids = [pid for pid in player_ids if pid not in injured_ids]

        logger.info(
            f"Injury filter: {len(player_ids)} → {len(healthy_ids)} "
            f"(excluded {len(injured_ids)}: {exclude_statuses})"
        )

        return healthy_ids

    def filter_players_by_injury_status(
        self,
        players: List[Player],
        exclude_statuses: Optional[List[str]] = None
    ) -> List[Player]:
        """
        Filter Player objects by injury status.

        Convenience method that works with Player objects instead of IDs.

        Args:
            players: List of Player objects
            exclude_statuses: Injury statuses to exclude

        Returns:
            Filtered list of Player objects (healthy players only)
        """
        player_ids = [p.id for p in players]
        healthy_ids = set(self.filter_by_injury_status(player_ids, exclude_statuses))

        return [p for p in players if p.id in healthy_ids]
