"""
Base prediction service for all sports.

Provides shared implementation for:
- Prediction generation orchestration
- Fallback chain for historical stats
- Confidence calculation
- Recommendation logic

Sport-specific services extend this class and provide:
- Model references
- Sport-specific business rules (optional)

Configuration-driven mode:
Services can use sport config for position averages, stat types, thresholds,
eliminating the need to implement abstract methods for configuration.
"""
import logging
import random
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Optional, Any, Type
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# =============================================================================
# MODEL VERSION CONFIGURATION (P2 #21: Prediction Versioning)
# =============================================================================

# Default model version for all sports
# Override in sport-specific services by setting MODEL_VERSION class attribute
DEFAULT_MODEL_VERSION = "1.0.0"

# Model version history for tracking changes over time
# Format: version -> (description, release_date)
MODEL_VERSION_HISTORY = {
    "1.0.0": ("Initial prediction model", "2025-01-15"),
}


# Optional: Import sport config for configuration-driven mode
try:
    from app.services.core.sport_adapter import (
        get_sport_config,
        get_position_averages,
        get_default_stat_types,
        get_recommendation_threshold,
        get_variance_percent,
        is_stat_relevant_for_position,
        get_primary_stat_for_position,
    )
    SPORT_CONFIG_AVAILABLE = True
except ImportError:
    SPORT_CONFIG_AVAILABLE = False


class BasePredictionService(ABC):
    """
    Base class for sport-specific prediction services.

    Implements the common prediction generation workflow while allowing
    sports to customize behavior through abstract methods and hooks.
    """

    # Sport-specific services can override this to track their model version
    MODEL_VERSION: str = DEFAULT_MODEL_VERSION

    def __init__(self, db: Session, sport_id: Optional[str] = None):
        """
        Initialize the prediction service.

        Args:
            db: SQLAlchemy database session
            sport_id: Optional sport identifier ('nba', 'nfl', 'mlb', 'nhl')
                     If provided, uses configuration-driven mode
        """
        self.db = db
        self._sport_id = sport_id

        # Load sport config if provided and available
        self._use_config_mode = (
            sport_id is not None and
            SPORT_CONFIG_AVAILABLE and
            self._try_load_sport_config(sport_id)
        )

    def _try_load_sport_config(self, sport_id: str) -> bool:
        """
        Try to load sport configuration.

        Returns True if config was loaded successfully.
        """
        try:
            self._sport_config = get_sport_config(sport_id)
            return True
        except (ValueError, ImportError):
            logger.warning(f"Could not load sport config for '{sport_id}', using abstract methods")
            return False

    @property
    def use_config_mode(self) -> bool:
        """Whether this service is using configuration-driven mode."""
        return getattr(self, '_use_config_mode', False)

    # ========================================================================
    # CONFIGURATION METHODS - Use sport config or override
    # ========================================================================

    def get_position_averages(self) -> Dict[str, Dict[str, float]]:
        """
        Get position-based stat averages for fallback when no historical data exists.

        In config mode: Loads from sport configuration.
        Override this method to provide custom averages.

        Returns:
            Dict mapping position names to stat averages.
            Example: {"PG": {"points": 14.5, "rebounds": 3.2}, None: {...}}
        """
        if self.use_config_mode:
            from app.services.core.sport_adapter import POSITION_AVERAGES
            sport_averages = POSITION_AVERAGES.get(self._sport_id, {})
            # Add None key for unknown positions
            if None not in sport_averages and sport_averages:
                # Create average of all positions as default
                all_stats = {}
                for pos_stats in sport_averages.values():
                    for stat, value in pos_stats.items():
                        if stat not in all_stats:
                            all_stats[stat] = []
                        all_stats[stat].append(value)
                default_stats = {stat: sum(vals) / len(vals) for stat, vals in all_stats.items()}
                sport_averages[None] = default_stats
            return sport_averages

        # Abstract method - must be implemented by subclasses not using config
        raise NotImplementedError(
            "get_position_averages() must be implemented, or pass sport_id to use config"
        )

    def get_default_stat_types(self) -> List[str]:
        """
        Get default stat types to generate predictions for.

        In config mode: Loads from sport configuration.
        Override this method to provide custom stat types.

        Returns:
            List of stat type names (e.g., ["points", "rebounds", "assists"])
        """
        if self.use_config_mode:
            return self._sport_config.default_stat_types

        raise NotImplementedError(
            "get_default_stat_types() must be implemented, or pass sport_id to use config"
        )

    def get_player_model(self) -> Type:
        """
        Get the Player model class for this sport.

        Returns:
            SQLAlchemy Player model class
        """
        if self.use_config_mode:
            from app.models import Player
            return Player
        raise NotImplementedError(
            "get_player_model() must be implemented, or pass sport_id to use unified models"
        )

    def get_game_model(self) -> Type:
        """
        Get the Game model class for this sport.

        Returns:
            SQLAlchemy Game model class
        """
        if self.use_config_mode:
            from app.models import Game
            return Game
        raise NotImplementedError(
            "get_game_model() must be implemented, or pass sport_id to use unified models"
        )

    def get_prediction_model(self) -> Type:
        """
        Get the Prediction model class for this sport.

        Returns:
            SQLAlchemy Prediction model class
        """
        if self.use_config_mode:
            from app.models import Prediction
            return Prediction
        raise NotImplementedError(
            "get_prediction_model() must be implemented, or pass sport_id to use unified models"
        )

    def get_model_version(self) -> str:
        """
        Get the current model version for this prediction service.

        The model version is stored with each prediction to track which
        model generated it. This allows for:
        - Tracking model performance over time
        - Regenerating predictions when models improve
        - A/B testing different model versions

        Returns:
            Model version string (e.g., "1.0.0")

        Examples:
            # Override in sport-specific service
            class NBAPredictionService(BasePredictionService):
                MODEL_VERSION = "1.1.0"  # Improved NBA model
        """
        # Allow sport-specific override via class attribute
        if hasattr(self, 'MODEL_VERSION') and self.MODEL_VERSION != DEFAULT_MODEL_VERSION:
            return self.MODEL_VERSION

        # In config mode, check if sport config has model version
        if self.use_config_mode and hasattr(self, '_sport_config'):
            return getattr(self._sport_config, 'model_version', DEFAULT_MODEL_VERSION)

        return DEFAULT_MODEL_VERSION

    def get_model_version_info(self) -> Dict[str, str]:
        """
        Get information about the current model version.

        Returns:
            Dict with version, description, and release_date
        """
        version = self.get_model_version()
        info = MODEL_VERSION_HISTORY.get(version, ("Unknown model version", "Unknown"))
        return {
            "version": version,
            "description": info[0],
            "release_date": info[1]
        }

    def get_season_stats_model(self) -> Type:
        """
        Get the PlayerSeasonStats model class for this sport.

        Returns:
            SQLAlchemy PlayerSeasonStats model class
        """
        if self.use_config_mode:
            from app.models import PlayerSeasonStats
            return PlayerSeasonStats
        raise NotImplementedError(
            "get_season_stats_model() must be implemented, or pass sport_id to use unified models"
        )

    def get_active_field_name(self) -> str:
        """
        Get the field name used to filter active players.

        In config mode: Returns 'active' for boolean, 'status' for string.
        Override this method for custom behavior.

        Some sports use 'active' boolean, others use 'status' with 'active' value.

        Returns:
            Field name for filtering active players
        """
        if self.use_config_mode:
            return "active" if self._sport_config.active_field_is_boolean else "status"

        raise NotImplementedError(
            "get_active_field_name() must be implemented, or pass sport_id to use config"
        )

    def is_stat_relevant_for_position(self, position: Optional[str], stat_type: str) -> bool:
        """
        Check if a stat type is relevant for a given position.

        In config mode: Checks position config for allowed stat types.
        Override this method for custom behavior.

        Args:
            position: Player position (e.g., "QB", "PG", "P")
            stat_type: Stat type to check (e.g., "points", "passing_yards")

        Returns:
            True if stat is relevant for this position
        """
        if self.use_config_mode:
            if position is None:
                return True  # No position data, allow all stats
            return is_stat_relevant_for_position(self._sport_id, position, stat_type)

        raise NotImplementedError(
            "is_stat_relevant_for_position() must be implemented, or pass sport_id to use config"
        )

    def get_position_stat_match(self) -> Dict[str, str]:
        """
        Get mapping of positions to their primary stat for confidence boosting.

        In config mode: Loads from sport configuration.
        Override this method for custom behavior.

        Used to increase confidence when predicting a player's primary stat.

        Returns:
            Dict mapping positions to their primary stat type.
            Example: {"QB": "passing_yards", "RB": "rushing_yards"}
        """
        if self.use_config_mode:
            return self._sport_config.position_primary_stats

        raise NotImplementedError(
            "get_position_stat_match() must be implemented, or pass sport_id to use config"
        )

    # ========================================================================
    # MAIN PUBLIC METHOD
    # ========================================================================

    def generate_predictions_for_game(
        self,
        game_id: str,
        stat_types: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Generate predictions for all players in a game.

        This is the main entry point for prediction generation. It:
        1. Loads the game
        2. Queries all active players for both teams
        3. For each player and stat type:
           - Checks if prediction already exists
           - Calculates predicted value
           - Calculates confidence
           - Creates prediction record
        4. Commits all predictions to database

        Args:
            game_id: Database UUID of the game
            stat_types: List of stat types to predict (uses default if None)

        Returns:
            List of generated prediction dictionaries with metadata
        """
        if stat_types is None:
            stat_types = self.get_default_stat_types()

        # Get model classes
        Game = self.get_game_model()
        Player = self.get_player_model()
        Prediction = self.get_prediction_model()

        # Load game
        game = self.db.query(Game).filter(Game.id == game_id).first()
        if not game:
            logger.error(f"Game {game_id} not found")
            return []

        # Get active players for both teams
        active_filter = self._get_active_filter()
        players = (
            self.db.query(Player)
            .filter(
                Player.team.in_([game.away_team, game.home_team]),
                active_filter
            )
            .all()
        )

        if not players:
            logger.warning(f"No active players found for game {game_id}")
            return []

        predictions_generated = []

        for player in players:
            for stat_type in stat_types:
                # Skip irrelevant stat types for position
                if not self.is_stat_relevant_for_position(player.position, stat_type):
                    continue

                # Check if prediction already exists
                existing = (
                    self.db.query(Prediction)
                    .filter(
                        Prediction.player_id == player.id,
                        Prediction.game_id == game.id,
                        Prediction.stat_type == stat_type
                    )
                    .first()
                )

                if existing:
                    logger.debug(f"Prediction already exists for {player.name} - {stat_type}")
                    continue

                # Get predicted value
                predicted_value = self._get_predicted_value(
                    player, stat_type, game
                )

                # Allow sport-specific adjustment (e.g., for injury status)
                predicted_value = self._adjust_predicted_value(
                    player, stat_type, predicted_value, game
                )

                # Skip if adjusted value is None (indicates player should be skipped)
                if predicted_value is None:
                    continue

                # Calculate confidence
                confidence = self._calculate_confidence(
                    player, stat_type, predicted_value, game
                )

                # Allow sport-specific confidence adjustment
                confidence = self._adjust_confidence(
                    player, stat_type, predicted_value, confidence, game
                )

                # Determine recommendation
                recommendation = self._get_recommendation(confidence)

                # Create prediction record
                prediction = self._create_prediction_record(
                    player_id=player.id,
                    game_id=game.id,
                    stat_type=stat_type,
                    predicted_value=predicted_value,
                    recommendation=recommendation,
                    confidence=confidence
                )

                self.db.add(prediction)

                # Build result dictionary
                result = {
                    "player": player.name,
                    "team": player.team,
                    "stat_type": stat_type,
                    "predicted_value": predicted_value,
                    "confidence": confidence,
                    "recommendation": recommendation
                }

                # Add position if available
                if hasattr(player, 'position'):
                    result["position"] = player.position

                predictions_generated.append(result)

                logger.info(
                    f"Generated prediction: {player.name} ({player.team}) "
                    f"- {stat_type}: {predicted_value:.2f} (confidence: {confidence:.2f})"
                )

        # Commit all predictions
        try:
            self.db.commit()
            logger.info(f"Generated {len(predictions_generated)} predictions for game {game_id}")
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error saving predictions: {e}")
            raise

        return predictions_generated

    # ========================================================================
    # PROTECTED METHODS - Shared implementation
    # ========================================================================

    def _get_active_filter(self):
        """
        Get the filter for active players based on sport's field configuration.

        Returns:
            SQLAlchemy filter expression for active players
        """
        Player = self.get_player_model()
        field_name = self.get_active_field_name()

        # Handle both 'active' boolean and 'status' string approaches
        if field_name == "active":
            return getattr(Player, "active") == True
        elif field_name == "status":
            return Player.status == "active"
        else:
            # Default to active boolean
            return Player.active == True

    def _get_predicted_value(
        self,
        player: Any,
        stat_type: str,
        game: Any
    ) -> float:
        """
        Calculate predicted value using player-specific historical stats.

        FALLBACK CHAIN:
        1. PlayerSeasonStats (current season) - most reliable
        2. Position averages - when no player data exists

        Args:
            player: Player model instance
            stat_type: Stat to predict
            game: Game model instance

        Returns:
            Predicted value for the stat
        """
        SeasonStats = self.get_season_stats_model()

        # Build query filters for season stats
        # Convert game.season (Integer) to string for comparison with PlayerSeasonStats.season (String)
        season_str = str(game.season) if game.season else None
        filters = [
            SeasonStats.player_id == player.id,
            SeasonStats.season == season_str
        ]

        # Add any sport-specific filters
        additional_filters = self._get_season_stats_query_filters()
        if additional_filters:
            filters.extend(additional_filters)

        # Try season stats first
        season_stats = (
            self.db.query(SeasonStats)
            .filter(*filters)
            .first()
        )

        predicted_value = None

        if season_stats:
            predicted_value = self._extract_value_from_season_stats(
                season_stats, stat_type, player, game
            )

        # Fallback to position averages
        if predicted_value is None:
            position = player.position if player.position else None
            averages = self.get_position_averages()
            position_avg = averages.get(position, averages.get(None, {}))
            predicted_value = position_avg.get(stat_type, 10.0)

            logger.debug(
                f"Using position averages for {player.name} ({position}): "
                f"{stat_type} = {predicted_value}"
            )

        # Apply variance (sport-specific hook)
        predicted_value = self._apply_variance(predicted_value, stat_type)

        return max(0, round(predicted_value, 2))

    def _get_season_stats_query_filters(self) -> List[Any]:
        """
        Get additional filters for season stats queries.

        Override this for sport-specific filtering (e.g., MLB's season_type == "REG").

        Returns:
            List of SQLAlchemy filter expressions
        """
        return []

    def _extract_value_from_season_stats(
        self,
        season_stats: Any,
        stat_type: str,
        player: Any,
        game: Any
    ) -> Optional[float]:
        """
        Extract predicted value from season stats.

        Handles different sports' approaches to per-game calculations.
        Override this for sport-specific stat extraction logic.

        Args:
            season_stats: PlayerSeasonStats instance
            stat_type: Stat type to extract
            player: Player instance
            game: Game instance

        Returns:
            Predicted value or None if not available
        """
        stat_value = getattr(season_stats, stat_type, None)
        if stat_value is None:
            return None

        # Default: assume cumulative stats that need per-game normalization
        games_played = getattr(season_stats, 'games_played', 0)

        if games_played and games_played > 0:
            predicted_value = stat_value / games_played
            logger.debug(
                f"Using season stats for {player.name}: {stat_type} = "
                f"{predicted_value:.2f}/game"
            )
            return predicted_value

        return None

    def _get_position_stat_match_for_confidence(
        self,
        position: Optional[str],
        stat_type: str
    ) -> bool:
        """
        Check if the stat type matches the position's primary stat.

        This is a helper for confidence calculation and is extracted to avoid
        duplication across sport services.

        Args:
            position: Player position
            stat_type: Stat type being predicted

        Returns:
            True if stat is the primary stat for this position
        """
        if not position:
            return False

        position_stat_match = self.get_position_stat_match()
        return position_stat_match.get(position) == stat_type

    def _calculate_confidence(
        self,
        player: Any,
        stat_type: str,
        predicted_value: float,
        game: Any
    ) -> float:
        """
        Calculate base confidence score for a prediction.

        Base confidence considers:
- Historical data availability
- Position-stat alignment
- Sample size (games played)

        Sports can override `_adjust_confidence()` for additional factors.

        Args:
            player: Player model instance
            stat_type: Stat type being predicted
            predicted_value: Calculated predicted value
            game: Game model instance

        Returns:
            Confidence score between 0.0 and 1.0
        """
        SeasonStats = self.get_season_stats_model()

        confidence = 0.50

        # Build season stats query
        # Convert game.season (Integer) to string for comparison with PlayerSeasonStats.season (String)
        season_str = str(game.season) if game.season else None
        filters = [
            SeasonStats.player_id == player.id,
            SeasonStats.season == season_str
        ]
        additional_filters = self._get_season_stats_query_filters()
        if additional_filters:
            filters.extend(additional_filters)

        # Check for historical stats
        season_stats = (
            self.db.query(SeasonStats)
            .filter(*filters)
            .first()
        )

        if season_stats:
            confidence += self._calculate_sample_size_confidence(
                season_stats, player, stat_type
            )

        # Position-stat alignment boost
        if self._get_position_stat_match_for_confidence(player.position, stat_type):
            confidence += 0.06

        # Add small randomness
        confidence += random.uniform(-0.03, 0.03)

        return round(max(0.30, min(0.75, confidence)), 2)

    def _calculate_sample_size_confidence(
        self,
        season_stats: Any,
        player: Any,
        stat_type: str
    ) -> float:
        """
        Calculate confidence boost based on sample size.

        This method can be overridden for sport-specific sample size logic.
        Default implementation uses games_played with standard thresholds.

        Args:
            season_stats: PlayerSeasonStats instance
            player: Player instance
            stat_type: Stat type

        Returns:
            Confidence boost to add to base confidence
        """
        games_played = getattr(season_stats, 'games_played', 0)

        # Sample size boosts
        if games_played >= 50:
            return 0.12  # High confidence
        elif games_played >= 20:
            return 0.06  # Moderate confidence
        elif games_played >= 8:
            return 0.03  # Low confidence
        elif games_played >= 4:
            return 0.02  # Minimal confidence

        return 0.0

    def _get_recommendation(self, confidence: float) -> str:
        """
        Get recommendation based on confidence score.

        In config mode: Uses sport's recommendation threshold.
        Override this method for custom behavior.

        Args:
            confidence: Confidence score

        Returns:
            "OVER", "UNDER", or "NONE"
        """
        if self.use_config_mode:
            threshold = self._sport_config.recommendation_threshold
        else:
            threshold = 0.58  # Default threshold

        if confidence >= threshold:
            return random.choice(["OVER", "UNDER"])
        else:
            return "NONE"

    def _apply_variance(self, value: float, stat_type: str) -> float:
        """
        Apply random variance to predicted value.

        In config mode: Uses sport's variance percent.
        Override this method for custom behavior.

        Args:
            value: Base predicted value
            stat_type: Stat type (for sport-specific variance)

        Returns:
            Value with variance applied
        """
        if self.use_config_mode:
            variance_percent = self._sport_config.variance_percent / 100
        else:
            variance_percent = 0.08  # Default 8%

        variance = random.uniform(-variance_percent, variance_percent)
        return value * (1.0 + variance)

    def _create_prediction_record(
        self,
        player_id: str,
        game_id: str,
        stat_type: str,
        predicted_value: float,
        recommendation: str,
        confidence: float
    ) -> Any:
        """
        Create a Prediction model instance.

        Args:
            player_id: Player database ID
            game_id: Game database ID
            stat_type: Stat type
            predicted_value: Predicted value
            recommendation: OVER/UNDER/NONE
            confidence: Confidence score

        Returns:
            Prediction model instance
        """
        Prediction = self.get_prediction_model()

        return Prediction(
            id=str(uuid.uuid4()),
            player_id=player_id,
            game_id=game_id,
            stat_type=stat_type,
            predicted_value=predicted_value,
            bookmaker_line=None,
            bookmaker_name=None,
            recommendation=recommendation,
            confidence=confidence,
            model_version=self.get_model_version(),
            over_price=None,
            under_price=None,
            odds_last_updated=None,
            created_at=datetime.utcnow()
        )

    # ========================================================================
    # HOOK METHODS - Optional overrides for sport-specific behavior
    # ========================================================================

    def _adjust_predicted_value(
        self,
        player: Any,
        stat_type: str,
        predicted_value: float,
        game: Any
    ) -> Optional[float]:
        """
        Hook for sport-specific adjustments to predicted value.

        Override this to apply sport-specific logic like:
        - Injury status adjustments
        - Teammate injury boosts
        - Matchup considerations

        Args:
            player: Player instance
            stat_type: Stat type
            predicted_value: Base predicted value
            game: Game instance

        Returns:
            Adjusted predicted value, or None to skip this prediction
        """
        return predicted_value

    def _adjust_confidence(
        self,
        player: Any,
        stat_type: str,
        predicted_value: float,
        base_confidence: float,
        game: Any
    ) -> float:
        """
        Hook for sport-specific confidence adjustments.

        Override this to apply sport-specific logic like:
        - Injury status penalties
        - Volatility adjustments
        - Historical hit rate weighting

        Args:
            player: Player instance
            stat_type: Stat type
            predicted_value: Predicted value
            base_confidence: Base confidence from _calculate_confidence
            game: Game instance

        Returns:
            Adjusted confidence score
        """
        return base_confidence
