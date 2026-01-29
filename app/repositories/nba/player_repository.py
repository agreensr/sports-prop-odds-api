"""
Player Repository for NBA player data access.

This repository encapsulates all database queries related to players,
providing a clean interface for services and API routes.

Usage:
    repo = PlayerRepository(db)
    player = repo.find_by_external_id("1628369")
    active_players = repo.find_active()
    bos_players = repo.find_by_team("BOS")
"""
from typing import Optional, List
from sqlalchemy import or_, and_

from app.models import Player
from app.repositories.base import BaseRepository


class PlayerRepository(BaseRepository[Player]):
    """Repository for NBA player data access."""

    def __init__(self, db):
        """Initialize the player repository."""
        super().__init__(Player, db)

    # ========================================================================
    # External ID Lookups
    # ========================================================================

    def find_by_external_id(self, external_id: str) -> Optional[Player]:
        """Find a player by external ID."""
        return self.where_first(Player.external_id == external_id)

    def find_by_nba_api_id(self, nba_api_id: int) -> Optional[Player]:
        """Find a player by NBA API ID."""
        return self.where_first(Player.nba_api_id == nba_api_id)

    def find_by_odds_api_id(self, odds_api_id: int) -> Optional[Player]:
        """Find a player by Odds API ID."""
        return self.where_first(Player.odds_api_id == odds_api_id)

    def find_by_espn_id(self, espn_id: int) -> Optional[Player]:
        """Find a player by ESPN ID."""
        return self.where_first(Player.espn_id == espn_id)

    # ========================================================================
    # Name-based Lookups
    # ========================================================================

    def find_by_name(self, name: str) -> Optional[Player]:
        """Find a player by exact name match."""
        return self.where_first(Player.name == name)

    def search_by_name(self, name: str, limit: int = 10) -> List[Player]:
        """
        Search for players by name (case-insensitive partial match).

        Args:
            name: Name or partial name to search for
            limit: Maximum number of results

        Returns:
            List of matching players
        """
        search_pattern = f"%{name.lower()}%"
        return self.db.query(Player).filter(
            Player.name.ilike(search_pattern)
        ).limit(limit).all()

    def find_by_canonical_name(self, canonical_name: str) -> Optional[Player]:
        """Find a player by canonical name."""
        return self.where_first(Player.canonical_name == canonical_name)

    # ========================================================================
    # Team-based Queries
    # ========================================================================

    def find_by_team(
        self,
        team: str,
        active_only: bool = True
    ) -> List[Player]:
        """
        Find all players for a specific team.

        Args:
            team: Team abbreviation (e.g., "BOS", "LAL")
            active_only: Only return active players

        Returns:
            List of players on the team
        """
        query = self.db.query(Player).filter(Player.team == team)
        if active_only:
            query = query.filter(Player.active == True)
        return query.all()

    def get_team_counts(
        self,
        active_only: bool = True,
        min_count: int = 1
    ) -> List[tuple]:
        """
        Get player counts grouped by team.

        Args:
            active_only: Only count active players
            min_count: Minimum player count to include

        Returns:
            List of (team, count) tuples ordered by count descending
        """
        query = self.db.query(Player.team, self.model_type.id)
        if active_only:
            query = query.filter(Player.active == True)
        query = query.filter(Player.team.isnot(None))

        from sqlalchemy import func, desc
        result = query.group_by(Player.team).order_by(
            desc(func.count(Player.id))
        ).all()

        if min_count > 1:
            result = [(team, count) for team, count in result if count >= min_count]

        return result

    # ========================================================================
    # Active/Inactive Status
    # ========================================================================

    def find_active(self, team: Optional[str] = None) -> List[Player]:
        """
        Find all active players.

        Args:
            team: Optional team filter

        Returns:
            List of active players
        """
        query = self.db.query(Player).filter(Player.active == True)
        if team:
            query = query.filter(Player.team == team)
        return query.all()

    def find_inactive(self) -> List[Player]:
        """Find all inactive players."""
        return self.db.query(Player).filter(Player.active == False).all()

    # ========================================================================
    # Position-based Queries
    # ========================================================================

    def find_by_position(
        self,
        position: str,
        active_only: bool = True
    ) -> List[Player]:
        """
        Find players by position.

        Args:
            position: Position abbreviation (e.g., "PG", "SF", "C")
            active_only: Only return active players

        Returns:
            List of players at the position
        """
        query = self.db.query(Player).filter(Player.position == position)
        if active_only:
            query = query.filter(Player.active == True)
        return query.all()

    # ========================================================================
    # Data Source Queries
    # ========================================================================

    def find_by_id_source(self, id_source: str) -> List[Player]:
        """
        Find players by ID source.

        Args:
            id_source: Source system (e.g., "nba", "odds_api", "espn")

        Returns:
            List of players with IDs from this source
        """
        return self.db.query(Player).filter(
            Player.id_source == id_source
        ).all()

    # ========================================================================
    # Roster-related Queries
    # ========================================================================

    def find_recently_checked(
        self,
        days: int = 7,
        team: Optional[str] = None
    ) -> List[Player]:
        """
        Find players whose roster was recently checked.

        Args:
            days: Number of days to look back
            team: Optional team filter

        Returns:
            List of players
        """
        from datetime import timedelta, timezone

        try:
            utc = timezone.utc
        except AttributeError:
            from datetime import timezone as tz
            utc = tz.utc

        cutoff = timedelta(days=days)
        query = self.db.query(Player).filter(
            Player.last_roster_check >= cutoff
        )
        if team:
            query = query.filter(Player.team == team)
        return query.all()

    # ========================================================================
    # Advanced Queries
    # ========================================================================

    def find_or_create_by_external_id(
        self,
        external_id: str,
        defaults: dict
    ) -> Player:
        """
        Find a player by external ID, or create if not found.

        Args:
            external_id: External ID to search for
            defaults: Dictionary of default values for new player

        Returns:
            Player instance (existing or newly created)
        """
        player = self.find_by_external_id(external_id)
        if not player:
            player = self.create(external_id=external_id, **defaults)
        return player

    def find_by_team_and_position(
        self,
        team: str,
        position: str,
        active_only: bool = True
    ) -> List[Player]:
        """Find players by team and position."""
        query = self.db.query(Player).filter(
            Player.team == team,
            Player.position == position
        )
        if active_only:
            query = query.filter(Player.active == True)
        return query.all()

    def search_multi_field(
        self,
        search_term: str,
        limit: int = 20
    ) -> List[Player]:
        """
        Search players across multiple fields.

        Searches in: name, canonical_name, team

        Args:
            search_term: Term to search for
            limit: Maximum results

        Returns:
            List of matching players
        """
        pattern = f"%{search_term.lower()}%"
        return self.db.query(Player).filter(
            or_(
                Player.name.ilike(pattern),
                Player.canonical_name.ilike(pattern),
                Player.team.ilike(pattern)
            )
        ).limit(limit).all()
