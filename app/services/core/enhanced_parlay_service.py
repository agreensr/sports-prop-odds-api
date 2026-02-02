"""
Phase 4: Enhanced Parlay Service

Generates 2-leg parlays from the top 10 single bets.

Key Changes from Original Parlay Service:
- Source: TOP 10 SINGLE BETS (not raw predictions)
- Focus: 2-leg parlays ONLY (no 3+ legs)
- Allowed: Same-game parlays (any combination)
- Allowed: Cross-game parlays
- Target: 3-5 parlays daily
- Filter: Parlay EV ≥ 8%
- Rank: By EV
"""
import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
from itertools import combinations
from dataclasses import dataclass, asdict
from enum import Enum
from sqlalchemy.orm import Session

from app.services.core.single_bet_service import SingleBetService, SingleBet

logger = logging.getLogger(__name__)


class ParlayRecommendation(Enum):
    """Parlay recommendation types."""
    SAME_GAME = "same_game"
    CROSS_GAME = "cross_game"


@dataclass
class ParlayBet:
    """Represents a 2-leg parlay recommendation."""
    id: str
    parlay_type: str  # "same_game" or "cross_game"
    legs: List[Dict]
    total_legs: int
    calculated_odds: int  # American odds
    decimal_odds: float
    implied_probability: float
    true_probability: float
    expected_value: float
    ev_percent: float
    confidence_score: float
    correlation_score: float
    created_at: datetime

    def __repr__(self):
        legs_str = " + ".join([
            f"{l['player_name'][:12]} {l['stat_type'][:4]} {l['recommendation'][:4]} {l['line']}"
            for l in self.legs
        ])
        return (f"ParlayBet({self.total_legs} legs | {self.ev_percent:+.1f}% EV | "
                f"{self.calculated_odds} | {legs_str})")


class EnhancedParlayService:
    """
    Enhanced parlay service that generates 2-leg parlays from top single bets.

    Strategy:
    - Source: Top 10 single bets from SingleBetService
    - Type: 2-leg parlays ONLY
    - Same-game: ALLOWED (any combination)
    - Cross-game: ALLOWED
    - Filter: Parlay EV ≥ 8%
    - Limit: Top 5 parlays
    - Rank: By EV (descending)
    """

    MIN_PARLAY_EV = 0.08  # 8% minimum EV for parlays
    MAX_PARLAYS = 5
    LEGS_PER_PARLAY = 2

    # Same-player stat correlations (for same-game parlays)
    SAME_PLAYER_CORRELATIONS = {
        ("points", "assists"): 0.65,
        ("points", "rebounds"): 0.55,
        ("points", "threes"): 0.70,
        ("assists", "threes"): 0.45,
        ("rebounds", "assists"): 0.35,
    }

    def __init__(self, db: Session):
        """
        Initialize the enhanced parlay service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self.single_bet_service = SingleBetService(db)

    def generate_daily_parlays(
        self,
        target_date: Optional[date] = None,
        sport_id: Optional[str] = None
    ) -> List[ParlayBet]:
        """
        Generate 2-leg parlays from the top 10 single bets.

        Args:
            target_date: Date to generate parlays for (default: today)
            sport_id: Filter by sport (default: all sports)

        Returns:
            List of ParlayBet objects, ranked by EV
        """
        if target_date is None:
            target_date = date.today()

        logger.info(f"Generating 2-leg parlays for {target_date}, sport={sport_id or 'all'}")

        # Step 1: Get top 10 single bets
        single_bets = self.single_bet_service.generate_daily_bets(
            target_date=target_date,
            sport_id=sport_id
        )

        if not single_bets:
            logger.warning("No single bets available for parlay generation")
            return []

        logger.info(f"Found {len(single_bets)} single bets to use as parlay legs")

        # Step 2: Generate all 2-leg combinations
        all_parlays = []

        # Generate same-game parlays
        same_game_parlays = self._generate_same_game_parlays(single_bets)
        all_parlays.extend(same_game_parlays)
        logger.info(f"Generated {len(same_game_parlays)} same-game parlay combinations")

        # Generate cross-game parlays
        cross_game_parlays = self._generate_cross_game_parlays(single_bets)
        all_parlays.extend(cross_game_parlays)
        logger.info(f"Generated {len(cross_game_parlays)} cross-game parlay combinations")

        if not all_parlays:
            logger.warning("No parlays generated")
            return []

        # Step 3: Filter by EV threshold
        qualified_parlays = [
            p for p in all_parlays
            if p.ev_percent >= (self.MIN_PARLAY_EV * 100)
        ]
        logger.info(f"{len(qualified_parlays)} parlays meet EV threshold ({self.MIN_PARLAY_EV * 100:.0f}%)")

        if not qualified_parlays:
            logger.info("No parlays meet the minimum EV threshold")
            return []

        # Step 4: Rank by EV and limit
        qualified_parlays.sort(key=lambda p: p.ev_percent, reverse=True)
        final_parlays = qualified_parlays[:self.MAX_PARLAYS]

        logger.info(f"Selected top {len(final_parlays)} parlays")
        for i, parlay in enumerate(final_parlays, 1):
            logger.info(f"  {i}. {parlay}")

        return final_parlays

    def _generate_same_game_parlays(self, single_bets: List[SingleBet]) -> List[ParlayBet]:
        """Generate same-game 2-leg parlays from single bets."""
        parlays = []

        # Group bets by game
        game_bets = {}
        for bet in single_bets:
            game_key = (bet.game_date.date(), bet.team, bet.opponent)
            if game_key not in game_bets:
                game_bets[game_key] = []
            game_bets[game_key].append(bet)

        # Generate 2-leg combinations within each game
        for game_key, bets in game_bets.items():
            if len(bets) < 2:
                continue

            # Generate all combinations of 2
            for bet1, bet2 in combinations(bets, 2):
                # Check if these are compatible (same bookmaker, no conflicts)
                if self._are_bets_compatible(bet1, bet2):
                    parlay = self._create_parlay_from_bets(
                        [bet1, bet2],
                        parlay_type="same_game"
                    )
                    if parlay:
                        parlays.append(parlay)

        return parlays

    def _generate_cross_game_parlays(self, single_bets: List[SingleBet]) -> List[ParlayBet]:
        """Generate cross-game 2-leg parlays from single bets."""
        parlays = []

        # Generate all combinations of 2 from different games
        for i, bet1 in enumerate(single_bets):
            for bet2 in single_bets[i+1:]:
                # Skip if same game
                if (bet1.game_date.date(), bet1.team, bet1.opponent) == \
                   (bet2.game_date.date(), bet2.team, bet2.opponent):
                    continue

                # Check if compatible
                if self._are_bets_compatible(bet1, bet2):
                    parlay = self._create_parlay_from_bets(
                        [bet1, bet2],
                        parlay_type="cross_game"
                    )
                    if parlay:
                        parlays.append(parlay)

        return parlays

    def _are_bets_compatible(self, bet1: SingleBet, bet2: SingleBet) -> bool:
        """
        Check if two bets can be combined into a parlay.

        Rules:
        - Same bookmaker required
        - Different player + stat combination (can't bet same thing twice)
        """
        # Same bookmaker required
        if bet1.bookmaker_name != bet2.bookmaker_name:
            return False

        # Different players OR different stats
        if (bet1.player_name == bet2.player_name and
            bet1.stat_type == bet2.stat_type):
            return False

        return True

    def _create_parlay_from_bets(
        self,
        bets: List[SingleBet],
        parlay_type: str
    ) -> Optional[ParlayBet]:
        """
        Create a parlay from a list of single bets.

        Args:
            bets: List of SingleBet objects (2 legs)
            parlay_type: "same_game" or "cross_game"

        Returns:
            ParlayBet or None if creation fails
        """
        if len(bets) != 2:
            logger.warning(f"Parlay must have exactly 2 legs, got {len(bets)}")
            return None

        # Calculate correlation for same-game parlays
        correlation_score = 0.0
        if parlay_type == "same_game":
            correlation_score = self._calculate_correlation(bets)

        # Convert SingleBets to leg dictionaries
        legs = []
        for bet in bets:
            leg = {
                "player_id": bet.id,
                "player_name": bet.player_name,
                "team": bet.team,
                "opponent": bet.opponent,
                "game_date": bet.game_date,
                "stat_type": bet.stat_type,
                "predicted_value": bet.predicted_value,
                "line": bet.bookmaker_line,
                "recommendation": bet.recommendation.value,
                "bookmaker_name": bet.bookmaker_name,
                "odds_american": bet.odds_american,
                "odds_decimal": bet.odds_decimal,
                "confidence": bet.confidence,
                "edge_percent": bet.edge_percent,
                "ev_percent": bet.ev_percent
            }
            legs.append(leg)

        # Calculate parlay metrics
        metrics = self._calculate_parlay_metrics(
            legs,
            correlation_score
        )

        if not metrics:
            return None

        # Create ParlayBet object
        parlay = ParlayBet(
            id=f"parlay_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hash(str(legs)) & 0xFFFFFF:06x}",
            parlay_type=parlay_type,
            legs=legs,
            total_legs=len(legs),
            calculated_odds=metrics["calculated_odds"],
            decimal_odds=metrics["decimal_odds"],
            implied_probability=metrics["implied_probability"],
            true_probability=metrics["true_probability"],
            expected_value=metrics["expected_value"],
            ev_percent=metrics["ev_percent"],
            confidence_score=metrics["confidence_score"],
            correlation_score=correlation_score,
            created_at=datetime.now()
        )

        return parlay

    def _calculate_parlay_metrics(
        self,
        legs: List[Dict],
        correlation_score: float
    ) -> Optional[Dict]:
        """
        Calculate odds, probability, and EV for a 2-leg parlay.

        Args:
            legs: List of leg dictionaries
            correlation_score: Correlation between legs (0.0 to 1.0)

        Returns:
            Dictionary with parlay metrics or None if calculation fails
        """
        if len(legs) != 2:
            return None

        try:
            # Get decimal odds for each leg
            odds1 = legs[0]["odds_decimal"]
            odds2 = legs[1]["odds_decimal"]

            # Calculate parlay decimal odds (product)
            parlay_decimal = odds1 * odds2

            # Convert to American odds
            if parlay_decimal >= 2.0:
                parlay_american = int((parlay_decimal - 1) * 100)
            else:
                parlay_american = int(-100 / (parlay_decimal - 1))

            # Implied probability from bookmaker
            implied_prob = 1.0 / parlay_decimal

            # True probability (accounting for vigorish)
            VIG_ADJUSTMENT = 0.95
            prob1 = (1.0 / odds1) * VIG_ADJUSTMENT
            prob2 = (1.0 / odds2) * VIG_ADJUSTMENT

            # Parlay probability (product for independent events)
            parlay_prob = prob1 * prob2

            # Apply correlation bonus (correlated legs increase win prob)
            if correlation_score > 0:
                correlation_multiplier = 1.0 + (correlation_score * 0.5)
                parlay_prob *= correlation_multiplier

            # Cap at 90%
            parlay_prob = min(parlay_prob, 0.90)

            # EV = (true_prob × parlay_decimal) - 1
            ev = (parlay_prob * parlay_decimal) - 1
            ev_percent = ev * 100

            # Average confidence
            avg_confidence = (legs[0]["confidence"] + legs[1]["confidence"]) / 2

            return {
                "calculated_odds": parlay_american,
                "decimal_odds": parlay_decimal,
                "implied_probability": implied_prob,
                "true_probability": parlay_prob,
                "expected_value": ev,
                "ev_percent": ev_percent,
                "confidence_score": avg_confidence,
                "total_legs": len(legs)
            }

        except Exception as e:
            logger.error(f"Error calculating parlay metrics: {e}")
            return None

    def _calculate_correlation(self, bets: List[SingleBet]) -> float:
        """
        Calculate correlation between two bets for same-game parlays.

        Args:
            bets: List of SingleBet objects (2 legs)

        Returns:
            Correlation score (0.0 to 1.0)
        """
        if len(bets) != 2:
            return 0.0

        # Same player, different stats
        if bets[0].player_name == bets[1].player_name:
            stat1 = bets[0].stat_type
            stat2 = bets[1].stat_type
            key = tuple(sorted((stat1, stat2)))
            return self.SAME_PLAYER_CORRELATIONS.get(key, 0.0)

        # Different players - low correlation
        return 0.0

    def format_parlays_for_display(self, parlays: List[ParlayBet]) -> str:
        """
        Format parlays for human-readable display.

        Args:
            parlays: List of ParlayBet objects

        Returns:
            Formatted string with Central Time display
        """
        if not parlays:
            return "No parlays available."

        lines = []
        lines.append(f"🎯 TOP {len(parlays)} 2-LEG PARLAYS - {date.today().strftime('%Y-%m-%d')}")
        lines.append("")
        lines.append(f"Minimum EV: {self.MIN_PARLAY_EV * 100:.0f}% | Max: {self.MAX_PARLAYS} parlays")
        lines.append("")

        for i, parlay in enumerate(parlays, 1):
            # Type indicator
            type_emoji = "🔗" if parlay.parlay_type == "same_game" else "🎲"

            # Format legs
            leg_strs = []
            for leg in parlay.legs:
                from app.utils.timezone import format_central_time
                game_time = format_central_time(leg["game_date"], "%-I:%M %p")
                leg_str = f"{leg['player_name']} ({leg['team']}) {leg['stat_type'][:4]} {leg['recommendation'][:4]} {leg['line']} @ {game_time}"
                leg_strs.append(leg_str)

            lines.append(f"{i}. {type_emoji} {leg_strs[0]}")
            lines.append(f"   + {leg_strs[1]}")
            lines.append(f"   Odds: {parlay.calculated_odds} | EV: {parlay.ev_percent:+.1f}% | Conf: {parlay.confidence_score:.1%}")
            lines.append("")

        return "\n".join(lines)


# Convenience function
def get_enhanced_parlay_service(db: Session) -> EnhancedParlayService:
    """Get an EnhancedParlayService instance."""
    return EnhancedParlayService(db)
