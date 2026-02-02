"""
Prediction Repository for NBA prediction data access.

This repository encapsulates all database queries related to predictions,
providing a clean interface for services and API routes.

Usage:
    repo = PredictionRepository(db)
    predictions = repo.find_by_player(player_id)
    top_picks = repo.find_top_picks(min_confidence=0.70)
    accuracy = repo.get_accuracy_stats()
"""
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import or_, and_, desc, func, case

from app.models import Prediction, Game
from app.repositories.base import BaseRepository


class PredictionRepository(BaseRepository[Prediction]):
    """Repository for NBA prediction data access."""

    def __init__(self, db):
        """Initialize the prediction repository."""
        super().__init__(Prediction, db)

    # ========================================================================
    # Player-based Queries
    # ========================================================================

    def find_by_player(
        self,
        player_id: str,
        stat_type: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Prediction]:
        """
        Find predictions for a specific player.

        Args:
            player_id: Player ID
            stat_type: Optional stat type filter
            limit: Maximum number of predictions

        Returns:
            List of predictions for the player
        """
        query = self.db.query(Prediction).filter(
            Prediction.player_id == player_id
        )
        if stat_type:
            query = query.filter(Prediction.stat_type == stat_type)
        query = query.order_by(desc(Prediction.created_at))
        if limit:
            query = query.limit(limit)
        return query.all()

    def find_by_player_and_game(
        self,
        player_id: str,
        game_id: str
    ) -> List[Prediction]:
        """Find all predictions for a player in a specific game."""
        return self.db.query(Prediction).filter(
            Prediction.player_id == player_id,
            Prediction.game_id == game_id
        ).all()

    def find_latest_for_player(
        self,
        player_id: str,
        stat_type: Optional[str] = None
    ) -> Optional[Prediction]:
        """Find the most recent prediction for a player."""
        query = self.db.query(Prediction).filter(
            Prediction.player_id == player_id
        )
        if stat_type:
            query = query.filter(Prediction.stat_type == stat_type)
        return query.order_by(desc(Prediction.created_at)).first()

    # ========================================================================
    # Game-based Queries
    # ========================================================================

    def find_by_game(
        self,
        game_id: str,
        stat_type: Optional[str] = None,
        min_confidence: Optional[float] = None
    ) -> List[Prediction]:
        """
        Find predictions for a specific game.

        Args:
            game_id: Game ID
            stat_type: Optional stat type filter
            min_confidence: Minimum confidence threshold

        Returns:
            List of predictions for the game
        """
        query = self.db.query(Prediction).filter(
            Prediction.game_id == game_id
        )
        if stat_type:
            query = query.filter(Prediction.stat_type == stat_type)
        if min_confidence is not None:
            query = query.filter(Prediction.confidence >= min_confidence)
        return query.order_by(desc(Prediction.confidence)).all()

    def find_by_game_with_odds(
        self,
        game_id: str
    ) -> List[Prediction]:
        """Find predictions for a game that have odds data."""
        return self.db.query(Prediction).filter(
            Prediction.game_id == game_id,
            Prediction.over_price.isnot(None)
        ).all()

    # ========================================================================
    # Confidence-based Queries
    # ========================================================================

    def find_by_confidence(
        self,
        min_confidence: float,
        max_confidence: Optional[float] = None,
        limit: Optional[int] = None
    ) -> List[Prediction]:
        """
        Find predictions within a confidence range.

        Args:
            min_confidence: Minimum confidence
            max_confidence: Optional maximum confidence
            limit: Maximum number of predictions

        Returns:
            List of predictions
        """
        query = self.db.query(Prediction).filter(
            Prediction.confidence >= min_confidence
        )
        if max_confidence is not None:
            query = query.filter(Prediction.confidence <= max_confidence)
        query = query.order_by(desc(Prediction.confidence))
        if limit:
            query = query.limit(limit)
        return query.all()

    def find_top_picks(
        self,
        min_confidence: float = 0.60,
        days_ahead: int = 1,
        limit: int = 10
    ) -> List[Prediction]:
        """
        Find top picks for upcoming games.

        Args:
            min_confidence: Minimum confidence threshold
            days_ahead: How many days ahead to look
            limit: Maximum number of predictions

        Returns:
            List of top pick predictions
        """
        from datetime import timezone

        try:
            utc = timezone.utc
        except AttributeError:
            from datetime import timezone as tz
            utc = tz.utc

        now = datetime.now(utc).replace(tzinfo=None)
        end_date = now + timedelta(days=days_ahead)

        return self.db.query(Prediction).join(Game).filter(
            Prediction.confidence >= min_confidence,
            Game.game_date >= now,
            Game.game_date <= end_date
        ).order_by(desc(Prediction.confidence)).limit(limit).all()

    # ========================================================================
    # Stat Type Queries
    # ========================================================================

    def find_by_stat_type(
        self,
        stat_type: str,
        days_back: int = 7,
        limit: Optional[int] = None
    ) -> List[Prediction]:
        """Find predictions by stat type."""
        from datetime import timezone

        try:
            utc = timezone.utc
        except AttributeError:
            from datetime import timezone as tz
            utc = tz.utc

        cutoff = datetime.now(utc).replace(tzinfo=None) - timedelta(days=days_back)

        query = self.db.query(Prediction).filter(
            Prediction.stat_type == stat_type,
            Prediction.created_at >= cutoff
        ).order_by(desc(Prediction.created_at))
        if limit:
            query = query.limit(limit)
        return query.all()

    def get_stat_type_counts(
        self,
        days_back: int = 30
    ) -> List[Tuple[str, int]]:
        """Get prediction counts grouped by stat type."""
        from datetime import timezone

        try:
            utc = timezone.utc
        except AttributeError:
            from datetime import timezone as tz
            utc = tz.utc

        cutoff = datetime.now(utc).replace(tzinfo=None) - timedelta(days=days_back)

        return self.db.query(
            Prediction.stat_type,
            func.count(Prediction.id)
        ).filter(
            Prediction.created_at >= cutoff
        ).group_by(Prediction.stat_type).order_by(
            desc(func.count(Prediction.id))
        ).all()

    # ========================================================================
    # Recommendation Queries
    # ========================================================================

    def find_by_recommendation(
        self,
        recommendation: str,
        days_back: int = 7,
        limit: Optional[int] = None
    ) -> List[Prediction]:
        """Find predictions by recommendation (OVER/UNDER)."""
        from datetime import timezone

        try:
            utc = timezone.utc
        except AttributeError:
            from datetime import timezone as tz
            utc = tz.utc

        cutoff = datetime.now(utc).replace(tzinfo=None) - timedelta(days=days_back)

        query = self.db.query(Prediction).filter(
            Prediction.recommendation == recommendation.upper(),
            Prediction.created_at >= cutoff
        ).order_by(desc(Prediction.confidence))
        if limit:
            query = query.limit(limit)
        return query.all()

    # ========================================================================
    # Odds Queries
    # ========================================================================

    def find_with_odds(
        self,
        days_back: int = 1,
        bookmaker: Optional[str] = None
    ) -> List[Prediction]:
        """Find predictions that have odds data."""
        from datetime import timezone

        try:
            utc = timezone.utc
        except AttributeError:
            from datetime import timezone as tz
            utc = tz.utc

        cutoff = datetime.now(utc).replace(tzinfo=None) - timedelta(days=days_back)

        query = self.db.query(Prediction).filter(
            Prediction.over_price.isnot(None),
            Prediction.created_at >= cutoff
        )
        if bookmaker:
            query = query.filter(Prediction.bookmaker_name == bookmaker)
        return query.order_by(desc(Prediction.created_at)).all()

    def find_without_odds(
        self,
        hours_ahead: int = 24
    ) -> List[Prediction]:
        """Find upcoming predictions without odds data."""
        from datetime import timezone

        try:
            utc = timezone.utc
        except AttributeError:
            from datetime import timezone as tz
            utc = tz.utc

        cutoff = datetime.now(utc).replace(tzinfo=None) + timedelta(hours=hours_ahead)

        return self.db.query(Prediction).join(Game).filter(
            Prediction.over_price.is_(None),
            Game.game_date >= datetime.now(utc).replace(tzinfo=None),
            Game.game_date <= cutoff
        ).all()

    # ========================================================================
    # Resolution Queries
    # ========================================================================

    def find_unresolved(
        self,
        days_back: int = 7
    ) -> List[Prediction]:
        """Find predictions that haven't been resolved yet."""
        from datetime import timezone

        try:
            utc = timezone.utc
        except AttributeError:
            from datetime import timezone as tz
            utc = tz.utc

        cutoff = datetime.now(utc).replace(tzinfo=None) - timedelta(days=days_back)

        return self.db.query(Prediction).join(Game).filter(
            Prediction.was_correct.is_(None),
            Game.game_date < cutoff
        ).all()

    def find_resolved(
        self,
        days_back: int = 30,
        limit: Optional[int] = None
    ) -> List[Prediction]:
        """Find predictions that have been resolved."""
        from datetime import timezone

        try:
            utc = timezone.utc
        except AttributeError:
            from datetime import timezone as tz
            utc = tz.utc

        cutoff = datetime.now(utc).replace(tzinfo=None) - timedelta(days=days_back)

        query = self.db.query(Prediction).filter(
            Prediction.was_correct.isnot(None),
            Prediction.created_at >= cutoff
        ).order_by(desc(Prediction.created_at))
        if limit:
            query = query.limit(limit)
        return query.all()

    # ========================================================================
    # Accuracy Statistics
    # ========================================================================

    def get_accuracy_stats(
        self,
        days_back: int = 30,
        stat_type: Optional[str] = None,
        bookmaker: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get accuracy statistics for predictions.

        Args:
            days_back: How many days back to analyze
            stat_type: Optional stat type filter
            bookmaker: Optional bookmaker filter

        Returns:
            Dictionary with accuracy stats
        """
        from datetime import timezone

        try:
            utc = timezone.utc
        except AttributeError:
            from datetime import timezone as tz
            utc = tz.utc

        cutoff = datetime.now(utc).replace(tzinfo=None) - timedelta(days=days_back)

        query = self.db.query(Prediction).filter(
            Prediction.was_correct.isnot(None),
            Prediction.created_at >= cutoff
        )
        if stat_type:
            query = query.filter(Prediction.stat_type == stat_type)
        if bookmaker:
            query = query.filter(Prediction.bookmaker_name == bookmaker)

        total = query.count()
        if total == 0:
            return {
                "total": 0,
                "correct": 0,
                "accuracy": 0.0,
                "by_stat_type": {},
                "by_recommendation": {}
            }

        correct = query.filter(Prediction.was_correct == True).count()

        # By stat type
        by_stat = {}
        for stat in ["points", "rebounds", "assists", "threes"]:
            stat_query = query.filter(Prediction.stat_type == stat)
            stat_total = stat_query.count()
            if stat_total > 0:
                stat_correct = stat_query.filter(Prediction.was_correct == True).count()
                by_stat[stat] = {
                    "total": stat_total,
                    "correct": stat_correct,
                    "accuracy": stat_correct / stat_total
                }

        # By recommendation
        by_rec = {}
        for rec in ["OVER", "UNDER"]:
            rec_query = query.filter(Prediction.recommendation == rec)
            rec_total = rec_query.count()
            if rec_total > 0:
                rec_correct = rec_query.filter(Prediction.was_correct == True).count()
                by_rec[rec] = {
                    "total": rec_total,
                    "correct": rec_correct,
                    "accuracy": rec_correct / rec_total
                }

        return {
            "total": total,
            "correct": correct,
            "accuracy": correct / total,
            "by_stat_type": by_stat,
            "by_recommendation": by_rec
        }

    # ========================================================================
    # Advanced Queries
    # ========================================================================

    def exists_for_player_game_stat(
        self,
        player_id: str,
        game_id: str,
        stat_type: str
    ) -> bool:
        """Check if a prediction exists for a player/game/stat combination."""
        return self.exists_where(
            Prediction.player_id == player_id,
            Prediction.game_id == game_id,
            Prediction.stat_type == stat_type
        )

    def find_for_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        min_confidence: Optional[float] = None
    ) -> List[Prediction]:
        """Find predictions within a date range."""
        query = self.db.query(Prediction).join(Game).filter(
            Game.game_date >= start_date,
            Game.game_date <= end_date
        )
        if min_confidence is not None:
            query = query.filter(Prediction.confidence >= min_confidence)
        return query.order_by(desc(Prediction.confidence)).all()

    def get_confidence_distribution(
        self,
        days_back: int = 30
    ) -> List[Tuple[str, int]]:
        """Get prediction counts by confidence ranges."""
        from datetime import timezone

        try:
            utc = timezone.utc
        except AttributeError:
            from datetime import timezone as tz
            utc = tz.utc

        cutoff = datetime.now(utc).replace(tzinfo=None) - timedelta(days=days_back)

        return self.db.query(
            case(
                (Prediction.confidence >= 0.80, "80-100%"),
                (Prediction.confidence >= 0.70, "70-79%"),
                (Prediction.confidence >= 0.60, "60-69%"),
                else_="50-59%"
            ),
            func.count(Prediction.id)
        ).filter(
            Prediction.created_at >= cutoff
        ).group_by(
            case(
                (Prediction.confidence >= 0.80, "80-100%"),
                (Prediction.confidence >= 0.70, "70-79%"),
                (Prediction.confidence >= 0.60, "60-69%"),
                else_="50-59%"
            )
        ).all()

    # ========================================================================
    # Batch Operations
    # ========================================================================

    def bulk_create_for_game(
        self,
        game_id: str,
        predictions: List[Dict[str, Any]]
    ) -> List[Prediction]:
        """
        Bulk create predictions for a game.

        Args:
            game_id: Game ID
            predictions: List of prediction data dictionaries

        Returns:
            List of created predictions
        """
        for pred in predictions:
            pred['game_id'] = game_id
        return self.bulk_create(predictions)

    def delete_for_game(self, game_id: str) -> int:
        """
        Delete all predictions for a game.

        Args:
            game_id: Game ID

        Returns:
            Number of predictions deleted
        """
        count = self.db.query(Prediction).filter(
            Prediction.game_id == game_id
        ).count()
        self.db.query(Prediction).filter(
            Prediction.game_id == game_id
        ).delete()
        return count
