"""
Prediction generation service for NBA player props.

Generates predictions for upcoming games using:
- Historical per-36 stats (player-specific efficiency)
- Projected minutes (lineups, injury context)
- Injury status adjustments
- Teammate injury boosts (usage opportunities)

Key formula: predicted_value = per_36_stat × (projected_minutes / 36)

Research-backed approach:
- Returning players maintain efficiency, only minutes restricted
- Source: https://www.jssm.org/volume24/iss2/cap/jssm-24-363.pdf

---
CONFIG MODE (New - Optional):
Instead of implementing abstract methods, you can pass sport_id:

    class PredictionService(BasePredictionService):
        def __init__(self, db: Session):
            super().__init__(db, sport_id="nba")  # Enables config mode
            # Now position averages, stat types, thresholds come from config
            # Only need to implement sport-specific business logic

This eliminates the need for:
- get_position_averages() (loaded from config)
- get_default_stat_types() (loaded from config)
- get_active_field_name() (loaded from config)
- is_stat_relevant_for_position() (loaded from config)
- get_position_stat_match() (loaded from config)
- _get_recommendation() threshold (loaded from config)
- _apply_variance() percent (loaded from config)
"""
import logging
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from app.models import Player, Game, Prediction, PlayerStats, PlayerSeasonStats
from app.services.core.base_prediction_service import BasePredictionService

logger = logging.getLogger(__name__)


# Position-based stat averages (fallback when no historical data)
# NOTE: These are now defined in app/services/core/sport_adapter/config.py
# When using config mode (pass sport_id="nba" to parent), this can be removed
POSITION_AVERAGES = {
    "PG": {"points": 14.5, "rebounds": 3.2, "assists": 6.8, "threes": 1.8},
    "SG": {"points": 15.2, "rebounds": 3.8, "assists": 3.1, "threes": 1.9},
    "SF": {"points": 13.8, "rebounds": 5.2, "assists": 2.9, "threes": 1.2},
    "PF": {"points": 12.5, "rebounds": 6.8, "assists": 2.1, "threes": 0.8},
    "C":  {"points": 11.2, "rebounds": 8.5, "assists": 1.5, "threes": 0.3},
    "G":  {"points": 14.8, "rebounds": 3.5, "assists": 4.9, "threes": 1.8},
    "F":  {"points": 13.1, "rebounds": 6.0, "assists": 2.5, "threes": 1.0},
    # Default for unknown position
    None: {"points": 12.0, "rebounds": 4.5, "assists": 2.5, "threes": 1.0}
}


class PredictionService(BasePredictionService):
    """Service for generating NBA player prop predictions."""

    def __init__(self, db: Session):
        super().__init__(db)
        # Lazy load services to avoid circular imports
        self._injury_service = None
        self._lineup_service = None
        self._nba_api_service = None
        self._sync_orchestrator = None
        self._weighted_stats_service = None
        self._volatility_service = None
        self._opponent_adjustment_service = None

    # ========================================================================
    # ABSTRACT METHOD IMPLEMENTATIONS
    # ========================================================================
    # NOTE: When using config mode, pass sport_id="nba" to parent __init__.
    # These methods can then be removed as they'll be loaded from config.

    def get_position_averages(self) -> Dict[str, Dict[str, float]]:
        return POSITION_AVERAGES

    def get_default_stat_types(self) -> List[str]:
        return ["points", "rebounds", "assists", "threes"]

    def get_player_model(self):
        return Player

    def get_game_model(self):
        return Game

    def get_prediction_model(self):
        return Prediction

    def get_season_stats_model(self):
        return PlayerSeasonStats

    def get_active_field_name(self) -> str:
        return "active"  # NBA uses boolean 'active' field

    def is_stat_relevant_for_position(self, position: Optional[str], stat_type: str) -> bool:
        # All positions can have all these stats in NBA
        return True

    def get_position_stat_match(self) -> Dict[str, str]:
        return {
            "PG": "assists",
            "SG": "points",
            "SF": "points",
            "PF": "rebounds",
            "C": "rebounds"
        }

    # ========================================================================
    # NBA-SPECIFIC OVERRIDES
    # ========================================================================

    def _get_season_stats_query_filters(self) -> List:
        """
        NBA uses cached season stats with a 48-hour TTL.
        """
        return [
            PlayerSeasonStats.fetched_at >= datetime.now() - timedelta(hours=48)
        ]

    def _extract_value_from_season_stats(
        self,
        season_stats: PlayerSeasonStats,
        stat_type: str,
        player: Player,
        game: Game
    ) -> Optional[float]:
        """
        NBA stores per-36 stats directly in the season stats.
        Try to apply EWMA adjustment for recent form.
        """
        # NBA stores per-36 stats directly
        per_36_value = getattr(season_stats, f'{stat_type}_per_36', None)

        if per_36_value is not None:
            logger.info(f"Using cached stats for {player.name}: {stat_type}_per_36 = {per_36_value}")

            # Try EWMA adjustment for recent form
            try:
                ewma_multiplier = self.weighted_stats_service.get_ewma_multiplier(
                    player_id=player.id,
                    stat_type=stat_type,
                    games_back=10
                )
                if ewma_multiplier != 1.0:
                    original = per_36_value
                    per_36_value = per_36_value * ewma_multiplier
                    logger.info(
                        f"EWMA adjustment for {player.name} {stat_type}: "
                        f"{original:.2f} → {per_36_value:.2f} ({ewma_multiplier:.2f}x)"
                    )
            except Exception as e:
                logger.debug(f"EWMA calculation failed for {player.name} {stat_type}: {e}")

            return per_36_value

        return None

    def _get_predicted_value(
        self,
        player: Player,
        stat_type: str,
        game: Game
    ) -> float:
        """
        NBA-specific prediction calculation using per-36 stats and minutes projections.

        Formula: predicted_value = per_36_stat × (projected_minutes / 36)
        """
        # First try cached season stats (which has per-36)
        SeasonStats = self.get_season_stats_model()
        cached_stats = (
            self.db.query(SeasonStats)
            .filter(
                SeasonStats.player_id == player.id,
                SeasonStats.season == "2025-26"
            )
            .first()
        )

        per_36_value = None

        if cached_stats:
            per_36_value = getattr(cached_stats, f'{stat_type}_per_36', None)

        # Try EWMA for recent form adjustment
        if per_36_value is not None:
            try:
                ewma_result = self.weighted_stats_service.calculate_ewma(
                    player_id=player.id,
                    stat_type=stat_type,
                    games_back=10
                )
                if ewma_result["sample_size"] >= 3:
                    ewma_multiplier = self.weighted_stats_service.get_ewma_multiplier(
                        player_id=player.id,
                        stat_type=stat_type,
                        games_back=10
                    )
                    if ewma_multiplier != 1.0:
                        original = per_36_value
                        per_36_value = per_36_value * ewma_multiplier
                        logger.info(
                            f"EWMA adjustment for {player.name} {stat_type}: "
                            f"{original:.2f} → {per_36_value:.2f} ({ewma_multiplier:.2f}x)"
                        )
            except Exception as e:
                logger.debug(f"EWMA calculation failed for {player.name} {stat_type}: {e}")

        # Fallback to PlayerStats (most recent game)
        if per_36_value is None:
            player_stats = (
                self.db.query(PlayerStats)
                .filter(PlayerStats.player_id == player.id)
                .order_by(PlayerStats.created_at.desc())
                .first()
            )

            if player_stats:
                stat_value = getattr(player_stats, stat_type, None)
                minutes = getattr(player_stats, 'minutes', None)

                if stat_value is not None and minutes and minutes > 0:
                    per_36_value = stat_value * (36.0 / minutes)
                    logger.debug(f"Using PlayerStats for {player.name}: {stat_type}_per_36 = {per_36_value}")

        # Final fallback to position averages
        if per_36_value is None:
            position = player.position if player.position else None
            averages = self.get_position_averages()
            per_36_value = averages.get(position, averages[None]).get(stat_type, 10.0)
            logger.debug(f"Using position averages for {player.name}: {stat_type}_per_36 = {per_36_value}")

        # Get minutes projection
        minutes_projection = self.lineup_service.get_player_minutes_projection(player.id, game.id)
        if minutes_projection is None:
            minutes_projection = 28  # Default starter minutes

        # Calculate prediction: per_36 × (minutes / 36)
        predicted_value = per_36_value * (minutes_projection / 36.0)

        # Apply opponent defensive adjustment
        opponent_team = None
        if player.team == game.home_team:
            opponent_team = game.away_team
        elif player.team == game.away_team:
            opponent_team = game.home_team

        if opponent_team:
            try:
                original_value = predicted_value
                predicted_value = self.opponent_adjustment_service.apply_opponent_adjustment(
                    base_prediction=predicted_value,
                    opponent_team=opponent_team,
                    stat_type=stat_type
                )
                if abs(predicted_value - original_value) > 0.5:
                    logger.info(
                        f"Opponent adjustment for {player.name} vs {opponent_team}: "
                        f"{original_value:.2f} → {predicted_value:.2f}"
                    )
            except Exception as e:
                logger.debug(f"Opponent adjustment failed: {e}")

        # Apply minimal variance
        predicted_value = self._apply_variance(predicted_value, stat_type)

        return max(0, round(predicted_value, 2))

    def _adjust_predicted_value(
        self,
        player: Player,
        stat_type: str,
        predicted_value: float,
        game: Game
    ) -> Optional[float]:
        """
        Apply NBA-specific adjustments based on injury context.
        Returns None to skip prediction for OUT players.
        """
        injury_context = self.injury_service.get_player_injury_context(player.id, game.id)

        if injury_context is None:
            injury_context = {}

        # Skip predictions for players who are OUT
        if (injury_context.get('self_injury') or {}).get('status') == 'out':
            logger.info(f"Skipping prediction for {player.name} - status: OUT")
            return None

        # Apply teammate boost (if teammates are out)
        teammate_count = len(injury_context.get('teammate_injuries', []))
        if teammate_count > 0:
            predicted_value *= (1.0 + min(teammate_count * 0.03, 0.10))

        return predicted_value

    def _adjust_confidence(
        self,
        player: Player,
        stat_type: str,
        predicted_value: float,
        base_confidence: float,
        game: Game
    ) -> float:
        """
        Apply NBA-specific confidence adjustments:
        - Injury status penalties
        - Teammate injury boosts
        - Historical hit rate weighting
        - Volatility penalty
        """
        injury_context = self.injury_service.get_player_injury_context(player.id, game.id)

        if injury_context is None:
            injury_context = {}

        confidence = base_confidence

        # Apply injury status adjustments
        self_injury_data = injury_context.get('self_injury') or {}
        self_injury_status = self_injury_data.get('status')

        if self_injury_status == 'doubtful':
            confidence -= 0.20
        elif self_injury_status == 'questionable':
            confidence -= 0.10
        elif self_injury_status == 'returning':
            confidence -= 0.05
        elif self_injury_status == 'day-to-day':
            confidence -= 0.08

        # Boost confidence when teammates are out
        teammate_count = len(injury_context.get('teammate_injuries', []))
        if teammate_count > 0:
            confidence += min(teammate_count * 0.03, 0.08)

        # Apply historical hit rate weighting
        try:
            from app.services.nba.historical_odds_service import HistoricalOddsService

            hit_rate_service = HistoricalOddsService(self.db)
            hit_rate_data = hit_rate_service.get_player_hit_rate(
                player_id=player.id,
                stat_type=stat_type,
                games_back=10,
                starters_only=True
            )

            hit_rate_weight = hit_rate_service.calculate_hit_rate_weight(
                hit_rate=hit_rate_data["hit_rate"],
                total_games=hit_rate_data["total_games"]
            )

            confidence = confidence * hit_rate_weight

            if hit_rate_data["total_games"] >= 5:
                logger.info(
                    f"Hit rate adjustment for {player.name} {stat_type}: "
                    f"{hit_rate_data['hit_rate']} ({hit_rate_data['over_hits']}/{hit_rate_data['total_games']}) "
                    f"weight={hit_rate_weight:.3f} "
                    f"confidence={base_confidence:.3f}->{confidence:.3f}"
                )

        except Exception as e:
            logger.debug(f"Could not apply hit rate weighting for {player.name} {stat_type}: {e}")

        # Apply volatility penalty
        try:
            cv_result = self.volatility_service.calculate_cv(
                player_id=player.id,
                stat_type=stat_type,
                games_back=10
            )

            if cv_result["sample_size"] >= 3:
                volatility_penalty = self.volatility_service.get_confidence_penalty(
                    cv=cv_result["cv"],
                    stat_type=stat_type
                )
                confidence += volatility_penalty

                if abs(volatility_penalty) > 0.01:
                    logger.info(
                        f"Volatility penalty for {player.name} {stat_type}: "
                        f"CV={cv_result['cv']:.3f} ({cv_result['volatility_level']}) "
                        f"penalty={volatility_penalty:.3f} "
                        f"confidence={base_confidence:.3f}->{confidence:.3f}"
                    )
        except Exception as e:
            logger.debug(f"Volatility penalty calculation failed: {e}")

        return round(max(0.25, min(0.80, confidence)), 2)

    def _get_recommendation(self, confidence: float) -> str:
        """NBA uses slightly higher threshold for recommendations."""
        if confidence >= 0.60:
            return random.choice(["OVER", "UNDER"])
        else:
            return "NONE"

    # ========================================================================
    # LAZY-LOADED SERVICE PROPERTIES
    # ========================================================================

    @property
    def injury_service(self):
        if self._injury_service is None:
            from app.services.nba.injury_service import InjuryService
            self._injury_service = InjuryService(self.db)
        return self._injury_service

    @property
    def lineup_service(self):
        if self._lineup_service is None:
            from app.services.nba.lineup_service import LineupService
            self._lineup_service = LineupService(self.db)
        return self._lineup_service

    @property
    def nba_api_service(self):
        if self._nba_api_service is None:
            from app.services.nba.nba_api_service import NbaApiService
            self._nba_api_service = NbaApiService(self.db)
        return self._nba_api_service

    @property
    def sync_orchestrator(self):
        if self._sync_orchestrator is None:
            from app.services.sync.orchestrator import SyncOrchestrator
            self._sync_orchestrator = SyncOrchestrator(self.db)
        return self._sync_orchestrator

    @property
    def weighted_stats_service(self):
        if self._weighted_stats_service is None:
            from app.services.nba.weighted_stats_service import WeightedStatsService
            self._weighted_stats_service = WeightedStatsService(self.db)
        return self._weighted_stats_service

    @property
    def volatility_service(self):
        if self._volatility_service is None:
            from app.services.nba.volatility_service import VolatilityService
            self._volatility_service = VolatilityService(self.db)
        return self._volatility_service

    @property
    def opponent_adjustment_service(self):
        if self._opponent_adjustment_service is None:
            from app.services.nba.opponent_adjustment_service import OpponentAdjustmentService
            self._opponent_adjustment_service = OpponentAdjustmentService(self.db)
        return self._opponent_adjustment_service


def uuid_uuid() -> str:
    """Generate a UUID string."""
    import uuid
    return str(uuid.uuid4())
