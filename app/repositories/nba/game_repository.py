"""
Game Repository for NBA game data access.

This repository encapsulates all database queries related to games,
providing a clean interface for services and API routes.

Usage:
    repo = GameRepository(db)
    game = repo.find_by_external_id("0022400101")
    upcoming = repo.find_upcoming()
    games_today = repo.find_by_date(datetime.now())
"""
from typing import Optional, List, Tuple
from datetime import datetime, timedelta
from sqlalchemy import or_, and_, desc

from app.models import Game
from app.repositories.base import BaseRepository


class GameRepository(BaseRepository[Game]):
    """Repository for NBA game data access."""

    def __init__(self, db):
        """Initialize the game repository."""
        super().__init__(Game, db)

    # ========================================================================
    # External ID Lookups
    # ========================================================================

    def find_by_external_id(self, external_id: str) -> Optional[Game]:
        """Find a game by external ID."""
        return self.where_first(Game.external_id == external_id)

    def find_by_id_source(self, id_source: str) -> List[Game]:
        """Find games by ID source."""
        return self.db.query(Game).filter(
            Game.id_source == id_source
        ).all()

    # ========================================================================
    # Date-based Queries
    # ========================================================================

    def find_by_date(
        self,
        date: datetime,
        start_offset: int = 0,
        end_offset: int = 1
    ) -> List[Game]:
        """
        Find games on a specific date.

        Args:
            date: Date to search for
            start_offset: Hours before date to include
            end_offset: Hours after date to include

        Returns:
            List of games on the date
        """
        from datetime import timezone

        try:
            utc = timezone.utc
        except AttributeError:
            from datetime import timezone as tz
            utc = tz.utc

        if date.tzinfo is not None:
            date = date.replace(tzinfo=None)

        start = date + timedelta(hours=start_offset)
        end = date + timedelta(hours=end_offset)

        return self.db.query(Game).filter(
            Game.game_date >= start,
            Game.game_date < end
        ).order_by(Game.game_date).all()

    def find_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[Game]:
        """
        Find games within a date range.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List of games in the range
        """
        return self.in_date_range('game_date', start_date, end_date)

    def find_upcoming(
        self,
        hours_ahead: int = 24,
        status: str = "scheduled"
    ) -> List[Game]:
        """
        Find upcoming games.

        Args:
            hours_ahead: How many hours ahead to look
            status: Game status filter (default: "scheduled")

        Returns:
            List of upcoming games
        """
        from datetime import timezone

        try:
            utc = timezone.utc
        except AttributeError:
            from datetime import timezone as tz
            utc = tz.utc

        now = datetime.now(utc).replace(tzinfo=None)
        cutoff = now + timedelta(hours=hours_ahead)

        return self.db.query(Game).filter(
            Game.game_date >= now,
            Game.game_date <= cutoff,
            Game.status == status
        ).order_by(Game.game_date).all()

    def find_recent(
        self,
        hours_back: int = 24,
        status: Optional[str] = None
    ) -> List[Game]:
        """
        Find recent games.

        Args:
            hours_back: How many hours back to look
            status: Optional game status filter

        Returns:
            List of recent games
        """
        from datetime import timezone

        try:
            utc = timezone.utc
        except AttributeError:
            from datetime import timezone as tz
            utc = tz.utc

        now = datetime.now(utc).replace(tzinfo=None)
        cutoff = now - timedelta(hours=hours_back)

        query = self.db.query(Game).filter(Game.game_date >= cutoff)
        if status:
            query = query.filter(Game.status == status)
        return query.order_by(desc(Game.game_date)).all()

    # ========================================================================
    # Team-based Queries
    # ========================================================================

    def find_by_team(
        self,
        team: str,
        season: Optional[int] = None,
        limit: Optional[int] = None
    ) -> List[Game]:
        """
        Find games for a specific team.

        Args:
            team: Team abbreviation (e.g., "BOS", "LAL")
            season: Optional season filter
            limit: Maximum number of games

        Returns:
            List of games involving the team
        """
        query = self.db.query(Game).filter(
            or_(
                Game.away_team == team,
                Game.home_team == team
            )
        )
        if season is not None:
            query = query.filter(Game.season == season)
        query = query.order_by(desc(Game.game_date))
        if limit:
            query = query.limit(limit)
        return query.all()

    def find_by_teams(
        self,
        team1: str,
        team2: str,
        days_back: int = 365
    ) -> Optional[Game]:
        """
        Find a game between two teams.

        Handles both team orderings (team1 @ team2 or team2 @ team1).

        Args:
            team1: First team
            team2: Second team
            days_back: How many days back to search

        Returns:
            Game if found, None otherwise
        """
        from datetime import timezone

        try:
            utc = timezone.utc
        except AttributeError:
            from datetime import timezone as tz
            utc = tz.utc

        cutoff = datetime.now(utc).replace(tzinfo=None) - timedelta(days=days_back)

        return self.db.query(Game).filter(
            or_(
                and_(
                    Game.away_team == team1,
                    Game.home_team == team2
                ),
                and_(
                    Game.away_team == team2,
                    Game.home_team == team1
                )
            ),
            Game.game_date >= cutoff
        ).order_by(desc(Game.game_date)).first()

    # ========================================================================
    # Status Queries
    # ========================================================================

    def find_by_status(self, status: str, limit: Optional[int] = None) -> List[Game]:
        """Find games by status."""
        query = self.db.query(Game).filter(Game.status == status)
        if limit:
            query = query.limit(limit)
        return query.order_by(desc(Game.game_date)).all()

    def find_scheduled(self, hours_ahead: int = 48) -> List[Game]:
        """Find scheduled upcoming games."""
        return self.find_upcoming(hours_ahead, status="scheduled")

    def find_in_progress(self) -> List[Game]:
        """Find games currently in progress."""
        return self.find_by_status("in_progress")

    def find_completed(
        self,
        days_back: int = 7,
        limit: Optional[int] = None
    ) -> List[Game]:
        """Find completed games."""
        from datetime import timezone

        try:
            utc = timezone.utc
        except AttributeError:
            from datetime import timezone as tz
            utc = tz.utc

        cutoff = datetime.now(utc).replace(tzinfo=None) - timedelta(days=days_back)
        query = self.db.query(Game).filter(
            Game.status.in_(["final", "completed", "Final"]),
            Game.game_date >= cutoff
        ).order_by(desc(Game.game_date))
        if limit:
            query = query.limit(limit)
        return query.all()

    # ========================================================================
    # Season Queries
    # ========================================================================

    def find_by_season(
        self,
        season: int,
        status: Optional[str] = None
    ) -> List[Game]:
        """Find games by season."""
        query = self.db.query(Game).filter(Game.season == season)
        if status:
            query = query.filter(Game.status == status)
        return query.order_by(Game.game_date).all()

    def get_seasons(self) -> List[int]:
        """Get all seasons with games."""
        from sqlalchemy import func
        result = self.db.query(Game.season).distinct().order_by(
            Game.season.desc()
        ).all()
        return [row[0] for row in result]

    # ========================================================================
    # Advanced Queries
    # ========================================================================

    def find_without_predictions(
        self,
        hours_ahead: int = 24,
        limit: int = 50
    ) -> List[Game]:
        """
        Find games that don't have predictions yet.

        Args:
            hours_ahead: How many hours ahead to look
            limit: Maximum number of games

        Returns:
            List of games without predictions
        """
        from app.models import Prediction

        upcoming = self.find_upcoming(hours_ahead)
        game_ids = [g.id for g in upcoming]

        games_with_predictions = self.db.query(Prediction.game_id).filter(
            Prediction.game_id.in_(game_ids)
        ).distinct().all()

        predicted_ids = {row[0] for row in games_with_predictions}

        return [g for g in upcoming if g.id not in predicted_ids][:limit]

    def find_by_team_and_season(
        self,
        team: str,
        season: int
    ) -> List[Game]:
        """Find all games for a team in a season."""
        return self.find_by_team(team, season=season)

    def count_by_status(self) -> List[Tuple[str, int]]:
        """Count games by status."""
        from sqlalchemy import func
        return self.db.query(
            Game.status,
            func.count(Game.id)
        ).group_by(Game.status).all()
