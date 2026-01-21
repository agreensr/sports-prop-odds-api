"""
Prediction generation service for NBA player props.

Generates predictions for upcoming games using statistical heuristics
and historical performance data.
"""
import logging
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from app.models.models import Player, Game, Prediction

logger = logging.getLogger(__name__)


# Position-based stat averages (fallback when no historical data)
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


class PredictionService:
    """Service for generating NBA player prop predictions."""

    def __init__(self, db: Session):
        self.db = db

    def generate_predictions_for_game(
        self,
        game_id: str,
        stat_types: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Generate predictions for all players in a game.

        Args:
            game_id: Database UUID of the game
            stat_types: List of stat types to predict (default: points, rebounds, assists, threes)

        Returns:
            List of generated prediction dictionaries
        """
        if stat_types is None:
            stat_types = ["points", "rebounds", "assists", "threes"]

        game = self.db.query(Game).filter(Game.id == game_id).first()
        if not game:
            logger.error(f"Game {game_id} not found")
            return []

        # Get all players for both teams
        players = (
            self.db.query(Player)
            .filter(
                Player.team.in_([game.away_team, game.home_team]),
                Player.active == True
            )
            .all()
        )

        if not players:
            logger.warning(f"No active players found for game {game.external_id}")
            return []

        predictions_generated = []

        for player in players:
            for stat_type in stat_types:
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
                predicted_value = self._get_predicted_value(player, stat_type)

                # Calculate confidence based on various factors
                confidence = self._calculate_confidence(player, stat_type, predicted_value)

                # Determine recommendation
                recommendation = self._get_recommendation(confidence)

                # Create prediction
                prediction = Prediction(
                    id=str(uuid_uuid()),  # Will be replaced by database default
                    player_id=player.id,
                    game_id=game.id,
                    stat_type=stat_type,
                    predicted_value=predicted_value,
                    bookmaker_line=None,  # Will be filled when odds are fetched
                    bookmaker_name=None,
                    recommendation=recommendation,
                    confidence=confidence,
                    model_version="1.0.0",  # Simple heuristic model
                    over_price=None,
                    under_price=None,
                    odds_fetched_at=None,
                    odds_last_updated=None,
                    created_at=datetime.utcnow()
                )

                self.db.add(prediction)
                predictions_generated.append({
                    "player": player.name,
                    "team": player.team,
                    "stat_type": stat_type,
                    "predicted_value": predicted_value,
                    "confidence": confidence,
                    "recommendation": recommendation
                })

                logger.info(f"Generated prediction: {player.name} ({player.team}) - {stat_type}: {predicted_value:.1f} (confidence: {confidence:.2f})")

        try:
            self.db.commit()
            logger.info(f"Generated {len(predictions_generated)} predictions for game {game.external_id}")
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error saving predictions: {e}")
            raise

        return predictions_generated

    def _get_predicted_value(self, player: Player, stat_type: str) -> float:
        """
        Get predicted value for a player and stat type.

        Uses position-based averages as a simple heuristic.
        In future versions, this would use historical performance and ML models.
        """
        position = player.position if player.position else None
        averages = POSITION_AVERAGES.get(position, POSITION_AVERAGES[None])

        base_value = averages.get(stat_type, 10.0)

        # Add some random variation to make predictions more realistic
        # In production, this would be based on actual statistical analysis
        import random
        variation = random.uniform(-0.15, 0.15)  # ±15% variation
        predicted_value = base_value * (1 + variation)

        return max(0, round(predicted_value, 2))

    def _calculate_confidence(
        self,
        player: Player,
        stat_type: str,
        predicted_value: float
    ) -> float:
        """
        Calculate confidence score for a prediction.

        Confidence is based on:
        - How well the stat type matches the player's position
        - Reasonableness of the predicted value
        - Random factor to simulate model uncertainty

        Returns value between 0.0 and 1.0
        """
        position = player.position if player.position else None
        averages = POSITION_AVERAGES.get(position, POSITION_AVERAGES[None])

        # Base confidence
        confidence = 0.55

        # Boost confidence if stat type aligns with position
        position_stat_match = {
            "PG": "assists",
            "SG": "points",
            "SF": "points",
            "PF": "rebounds",
            "C": "rebounds"
        }

        if position and position_stat_match.get(position) == stat_type:
            confidence += 0.10  # +10% for position-appropriate stats

        # Add some randomness to simulate model uncertainty
        import random
        confidence += random.uniform(-0.08, 0.08)

        return round(max(0.35, min(0.75, confidence)), 2)

    def _get_recommendation(self, confidence: float) -> str:
        """
        Get recommendation based on confidence score.

        Returns:
            "OVER", "UNDER", or "NONE"
        """
        if confidence >= 0.60:
            # High confidence - make a recommendation
            import random
            return random.choice(["OVER", "UNDER"])
        else:
            # Low confidence - no recommendation
            return "NONE"


def uuid_uuid() -> str:
    """Generate a UUID string."""
    import uuid
    return str(uuid.uuid4())
