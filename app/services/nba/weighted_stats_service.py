"""
Exponentially Weighted Moving Average (EWMA) Service.

Recent games are more predictive than older games. EWMA gives
exponentially decaying weights to recent performance.

Formula:
    EWMA_t = λ × value_t + (1-λ) × EWMA_{t-1}

Where:
    λ = decay factor (higher = more weight on recent games)
    value_t = stat value in game t

Decay factors by stat type:
- threes: 0.20 (shooting is volatile, recent form critical)
- assists: 0.18 (role-dependent but can trend)
- points: 0.15 (moderate decay, scoring is relatively stable)
- rebounds: 0.12 (low decay, rebounding is very consistent)
"""
import logging
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

try:
    from datetime import UTC
except ImportError:
    from datetime import timezone
    UTC = timezone.utc

from app.models import PlayerStats

logger = logging.getLogger(__name__)


class WeightedStatsService:
    """Calculate exponentially weighted moving averages for player stats."""

    # Stat-specific decay factors (higher = more weight on recent games)
    DECAY_FACTORS = {
        "points": 0.15,
        "rebounds": 0.12,
        "assists": 0.18,
        "threes": 0.20
    }

    def __init__(self, db: Session, default_games: int = 10):
        """
        Initialize EWMA service.

        Args:
            db: SQLAlchemy database session
            default_games: Default number of games to analyze
        """
        self.db = db
        self.default_games = default_games
        self._cache = {}

    def calculate_ewma(
        self,
        player_id: str,
        stat_type: str,
        games_back: int = 10
    ) -> Dict[str, float]:
        """
        Calculate EWMA for a player's stat.

        Args:
            player_id: Database UUID of the player
            stat_type: Stat type (points, rebounds, assists, threes)
            games_back: Number of recent games to analyze

        Returns:
            Dict with:
            - ewma: Exponentially weighted moving average
            - simple_avg: Simple arithmetic mean
            - trend: Trend indicator (-1.0 to 1.0, positive = improving)
            - sample_size: Number of games analyzed
        """
        # Map stat_type to column
        stat_column = {
            "points": "points",
            "rebounds": "rebounds",
            "assists": "assists",
            "threes": "threes"
        }.get(stat_type)

        if not stat_column:
            logger.warning(f"Unknown stat_type: {stat_type}")
            return {"ewma": 0, "simple_avg": 0, "trend": 0, "sample_size": 0}

        # Get recent games
        cutoff = datetime.now(UTC) - timedelta(days=90)  # 90 day window
        stats = self.db.query(PlayerStats).filter(
            PlayerStats.player_id == player_id,
            PlayerStats.created_at >= cutoff
        ).order_by(desc(PlayerStats.created_at)).limit(games_back).all()

        if not stats:
            logger.debug(f"No stats found for player {player_id}, stat {stat_type}")
            return {"ewma": 0, "simple_avg": 0, "trend": 0, "sample_size": 0}

        # Extract values (most recent first from query)
        values = [getattr(s, stat_column) or 0 for s in stats]
        # Reverse to get oldest to newest for EWMA calculation
        values.reverse()

        if len(values) < 2:
            # Need at least 2 data points for meaningful EWMA
            return {
                "ewma": values[0] if values else 0,
                "simple_avg": values[0] if values else 0,
                "trend": 0,
                "sample_size": len(values)
            }

        # Calculate EWMA
        decay = self.DECAY_FACTORS.get(stat_type, 0.15)
        ewma = values[0]  # Initialize with first value
        for val in values[1:]:
            ewma = decay * val + (1 - decay) * ewma

        # Simple average
        simple_avg = statistics.mean(values)

        # Trend: compare second half vs first half
        # Positive trend = recent performance > earlier performance
        mid = len(values) // 2
        early_avg = statistics.mean(values[:mid]) if mid > 0 else simple_avg
        late_avg = statistics.mean(values[mid:]) if len(values) > mid else simple_avg
        trend = (late_avg - early_avg) / max(early_avg, 1.0)

        return {
            "ewma": round(ewma, 2),
            "simple_avg": round(simple_avg, 2),
            "trend": round(trend, 3),
            "sample_size": len(values)
        }

    def get_ewma_multiplier(
        self,
        player_id: str,
        stat_type: str,
        games_back: int = 10
    ) -> float:
        """
        Get EWMA-based multiplier for prediction adjustment.

        Compares EWMA to simple average:
        - EWMA > simple_avg: Recent form is strong (> 1.0 multiplier)
        - EWMA < simple_avg: Recent form is weak (< 1.0 multiplier)
        - EWMA ≈ simple_avg: Stable form (≈ 1.0 multiplier)

        Args:
            player_id: Database UUID of the player
            stat_type: Stat type
            games_back: Number of games to analyze

        Returns:
            Multiplier (typically 0.90 to 1.10)
        """
        result = self.calculate_ewma(player_id, stat_type, games_back)

        if result["sample_size"] < 3:
            return 1.0  # Not enough data

        ewma = result["ewma"]
        simple_avg = result["simple_avg"]

        if simple_avg == 0:
            return 1.0

        # Calculate ratio
        ratio = ewma / simple_avg

        # Clamp to reasonable range (±10% adjustment)
        return max(0.90, min(1.10, round(ratio, 3)))

    def get_trend_indicator(
        self,
        player_id: str,
        stat_type: str,
        games_back: int = 10
    ) -> str:
        """
        Get human-readable trend indicator.

        Args:
            player_id: Database UUID of the player
            stat_type: Stat type
            games_back: Number of games to analyze

        Returns:
            Trend indicator: "rising", "stable", "falling"
        """
        result = self.calculate_ewma(player_id, stat_type, games_back)
        trend = result.get("trend", 0)

        if trend > 0.05:
            return "rising"
        elif trend < -0.05:
            return "falling"
        else:
            return "stable"

    def batch_calculate_ewma(
        self,
        player_ids: List[str],
        stat_types: List[str],
        games_back: int = 10
    ) -> Dict[str, Dict[str, Dict]]:
        """
        Calculate EWMA for multiple players and stat types.

        Useful for batch prediction generation.

        Args:
            player_ids: List of player database UUIDs
            stat_types: List of stat types to analyze
            games_back: Number of games to analyze

        Returns:
            Nested dict:
            {
                "player_id_1": {
                    "points": {"ewma": 22.5, "simple_avg": 21.2, "trend": 0.05, ...},
                    "assists": {...}
                },
                ...
            }
        """
        results = {}

        for player_id in player_ids:
            results[player_id] = {}
            for stat_type in stat_types:
                results[player_id][stat_type] = self.calculate_ewma(
                    player_id=player_id,
                    stat_type=stat_type,
                    games_back=games_back
                )

        return results
