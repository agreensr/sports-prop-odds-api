"""
Single Bet Service for multi-sport betting predictions.

This service generates single bets (not parlays) as the primary output
of the prediction system.

Strategy:
- Target: 10 single bets per day (manageable for betting)
- Min confidence: 0.60 (60% win probability)
- Min edge: 5% (positive expected value)
- Max 3 bets per game (diversification)
- Ranked by: EV × confidence

Edge Calculation:
- edge = (implied_probability - market_probability) × 100
- Where market_probability is derived from bookmaker odds

EV Calculation:
- EV = (win_probability × profit) - (lose_probability × stake)
- Or simplified: EV = edge × odds_decimal

Priority Formula:
- priority = EV × confidence
- Higher priority bets ranked first
"""
import logging
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, func
from dataclasses import dataclass
from enum import Enum

from app.models import Prediction, Player, Game
from app.utils.timezone import utc_to_central, format_central_time

logger = logging.getLogger(__name__)


class BetRecommendation(Enum):
    """Bet recommendation types."""
    OVER = "OVER"
    UNDER = "UNDER"


@dataclass
class SingleBet:
    """Represents a single bet recommendation."""
    id: str
    sport_id: str
    player_name: str
    team: str
    opponent: str
    game_date: datetime
    stat_type: str
    predicted_value: float
    bookmaker_line: float
    recommendation: BetRecommendation
    bookmaker_name: str
    odds_american: int  # e.g., -110, +150
    odds_decimal: float  # e.g., 1.91, 2.50
    confidence: float  # 0.0 to 1.0
    edge_percent: float  # e.g., 5.2 = 5.2% edge
    ev_percent: float  # Expected value percent
    priority_score: float  # EV × confidence for ranking
    created_at: datetime

    def __repr__(self):
        rec = self.recommendation.value
        return (f"SingleBet({self.player_name} {rec} {self.stat_type} "
                f"{self.bookmaker_line} | {self.confidence:.0%} conf | "
                f"{self.edge_percent:+.1f}% edge | {self.odds_american})")


class SingleBetService:
    """
    Service for generating single bet recommendations.

    This is the primary output of the prediction system:
    - 10 single bets per day
    - Min 60% confidence
    - Min 5% edge
    - Max 3 bets per game
    - Ranked by EV × confidence
    """

    # Thresholds
    MIN_CONFIDENCE = 0.60  # 60%
    MIN_EDGE = 5.0  # 5%
    MAX_BETS_PER_DAY = 10
    MAX_BETS_PER_GAME = 3

    def __init__(self, db: Session):
        """
        Initialize the single bet service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def generate_daily_bets(
        self,
        target_date: Optional[date] = None,
        sport_id: Optional[str] = None
    ) -> List[SingleBet]:
        """
        Generate single bets for a specific date.

        Args:
            target_date: Date to generate bets for (default: today)
            sport_id: Filter by sport (default: all sports)

        Returns:
            List of SingleBet objects, ranked by priority
        """
        if target_date is None:
            target_date = date.today()

        logger.info(f"Generating single bets for {target_date}, sport={sport_id or 'all'}")

        # Step 1: Fetch qualifying predictions
        predictions = self._fetch_qualifying_predictions(target_date, sport_id)

        if not predictions:
            logger.warning("No qualifying predictions found")
            return []

        logger.info(f"Found {len(predictions)} qualifying predictions")

        # Step 2: Calculate edge and EV for each
        bets = []
        for pred in predictions:
            bet = self._prediction_to_bet(pred)
            if bet and self._meets_thresholds(bet):
                bets.append(bet)

        logger.info(f"{len(bets)} predictions meet thresholds")

        # Step 3: Rank by priority (EV × confidence)
        bets.sort(key=lambda b: b.priority_score, reverse=True)

        # Step 4: Limit to 10 bets total, max 3 per game
        final_bets = self._apply_limits(bets)

        logger.info(f"Generated {len(final_bets)} single bets")
        for i, bet in enumerate(final_bets, 1):
            logger.info(f"  {i}. {bet}")

        return final_bets

    def _fetch_qualifying_predictions(
        self,
        target_date: date,
        sport_id: Optional[str]
    ) -> List[Prediction]:
        """
        Fetch predictions that qualify for bet consideration.

        Qualifying criteria:
        - Game is on target_date or in next 2 days
        - Has valid odds (over_price or under_price)
        - Confidence ≥ MIN_CONFIDENCE
        - Not already resolved
        """
        start_date = datetime.combine(target_date, datetime.min.time())
        end_date = start_date.replace(hour=23, minute=59, second=59)

        # Look at today + next 2 days
        from datetime import timedelta
        end_date = end_date + timedelta(days=2)

        query = self.db.query(Prediction).join(Game).filter(
            and_(
                Game.game_date >= start_date,
                Game.game_date <= end_date,
                Game.status.in_(['scheduled', 'pending']),
                Prediction.confidence >= self.MIN_CONFIDENCE,
                Prediction.was_correct.is_(None),
                Prediction.odds_last_updated.isnot(None)
            )
        )

        if sport_id:
            query = query.filter(Prediction.sport_id == sport_id)

        predictions = query.order_by(desc(Prediction.confidence)).all()

        return predictions

    def _prediction_to_bet(self, prediction: Prediction) -> Optional[SingleBet]:
        """
        Convert a prediction to a SingleBet with calculated edge/EV.

        Args:
            prediction: Prediction model instance

        Returns:
            SingleBet or None if odds are invalid
        """
        # Get game info
        game = self.db.query(Game).filter(Game.id == prediction.game_id).first()
        if not game:
            logger.warning(f"Game not found for prediction {prediction.id}")
            return None

        # Get player info
        player = self.db.query(Player).filter(Player.id == prediction.player_id).first()
        if not player:
            logger.warning(f"Player not found for prediction {prediction.id}")
            return None

        # Determine which side to bet (OVER or UNDER)
        # We bet the side where our predicted value differs from the line
        if prediction.predicted_value > prediction.bookmaker_line:
            recommendation = BetRecommendation.OVER
            price = prediction.over_price
        else:
            recommendation = BetRecommendation.UNDER
            price = prediction.under_price

        if not price:
            return None

        # Calculate odds
        odds_american = int(price)
        odds_decimal = self._american_to_decimal(odds_american)

        # Calculate implied probability from bookmaker odds
        implied_prob = self._decimal_to_implied_probability(odds_decimal)

        # Our win probability (from confidence)
        # Confidence is already calibrated (0.50 = breakeven)
        win_prob = prediction.confidence

        # Calculate edge
        # edge = (our_probability - implied_probability) × 100
        edge = (win_prob - implied_prob) * 100

        # Calculate EV
        # EV = (win_prob × profit) - (lose_prob × stake)
        # Profit = odds_decimal - 1 for win, stake = 1 for loss
        ev = (win_prob * (odds_decimal - 1)) - ((1 - win_prob) * 1)
        ev_percent = ev * 100

        # Calculate priority score (for ranking)
        priority_score = ev_percent * win_prob

        # Determine opponent
        opponent = self._get_opponent(game, player.team)

        # Convert UTC datetimes to Central Time for user display
        game_date_central = utc_to_central(game.game_date)
        created_at_central = utc_to_central(prediction.created_at)

        return SingleBet(
            id=prediction.id,
            sport_id=prediction.sport_id,
            player_name=player.name,
            team=player.team,
            opponent=opponent,
            game_date=game_date_central or game.game_date,
            stat_type=prediction.stat_type,
            predicted_value=prediction.predicted_value,
            bookmaker_line=prediction.bookmaker_line,
            recommendation=recommendation,
            bookmaker_name=prediction.bookmaker_name or "Unknown",
            odds_american=odds_american,
            odds_decimal=odds_decimal,
            confidence=prediction.confidence,
            edge_percent=edge,
            ev_percent=ev_percent,
            priority_score=priority_score,
            created_at=created_at_central or prediction.created_at
        )

    def _meets_thresholds(self, bet: SingleBet) -> bool:
        """
        Check if bet meets minimum thresholds.

        Args:
            bet: SingleBet to check

        Returns:
            True if bet meets all thresholds
        """
        if bet.confidence < self.MIN_CONFIDENCE:
            return False

        if bet.edge_percent < self.MIN_EDGE:
            return False

        return True

    def _apply_limits(self, bets: List[SingleBet]) -> List[SingleBet]:
        """
        Apply business limits to the bet list.

        Limits:
        - Max 10 bets per day
        - Max 3 bets per game

        Args:
            bets: Ranked list of bets (by priority)

        Returns:
            Filtered list of bets
        """
        final_bets = []
        game_counts = {}  # game_id → count

        for bet in bets:
            # Check daily limit
            if len(final_bets) >= self.MAX_BETS_PER_DAY:
                break

            # Check per-game limit
            # Use game_date + teams as game identifier
            game_key = (bet.game_date, bet.team, bet.opponent)
            count = game_counts.get(game_key, 0)

            if count >= self.MAX_BETS_PER_GAME:
                logger.debug(f"Skipping {bet} - max bets per game reached")
                continue

            # Add bet
            final_bets.append(bet)
            game_counts[game_key] = count + 1

        return final_bets

    def _get_opponent(self, game: Game, player_team: str) -> str:
        """Get opponent team abbreviation."""
        if game.away_team == player_team:
            return game.home_team
        else:
            return game.away_team

    @staticmethod
    def _american_to_decimal(american: int) -> float:
        """Convert American odds to decimal."""
        if american > 0:
            return (american / 100) + 1
        else:
            return (100 / abs(american)) + 1

    @staticmethod
    def _decimal_to_implied_probability(decimal: float) -> float:
        """Convert decimal odds to implied probability (with vigorish)."""
        return 1 / decimal

    def format_bets_for_display(self, bets: List[SingleBet]) -> str:
        """
        Format bets for human-readable display.

        Args:
            bets: List of SingleBet objects

        Returns:
            Formatted string with times in Central Time (CST/CDT)
        """
        if not bets:
            return "No bets available."

        lines = []
        lines.append(f"🎯 TOP {len(bets)} SINGLE BETS - {date.today().strftime('%Y-%m-%d')}")
        lines.append("")

        for i, bet in enumerate(bets, 1):
            rec = bet.recommendation.value
            # Format game time in Central Time
            game_time_str = format_central_time(bet.game_date, "%Y-%m-%d %I:%M %p")

            lines.append(
                f"{i}. {bet.player_name} ({bet.team}) - {bet.stat_type} {rec} {bet.bookmaker_line}"
            )
            lines.append(f"   Game: {bet.team} vs {bet.opponent} @ {game_time_str}")
            lines.append(f"   Confidence: {bet.confidence:.1%} | Edge: {bet.edge_percent:+.1f}% | "
                        f"EV: {bet.ev_percent:+.1f}% | Odds: {bet.odds_american}")

        return "\n".join(lines)

    def get_bets_by_sport(
        self,
        sport_id: str,
        days: int = 7
    ) -> List[SingleBet]:
        """
        Get recent bets for a specific sport.

        Args:
            sport_id: Sport identifier ('nba', 'nfl', 'mlb', 'nhl')
            days: Number of days to look back

        Returns:
            List of SingleBet objects
        """
        start_date = datetime.now() - timedelta(days=days)

        predictions = self.db.query(Prediction).filter(
            and_(
                Prediction.sport_id == sport_id,
                Prediction.created_at >= start_date,
                Prediction.confidence >= self.MIN_CONFIDENCE
            )
        ).all()

        bets = []
        for pred in predictions:
            bet = self._prediction_to_bet(pred)
            if bet:
                bets.append(bet)

        return sorted(bets, key=lambda b: b.priority_score, reverse=True)


# Convenience function
def get_single_bet_service(db: Session) -> SingleBetService:
    """Get a SingleBetService instance."""
    return SingleBetService(db)
