"""
Volatility Service - Coefficient of Variation (CV) Analysis.

Higher volatility = less predictable = lower confidence.

The Coefficient of Variation (CV) measures relative variability:
    CV = standard_deviation / mean

CV Interpretation:
- CV < 0.20: Low volatility (consistent performance)
- CV 0.20-0.30: Medium volatility
- CV 0.30-0.40: High volatility
- CV > 0.40: Very high volatility (unpredictable)

Confidence Penalties:
- Low volatility (< 0.20): No penalty
- Medium volatility (0.20-0.30): -5% confidence
- High volatility (0.30-0.40): -10% confidence
- Very high volatility (> 0.40): -20% confidence
"""
import logging
import statistics
from datetime import timedelta
from typing import Dict
from sqlalchemy.orm import Session
from sqlalchemy import desc

try:
    from datetime import UTC
except ImportError:
    from datetime import timezone
    UTC = timezone.utc

from app.models.nba.models import PlayerStats

logger = logging.getLogger(__name__)


class VolatilityService:
    """Calculate coefficient of variation for player stats."""

    # CV thresholds for confidence penalties
    CV_PENALTIES = [
        (0.20, 0.00),    # Low volatility: no penalty
        (0.30, -0.05),   # Medium: -5%
        (0.40, -0.10),   # High: -10%
        (float('inf'), -0.20)  # Very high: -20%
    ]

    def __init__(self, db: Session):
        """
        Initialize volatility service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def calculate_cv(
        self,
        player_id: str,
        stat_type: str,
        games_back: int = 10
    ) -> Dict[str, float]:
        """
        Calculate coefficient of variation for a player's stat.

        Args:
            player_id: Database UUID of the player
            stat_type: Stat type (points, rebounds, assists, threes)
            games_back: Number of recent games to analyze

        Returns:
            Dict with:
            - cv: Coefficient of variation
            - std_dev: Standard deviation
            - mean: Mean value
            - volatility_level: Category (low, medium, high, very_high)
            - sample_size: Number of games analyzed
        """
        stat_column = {
            "points": "points",
            "rebounds": "rebounds",
            "assists": "assists",
            "threes": "threes"
        }.get(stat_type)

        if not stat_column:
            logger.warning(f"Unknown stat_type: {stat_type}")
            return {
                "cv": 0,
                "std_dev": 0,
                "mean": 0,
                "volatility_level": "unknown",
                "sample_size": 0
            }

        # Get recent stats
        cutoff = datetime.now(UTC) - timedelta(days=90)
        stats = self.db.query(PlayerStats).filter(
            PlayerStats.player_id == player_id,
            PlayerStats.created_at >= cutoff
        ).order_by(desc(PlayerStats.created_at)).limit(games_back).all()

        if len(stats) < 3:
            # Need at least 3 data points for meaningful CV
            return {
                "cv": 0,
                "std_dev": 0,
                "mean": 0,
                "volatility_level": "insufficient_data",
                "sample_size": len(stats)
            }

        values = [getattr(s, stat_column) or 0 for s in stats]

        try:
            mean = statistics.mean(values)
            std_dev = statistics.stdev(values) if len(values) > 1 else 0

            # Avoid division by zero
            cv = std_dev / max(mean, 1.0) if mean > 0 else 0

            # Determine volatility level
            if cv < 0.20:
                level = "low"
            elif cv < 0.30:
                level = "medium"
            elif cv < 0.40:
                level = "high"
            else:
                level = "very_high"

            return {
                "cv": round(cv, 3),
                "std_dev": round(std_dev, 2),
                "mean": round(mean, 2),
                "volatility_level": level,
                "sample_size": len(values)
            }

        except statistics.StatisticsError as e:
            logger.error(f"Statistics error for player {player_id}, stat {stat_type}: {e}")
            return {
                "cv": 0,
                "std_dev": 0,
                "mean": 0,
                "volatility_level": "error",
                "sample_size": len(values)
            }

    def get_confidence_penalty(
        self,
        cv: float,
        stat_type: str
    ) -> float:
        """
        Convert CV to confidence penalty.

        Higher CV = larger penalty.

        Args:
            cv: Coefficient of variation
            stat_type: Stat type (for potential stat-specific adjustments)

        Returns:
            Confidence penalty (negative value, e.g., -0.10 for -10%)
        """
        for threshold, penalty in self.CV_PENALTIES:
            if cv < threshold:
                return penalty
        return -0.20

    def get_adjusted_confidence(
        self,
        base_confidence: float,
        player_id: str,
        stat_type: str,
        games_back: int = 10
    ) -> float:
        """
        Apply volatility penalty to base confidence.

        Args:
            base_confidence: Initial confidence score (0.0 to 1.0)
            player_id: Database UUID of the player
            stat_type: Stat type
            games_back: Number of games to analyze

        Returns:
            Adjusted confidence score (0.0 to 1.0)
        """
        cv_data = self.calculate_cv(player_id, stat_type, games_back)
        penalty = self.get_confidence_penalty(cv_data["cv"], stat_type)

        adjusted = base_confidence + penalty

        # Clamp to valid range
        return max(0.25, min(0.85, adjusted))

    def batch_calculate_cv(
        self,
        player_ids: list,
        stat_types: list,
        games_back: int = 10
    ) -> Dict:
        """
        Calculate CV for multiple players and stat types.

        Args:
            player_ids: List of player database UUIDs
            stat_types: List of stat types
            games_back: Number of games to analyze

        Returns:
            Nested dict with CV data for all combinations
        """
        results = {}

        for player_id in player_ids:
            results[player_id] = {}
            for stat_type in stat_types:
                results[player_id][stat_type] = self.calculate_cv(
                    player_id=player_id,
                    stat_type=stat_type,
                    games_back=games_back
                )

        return results

    def get_volatility_report(
        self,
        player_id: str,
        games_back: int = 10
    ) -> Dict:
        """
        Get comprehensive volatility report for a player.

        Args:
            player_id: Database UUID of the player
            games_back: Number of games to analyze

        Returns:
            Dict with CV data for all stat types
        """
        stat_types = ["points", "rebounds", "assists", "threes"]
        report = {
            "player_id": player_id,
            "games_back": games_back,
            "volatility": {}
        }

        for stat_type in stat_types:
            report["volatility"][stat_type] = self.calculate_cv(
                player_id=player_id,
                stat_type=stat_type,
                games_back=games_back
            )

        return report
