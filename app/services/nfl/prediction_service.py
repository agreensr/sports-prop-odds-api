"""
Prediction generation service for NFL player props.

Generates predictions for upcoming games using:
- Historical per-game stats (player-specific efficiency)
- Game script projections (expected point totals, team totals)
- Injury status adjustments
- Matchup considerations

Key formula: predicted_value = avg_stat × usage_adjustment × matchup_multiplier

CONFIG MODE:
This service uses the unified config mode by passing sport_id="nfl" to the base class.
This eliminates the need for most abstract method implementations as they are loaded
from the sport configuration in app/services/core/sport_adapter/config.py.
"""
import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.models import Player, Game, Prediction, PlayerSeasonStats
from app.services.core.base_prediction_service import BasePredictionService

logger = logging.getLogger(__name__)


class PredictionService(BasePredictionService):
    """
    Service for generating NFL player prop predictions.

    Uses config mode: sport_id="nfl" is passed to parent to load all
    sport-specific configuration from the central config.
    """

    def __init__(self, db: Session):
        """
        Initialize the NFL prediction service.

        Args:
            db: SQLAlchemy database session
        """
        # Pass sport_id to enable config mode - loads from:
        # app/services/core/sport_adapter/config.py -> NFL_CONFIG
        super().__init__(db, sport_id="nfl")

    # ========================================================================
    # MODEL REFERENCES (Required for non-unified models)
    # ========================================================================
    # Note: These can be removed once fully migrated to unified models

    def get_player_model(self):
        return Player

    def get_game_model(self):
        return Game

    def get_prediction_model(self):
        return Prediction

    def get_season_stats_model(self):
        return PlayerSeasonStats

    # ========================================================================
    # NFL-SPECIFIC OVERRIDES
    # ========================================================================
    # The following are loaded from config when using config mode:
    # - get_position_averages() -> from NFL_POSITION_AVERAGES
    # - get_default_stat_types() -> from NFL_CONFIG.default_stat_types
    # - get_active_field_name() -> from NFL_CONFIG.active_field_is_boolean
    # - is_stat_relevant_for_position() -> from NFL_CONFIG.positions
    # - get_position_stat_match() -> from NFL_CONFIG.position_primary_stats
    # - _get_recommendation() threshold -> from NFL_CONFIG.recommendation_threshold
    # - _apply_variance() percent -> from NFL_CONFIG.variance_percent

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


def get_prediction_service(db: Session) -> PredictionService:
    """Get a PredictionService instance."""
    return PredictionService(db)
