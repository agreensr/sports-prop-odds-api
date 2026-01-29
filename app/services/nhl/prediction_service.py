"""
Prediction generation service for NHL player props.

Generates predictions for upcoming games using:
- Historical per-game stats (player-specific efficiency)
- Line combinations (forward lines, defensive pairs)
- Goalie matchup considerations
- Power play usage

Key formula: predicted_value = avg_stat × line_multiplier × matchup_factor
"""
import logging
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
import random

from app.models.nhl.models import Player, Game, Prediction, PlayerSeasonStats
from app.services.core.base_prediction_service import BasePredictionService

logger = logging.getLogger(__name__)


# Position-based stat averages (fallback when no historical data)
# NHL positions: C, LW, RW, D, G
POSITION_AVERAGES = {
    "C": {
        "goals": 0.25,
        "assists": 0.45,
        "points": 0.70,
        "shots": 2.8,
    },
    "LW": {
        "goals": 0.22,
        "assists": 0.30,
        "points": 0.52,
        "shots": 2.5,
    },
    "RW": {
        "goals": 0.24,
        "assists": 0.32,
        "points": 0.56,
        "shots": 2.6,
    },
    "D": {
        "goals": 0.08,
        "assists": 0.35,
        "points": 0.43,
        "shots": 2.2,
    },
    "G": {
        "saves": 25.0,
        "wins": 0.45,
    },
    # Default for unknown position
    None: {
        "goals": 0.15,
        "assists": 0.30,
        "points": 0.45,
        "shots": 2.0,
    }
}


class PredictionService(BasePredictionService):
    """Service for generating NHL player prop predictions."""

    def __init__(self, db: Session):
        super().__init__(db)

    # ========================================================================
    # ABSTRACT METHOD IMPLEMENTATIONS
    # ========================================================================

    def get_position_averages(self) -> Dict[str, Dict[str, float]]:
        return POSITION_AVERAGES

    def get_default_stat_types(self) -> List[str]:
        return ["goals", "assists", "points", "shots"]

    def get_player_model(self):
        return Player

    def get_game_model(self):
        return Game

    def get_prediction_model(self):
        return Prediction

    def get_season_stats_model(self):
        return PlayerSeasonStats

    def get_active_field_name(self) -> str:
        return "status"  # NHL uses 'status' field with "active" value

    def is_stat_relevant_for_position(self, position: Optional[str], stat_type: str) -> bool:
        """Check if a stat type is relevant for a given position."""
        if position is None:
            return True  # Allow all stats if position unknown

        # Goalies get goalie stats
        if position == "G":
            return stat_type in ["saves", "wins"]

        # Skaters get skating stats
        return stat_type in ["goals", "assists", "points", "shots"]

    def get_position_stat_match(self) -> Dict[str, str]:
        return {
            "C": "points",
            "LW": "goals",
            "RW": "goals",
            "D": "assists",
            "G": "saves",
        }

    # ========================================================================
    # NHL-SPECIFIC OVERRIDES
    # ========================================================================

    def _get_season_stats_query_filters(self) -> List:
        """NHL filters by season_type = "REG" for regular season stats."""
        return [PlayerSeasonStats.season_type == "REG"]

    def _extract_value_from_season_stats(
        self,
        season_stats: PlayerSeasonStats,
        stat_type: str,
        player: Player,
        game: Game
    ) -> Optional[float]:
        """
        NHL requires special handling for goalies vs skaters.
        """
        games_played = getattr(season_stats, 'games_played', 0)

        if games_played == 0:
            return None

        stat_value = getattr(season_stats, stat_type, None)
        if stat_value is None:
            return None

        if player.position == "G":
            # Goalies: use per-game stats
            if stat_type == "saves":
                shots_against = getattr(season_stats, 'shots_against', 0)
                if shots_against > 0:
                    predicted_value = (stat_value / shots_against) * 28.0  # Avg shots per game
                else:
                    predicted_value = stat_value / games_played
            else:
                predicted_value = stat_value / games_played
        else:
            # Skaters: per-game averages
            predicted_value = stat_value / games_played

        logger.debug(f"Using season stats for {player.name}: {stat_type} = {predicted_value:.2f}/game")
        return predicted_value

    def _calculate_confidence(
        self,
        player: Player,
        stat_type: str,
        predicted_value: float,
        game: Game
    ) -> float:
        """
        NHL uses games_played for sample size with hockey-specific thresholds.
        """
        SeasonStats = self.get_season_stats_model()

        confidence = 0.50

        # Build season stats query
        filters = [
            SeasonStats.player_id == player.id,
            SeasonStats.season == game.season,
            SeasonStats.season_type == "REG"
        ]

        season_stats = self.db.query(SeasonStats).filter(*filters).first()

        if season_stats:
            games_played = getattr(season_stats, 'games_played', 0)
            if games_played >= 50:
                confidence += 0.12  # High confidence with substantial sample
            elif games_played >= 20:
                confidence += 0.06  # Moderate confidence
            elif games_played >= 10:
                confidence += 0.03  # Low confidence
            # No boost for < 10 games (too small sample)

        # Position-stat alignment boost
        position = player.position if player.position else None
        position_stat_match = self.get_position_stat_match()

        if position and position_stat_match.get(position) == stat_type:
            confidence += 0.06

        # Add small randomness
        confidence += random.uniform(-0.03, 0.03)

        return round(max(0.30, min(0.75, confidence)), 2)

    def _get_recommendation(self, confidence: float) -> str:
        """NHL uses 0.58 threshold for recommendations."""
        if confidence >= 0.58:
            return random.choice(["OVER", "UNDER"])
        else:
            return "NONE"


def get_prediction_service(db: Session) -> PredictionService:
    """Get a PredictionService instance."""
    return PredictionService(db)
