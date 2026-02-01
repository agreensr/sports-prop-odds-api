"""
Project Manager Agent for Sports Betting Operations.

Orchestrates predictions across all sports and manages bankroll growth
from $500 to $5,000 through data-driven player prop predictions.

This agent coordinates between NBAAGENT and NHLAGENT (future: MLBAGENT)
to aggregate high-confidence picks and generate daily betting cards.

RESPONSIBILITIES:
1. Aggregate high-confidence predictions from all sports
2. Calculate optimal bet sizing using Kelly Criterion
3. Track bankroll and profit/loss
4. Generate daily betting reports
5. Manage straight bets vs parlay allocation

BANKROLL GROWTH STRATEGY:
Starting Bankroll: $500
Target: $5,000
Method: 40% weekly ROI through high-confidence picks

Daily Strategy:
- 70% Straight bets on 70%+ confidence picks
- 20% 2-leg parlays from 75%+ confidence (correlated)
- 10% 3-leg parlays from 80%+ confidence (limited)
"""
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, text

from app.core.logging import get_logger

logger = get_logger(__name__)


class ProjectManagerAgent:
    """
    Orchestrate multi-sport betting operations.

    Manages bankroll, aggregates predictions, calculates bet sizes,
    and generates daily betting cards across all supported sports.
    """

    def __init__(
        self,
        db: Session,
        starting_bankroll: float = 500.00,
        target_bankroll: float = 5000.00,
        min_confidence: float = 0.70
    ):
        """
        Initialize the Project Manager Agent.

        Args:
            db: Database session
            starting_bankroll: Initial bankroll amount (default: $500)
            target_bankroll: Target bankroll (default: $5,000)
            min_confidence: Minimum confidence for betting (default: 70%)
        """
        self.db = db
        self.starting_bankroll = starting_bankroll
        self.target_bankroll = target_bankroll
        self.min_confidence = min_confidence
        self.current_bankroll = self._load_current_bankroll()

        # Kelly Criterion parameters
        self.kelly_fraction = 0.25  # Quarter Kelly for conservative betting
        self.max_bet_percent = 0.05  # Max 5% of bankroll per bet

        # Confidence tiers
        self.tiers = {
            "high": 0.80,      # 80%+ confidence = 3-leg parlay eligible
            "medium": 0.75,    # 75%+ confidence = 2-leg parlay eligible
            "standard": 0.70   # 70%+ confidence = straight bets
        }

        logger.info(
            f"PMAGENT initialized: bankroll=${self.current_bankroll:.2f}, "
            f"min_confidence={self.min_confidence}"
        )

    def _load_current_bankroll(self) -> float:
        """Load current bankroll from tracking data or return starting amount."""
        # TODO: Query from placed_bets table when implemented
        return self.starting_bankroll

    def get_daily_betting_card(
        self,
        days_ahead: int = 1
    ) -> Dict:
        """
        Generate today's betting card across all sports.

        Aggregates high-confidence predictions from NBA and NHL,
        calculates Kelly bet sizes, and organizes into straights and parlays.

        Args:
            days_ahead: Number of days ahead to look (default: 1 = today)

        Returns:
            {
                "date": "2025-01-30",
                "bankroll": {...},
                "straight_bets": [...],
                "two_leg_parlays": [...],
                "three_leg_parlays": [...],
                "summary": {...}
            }
        """
        today = date.today()
        end_date = today + timedelta(days=days_ahead)

        # Fetch predictions from all sports
        predictions = []

        # NBA predictions only (FanDuel-only)
        nba_preds = self._get_nba_predictions(today, end_date)
        predictions.extend(nba_preds)
        logger.info(f"Fetched {len(nba_preds)} NBA predictions")

        # NHL skipped - FanDuel doesn't offer assists/points props
        # Only offers goals which aren't bettable

        # Sort by confidence
        predictions.sort(key=lambda x: x.get("confidence", 0), reverse=True)

        # Filter by minimum confidence
        high_conf_preds = [
            p for p in predictions
            if p.get("confidence", 0) >= self.min_confidence
        ]

        logger.info(f"High-confidence predictions: {len(high_conf_preds)}")

        # Calculate Kelly bet sizes
        for pred in high_conf_preds:
            pred["kelly_fraction"] = self._calculate_kelly_bet(pred)
            pred["bet_amount"] = self.current_bankroll * pred["kelly_fraction"]

        # Separate into straights and parlay candidates
        straights = []
        parlay_candidates = []

        for pred in high_conf_preds:
            if pred["confidence"] >= 0.75:
                parlay_candidates.append(pred)
            if pred["confidence"] >= self.min_confidence:
                straights.append(pred)

        # Build parlays
        two_leg_parlays = self._build_two_leg_parlays(parlay_candidates)
        three_leg_parlays = self._build_three_leg_parlays(parlay_candidates)

        # Calculate summary
        total_straight_wager = sum(p["bet_amount"] for p in straights[:5])  # Top 5 straights
        total_parlay_wager = sum(p["wager"] for p in two_leg_parlays) + sum(p["wager"] for p in three_leg_parlays)
        total_wager = total_straight_wager + total_parlay_wager

        return {
            "date": today.isoformat(),
            "bankroll": {
                "current": round(self.current_bankroll, 2),
                "starting": round(self.starting_bankroll, 2),
                "target": round(self.target_bankroll, 2),
                "growth_needed": round(self.target_bankroll - self.current_bankroll, 2),
                "growth_percent": round((self.target_bankroll / self.current_bankroll - 1) * 100, 1)
            },
            "straight_bets": straights[:5],  # Top 5 straight bets
            "two_leg_parlays": two_leg_parlays,
            "three_leg_parlays": three_leg_parlays,
            "summary": {
                "total_predictions": len(predictions),
                "high_confidence_count": len(high_conf_preds),
                "straight_bets_count": len(straights[:5]),
                "two_leg_parlays_count": len(two_leg_parlays),
                "three_leg_parlays_count": len(three_leg_parlays),
                "total_wager": round(total_wager, 2),
                "max_risk_percent": round((total_wager / self.current_bankroll) * 100, 1) if self.current_bankroll > 0 else 0
            }
        }

    def _get_nba_predictions(
        self,
        start_date: date,
        end_date: date
    ) -> List[Dict]:
        """Fetch NBA predictions for the date range."""
        predictions = []

        try:
            # Fetch existing predictions with bookmaker odds from nba_props database
            # Use raw SQL to avoid model/schema mismatches
            query = text("""
                SELECT
                    p.id,
                    pl.name as player_name,
                    pl.team,
                    g.home_team,
                    g.away_team,
                    g.game_date,
                    p.stat_type,
                    p.predicted_value,
                    p.bookmaker_line,
                    p.bookmaker_name,
                    p.confidence,
                    p.recommendation,
                    p.over_price,
                    p.under_price,
                    g.odds_api_event_id
                FROM predictions p
                JOIN players pl ON p.player_id = pl.id
                JOIN games g ON p.game_id = g.id
                WHERE g.game_date >= :start_date
                  AND g.game_date <= :end_date
                  AND g.status = 'scheduled'
                  AND p.bookmaker_name ILIKE 'fanduel'
                  AND p.over_price IS NOT NULL
                ORDER BY p.confidence DESC
            """)

            # Add 1 day to end_date to include games on the end_date
            # (since game_date is timestamp, not just date)
            end_date_inclusive = end_date + timedelta(days=1)

            result = self.db.execute(query, {
                "start_date": start_date,
                "end_date": end_date_inclusive
            })

            # Debug logging
            logger.info(f"Query params: start_date={start_date}, end_date={end_date_inclusive}")

            for row in result:
                # Convert row to dict
                pred = {
                    "sport": "nba",
                    "player": row.player_name,
                    "player_id": row.id,
                    "team": row.team,
                    "opponent": f"{row.away_team}@{row.home_team}",
                    "stat_type": row.stat_type,
                    "projected": row.predicted_value,
                    "line": row.bookmaker_line,
                    "recommendation": row.recommendation,
                    "confidence": row.confidence,
                    "bookmaker": row.bookmaker_name,
                    "over_price": row.over_price,
                    "under_price": row.under_price,
                    "game_date": row.game_date.isoformat() if row.game_date else None
                }
                predictions.append(pred)

            logger.info(f"Fetched {len(predictions)} NBA predictions from database")

        except Exception as e:
            logger.warning(f"Error fetching NBA predictions: {e}")

        return predictions

    def _get_nhl_predictions(
        self,
        start_date: date,
        end_date: date
    ) -> List[Dict]:
        """Fetch NHL predictions for the date range."""
        predictions = []

        try:
            # NHL predictions are in a separate database (seantrader)
            # For now, we'll use the enhanced prediction service which queries the seantrader DB
            from app.services.nhl.enhanced_prediction_service import EnhancedNHLPredictionService
            from app.services.core.odds_api_service import get_odds_service
            from app.core.config import settings

            if not settings.THE_ODDS_API_KEY:
                return []

            odds_service = get_odds_service(settings.THE_ODDS_API_KEY, sport="nhl")
            svc = EnhancedNHLPredictionService(self.db, odds_api_service=odds_service)

            # Get predictions from the service (it handles database queries internally)
            preds = svc.get_predictions_with_odds(
                start_date=start_date,
                end_date=end_date,
                stat_types=["assists", "points"]  # Only bettable markets
            )

            for p in preds:
                p["sport"] = "nhl"
                predictions.append(p)

            logger.info(f"Fetched {len(predictions)} NHL predictions from service")

        except Exception as e:
            logger.warning(f"Error fetching NHL predictions: {e}")

        return predictions

    def _calculate_kelly_bet(
        self,
        prediction: Dict
    ) -> float:
        """
        Calculate Kelly Criterion bet size.

        Kelly = (bp - q) / b

        Where:
        b = decimal odds - 1
        p = probability of winning (confidence)
        q = probability of losing (1 - p)

        Uses fractional Kelly (1/4) for conservative betting.

        Args:
            prediction: Prediction dict with confidence and odds

        Returns:
            Kelly fraction of bankroll to bet
        """
        confidence = prediction.get("confidence", 0.70)
        over_price = prediction.get("over_price", -110)

        # Convert to decimal odds
        # Decimal odds: > 1.01 (e.g., 1.91, 2.50, 3.40)
        # American odds: negative for favorites (-110), positive for underdogs (+240)
        if over_price > 1.01:
            # Already in decimal format
            decimal_odds = over_price
        elif over_price < 0:
            # American odds for favorites (e.g., -110)
            decimal_odds = (100.0 / abs(over_price)) + 1.0
        else:
            # American odds for underdogs (e.g., +240)
            decimal_odds = (over_price / 100.0) + 1.0

        # Calculate b (net profit per unit wagered)
        b = decimal_odds - 1.0

        # Kelly formula: (b*p - q) / b
        # Where p = confidence, q = 1 - confidence
        if b > 0:
            kelly = (b * confidence - (1 - confidence)) / b
        else:
            kelly = 0

        # Apply fractional Kelly
        kelly_fraction = kelly * self.kelly_fraction

        # Clamp to max bet percent
        return max(0, min(kelly_fraction, self.max_bet_percent))

    def _build_two_leg_parlays(
        self,
        predictions: List[Dict],
        max_parlays: int = 5
    ) -> List[Dict]:
        """
        Build 2-leg parlays from high-confidence predictions.

        Rules:
        - Only use 75%+ confidence picks
        - Prefer correlated stats on same player
        - Max 5 parlays per day
        - Fixed $10 wager per parlay

        Args:
            predictions: List of high-confidence predictions
            max_parlays: Maximum number of parlays to build

        Returns:
            List of parlay dictionaries
        """
        from app.services.betting.parlay_builder import ParlayBuilder

        builder = ParlayBuilder()
        parlays = builder.build_two_leg_parlays(
            predictions,
            min_confidence=0.75,
            max_parlays=max_parlays
        )

        return parlays

    def _build_three_leg_parlays(
        self,
        predictions: List[Dict],
        max_parlays: int = 2
    ) -> List[Dict]:
        """
        Build 3-leg parlays from VERY high-confidence predictions.

        Rules:
        - Only use 80%+ confidence picks
        - All legs must be on different players
        - Max 2 parlays per day
        - Fixed $5 wager per parlay (higher risk)

        Args:
            predictions: List of high-confidence predictions
            max_parlays: Maximum number of parlays to build

        Returns:
            List of parlay dictionaries
        """
        from app.services.betting.parlay_builder import ParlayBuilder

        builder = ParlayBuilder()
        parlays = builder.build_three_leg_parlays(
            predictions,
            min_confidence=0.80,
            max_parlays=max_parlays
        )

        return parlays

    def get_unit_size(self) -> float:
        """
        Get current unit size based on bankroll.

        Unit sizing scales with bankroll for consistent growth:
        - $500-$750: $10 units
        - $750-$1,000: $15 units
        - $1,000-$2,000: $20 units
        - $2,000-$3,000: $25 units
        - $3,000+: $30 units

        Returns:
            Current unit size in dollars
        """
        br = self.current_bankroll

        if br < 750:
            return 10.0
        elif br < 1000:
            return 15.0
        elif br < 2000:
            return 20.0
        elif br < 3000:
            return 25.0
        else:
            return 30.0

    def get_performance_summary(
        self,
        days_back: int = 30
    ) -> Dict:
        """
        Get performance metrics by sport and confidence tier.

        Args:
            days_back: Number of days to analyze

        Returns:
            Performance summary dict
        """
        # TODO: Query from prediction_tracking table
        # For now, return placeholder

        return {
            "period_days": days_back,
            "total_bets": 0,
            "wins": 0,
            "losses": 0,
            "pushes": 0,
            "win_rate": 0.0,
            "roi": 0.0,
            "profit_loss": 0.0,
            "by_sport": {
                "nba": {"bets": 0, "wins": 0, "roi": 0.0}
                # NHL skipped - FanDuel doesn't offer bettable props
            },
            "by_confidence": {
                "80_plus": {"bets": 0, "wins": 0, "roi": 0.0},
                "75_79": {"bets": 0, "wins": 0, "roi": 0.0},
                "70_74": {"bets": 0, "wins": 0, "roi": 0.0}
            }
        }

    def update_bankroll(
        self,
        profit_loss: float
    ) -> Dict:
        """
        Update bankroll after bets settle.

        Args:
            profit_loss: Profit or loss amount

        Returns:
            Updated bankroll info
        """
        self.current_bankroll += profit_loss

        return {
            "previous_bankroll": round(self.current_bankroll - profit_loss, 2),
            "current_bankroll": round(self.current_bankroll, 2),
            "profit_loss": round(profit_loss, 2),
            "growth_percent": round((self.current_bankroll / self.starting_bankroll - 1) * 100, 1)
        }


def get_project_manager(db: Session) -> ProjectManagerAgent:
    """Get a ProjectManagerAgent instance."""
    return ProjectManagerAgent(db)
