"""
Parlay Builder for creating correlated multi-leg bets.

Identifies high-confidence picks that correlate well together for
building smart 2-leg and 3-leg parlays.

CORRELATION STRATEGY:
- Same-player parlays have highest correlation (points + assists)
- Same-team parlays have medium correlation
- Different teams have lowest correlation (avoid unless very high confidence)

PARLAY RULES:
2-Leg Parlays (20% of action):
- Min 75% confidence per leg
- Prefer correlated stats (same player)
- Fixed $10 wager per parlay
- Max 5 parlays per day

3-Leg Parlays (10% of action):
- Min 80% confidence per leg
- Different players only (risk management)
- Fixed $5 wager per parlay (higher risk, smaller wager)
- Max 2 parlays per day
"""
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from app.core.logging import get_logger

logger = get_logger(__name__)


class ParlayBuilder:
    """
    Build smart parlays from high-confidence predictions.

    Uses correlation matrices to identify optimal parlay combinations
    and calculates expected value for each parlay.
    """

    # Correlation weights for different stat combinations
    # Higher value = higher correlation
    CORRELATION_MATRIX = {
        # Same player - very high correlation
        ("points", "assists"): 0.85,     # Guards/playmakers
        ("points", "threes"): 0.80,      # Shooters
        ("points", "rebounds"): 0.70,    # All-around players
        ("assists", "threes"): 0.60,     # Ballhandlers
        ("rebounds", "assists"): 0.65,   # Point-forwards

        # NHL specific
        ("goals", "assists"): 0.85,      # Points = goals + assists
        ("goals", "shots"): 0.75,        # Shooters score more
        ("assists", "points"): 0.90,     # Very high (points includes assists)
        ("goals", "points"): 0.90,       # Very high (points includes goals)

        # Cross-player (same team) - medium correlation
        ("teammate_points", "teammate_points"): 0.5,  # High-scoring game

        # Cross-player (different teams) - low correlation
        ("opponent", "opponent"): 0.1,  # Independent outcomes
    }

    # Fixed wager amounts
    TWO_LEG_WAGER = 10.0
    THREE_LEG_WAGER = 5.0

    def __init__(self):
        """Initialize the parlay builder."""
        self.two_leg_wager = self.TWO_LEG_WAGER
        self.three_leg_wager = self.THREE_LEG_WAGER

    def build_two_leg_parlays(
        self,
        predictions: List[Dict],
        min_confidence: float = 0.75,
        max_parlays: int = 5
    ) -> List[Dict]:
        """
        Build 2-leg parlays from high-confidence predictions.

        Strategy:
        1. Prioritize same-player parlays (highest correlation)
        2. Then consider same-team parlays (medium correlation)
        3. Avoid cross-team parlays unless very high confidence

        Args:
            predictions: List of prediction dicts with:
                - player_id, player_name, team
                - stat_type, confidence, line
                - sport (nba/nhl)
            min_confidence: Minimum confidence for parlay legs
            max_parlays: Maximum number of parlays to return

        Returns:
            List of parlay dicts with legs, combined_confidence, wager, ev
        """
        parlays = []
        high_conf = [p for p in predictions if p.get("confidence", 0) >= min_confidence]

        logger.info(f"Building 2-leg parlays from {len(high_conf)} high-confidence predictions")

        # Group by player to find same-player correlations
        by_player = {}
        for pred in high_conf:
            player_id = pred.get("player_id")
            if player_id not in by_player:
                by_player[player_id] = []
            by_player[player_id].append(pred)

        # Build same-player parlays first (highest correlation)
        for player_id, player_preds in by_player.items():
            if len(player_preds) >= 2:
                player_parlays = self._build_same_player_parlays(
                    player_preds, min_confidence, legs=2
                )
                parlays.extend(player_parlays)

        # If we have room, build same-team parlays
        if len(parlays) < max_parlays:
            remaining = max_parlays - len(parlays)
            team_parlays = self._build_same_team_parlays(
                high_conf, min_confidence, legs=2, max_parlays=remaining
            )
            parlays.extend(team_parlays)

        # Sort by expected value and return top N
        parlays.sort(key=lambda x: x.get("expected_value", 0), reverse=True)
        return parlays[:max_parlays]

    def build_three_leg_parlays(
        self,
        predictions: List[Dict],
        min_confidence: float = 0.80,
        max_parlays: int = 2
    ) -> List[Dict]:
        """
        Build 3-leg parlays from VERY high-confidence predictions.

        Strategy:
        - All legs must be on different players (risk management)
        - Higher confidence threshold (80%+)
        - Smaller wager due to higher risk

        Args:
            predictions: List of prediction dicts
            min_confidence: Minimum confidence for parlay legs
            max_parlays: Maximum number of parlays to return

        Returns:
            List of 3-leg parlay dicts
        """
        parlays = []
        high_conf = [p for p in predictions if p.get("confidence", 0) >= min_confidence]

        logger.info(f"Building 3-leg parlays from {len(high_conf)} very high-confidence predictions")

        # Build combinations across different players
        for i, pred1 in enumerate(high_conf):
            for j, pred2 in enumerate(high_conf[i+1:], i+1):
                if pred2.get("player_id") == pred1.get("player_id"):
                    continue  # Skip same player

                for k, pred3 in enumerate(high_conf[j+1:], j+1):
                    if pred3.get("player_id") in [pred1.get("player_id"), pred2.get("player_id")]:
                        continue  # Skip same player

                    # Calculate combined confidence (conservative - geometric mean)
                    conf1 = pred1.get("confidence", 0.80)
                    conf2 = pred2.get("confidence", 0.80)
                    conf3 = pred3.get("confidence", 0.80)
                    combined = (conf1 * conf2 * conf3) ** (1/3)

                    # Require combined confidence to still be strong
                    if combined >= 0.75:
                        # Calculate parlay odds
                        parlay = self._create_parlay_dict(
                            [pred1, pred2, pred3],
                            combined,
                            self.three_leg_wager
                        )
                        parlays.append(parlay)

        # Sort by expected value and return top N
        parlays.sort(key=lambda x: x.get("expected_value", 0), reverse=True)
        return parlays[:max_parlays]

    def _build_same_player_parlays(
        self,
        player_preds: List[Dict],
        min_confidence: float,
        legs: int = 2
    ) -> List[Dict]:
        """Build parlays from different stats for the same player."""
        parlays = []

        # Filter to eligible predictions
        eligible = [p for p in player_preds if p.get("confidence", 0) >= min_confidence]

        if len(eligible) < legs:
            return parlays

        # Try all combinations
        for i in range(len(eligible)):
            for j in range(i + 1, len(eligible)):
                pred1 = eligible[i]
                pred2 = eligible[j]

                # Get correlation
                correlation = self._get_correlation(
                    pred1.get("stat_type"),
                    pred2.get("stat_type"),
                    same_player=True
                )

                # Only use if correlation is decent
                if correlation >= 0.6:
                    # Combined confidence (geometric mean)
                    combined = (
                        pred1.get("confidence", 0.75) *
                        pred2.get("confidence", 0.75)
                    ) ** 0.5

                    parlay = self._create_parlay_dict(
                        [pred1, pred2],
                        combined,
                        self.two_leg_wager,
                        correlation
                    )
                    parlays.append(parlay)

        return parlays

    def _build_same_team_parlays(
        self,
        predictions: List[Dict],
        min_confidence: float,
        legs: int = 2,
        max_parlays: int = 5
    ) -> List[Dict]:
        """Build parlays from different players on the same team."""
        parlays = []

        # Group by team
        by_team = {}
        for pred in predictions:
            team = pred.get("team")
            player_id = pred.get("player_id")

            # Initialize team entry
            if team not in by_team:
                by_team[team] = {}

            # Add prediction if we don't have this player yet
            if player_id not in by_team[team]:
                by_team[team][player_id] = pred

        # Build parlays within each team
        for team, team_players in by_team.items():
            if len(team_players) < 2:
                continue

            team_preds = list(team_players.values())

            # Try combinations
            for i in range(len(team_preds)):
                for j in range(i + 1, len(team_preds)):
                    pred1 = team_preds[i]
                    pred2 = team_preds[j]

                    # Check confidence
                    if (pred1.get("confidence", 0) >= min_confidence and
                        pred2.get("confidence", 0) >= min_confidence):

                        # Same-team correlation (moderate)
                        correlation = 0.4

                        # Combined confidence
                        combined = (
                            pred1.get("confidence", 0.75) *
                            pred2.get("confidence", 0.75)
                        ) ** 0.5

                        parlay = self._create_parlay_dict(
                            [pred1, pred2],
                            combined,
                            self.two_leg_wager,
                            correlation
                        )
                        parlays.append(parlay)

                        if len(parlays) >= max_parlays:
                            return parlays

        return parlays

    def _create_parlay_dict(
        self,
        legs: List[Dict],
        combined_confidence: float,
        wager: float,
        correlation: float = 0.5
    ) -> Dict:
        """
        Create a parlay dictionary with all necessary fields.

        Args:
            legs: List of prediction dicts
            combined_confidence: Combined confidence of all legs
            wager: Wager amount
            correlation: Correlation coefficient (0-1)

        Returns:
            Parlay dict
        """
        num_legs = len(legs)

        # Calculate parlay odds (assuming -110 per leg)
        # For 2-leg: (-110 * -110) = +264
        # For 3-leg: (-110 * -110 * -110) = +596
        if num_legs == 2:
            american_odds = 264
            decimal_odds = 3.64
        elif num_legs == 3:
            american_odds = 596
            decimal_odds = 6.96
        else:
            # Generic calculation
            decimal_odds = (1.91 ** num_legs)
            american_odds = int((decimal_odds - 1) * 100)

        # Calculate expected value
        # EV = (win_prob * profit) - (lose_prob * wager)
        win_prob = combined_confidence
        lose_prob = 1 - win_prob
        profit = wager * (decimal_odds - 1)
        expected_value = (win_prob * profit) - (lose_prob * wager)

        return {
            "legs": [
                {
                    "player": leg.get("player"),
                    "player_id": leg.get("player_id"),
                    "team": leg.get("team"),
                    "stat_type": leg.get("stat_type"),
                    "line": leg.get("line"),
                    "recommendation": leg.get("recommendation"),
                    "confidence": leg.get("confidence"),
                    "sport": leg.get("sport", "unknown")
                }
                for leg in legs
            ],
            "num_legs": num_legs,
            "correlation": round(correlation, 2),
            "combined_confidence": round(combined_confidence, 2),
            "american_odds": american_odds,
            "decimal_odds": round(decimal_odds, 2),
            "wager": wager,
            "to_win": round(profit, 2),
            "expected_value": round(expected_value, 2),
            "created_at": datetime.utcnow().isoformat()
        }

    def _get_correlation(
        self,
        stat1: str,
        stat2: str,
        same_player: bool = False
    ) -> float:
        """
        Get correlation between two stat types.

        Args:
            stat1: First stat type
            stat2: Second stat type
            same_player: Whether stats are for same player

        Returns:
            Correlation coefficient (0-1)
        """
        if same_player:
            # Check both orderings
            key1 = (stat1, stat2)
            key2 = (stat2, stat1)

            correlation = self.CORRELATION_MATRIX.get(key1) or \
                          self.CORRELATION_MATRIX.get(key2, 0.0)

            return max(0.0, min(1.0, correlation))
        else:
            # Different players = lower correlation
            return 0.3  # Moderate baseline for same-team

    def get_parlay_count_limits(self) -> Dict:
        """
        Get daily parlay count limits by type.

        Returns:
            Dict with max_parlays for each parlay type
        """
        return {
            "two_leg_max": 5,
            "three_leg_max": 2,
            "total_parlay_max": 7
        }


def get_parlay_builder() -> ParlayBuilder:
    """Get a ParlayBuilder instance."""
    return ParlayBuilder()
