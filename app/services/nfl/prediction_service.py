"""
Prediction generation service for NFL player props.

Generates predictions for upcoming games using:
- Historical per-game stats (player-specific efficiency)
- Game script projections (expected point totals, team totals)
- Injury status adjustments
- Matchup considerations

Key formula: predicted_value = avg_stat × usage_adjustment × matchup_multiplier
"""
import logging
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
import random

from app.models.nfl.models import Player, Game, Prediction, PlayerSeasonStats
from app.services.core.base_prediction_service import BasePredictionService

logger = logging.getLogger(__name__)


# Position-based stat averages (fallback when no historical data)
# NFL positions: QB, RB, WR, TE, K, DST
POSITION_AVERAGES = {
    "QB": {
        "passing_yards": 240.0,
        "passing_touchdowns": 1.8,
        "passing_completions": 22.0,
        "passing_attempts": 35.0,
        "rushing_yards": 15.0,
    },
    "RB": {
        "rushing_yards": 55.0,
        "rushing_touchdowns": 0.4,
        "rushing_attempts": 14.0,
        "receptions": 2.5,
        "receiving_yards": 20.0,
    },
    "WR": {
        "receptions": 5.0,
        "receiving_yards": 65.0,
        "receiving_touchdowns": 0.5,
        "targets": 8.0,
    },
    "TE": {
        "receptions": 4.0,
        "receiving_yards": 45.0,
        "receiving_touchdowns": 0.4,
        "targets": 6.0,
    },
    # Default for unknown position
    None: {
        "receptions": 3.0,
        "receiving_yards": 35.0,
        "rushing_yards": 20.0,
    }
}


class PredictionService(BasePredictionService):
    """Service for generating NFL player prop predictions."""

    def __init__(self, db: Session):
        super().__init__(db)

    # ========================================================================
    # ABSTRACT METHOD IMPLEMENTATIONS
    # ========================================================================

    def get_position_averages(self) -> Dict[str, Dict[str, float]]:
        return POSITION_AVERAGES

    def get_default_stat_types(self) -> List[str]:
        return [
            "passing_yards", "rushing_yards", "receptions",
            "receiving_yards", "passing_touchdowns"
        ]

    def get_player_model(self):
        return Player

    def get_game_model(self):
        return Game

    def get_prediction_model(self):
        return Prediction

    def get_season_stats_model(self):
        return PlayerSeasonStats

    def get_active_field_name(self) -> str:
        return "status"  # NFL uses 'status' field with "active" value

    def is_stat_relevant_for_position(self, position: Optional[str], stat_type: str) -> bool:
        """Check if a stat type is relevant for a given position."""
        if position is None:
            return True  # Allow all stats if position unknown

        relevant_stats = {
            "QB": ["passing_yards", "passing_touchdowns", "passing_completions",
                   "passing_attempts", "rushing_yards"],
            "RB": ["rushing_yards", "rushing_touchdowns", "rushing_attempts",
                   "receptions", "receiving_yards"],
            "WR": ["receptions", "receiving_yards", "receiving_touchdowns", "targets"],
            "TE": ["receptions", "receiving_yards", "receiving_touchdowns", "targets"],
            "K": ["field_goals_made", "extra_points_made"],
        }

        return stat_type in relevant_stats.get(position, [])

    def get_position_stat_match(self) -> Dict[str, str]:
        return {
            "QB": "passing_yards",
            "RB": "rushing_yards",
            "WR": "receiving_yards",
            "TE": "receiving_yards",
        }

    # ========================================================================
    # NFL-SPECIFIC OVERRIDES
    # ========================================================================

    def _extract_value_from_season_stats(
        self,
        season_stats: PlayerSeasonStats,
        stat_type: str,
        player: Player,
        game: Game
    ) -> Optional[float]:
        """
        NFL uses cumulative season stats directly - no per-game conversion needed.
        """
        stat_value = getattr(season_stats, stat_type, None)
        if stat_value is not None:
            logger.debug(f"Using season stats for {player.name}: {stat_type} = {stat_value}")
            return stat_value
        return None

    def _get_recommendation(self, confidence: float) -> str:
        """NFL uses 0.58 threshold for recommendations."""
        if confidence >= 0.58:
            return random.choice(["OVER", "UNDER"])
        else:
            return "NONE"


def get_prediction_service(db: Session) -> PredictionService:
    """Get a PredictionService instance."""
    return PredictionService(db)
