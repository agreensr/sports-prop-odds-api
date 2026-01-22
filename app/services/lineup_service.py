"""
Lineup tracking service for NBA player prop predictions.

This service fetches lineup data from multiple sources:
1. NBA depth charts via NBA.com API
2. Firecrawl scraping of lineup projection sites

Lineups are critical for accurate predictions because:
- Starting role = 28-35 minutes typically
- Bench role = 12-20 minutes typically
- Minutes-based prediction: per_36_stats × (projected_minutes / 36)

Example - Jay Huff:
- Old approach: Assumed starter minutes (28-35) → 11.9 points predicted
- Actual: Bench role, 10 minutes → 2.0 points actual (83% error)
- New approach: Bench projection (10-15 min) → ~4 points predicted (much closer!)
"""
import asyncio
import httpx
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_
import logging
import uuid

logger = logging.getLogger(__name__)

# Firecrawl configuration
FIRECRAWL_BASE_URL = "http://89.117.150.95:3002"

# Lineup projection sources (can be extended)
LINEUP_SOURCES = [
    {"name": "rotowire", "url": "https://www.rotowire.com/basketball/nba-lineups.php"},
    {"name": "espn", "url": "https://www.espn.com/nba/dailylineup"},
    {"name": "nba", "url": "https://www.nba.com/games"},
]

# Default minutes by position and role
DEFAULT_MINUTES = {
    "starter": 30,  # Starting players
    "sixth_man": 24,  # Key bench player
    "bench": 14,  # Regular rotation player
    "deep_bench": 6,  # Minimal playing time
}


class CacheEntry:
    """Simple cache entry with TTL."""
    def __init__(self, data: any, valid_until: datetime):
        self.data = data
        self.valid_until = valid_until

    def is_valid(self) -> bool:
        """Check if cache entry is still valid."""
        return datetime.now() < self.valid_until


class LineupService:
    """
    Lineup tracking and projection service.

    Fetches lineup data from multiple sources, stores in database,
    and provides minutes projections for predictions.
    """

    def __init__(self, db: Session, cache_ttl: int = 1800):
        """
        Initialize lineup service.

        Args:
            db: SQLAlchemy database session
            cache_ttl: Default cache TTL in seconds (default: 30 min for lineups)
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

    async def fetch_lineups_from_firecrawl(self, source: str = "rotowire") -> List[Dict]:
        """
        Fetch lineup data from a projection source via Firecrawl.

        Args:
            source: Source name (rotowire, espn, nba)

        Returns:
            List of lineup entries with:
            - team: Team abbreviation
            - player_name: Player name
            - position: Position (PG, SG, SF, PF, C)
            - is_starter: Whether player is projected starter
            - status: Starting, Bench, Out, etc.
        """
        source_config = next((s for s in LINEUP_SOURCES if s["name"] == source), None)
        if not source_config:
            logger.error(f"Unknown lineup source: {source}")
            return []

        cache_key = self._get_cache_key("lineups", source=source)
        cached = await self._get_cached(cache_key)
        if cached:
            logger.info(f"Using cached lineups from {source}")
            return cached

        try:
            # Call Firecrawl API
            async with httpx.AsyncClient(timeout=60.0) as client:
                payload = {
                    "url": source_config["url"]
                }
                response = await client.post(
                    f"{FIRECRAWL_BASE_URL}/v1/scrape",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                data = response.json()

            # Parse the scraped content
            content = data.get("data", {}).get("markdown", "")
            lineups = self._parse_lineup_content(content, source)

            logger.info(f"Parsed {len(lineups)} lineup entries from {source}")

            # Cache for 30 minutes (lineups change frequently)
            await self._set_cache(cache_key, lineups, ttl=1800)
            return lineups

        except Exception as e:
            logger.error(f"Error fetching lineups from {source}: {e}")
            return []

    def _parse_lineup_content(self, content: str, source: str) -> List[Dict]:
        """
        Parse lineup content into structured data.

        Args:
            content: Markdown content from lineup site
            source: Source name (for parsing logic)

        Returns:
            List of parsed lineup entries
        """
        lineups = []
        lines = content.split("\n")

        if source == "rotowire":
            import re

            current_team = None
            is_starters = True
            current_position = None

            for line in lines:
                line = line.strip()

                # Detect team headers (e.g., "CLE (25-20)" or "CLE]")
                if not line:
                    continue

                # Check for team abbreviation in brackets or with record
                team_match = re.search(r'\[([A-Z]{3})\]', line)
                if team_match:
                    current_team = team_match.group(1)
                    is_starters = True
                    current_position = None
                    continue

                # Detect position markers (PG, SG, SF, PF, C)
                if re.match(r'^\*\s+(PG|SG|SF|PF|C)\s*$', line):
                    current_position = line.replace('*', '').strip()
                    continue

                # Detect "BENCH" or "MAY NOT PLAY" section
                if "BENCH" in line.upper() or "MAY NOT PLAY" in line.upper():
                    is_starters = False
                    current_position = None
                    continue

                # Detect "Confirmed Lineup" section
                if "CONFIRMED LINEUP" in line.upper():
                    is_starters = True
                    continue

                # Parse player entries - markdown link format
                # Format: [Player Name](url) or [F. Lastname](url)
                player_match = re.search(r'\[([A-Z][A-Za-z\.\s]+?)\]\(https://', line)
                if player_match and current_team:
                    player_name = player_match.group(1).strip()

                    # Check for status indicators on the same line
                    status = "Starting" if is_starters else "Bench"
                    if " Out" in line:
                        status = "Out"
                    elif " Ques" in line:
                        status = "Questionable"
                    elif " OFS" in line:
                        status = "Out - For Season"
                    elif "GTD" in line:
                        status = "Questionable"

                    lineups.append({
                        "team": current_team,
                        "player_name": player_name,
                        "position": current_position,
                        "is_starter": is_starters and status == "Starting",
                        "status": status,
                        "source": source
                    })

        return lineups

    def _get_team_abbrs(self) -> List[str]:
        """Get list of NBA team abbreviations."""
        return [
            "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN",
            "DET", "GSW", "HOU", "IND", "LAC", "LAL", "MEM", "MIA",
            "MIL", "MIN", "NOP", "NYK", "OKC", "ORL", "PHI", "PHX",
            "POR", "SAC", "SAS", "TOR", "UTA", "WAS"
        ]

    def _extract_team_abbr(self, text: str) -> Optional[str]:
        """Extract team abbreviation from text."""
        text_upper = text.upper()
        for abbr in self._get_team_abbrs():
            if abbr in text_upper:
                return abbr
        return None

    def ingest_lineups(self, lineups: List[Dict], game_id: Optional[str] = None) -> int:
        """
        Store lineup data in database.

        Args:
            lineups: List of lineup entries to store
            game_id: Optional game ID to associate lineups with

        Returns:
            Number of lineups stored
        """
        from app.models.models import Player, ExpectedLineup

        count = 0

        for lineup_data in lineups:
            try:
                # Look up player by name and team
                player = self.db.query(Player).filter(
                    Player.name.ilike(f"%{lineup_data['player_name']}%"),
                    Player.team == lineup_data['team']
                ).first()

                if not player:
                    logger.debug(f"Player not found: {lineup_data['player_name']} ({lineup_data['team']})")
                    continue

                # Determine position
                position = lineup_data.get('position')

                # Estimate minutes based on role
                if lineup_data['is_starter']:
                    minutes_projection = DEFAULT_MINUTES['starter']
                    starter_position = position or "SF"  # Default position if unknown
                else:
                    minutes_projection = DEFAULT_MINUTES['bench']
                    starter_position = None

                # Check if lineup entry already exists
                if game_id:
                    existing = self.db.query(ExpectedLineup).filter(
                        and_(
                            ExpectedLineup.game_id == game_id,
                            ExpectedLineup.player_id == player.id,
                            ExpectedLineup.team == lineup_data['team']
                        )
                    ).first()
                else:
                    existing = None

                if existing:
                    # Update existing entry
                    existing.starter_position = starter_position
                    existing.is_confirmed = False  # Projected, not confirmed
                    existing.minutes_projection = minutes_projection
                    existing.updated_at = datetime.now()
                else:
                    # Create new lineup entry
                    lineup = ExpectedLineup(
                        id=str(uuid.uuid4()),
                        game_id=game_id,
                        team=lineup_data['team'],
                        player_id=player.id,
                        starter_position=starter_position,
                        is_confirmed=False,
                        minutes_projection=minutes_projection,
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    self.db.add(lineup)
                    count += 1

            except Exception as e:
                logger.error(f"Error ingesting lineup for {lineup_data.get('player_name')}: {e}")

        try:
            self.db.commit()
            logger.info(f"Ingested {count} new lineup entries")
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error committing lineups: {e}")

        return count

    def get_game_lineups(self, game_id: str) -> Dict[str, List[Dict]]:
        """
        Get projected lineups for a game grouped by team.

        Args:
            game_id: Game ID

        Returns:
            Dict with team abbreviations as keys and lists of players as values
        """
        from app.models.models import ExpectedLineup, Player

        lineups = self.db.query(ExpectedLineup).join(Player).filter(
            ExpectedLineup.game_id == game_id
        ).order_by(ExpectedLineup.team, ExpectedLineup.starter_position.desc().nulls_last()).all()

        result = {}
        for lineup in lineups:
            if lineup.team not in result:
                result[lineup.team] = []

            result[lineup.team].append({
                "player_id": lineup.player_id,
                "player_name": lineup.player.name,
                "position": lineup.starter_position,
                "is_starter": lineup.starter_position is not None,
                "is_confirmed": lineup.is_confirmed,
                "minutes_projection": lineup.minutes_projection
            })

        return result

    def get_player_minutes_projection(
        self,
        player_id: str,
        game_id: Optional[str] = None
    ) -> Optional[int]:
        """
        Get projected minutes for a player.

        Args:
            player_id: Player ID
            game_id: Optional game ID for game-specific projections

        Returns:
            Projected minutes or None if no projection available
        """
        from app.models.models import ExpectedLineup

        query = self.db.query(ExpectedLineup).filter(
            ExpectedLineup.player_id == player_id
        )

        if game_id:
            query = query.filter(ExpectedLineup.game_id == game_id)

        # Get most recent projection
        projection = query.order_by(ExpectedLineup.created_at.desc()).first()

        if projection:
            return projection.minutes_projection

        return None

    def estimate_minutes_from_lineups(
        self,
        player_id: str,
        team: str,
        game_id: Optional[str] = None
    ) -> int:
        """
        Estimate minutes for a player based on team lineups.

        If player is in projected lineup, use their projection.
        If not, estimate based on team depth.

        Args:
            player_id: Player ID
            team: Team abbreviation
            game_id: Optional game ID

        Returns:
            Estimated minutes (default 28 for unknown players)
        """
        from app.models.models import ExpectedLineup, Player

        # First try to get specific projection
        specific = self.get_player_minutes_projection(player_id, game_id)
        if specific:
            return specific

        # Check if player is a starter on their team
        player = self.db.query(Player).filter(Player.id == player_id).first()
        if not player:
            return 28  # Default for unknown players

        # Count starters for this team/game
        if game_id:
            starter_count = self.db.query(ExpectedLineup).filter(
                and_(
                    ExpectedLineup.game_id == game_id,
                    ExpectedLineup.team == team,
                    ExpectedLineup.starter_position.isnot(None)
                )
            ).count()
        else:
            # Use most recent projections
            starter_count = self.db.query(ExpectedLineup).filter(
                and_(
                    ExpectedLineup.team == team,
                    ExpectedLineup.starter_position.isnot(None)
                )
            ).count()

        # If less than 5 starters, assume this player might start
        if starter_count < 5:
            return DEFAULT_MINUTES['starter']

        # Otherwise assume bench role
        return DEFAULT_MINUTES['bench']

    def confirm_lineups_from_boxscore(self, game_id: str, boxscore_data: Dict) -> int:
        """
        Update lineups to confirmed based on actual boxscore data.

        Args:
            game_id: Game ID
            boxscore_data: Boxscore data with actual players

        Returns:
            Number of lineup entries updated
        """
        from app.models.models import ExpectedLineup, Player

        count = 0
        player_stats = boxscore_data.get('PlayerStats', [])

        # Group by team and identify starters (top 5 by minutes)
        team_minutes: Dict[str, List[tuple]] = {}

        for stat in player_stats:
            player_id = stat.get('PLAYER_ID')
            minutes = stat.get('MIN', 0)

            if not player_id:
                continue

            player = self.db.query(Player).filter(
                Player.external_id == player_id
            ).first()

            if not player:
                continue

            if player.team not in team_minutes:
                team_minutes[player.team] = []

            team_minutes[player.team].append((player.id, minutes or 0))

        # For each team, top 5 in minutes are starters
        for team, players in team_minutes.items():
            # Sort by minutes descending
            players.sort(key=lambda x: x[1], reverse=True)

            for i, (player_id, minutes) in enumerate(players[:5]):  # Top 5
                # Update or create lineup entry
                existing = self.db.query(ExpectedLineup).filter(
                    and_(
                        ExpectedLineup.game_id == game_id,
                        ExpectedLineup.player_id == player_id
                    )
                ).first()

                if existing:
                    existing.is_confirmed = True
                    existing.minutes_projection = minutes
                    existing.updated_at = datetime.now()
                    count += 1

        try:
            self.db.commit()
            logger.info(f"Confirmed {count} lineup entries from boxscore")
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error confirming lineups: {e}")

        return count
