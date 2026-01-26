"""
Parlay generation service for NBA player prop bets.

Generates same-game and multi-game parlays with correlation analysis
and expected value calculations.
"""
import logging
import uuid
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
from itertools import combinations
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_

from app.models.nba.models import Parlay, ParlayLeg, Prediction, Game, Player
from app.utils.timezone import utc_to_central, format_game_time_central

logger = logging.getLogger(__name__)


# Correlation coefficients based on basketball analytics research
# These represent how different stat types correlate for the same player
SAME_PLAYER_CORRELATIONS = {
    ("points", "assists"): 0.65,   # Scorers create opportunities
    ("points", "rebounds"): 0.55,  # Active players involved in plays
    ("points", "threes"): 0.70,    # Threes directly count toward points
    ("assists", "threes"): 0.45,   # Ball handlers who shoot
    ("rebounds", "assists"): 0.35, # All-around contributors
}

# Teammate correlations - how one player's stats correlate with teammate's stats
TEAMMATE_CORRELATIONS = {
    ("assists", "points"): 0.30,   # Passer to scorer
    ("rebounds", "points"): 0.25,  # Screen to scorer
    ("points", "points"): -0.20,   # AVOID - shot competition
    ("points", "assists"): 0.20,   # Cutter to passer
}


class ParlayService:
    """Service for generating and managing parlay bets."""

    def __init__(self, db: Session):
        self.db = db

    def generate_same_game_parlays(
        self,
        game_id: str,
        min_confidence: float = 0.60,
        max_legs: int = 3,
        min_ev: float = 0.05,
        limit: int = 50
    ) -> List[Dict]:
        """
        Generate same-game parlays with correlation analysis.

        Args:
            game_id: Database UUID of the game
            min_confidence: Minimum confidence score for predictions (0.0 to 1.0)
            max_legs: Maximum number of legs per parlay (2-4)
            min_ev: Minimum expected value as decimal (0.05 = 5%)
            limit: Maximum number of parlays to return

        Returns:
            List of generated parlay dictionaries
        """
        game = self.db.query(Game).filter(Game.id == game_id).first()
        if not game:
            logger.error(f"Game {game_id} not found")
            return []

        # Get high-confidence predictions for this game with odds
        predictions = self._get_game_predictions(
            game_id=game_id,
            min_confidence=min_confidence,
            has_odds=True
        )

        if not predictions:
            logger.warning(f"No qualifying predictions found for game {game.external_id}")
            return []

        logger.info(f"Found {len(predictions)} predictions for game {game.external_id}")

        # Group predictions by player
        player_predictions = self._group_predictions_by_player(predictions)

        generated_parlays = []

        # Generate same-player combinations
        for player_id, preds in player_predictions.items():
            if len(preds) >= 2:
                # Generate combinations of 2-4 legs for same player
                for num_legs in range(2, min(len(preds), max_legs) + 1):
                    for combo in combinations(preds, num_legs):
                        parlay = self._create_parlay_from_predictions(
                            predictions=list(combo),
                            parlay_type="same_game",
                            correlation_bonus=self._calculate_same_player_correlation(combo)
                        )
                        if parlay and parlay["expected_value"] >= min_ev:
                            generated_parlays.append(parlay)

        # Generate teammate combinations (only positive correlations)
        for player1_id, preds1 in player_predictions.items():
            for player2_id, preds2 in player_predictions.items():
                if player1_id >= player2_id:
                    continue  # Avoid duplicates

                for pred1 in preds1[:2]:  # Top 2 predictions per player
                    for pred2 in preds2[:2]:
                        # Check if this combination has positive correlation
                        correlation = self._calculate_teammate_correlation(
                            pred1["stat_type"],
                            pred2["stat_type"]
                        )
                        if correlation > 0:
                            parlay = self._create_parlay_from_predictions(
                                predictions=[pred1, pred2],
                                parlay_type="same_game",
                                correlation_bonus=correlation
                            )
                            if parlay and parlay["expected_value"] >= min_ev:
                                generated_parlays.append(parlay)

        # Sort by expected value and return top results
        generated_parlays.sort(key=lambda x: x["expected_value"], reverse=True)
        results = generated_parlays[:limit]

        # Save parlays to database
        for parlay_data in results:
            self._save_parlay(parlay_data, "same_game")

        logger.info(f"Generated {len(results)} same-game parlays for game {game.external_id}")
        return results

    def generate_multi_game_parlays(
        self,
        days_ahead: int = 3,
        min_confidence: float = 0.60,
        max_legs: int = 3,
        min_ev: float = 0.05,
        games_per_parlay: int = 3,
        limit: int = 50
    ) -> List[Dict]:
        """
        Generate multi-game parlays across different teams/games.

        Args:
            days_ahead: How many days ahead to look for predictions
            min_confidence: Minimum confidence score for predictions
            max_legs: Maximum number of legs per parlay
            min_ev: Minimum expected value
            games_per_parlay: Number of different games to combine
            limit: Maximum number of parlays to return

        Returns:
            List of generated parlay dictionaries
        """
        # Get upcoming predictions with odds
        predictions = self._get_upcoming_predictions(
            days_ahead=days_ahead,
            min_confidence=min_confidence,
            has_odds=True
        )

        if not predictions:
            logger.warning("No qualifying predictions found for upcoming games")
            return []

        # Group predictions by game
        game_predictions = self._group_predictions_by_game(predictions)

        if len(game_predictions) < 2:
            logger.warning("Need at least 2 games with predictions for multi-game parlays")
            return []

        generated_parlays = []

        # Get top predictions per game
        top_predictions_by_game = []
        for game_id, preds in game_predictions.items():
            # Sort by confidence and take top 2
            sorted_preds = sorted(preds, key=lambda x: x["confidence"], reverse=True)
            top_predictions_by_game.append(
                sorted_preds[:2]  # Top 2 per game
            )

        # Generate combinations across games
        available_games = len(top_predictions_by_game)
        for num_games in range(2, min(available_games, games_per_parlay) + 1):
            for game_indices in combinations(range(available_games), num_games):
                # For each selected game, pick one prediction
                for pred_selections in _product_of_top_predictions([
                    top_predictions_by_game[i] for i in game_indices
                ]):
                    if 2 <= len(pred_selections) <= max_legs:
                        parlay = self._create_parlay_from_predictions(
                            predictions=pred_selections,
                            parlay_type="multi_game",
                            correlation_bonus=0.0  # No correlation for multi-game
                        )
                        if parlay and parlay["expected_value"] >= min_ev:
                            generated_parlays.append(parlay)

        # Sort by expected value
        generated_parlays.sort(key=lambda x: x["expected_value"], reverse=True)
        results = generated_parlays[:limit]

        # Save parlays to database
        for parlay_data in results:
            self._save_parlay(parlay_data, "multi_game")

        logger.info(f"Generated {len(results)} multi-game parlays")
        return results

    def generate_same_game_parlays_optimized(
        self,
        game_id: str,
        min_confidence: float = 0.65,
        max_legs: int = 4,
        min_ev: float = 0.08,
        limit: int = 50
    ) -> List[Dict]:
        """
        Generate same-game parlays with optimized parameters.

        Higher confidence threshold (0.65) and EV threshold (0.08) for
        more selective, higher-quality parlays.

        Args:
            game_id: Database UUID of the game
            min_confidence: Minimum confidence score (default: 0.65)
            max_legs: Maximum number of legs (2-4)
            min_ev: Minimum expected value (default: 0.08)
            limit: Maximum number of parlays to return

        Returns:
            List of generated parlay dictionaries
        """
        game = self.db.query(Game).filter(Game.id == game_id).first()
        if not game:
            logger.error(f"Game {game_id} not found")
            return []

        # Get high-confidence predictions for this game with odds
        predictions = self._get_game_predictions(
            game_id=game_id,
            min_confidence=min_confidence,
            has_odds=True
        )

        if not predictions:
            logger.warning(f"No qualifying predictions found for game {game.external_id}")
            return []

        logger.info(f"Found {len(predictions)} predictions for game {game.external_id}")

        # Group predictions by player
        player_predictions = self._group_predictions_by_player(predictions)

        generated_parlays = []

        # Generate 2-leg same-game parlays (different players)
        player_ids = list(player_predictions.keys())
        for i in range(len(player_ids)):
            for j in range(i + 1, len(player_ids)):
                player1_id, player2_id = player_ids[i], player_ids[j]

                # Get top prediction for each player
                preds1 = sorted(
                    player_predictions[player1_id],
                    key=lambda x: x["confidence"],
                    reverse=True
                )[:1]
                preds2 = sorted(
                    player_predictions[player2_id],
                    key=lambda x: x["confidence"],
                    reverse=True
                )[:1]

                if preds1 and preds2:
                    parlay = self._create_parlay_from_predictions(
                        predictions=[preds1[0], preds2[0]],
                        parlay_type="same_game",
                        correlation_bonus=0.0  # Different players, low correlation
                    )
                    if parlay and parlay["expected_value"] >= min_ev:
                        generated_parlays.append(parlay)

        # Generate 3-leg same-game parlays
        if len(player_ids) >= 3:
            for combo in combinations(player_ids, 3):
                legs = []
                for pid in combo:
                    top_pred = sorted(
                        player_predictions[pid],
                        key=lambda x: x["confidence"],
                        reverse=True
                    )[:1]
                    if top_pred:
                        legs.append(top_pred[0])

                if len(legs) == 3:
                    parlay = self._create_parlay_from_predictions(
                        predictions=legs,
                        parlay_type="same_game",
                        correlation_bonus=0.0
                    )
                    if parlay and parlay["expected_value"] >= min_ev:
                        generated_parlays.append(parlay)

        # Sort by expected value and return top results
        generated_parlays.sort(key=lambda x: x["expected_value"], reverse=True)
        results = generated_parlays[:limit]

        # Save parlays to database
        for parlay_data in results:
            self._save_parlay(parlay_data, "same_game")

        logger.info(f"Generated {len(results)} optimized same-game parlays for game {game.external_id}")
        return results

    def generate_cross_game_parlays(
        self,
        days_ahead: int = 1,
        min_confidence: float = 0.65,
        min_ev: float = 0.08,
        limit: int = 30
    ) -> List[Dict]:
        """
        Generate 2-leg parlays across different games.

        Independent events (no correlation penalty) across different games.

        Args:
            days_ahead: Number of days ahead to look for predictions
            min_confidence: Minimum confidence score
            min_ev: Minimum expected value
            limit: Maximum number of parlays to return

        Returns:
            List of generated parlay dictionaries
        """
        # Get upcoming predictions with odds
        predictions = self._get_upcoming_predictions(
            days_ahead=days_ahead,
            min_confidence=min_confidence,
            has_odds=True
        )

        if not predictions:
            logger.warning("No qualifying predictions found for upcoming games")
            return []

        # Group predictions by game
        game_predictions = self._group_predictions_by_game(predictions)

        if len(game_predictions) < 2:
            logger.warning("Need at least 2 games with predictions for cross-game parlays")
            return []

        generated_parlays = []

        # Get top 2 predictions per game
        top_predictions_by_game = []
        for game_id, preds in game_predictions.items():
            sorted_preds = sorted(preds, key=lambda x: x["confidence"], reverse=True)
            top_predictions_by_game.append({
                "game_id": game_id,
                "predictions": sorted_preds[:2]
            })

        # Generate 2-leg parlays across different games
        for i in range(len(top_predictions_by_game)):
            for j in range(i + 1, len(top_predictions_by_game)):
                game1 = top_predictions_by_game[i]
                game2 = top_predictions_by_game[j]

                # Generate all combinations of top predictions
                for pred1 in game1["predictions"]:
                    for pred2 in game2["predictions"]:
                        parlay = self._create_parlay_from_predictions(
                            predictions=[pred1, pred2],
                            parlay_type="multi_game",
                            correlation_bonus=0.0  # No correlation across games
                        )
                        if parlay and parlay["expected_value"] >= min_ev:
                            generated_parlays.append(parlay)

        # Sort by expected value and return top results
        generated_parlays.sort(key=lambda x: x["expected_value"], reverse=True)
        results = generated_parlays[:limit]

        # Save parlays to database
        for parlay_data in results:
            self._save_parlay(parlay_data, "multi_game")

        logger.info(f"Generated {len(results)} cross-game parlays")
        return results

    def generate_combo_parlays(
        self,
        days_ahead: int = 1,
        min_ev: float = 0.10,
        limit: int = 20
    ) -> List[Dict]:
        """
        Generate 4-leg combo parlays by combining two 2-leg parlays.

        Combines the best 2-leg cross-game parlays into higher-payout
        4-leg combo parlays.

        Args:
            days_ahead: Number of days ahead to look for predictions
            min_ev: Minimum expected value for component 2-leg parlays
            limit: Maximum number of combo parlays to return

        Returns:
            List of generated 4-leg combo parlay dictionaries
        """
        # First, generate 2-leg cross-game parlays
        two_leg_parlays = self.generate_cross_game_parlays(
            days_ahead=days_ahead,
            min_confidence=0.65,
            min_ev=min_ev,
            limit=limit * 2  # Get more to have better combinations
        )

        if len(two_leg_parlays) < 2:
            logger.warning("Need at least 2 two-leg parlays to create combos")
            return []

        generated_combos = []

        # Combine pairs of 2-leg parlays into 4-leg combos
        for i in range(len(two_leg_parlays)):
            for j in range(i + 1, len(two_leg_parlays)):
                parlay1 = two_leg_parlays[i]
                parlay2 = two_leg_parlays[j]

                # Combine legs from both parlays
                combined_legs = parlay1["legs"] + parlay2["legs"]

                # Check for duplicate player-stat combinations
                leg_signatures = set()
                has_duplicate = False
                for leg in combined_legs:
                    signature = f"{leg['player_id']}_{leg['stat_type']}"
                    if signature in leg_signatures:
                        has_duplicate = True
                        break
                    leg_signatures.add(signature)

                if has_duplicate:
                    continue  # Skip combinations with duplicates

                # Calculate combo parlay metrics
                combo = self._create_parlay_from_predictions(
                    predictions=combined_legs,
                    parlay_type="multi_game",
                    correlation_bonus=0.0  # Independent across games
                )

                if combo and combo["expected_value"] >= min_ev * 1.5:  # Higher EV threshold for 4-leg
                    combo["source_parlays"] = [parlay1.get("id"), parlay2.get("id")]
                    generated_combos.append(combo)

        # Sort by expected value and return top results
        generated_combos.sort(key=lambda x: x["expected_value"], reverse=True)
        results = generated_combos[:limit]

        # Save parlays to database
        for parlay_data in results:
            self._save_parlay(parlay_data, "multi_game")

        logger.info(f"Generated {len(results)} 4-leg combo parlays")
        return results

    def get_parlays(
        self,
        parlay_type: Optional[str] = None,
        min_ev: Optional[float] = None,
        min_confidence: Optional[float] = None,
        game_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Retrieve parlays from database with optional filtering.

        Args:
            parlay_type: Filter by parlay type ('same_game' or 'multi_game')
            min_ev: Filter by minimum expected value
            min_confidence: Filter by minimum confidence score
            game_id: Filter by specific game ID
            limit: Maximum number of results

        Returns:
            List of parlay dictionaries
        """
        query = self.db.query(Parlay)

        if parlay_type:
            query = query.filter(Parlay.parlay_type == parlay_type)

        if min_ev is not None:
            query = query.filter(Parlay.expected_value >= min_ev)

        if min_confidence is not None:
            query = query.filter(Parlay.confidence_score >= min_confidence)

        if game_id:
            # Filter by parlays that have legs from this game
            query = query.join(ParlayLeg).join(Prediction).filter(
                Prediction.game_id == game_id
            )

        query = query.order_by(Parlay.expected_value.desc())
        parlays = query.limit(limit).all()

        results = []
        for parlay in parlays:
            results.append(self._parlay_to_dict(parlay))

        return results

    def get_parlay_details(self, parlay_id: str) -> Optional[Dict]:
        """Get detailed information about a specific parlay."""
        from sqlalchemy.orm import selectinload

        parlay = (
            self.db.query(Parlay)
            .options(
                selectinload(Parlay.legs).selectinload(ParlayLeg.prediction)
            )
            .filter(Parlay.id == parlay_id)
            .first()
        )
        if not parlay:
            return None
        return self._parlay_to_dict(parlay, include_legs=True)

    def cleanup_old_parlays(self, days_old: int = 7) -> int:
        """
        Delete parlays older than specified days.

        Args:
            days_old: Number of days to keep parlays

        Returns:
            Number of parlays deleted
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        deleted = self.db.query(Parlay).filter(
            Parlay.created_at < cutoff_date
        ).delete()
        self.db.commit()
        logger.info(f"Deleted {deleted} old parlays")
        return deleted

    # ===== Private Helper Methods =====

    def _get_game_predictions(
        self,
        game_id: str,
        min_confidence: float,
        has_odds: bool = False
    ) -> List[Dict]:
        """Get predictions for a specific game.

        Args:
            game_id: Database UUID of the game
            min_confidence: Minimum confidence score
            has_odds: Whether to filter for predictions with odds
        """
        query = (
            self.db.query(Prediction, Player, Game)
            .join(Player, Prediction.player_id == Player.id)
            .join(Game, Prediction.game_id == Game.id)
            .filter(Prediction.game_id == game_id)
            .filter(Prediction.confidence >= min_confidence)
            .filter(Prediction.recommendation.in_(["OVER", "UNDER"]))
        )

        if has_odds:
            query = query.filter(
                and_(
                    Prediction.over_price.isnot(None),
                    Prediction.under_price.isnot(None)
                )
            )

        results = query.all()
        return [self._prediction_to_dict(p, player, game) for p, player, game in results]

    def _get_upcoming_predictions(
        self,
        days_ahead: int,
        min_confidence: float,
        has_odds: bool = False
    ) -> List[Dict]:
        """Get predictions for upcoming games.

        Args:
            days_ahead: Number of days ahead to look
            min_confidence: Minimum confidence score
            has_odds: Whether to filter for predictions with odds
        """
        start_date = date.today()
        end_date = start_date + timedelta(days=days_ahead)

        query = (
            self.db.query(Prediction, Player, Game)
            .join(Player, Prediction.player_id == Player.id)
            .join(Game, Prediction.game_id == Game.id)
            .filter(
                Game.game_date >= start_date,
                Game.game_date <= end_date,
                Prediction.confidence >= min_confidence,
                Prediction.recommendation.in_(["OVER", "UNDER"])
            )
        )

        if has_odds:
            query = query.filter(
                and_(
                    Prediction.over_price.isnot(None),
                    Prediction.under_price.isnot(None)
                )
            )

        results = query.all()
        return [self._prediction_to_dict(p, player, game) for p, player, game in results]

    def _group_predictions_by_player(self, predictions: List[Dict]) -> Dict[str, List[Dict]]:
        """Group predictions by player ID."""
        grouped = {}
        for pred in predictions:
            player_id = pred["player_id"]
            if player_id not in grouped:
                grouped[player_id] = []
            grouped[player_id].append(pred)
        return grouped

    def _group_predictions_by_game(self, predictions: List[Dict]) -> Dict[str, List[Dict]]:
        """Group predictions by game ID."""
        grouped = {}
        for pred in predictions:
            game_id = pred["game_id"]
            if game_id not in grouped:
                grouped[game_id] = []
            grouped[game_id].append(pred)
        return grouped

    def _calculate_parlay_metrics(
        self,
        legs: List[Dict],
        correlation_bonus: float = 0.0
    ) -> Optional[Dict]:
        """
        Calculate odds, probability, and EV for a parlay.

        Uses odds-implied probabilities adjusted for vigorish, not confidence scores.
        For parlays: P(A and B) = P(A) × P(B), not average.
        """
        if not legs:
            return None

        # Get decimal odds for each leg (legs now have 'odds' key directly)
        leg_decimal_odds = []
        for leg in legs:
            decimal_odds = self._american_to_decimal(leg["odds"])
            leg_decimal_odds.append(decimal_odds)

        # Calculate parlay odds (product of all leg odds)
        parlay_decimal = 1.0
        for odds in leg_decimal_odds:
            parlay_decimal *= odds

        parlay_american = self._decimal_to_american(parlay_decimal)
        implied_prob = 1.0 / parlay_decimal

        # Calculate true probability from odds (accounting for vigorish)
        # Bookmaker implied probability includes ~5% vigorish
        VIGORISH_ADJUSTMENT = 0.95

        # Individual leg probabilities from odds (adjusted for vigorish)
        leg_probabilities = []
        for decimal_odds in leg_decimal_odds:
            leg_implied_prob = 1.0 / decimal_odds
            leg_true_prob = leg_implied_prob * VIGORISH_ADJUSTMENT
            leg_probabilities.append(leg_true_prob)

        # Calculate parlay probability (PRODUCT of individual probabilities)
        # For independent events: P(A and B) = P(A) × P(B)
        parlay_prob = 1.0
        for prob in leg_probabilities:
            parlay_prob *= prob

        # Apply correlation bonus (correlated legs increase win probability)
        # Correlation ranges 0.0 to 0.7, so max boost is 35%
        if correlation_bonus > 0:
            correlation_multiplier = 1.0 + (correlation_bonus * 0.5)
            parlay_prob *= correlation_multiplier

        # Cap parlay probability at 90% (conservative cap for correlated events)
        parlay_prob = min(parlay_prob, 0.90)

        # EV = (true_prob × parlay_decimal) - 1
        ev = (parlay_prob * parlay_decimal) - 1

        # Average confidence is still useful for display/sorting
        avg_confidence = sum(leg["confidence"] for leg in legs) / len(legs)

        return {
            "legs": legs,
            "total_legs": len(legs),
            "calculated_odds": parlay_american,
            "decimal_odds": parlay_decimal,
            "implied_probability": implied_prob,
            "true_probability": parlay_prob,
            "expected_value": ev,
            "confidence_score": avg_confidence,
            "correlation_score": correlation_bonus
        }

    def _calculate_same_player_correlation(self, predictions: List[Dict]) -> float:
        """Calculate average correlation for same-player stat combinations."""
        if len(predictions) < 2:
            return 0.0

        stat_types = [p["stat_type"] for p in predictions]
        total_correlation = 0.0
        count = 0

        for i, stat1 in enumerate(stat_types):
            for stat2 in stat_types[i+1:]:
                key = tuple(sorted((stat1, stat2)))
                correlation = SAME_PLAYER_CORRELATIONS.get(key, 0.0)
                total_correlation += correlation
                count += 1

        return total_correlation / count if count > 0 else 0.0

    def _calculate_teammate_correlation(self, stat_type_1: str, stat_type_2: str) -> float:
        """Get correlation coefficient for teammate stat combinations."""
        key = (stat_type_1, stat_type_2)
        return TEAMMATE_CORRELATIONS.get(key, 0.0)

    def _create_parlay_from_predictions(
        self,
        predictions: List[Dict],
        parlay_type: str,
        correlation_bonus: float
    ) -> Optional[Dict]:
        """Create a parlay dict from a list of predictions.

        All legs must be from the same bookmaker for valid parlays.
        """
        # Check that all predictions have odds from the same bookmaker
        bookmakers = set()
        for pred in predictions:
            if pred.get("bookmaker_name"):
                bookmakers.add(pred["bookmaker_name"])

        # Skip if no bookmaker info, or if multiple bookmakers are involved
        if not bookmakers or len(bookmakers) > 1:
            logger.debug(f"Skipping parlay: inconsistent bookmakers {bookmakers}")
            return None

        # Build enriched legs data first
        legs_data = []
        for pred in predictions:
            odds = pred["over_price"] if pred["recommendation"] == "OVER" else pred["under_price"]
            legs_data.append({
                "player_id": pred["player_id"],
                "player_name": pred["player_name"],
                "team": pred["team"],
                "game_id": pred["game_id"],
                "stat_type": pred["stat_type"],
                "selection": pred["recommendation"],
                "line": pred["bookmaker_line"],
                "odds": odds,
                "confidence": pred["confidence"],
                "prediction_id": pred["id"],
                "bookmaker_name": pred["bookmaker_name"]
            })

        # Calculate metrics using legs_data
        metrics = self._calculate_parlay_metrics(legs_data, correlation_bonus)
        if not metrics:
            return None

        # Replace the legs in metrics with our enriched legs_data
        metrics["legs"] = legs_data

        return {
            "parlay_type": parlay_type,
            **metrics
        }

    def _save_parlay(self, parlay_data: Dict, parlay_type: str) -> str:
        """Save a parlay to the database."""
        parlay = Parlay(
            id=str(uuid.uuid4()),
            parlay_type=parlay_type,
            calculated_odds=parlay_data["calculated_odds"],
            implied_probability=parlay_data["implied_probability"],
            expected_value=parlay_data["expected_value"],
            confidence_score=parlay_data["confidence_score"],
            total_legs=parlay_data["total_legs"],
            correlation_score=parlay_data["correlation_score"],
            created_at=datetime.utcnow()
        )

        self.db.add(parlay)
        self.db.flush()  # Get the parlay ID

        # Create legs
        for i, leg_data in enumerate(parlay_data["legs"]):
            leg = ParlayLeg(
                id=str(uuid.uuid4()),
                parlay_id=parlay.id,
                prediction_id=leg_data["prediction_id"],
                leg_order=i,
                selection=leg_data["selection"],
                leg_odds=leg_data["odds"],
                leg_confidence=leg_data["confidence"],
                correlation_with_parlay=parlay_data["correlation_score"],
                created_at=datetime.utcnow()
            )
            self.db.add(leg)

        self.db.commit()
        logger.debug(f"Saved parlay {parlay.id} with {len(parlay_data['legs'])} legs")
        return str(parlay.id)

    def _parlay_to_dict(self, parlay: Parlay, include_legs: bool = False) -> Dict:
        """Convert Parlay model to dictionary."""
        result = {
            "id": str(parlay.id),
            "parlay_type": parlay.parlay_type,
            "calculated_odds": int(parlay.calculated_odds) if parlay.calculated_odds >= 0 else parlay.calculated_odds,
            "implied_probability": round(parlay.implied_probability, 4),
            "expected_value": round(parlay.expected_value, 4),
            "expected_value_percent": round(parlay.expected_value * 100, 2),
            "confidence_score": round(parlay.confidence_score, 3),
            "total_legs": parlay.total_legs,
            "correlation_score": round(parlay.correlation_score, 3) if parlay.correlation_score else None,
            "created_at": parlay.created_at.isoformat()
        }

        if include_legs:
            result["legs"] = []
            for leg in sorted(parlay.legs, key=lambda x: x.leg_order):
                pred = leg.prediction

                # Always fetch game directly to avoid lazy loading issues
                game = self.db.query(Game).filter(Game.id == pred.game_id).first()

                # Convert stored odds to American format for display
                leg_odds = leg.leg_odds
                if abs(leg_odds) < 10:
                    # Stored as decimal - convert to American
                    display_odds = self._decimal_to_american(leg_odds)
                else:
                    # Already stored as American
                    display_odds = int(leg_odds)

                leg_data = {
                    "leg_order": leg.leg_order,
                    "player": pred.player.name if pred.player else "Unknown",
                    "team": pred.player.team if pred.player else "UNK",
                    "stat_type": pred.stat_type,
                    "selection": leg.selection,
                    "line": pred.bookmaker_line,
                    "predicted_value": pred.predicted_value,
                    "odds": display_odds,
                    "confidence": round(leg.leg_confidence, 3),
                    "correlation_with_parlay": round(leg.correlation_with_parlay, 3) if leg.correlation_with_parlay else None
                }

                if game:
                    central_time = utc_to_central(game.game_date)
                    leg_data["game"] = {
                        "id": str(game.id),
                        "matchup": f"{game.away_team} @ {game.home_team}",
                        "date_utc": game.game_date.isoformat(),
                        "date_central": central_time.isoformat(),
                        "date_display": format_game_time_central(game.game_date),
                        "status": game.status
                    }

                result["legs"].append(leg_data)

        return result

    def _prediction_to_dict(self, pred: Prediction, player: Player, game: Game) -> Dict:
        """Convert Prediction model to dictionary."""
        return {
            "id": str(pred.id),
            "player_id": str(player.id),
            "player_name": player.name,
            "team": player.team,
            "game_id": str(game.id),
            "stat_type": pred.stat_type,
            "predicted_value": pred.predicted_value,
            "bookmaker_line": pred.bookmaker_line,
            "bookmaker_name": pred.bookmaker_name,
            "recommendation": pred.recommendation,
            "confidence": pred.confidence,
            "over_price": pred.over_price,
            "under_price": pred.under_price
        }

    def _american_to_decimal(self, odds: float) -> float:
        """
        Convert odds to decimal format.

        Auto-detects input format:
        - American odds: |value| >= 100 (e.g., -110, +200)
        - Decimal odds: value < 10 (e.g., 1.91, 2.50)

        Args:
            odds: American or decimal odds

        Returns:
            Decimal odds
        """
        # Detect format: if abs(value) >= 100, it's American odds
        if abs(odds) >= 100:
            # American odds conversion
            if odds > 0:
                return (odds / 100) + 1
            else:
                return (100 / abs(odds)) + 1
        else:
            # Already decimal odds
            return odds

    def _decimal_to_american(self, decimal: float) -> int:
        """Convert decimal odds to American odds."""
        if decimal >= 2.0:
            return int(round((decimal - 1) * 100))
        else:
            return int(round(-100 / (decimal - 1)))


def _product_of_top_predictions(predictions_per_game: List[List[Dict]]) -> List[List[Dict]]:
    """
    Generate all combinations of picking one prediction from each game's list.
    Helper for multi-game parlay generation.
    """
    if not predictions_per_game:
        return []

    result = [[]]
    for predictions in predictions_per_game:
        new_result = []
        for existing in result:
            for pred in predictions:
                new_result.append(existing + [pred])
        result = new_result

    return result
