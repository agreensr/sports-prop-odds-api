"""
Opponent Defensive Adjustment Service.

Adjusts predictions based on opponent defensive rankings.

Formula:
    adjusted_prediction = base_prediction × defense_multiplier

Defense multipliers by rank tier:
- Top 5 defense (rank 1-5): 0.90 (-10%)
- 6-10: 0.95 (-5%)
- 11-20: 1.00 (neutral)
- 21-25: 1.05 (+5%)
- 26-30: 1.10 (+10%)

Example:
- Player averages 25 PPG
- Opponent ranks 3rd in points allowed (elite defense)
- Adjusted prediction: 25 × 0.90 = 22.5 PPG
"""
import json
import logging
from pathlib import Path
from typing import Dict, Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class OpponentAdjustmentService:
    """Adjust predictions based on opponent defensive strength."""

    # Defense multipliers based on rank (1-30)
    # Rank 1 = best defense, Rank 30 = worst
    DEFENSE_MULTIPLIERS = {
        (1, 5): 0.90,    # Top 5: -10%
        (6, 10): 0.95,   # 6-10: -5%
        (11, 20): 1.00,  # Average: 0%
        (21, 25): 1.05,  # 21-25: +5%
        (26, 30): 1.10   # Bottom 5: +10%
    }

    # Default rankings (all average) when seed data unavailable
    DEFAULT_RANKINGS = {
        "points": 15,
        "rebounds": 15,
        "assists": 15,
        "threes": 15
    }

    def __init__(self, db: Session):
        """
        Initialize opponent adjustment service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self._rankings = None
        self._load_rankings()

    def _load_rankings(self):
        """Load defensive rankings from seed file."""
        seed_path = Path(__file__).parent.parent.parent / "seeds" / "defensive_rankings_2025-26.json"

        if seed_path.exists():
            try:
                with open(seed_path, 'r') as f:
                    self._rankings = json.load(f)
                logger.info(f"Loaded defensive rankings for {len(self._rankings)} teams")
            except Exception as e:
                logger.error(f"Error loading defensive rankings: {e}")
                self._rankings = {}
        else:
            logger.warning(f"Defensive rankings seed file not found: {seed_path}")
            self._rankings = {}

    def get_opponent_adjustment(
        self,
        opponent_team: str,
        stat_type: str
    ) -> float:
        """
        Get adjustment multiplier for opponent.

        Args:
            opponent_team: 3-letter team abbreviation (BOS, LAL, etc.)
            stat_type: Stat type (points, rebounds, assists, threes)

        Returns:
            Adjustment multiplier (0.90 to 1.10)
        """
        if not self._rankings or opponent_team not in self._rankings:
            logger.debug(f"No rankings data for {opponent_team}, using neutral")
            return 1.00

        team_data = self._rankings[opponent_team]
        rank_key = f"{stat_type}_rank"
        rank = team_data.get(rank_key, 15)

        # Find applicable multiplier
        for (min_rank, max_rank), multiplier in self.DEFENSE_MULTIPLIERS.items():
            if min_rank <= rank <= max_rank:
                logger.debug(
                    f"{opponent_team} {stat_type} rank: {rank}, "
                    f"multiplier: {multiplier}"
                )
                return multiplier

        return 1.00

    def apply_opponent_adjustment(
        self,
        base_prediction: float,
        opponent_team: str,
        stat_type: str
    ) -> float:
        """
        Apply opponent adjustment to base prediction.

        Args:
            base_prediction: Original predicted value
            opponent_team: 3-letter team abbreviation
            stat_type: Stat type

        Returns:
            Adjusted prediction value
        """
        multiplier = self.get_opponent_adjustment(opponent_team, stat_type)
        adjusted = base_prediction * multiplier

        logger.debug(
            f"Opponent adjustment: {base_prediction:.2f} → {adjusted:.2f} "
            f"({opponent_team} {stat_type} defense, {multiplier:.2f}x)"
        )

        return round(adjusted, 2)

    def get_ranking(
        self,
        team: str,
        stat_type: str
    ) -> int:
        """
        Get defensive ranking for a team.

        Args:
            team: 3-letter team abbreviation
            stat_type: Stat type

        Returns:
            Defensive rank (1-30, 15 = average)
        """
        if not self._rankings or team not in self._rankings:
            return 15

        return self._rankings[team].get(f"{stat_type}_rank", 15)

    def get_all_rankings(self, team: str) -> Dict[str, int]:
        """
        Get all defensive rankings for a team.

        Args:
            team: 3-letter team abbreviation

        Returns:
            Dict with rankings for all stat types
        """
        if not self._rankings or team not in self._rankings:
            return {
                "points_rank": 15,
                "rebounds_rank": 15,
                "assists_rank": 15,
                "threes_rank": 15
            }

        return self._rankings[team]

    def reload_rankings(self):
        """Reload defensive rankings from seed file."""
        self._load_rankings()
