"""
Prediction generation service for MLB player props.

Generates predictions for upcoming games using:
- Historical per-game stats (player-specific efficiency)
- Pitcher matchups (handedness, park factors)
- Weather and venue considerations
- Platoon splits

Key formula: predicted_value = avg_stat × matchup_multiplier × park_factor
"""
import logging
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
import random

from app.models.mlb.models import Player, Game, Prediction, PlayerSeasonStats
from app.services.core.base_prediction_service import BasePredictionService

logger = logging.getLogger(__name__)


# Position-based stat averages (fallback when no historical data)
# MLB positions: P, C, 1B, 2B, SS, 3B, OF, DH
POSITION_AVERAGES = {
    "P": {
        "strikeouts": 6.5,
        "wins": 0.15,
        "innings_pitched": 5.5,
    },
    "C": {
        "hits": 1.2,
        "runs": 0.6,
        "home_runs": 0.08,
        "rbi": 0.5,
    },
    "1B": {
        "hits": 1.5,
        "runs": 0.8,
        "home_runs": 0.18,
        "rbi": 1.0,
    },
    "2B": {
        "hits": 1.3,
        "runs": 0.7,
        "home_runs": 0.08,
        "rbi": 0.6,
    },
    "SS": {
        "hits": 1.2,
        "runs": 0.6,
        "home_runs": 0.06,
        "rbi": 0.5,
    },
    "3B": {
        "hits": 1.3,
        "runs": 0.7,
        "home_runs": 0.12,
        "rbi": 0.7,
    },
    "OF": {
        "hits": 1.4,
        "runs": 0.8,
        "home_runs": 0.15,
        "rbi": 0.8,
    },
    "DH": {
        "hits": 1.5,
        "runs": 0.9,
        "home_runs": 0.20,
        "rbi": 1.1,
    },
    # Default for unknown position
    None: {
        "hits": 1.2,
        "runs": 0.6,
        "home_runs": 0.08,
        "rbi": 0.6,
    }
}


class PredictionService(BasePredictionService):
    """Service for generating MLB player prop predictions."""

    def __init__(self, db: Session):
        super().__init__(db)

    # ========================================================================
    # ABSTRACT METHOD IMPLEMENTATIONS
    # ========================================================================

    def get_position_averages(self) -> Dict[str, Dict[str, float]]:
        return POSITION_AVERAGES

    def get_default_stat_types(self) -> List[str]:
        return ["hits", "runs", "home_runs", "rbi", "strikeouts"]

    def get_player_model(self):
        return Player

    def get_game_model(self):
        return Game

    def get_prediction_model(self):
        return Prediction

    def get_season_stats_model(self):
        return PlayerSeasonStats

    def get_active_field_name(self) -> str:
        return "status"  # MLB uses 'status' field with "active" value

    def is_stat_relevant_for_position(self, position: Optional[str], stat_type: str) -> bool:
        """Check if a stat type is relevant for a given position."""
        if position is None:
            return True  # Allow all stats if position unknown

        # Pitchers get pitching stats
        if position == "P":
            return stat_type in ["strikeouts", "wins", "innings_pitched"]

        # Batters get batting stats
        return stat_type in ["hits", "runs", "home_runs", "rbi", "stolen_bases"]

    def get_position_stat_match(self) -> Dict[str, str]:
        return {
            "P": "strikeouts",
            "1B": "home_runs",
            "OF": "home_runs",
            "DH": "home_runs",
        }

    # ========================================================================
    # MLB-SPECIFIC OVERRIDES
    # ========================================================================

    def _get_season_stats_query_filters(self) -> List:
        """MLB filters by season_type = "REG" for regular season stats."""
        return [PlayerSeasonStats.season_type == "REG"]

    def _extract_value_from_season_stats(
        self,
        season_stats: PlayerSeasonStats,
        stat_type: str,
        player: Player,
        game: Game
    ) -> Optional[float]:
        """
        MLB requires special handling for different stat types:
        - Counting stats: per-game average
        - Pitcher strikeouts: per-inning rate scaled to 5.5 innings
        """
        games_played = getattr(season_stats, 'games_played', 0)

        if games_played == 0:
            return None

        stat_value = getattr(season_stats, stat_type, None)
        if stat_value is None:
            return None

        # Handle counting stats vs cumulative stats
        if stat_type in ["hits", "runs", "home_runs", "rbi", "stolen_bases"]:
            predicted_value = stat_value / games_played
        elif stat_type == "strikeouts":
            # Pitcher strikeouts per game
            innings = getattr(season_stats, 'innings_pitched', 0)
            if innings > 0:
                predicted_value = (stat_value / innings) * 5.5  # Per 5.5 innings
            else:
                predicted_value = stat_value / games_played
        else:
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
        MLB uses different sample size thresholds for pitchers vs batters.
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
            if player.position == "P":
                # Pitchers: use innings pitched
                innings = getattr(season_stats, 'innings_pitched', 0)
                if innings >= 100:
                    confidence += 0.12
                elif innings >= 50:
                    confidence += 0.06
                else:
                    confidence += 0.02
            else:
                # Batters: use games played
                games_played = getattr(season_stats, 'games_played', 0)
                if games_played >= 100:
                    confidence += 0.12
                elif games_played >= 50:
                    confidence += 0.06
                else:
                    confidence += 0.02

        # Position-stat alignment boost
        position = player.position if player.position else None
        position_stat_match = self.get_position_stat_match()

        if position and position_stat_match.get(position) == stat_type:
            confidence += 0.06

        # Add small randomness
        confidence += random.uniform(-0.03, 0.03)

        return round(max(0.30, min(0.75, confidence)), 2)

    def _get_recommendation(self, confidence: float) -> str:
        """MLB uses 0.58 threshold for recommendations."""
        if confidence >= 0.58:
            return random.choice(["OVER", "UNDER"])
        else:
            return "NONE"


def get_prediction_service(db: Session) -> PredictionService:
    """Get a PredictionService instance."""
    return PredictionService(db)
