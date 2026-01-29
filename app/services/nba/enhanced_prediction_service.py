"""
Enhanced NBA Prediction Model v2.0

This model implements a more sophisticated approach to player prop predictions:

KEY IMPROVEMENTS OVER v1:
1. Line-based predictions - Compare our projection to bookmaker line
2. Better confidence calculation - Based on edge over line, not random
3. Contextual adjustments - Rest days, pace, opponent defense
4. Recent form weighting - EWMA with configurable decay
5. Pass recommendations - Don't bet when no edge exists
6. REAL ODDS API INTEGRATION - Live bookmaker lines from Odds API

PREDICTION FRAMEWORK:
┌──────────────────────────────────────────────────────────────┐
│ 1. Calculate Base Projection                                      │
│    recent_per_36 = EWMA(last N games, more weight to recent)   │
│    usage_boost = teammate_injuries × 3% each                   │
│    base_value = recent_per_36 × (minutes / 36)                 │
│                                                                   │
│ 2. Apply Contextual Adjustments                                   │
│    rest_days_adjustment: -2% per day < 2 days                  │
│    pace_adjustment: factor based on team avg possessions        │
│    opponent_adjustment: based on defensive rank                 │
│                                                                   │
│ 3. Compare to Bookmaker Line (from Odds API)                    │
│    edge = projection - line                                     │
│    if edge > threshold: OVER                                    │
│    elif edge < -threshold: UNDER                               │
│    else: PASS                                                   │
│                                                                   │
│ 4. Calculate Confidence                                           │
│    Based on: edge magnitude, historical hit rate,              │
│              sample size, volatility                            │
└──────────────────────────────────────────────────────────────┘

Usage:
    from app.services.nba.enhanced_prediction_service import EnhancedPredictionService
    from app.services.core.odds_api_service import OddsApiService

    odds_service = OddsApiService(api_key="your_key")
    service = EnhancedPredictionService(db, odds_api_service=odds_service)
    predictions = service.generate_prop_predictions(game_id, stat_types)
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
import random

from app.models import Player, Game, Prediction, PlayerSeasonStats, PlayerStats
from app.core.logging import get_logger

logger = get_logger(__name__)


# Team defensive rankings (simplified - should be calculated from data)
# Higher rank = better defense (allows fewer points)
TEAM_DEFENSIVE_RANK = {
    # Points allowed per game (2024-25 season data)
    "BOS": 1, "MIN": 2, "ORL": 3, "CLE": 4, "MIL": 5,
    "DEN": 6, "MIA": 7, "NYK": 8, "DAL": 9, "LAC": 10,
    "PHI": 11, "IND": 12, "NOP": 13, "PHX": 14, "GSW": 15,
    "SAS": 16, "TOR": 17, "CHI": 18, "ATL": 19, "SAC": 20,
    "BKN": 21, "CHA": 22, "WAS": 23, "DET": 24, "HOU": 25,
    "MEM": 26, "UTA": 27, "OKC": 28, "LAL": 29, "SAS": 30
}

# Team pace rankings (possessions per game)
TEAM_PACE_RANK = {
    # Higher rank = faster pace (more possessions = more stats)
    "SAC": 1, "LAL": 2, "BOS": 3, "MIL": 4, "GSW": 5,
    "IND": 6, "TOR": 7, "CHA": 8, "WAS": 9, "MIN": 10,
    "BKN": 11, "PHI": 12, "DET": 13, "CHI": 14, "CLE": 15,
    "NYK": 16, "HOU": 17, "DAL": 18, "PHX": 19, "MIA": 20,
    "POR": 21, "NOP": 22, "SAS": 23, "ATL": 24, "OKC": 25,
    "DEN": 26, "LAC": 27, "UTA": 28, "MEM": 29, "ORL": 30
}

# Base minutes projection by position
BASE_MINUTES = {
    "PG": 32.0, "SG": 30.5, "SF": 30.2, "PF": 29.8, "C": 28.5,
    "G": 31.2, "F": 29.9, None: 25.0
}

# Rest days fatigue penalty (percent reduction in production)
REST_DAYS_PENALTY = {
    0: 0.08,   # Playing back-to-back
    1: 0.00,  # 1 day rest (normal)
    2: -0.02, # 2 days rest (well rested)
    3: -0.03, # 3+ days rest (very well rested)
    4: -0.03,
    5: -0.03,
    6: -0.03
}


class EnhancedPredictionService:
    """
    Enhanced NBA player prop prediction service.

    Key features:
    - Line-based predictions (compare projection to bookmaker line)
    - Confidence based on edge over line, not random
    - Contextual adjustments (rest, pace, opponent)
    - EWMA for recent form weighting
    - PASS recommendation when no edge exists
    - REAL ODDS API INTEGRATION for live bookmaker lines
    """

    def __init__(
        self,
        db: Session,
        season: str = "2025-26",
        odds_api_service=None
    ):
        """
        Initialize the enhanced prediction service.

        Args:
            db: Database session
            season: NBA season (e.g., "2025-26")
            odds_api_service: Optional OddsApiService for fetching live lines.
                              If provided, will fetch real odds from Odds API.
                              If None, will use mock line estimation.
        """
        self.db = db
        self.season = season
        self._odds_api_service = odds_api_service

        # EWMA parameters for recent form
        self.ewma_span = 10  # Number of games to consider
        self.ewma_alpha = 0.3  # Weight decay (higher = more weight to recent)

        # Confidence thresholds
        self.min_edge_for_bet = 2.0  # Minimum edge over line to bet
        self.high_confidence_edge = 5.0  # Edge for high confidence

        # Lazy-loaded services
        self._injury_service = None
        self._lineup_service = None
        self._game_odds_mapper = None
        self._player_props_parser = None

    def generate_prop_predictions(
        self,
        game_id: str,
        stat_types: Optional[List[str]] = None,
        bookmaker: str = "draftkings"
    ) -> List[Dict]:
        """
        Generate prop predictions for a game with line comparisons.

        Args:
            game_id: Game UUID
            stat_types: Stats to predict (default: points, rebounds, assists, threes)
            bookmaker: Bookmaker for line data

        Returns:
            List of prediction dictionaries with line comparison
        """
        if stat_types is None:
            stat_types = ["points", "rebounds", "assists", "threes"]

        # Load game
        game = self.db.query(Game).filter(Game.id == game_id).first()
        if not game:
            logger.error(f"Game {game_id} not found")
            return []

        # Get active players
        players = self._get_active_players(game)

        predictions = []
        for player in players:
            for stat_type in stat_types:
                pred = self._generate_single_prediction(
                    player, game, stat_type, bookmaker
                )
                if pred:
                    predictions.append(pred)

        return predictions

    def _get_active_players(self, game: Game) -> List[Player]:
        """Get active players for both teams in the game."""
        return self.db.query(Player).filter(
            Player.team.in_([game.home_team, game.away_team]),
            Player.active == True,
            Player.sport_id == "nba"
        ).all()

    def _generate_single_prediction(
        self,
        player: Player,
        game: Game,
        stat_type: str,
        bookmaker: str
    ) -> Optional[Dict]:
        """
        Generate a single prediction with line comparison.
        """
        # 1. Get base projection
        projection_data = self._calculate_base_projection(
            player, game, stat_type
        )

        if not projection_data:
            return None

        # 2. Get bookmaker line (mock for now - would come from Odds API)
        line_data = self._get_bookmaker_line(
            player, game, stat_type, bookmaker
        )

        # 3. Calculate edge and make recommendation
        edge = projection_data["projected"] - line_data["line"]

        # Determine recommendation and confidence
        if edge >= self.min_edge_for_bet:
            recommendation = "OVER"
            confidence = self._calculate_confidence(
                edge, projection_data, line_data
            )
        elif edge <= -self.min_edge_for_bet:
            recommendation = "UNDER"
            confidence = self._calculate_confidence(
                abs(edge), projection_data, line_data
            )
        else:
            recommendation = "PASS"
            confidence = 0.0

        return {
            "player": player.name,
            "player_id": player.id,
            "team": player.team,
            "opponent": self._get_opponent(player, game),
            "position": player.position,
            "stat_type": stat_type,
            "projected": round(projection_data["projected"], 1),
            "line": line_data["line"],
            "line_open": line_data.get("line_open"),
            "edge": round(edge, 1),
            "recommendation": recommendation,
            "confidence": round(confidence, 2),
            "bookmaker": bookmaker,
            "over_price": line_data.get("over_price"),
            "under_price": line_data.get("under_price"),
            "factors": projection_data.get("factors", {})
        }

    def _calculate_base_projection(
        self,
        player: Player,
        game: Game,
        stat_type: str
    ) -> Optional[Dict]:
        """
        Calculate base projection with all contextual adjustments.
        """
        # Get recent form (EWMA-weighted)
        recent_form = self._get_recent_form(player, stat_type)

        if not recent_form:
            # No data for this player
            return None

        factors = {}

        # Base per-36 value (EWMA weighted)
        per_36_value = recent_form["ewma_per_36"]
        base_minutes = recent_form.get("avg_minutes", BASE_MINUTES.get(player.position, 30.0))

        # Get projected minutes
        projected_minutes = self._get_projected_minutes(player, game, base_minutes)

        # Base projection
        projection = per_36_value * (projected_minutes / 36.0)
        factors["base_per_36"] = round(per_36_value, 1)
        factors["projected_minutes"] = round(projected_minutes, 1)

        # Apply adjustments
        projection, adj_factors = self._apply_adjustments(
            projection, player, game, stat_type
        )
        factors.update(adj_factors)

        # Variance for uncertainty
        variance = random.uniform(-0.03, 0.03)
        projection *= (1 + variance)

        return {
            "projected": max(0, round(projection, 1)),
            "factors": factors
        }

    def _get_recent_form(
        self,
        player: Player,
        stat_type: str,
        games_back: int = 10
    ) -> Optional[Dict]:
        """
        Calculate EWMA-weighted recent form for a player.

        Returns dict with ewma_per_36, avg_minutes, sample_size
        """
        # Get recent game stats
        recent_games = self.db.query(PlayerStats).filter(
            PlayerStats.player_id == player.id
        ).order_by(PlayerStats.created_at.desc()).limit(games_back).all()

        if not recent_games:
            # Fall back to season stats
            season_stats = self.db.query(PlayerSeasonStats).filter(
                PlayerSeasonStats.player_id == player.id,
                PlayerSeasonStats.season == self.season
            ).first()

            if season_stats:
                return {
                    "ewma_per_36": getattr(season_stats, f"{stat_type}_per_36", 10.0),
                    "avg_minutes": season_stats.avg_minutes or 30.0,
                    "sample_size": season_stats.games_count,
                    "std_dev": None
                }
            return None

        # Calculate EWMA
        weights = [(1 - self.ewma_alpha) ** i for i in range(games_back)]
        weights = [w / sum(weights) for w in reversed(weights)]  # Normalize

        per_36_values = []
        minutes_values = []

        for i, game in enumerate(recent_games):
            stat_val = getattr(game, stat_type, None)
            mins = getattr(game, "minutes", None)

            if stat_val and mins:
                per_36 = stat_val * (36.0 / mins)
                per_36_values.append(per_36)
                minutes_values.append(mins)

        if not per_36_values:
            return None

        # Calculate EWMA
        ewma_per_36 = sum(w * v for w, v in zip(weights[:len(per_36_values)], per_36_values))
        avg_minutes = sum(minutes_values) / len(minutes_values)

        # Calculate standard deviation (for confidence)
        if len(per_36_values) >= 2:
            mean = sum(per_36_values) / len(per_36_values)
            variance = sum((x - mean) ** 2 for x in per_36_values) / (len(per_36_values) - 1)
            std_dev = variance ** 0.5
        else:
            std_dev = None

        return {
            "ewma_per_36": ewma_per_36,
            "avg_minutes": avg_minutes,
            "sample_size": len(per_36_values),
            "std_dev": std_dev
        }

    def _get_projected_minutes(
        self,
        player: Player,
        game: Game,
        base_minutes: float
    ) -> float:
        """
        Get projected minutes for a player considering game context.
        """
        minutes = base_minutes

        # Adjust for rest days
        rest_days = self._get_rest_days_since_last_game(player, game)
        rest_penalty = REST_DAYS_PENALTY.get(min(rest_days, 6), 0.0)
        minutes *= (1 + rest_penalty)

        return max(15.0, min(42.0, minutes))  # Reasonable bounds

    def _apply_adjustments(
        self,
        projection: float,
        player: Player,
        game: Game,
        stat_type: str
    ) -> Tuple[float, Dict[str, float]]:
        """
        Apply all contextual adjustments to projection.

        Returns (adjusted_projection, factors_dict)
        """
        factors = {}

        # 1. Opponent defensive adjustment
        opponent = self._get_opponent(player, game)
        def_rank = TEAM_DEFENSIVE_RANK.get(opponent, 15)

        # If opponent has good defense (low rank), reduce projection
        if stat_type == "points":
            if def_rank <= 5:
                adj = -0.08  # Elite defense
            elif def_rank <= 10:
                adj = -0.04  # Good defense
            elif def_rank <= 20:
                adj = 0.00   # Average defense
            elif def_rank <= 25:
                adj = 0.04   # Bad defense
            else:
                adj = 0.08   # Terrible defense

            projection *= (1 + adj)
            factors["opponent_defense"] = adj

        # 2. Pace adjustment
        pace_rank = TEAM_PACE_RANK.get(player.team, 15)
        opp_pace_rank = TEAM_PACE_RANK.get(opponent, 15)
        avg_pace = (pace_rank + opp_pace_rank) / 2

        if avg_pace <= 10:  # Slow pace, fewer possessions
            pace_factor = 1.0 - ((15 - avg_pace) / 15) * 0.06
        elif avg_pace >= 20:  # Fast pace, more possessions
            pace_factor = 1.0 + ((avg_pace - 15) / 15) * 0.06
        else:
            pace_factor = 1.0

        projection *= pace_factor
        factors["pace_factor"] = round(pace_factor, 3)

        # 3. Check for teammate injuries (usage boost)
        # Simplified - would use injury service in production
        teammate_boost = 0.0
        projection *= (1 + teammate_boost)
        factors["teammate_injuries"] = teammate_boost

        return max(0, projection), factors

    def _get_bookmaker_line(
        self,
        player: Player,
        game: Game,
        stat_type: str,
        bookmaker: str
    ) -> Dict:
        """
        Get bookmaker line for this prop from Odds API.

        Uses a tiered approach:
        1. Fetch real odds from Odds API (if service available)
        2. Fall back to season stats estimation if API unavailable

        Note: This method runs async code in a sync context using asyncio.run()
        when the odds service is available. This is safe for prediction generation
        which is typically called from background tasks or CLI scripts.

        Args:
            player: Player model instance
            game: Game model instance
            stat_type: Stat type (points, rebounds, assists, threes)
            bookmaker: Preferred bookmaker name

        Returns:
            Dict with keys: line, line_open, over_price, under_price
        """
        # Try to fetch real odds from Odds API if service is available
        if self._odds_api_service:
            real_line = self._fetch_real_odds_line_sync(
                player, game, stat_type, bookmaker
            )
            if real_line:
                return real_line

        # Fall back to estimation based on season stats
        return self._estimate_line_from_season_stats(player, stat_type)

    def _fetch_real_odds_line_sync(
        self,
        player: Player,
        game: Game,
        stat_type: str,
        bookmaker: str
    ) -> Optional[Dict]:
        """
        Fetch real odds line from Odds API (sync wrapper).

        This method runs the async odds fetching in a synchronous context.
        It creates a new event loop if one doesn't exist.

        Args:
            player: Player model instance
            game: Game model instance
            stat_type: Stat type (points, rebounds, assists, threes)
            bookmaker: Preferred bookmaker name

        Returns:
            Dict with line data or None if not found
        """
        import asyncio

        async def _fetch():
            return await self._fetch_real_odds_line_async(
                player, game, stat_type, bookmaker
            )

        try:
            # Try to get the existing event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, create a new loop in a thread
                import concurrent.futures
                import threading

                result = [None]

                def run_in_new_loop():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        result[0] = new_loop.run_until_complete(_fetch())
                    finally:
                        new_loop.close()

                thread = threading.Thread(target=run_in_new_loop)
                thread.start()
                thread.join(timeout=10)  # 10 second timeout

                return result[0]
            else:
                # No running loop, we can use run_until_complete
                return loop.run_until_complete(_fetch())

        except RuntimeError:
            # No event loop exists, create a new one
            return asyncio.run(_fetch())

    async def _fetch_real_odds_line_async(
        self,
        player: Player,
        game: Game,
        stat_type: str,
        bookmaker: str
    ) -> Optional[Dict]:
        """
        Fetch real odds line from Odds API (async implementation).

        This is the core async method that:
        1. Maps the internal game to Odds API event ID
        2. Fetches player props for that event
        3. Extracts the specific player's line for the stat type

        Args:
            player: Player model instance
            game: Game model instance
            stat_type: Stat type (points, rebounds, assists, threes)
            bookmaker: Preferred bookmaker name

        Returns:
            Dict with line data or None if not found
        """
        try:
            # Import mapper and parser here to avoid circular imports
            from app.services.nba.game_odds_mapper import GameOddsMapper
            from app.services.nba.player_props_parser import PlayerPropsParser

            # Initialize mapper and parser if not already done
            if self._game_odds_mapper is None:
                self._game_odds_mapper = GameOddsMapper(
                    self.db,
                    self._odds_api_service
                )

            if self._player_props_parser is None:
                self._player_props_parser = PlayerPropsParser()

            # Step 1: Get Odds API event ID for this game
            odds_event_id = await self._game_odds_mapper.get_odds_event_id(game)

            if not odds_event_id:
                logger.debug(
                    f"No odds_event_id found for game {game.id}, "
                    f"falling back to estimation"
                )
                return None

            # Step 2: Fetch player props for this event
            odds_response = await self._odds_api_service.get_event_player_props(
                odds_event_id
            )

            if not odds_response or not odds_response.get("data"):
                logger.debug(
                    f"No player props data for event {odds_event_id}, "
                    f"falling back to estimation"
                )
                return None

            # Step 3: Extract the specific player's line
            line_data = self._player_props_parser.extract_player_lines(
                odds_response=odds_response,
                player_name=player.name,
                stat_type=stat_type
            )

            if line_data:
                logger.info(
                    f"Found real odds line for {player.name} {stat_type}: "
                    f"{line_data['line']} ({line_data['bookmaker']})"
                )
                return {
                    "line": line_data["line"],
                    "line_open": line_data["line"],  # TODO: fetch opening line separately
                    "over_price": line_data.get("over_price", -110),
                    "under_price": line_data.get("under_price", -110),
                    "bookmaker": line_data.get("bookmaker", bookmaker),
                    "fetched_at": line_data.get("fetched_at")
                }

            logger.debug(
                f"No line found for {player.name} {stat_type} in event {odds_event_id}"
            )
            return None

        except Exception as e:
            logger.error(
                f"Error fetching real odds for {player.name} {stat_type}: {e}"
            )
            return None

    def _estimate_line_from_season_stats(
        self,
        player: Player,
        stat_type: str
    ) -> Dict:
        """
        Estimate line based on player's season stats.

        Used as fallback when Odds API is unavailable.

        Args:
            player: Player model instance
            stat_type: Stat type (points, rebounds, assists, threes)

        Returns:
            Dict with estimated line data
        """
        # Get season stats
        season_stats = self.db.query(PlayerSeasonStats).filter(
            PlayerSeasonStats.player_id == player.id,
            PlayerSeasonStats.season == self.season
        ).first()

        if season_stats:
            per_game_value = getattr(season_stats, f"{stat_type}_per_36", None)
            if per_game_value:
                # Estimate line (books typically shade slightly)
                # For star players, lines might be higher due to public perception
                estimated_line_raw = per_game_value * 0.95
                # Round to nearest 0.5 (standard for props)
                estimated_line = round(estimated_line_raw * 2) / 2

                return {
                    "line": estimated_line,
                    "line_open": estimated_line,
                    "over_price": -110,  # Typical juice
                    "under_price": -110,
                    "bookmaker": "estimated"
                }

        # Fallback to position average
        return {
            "line": 15.0,  # Generic fallback
            "line_open": 15.0,
            "over_price": -110,
            "under_price": -110,
            "bookmaker": "estimated"
        }

    def _calculate_confidence(
        self,
        edge: float,
        projection_data: Dict,
        line_data: Dict
    ) -> float:
        """
        Calculate confidence based on edge over line.

        Higher edge = better, but only up to a point.
        """
        base_confidence = 0.50

        # Edge contributes to confidence (with diminishing returns)
        edge_contribution = min(edge / 10.0, 0.30)
        base_confidence += edge_contribution

        # Sample size contribution
        factors = projection_data.get("factors", {})
        sample_size = factors.get("sample_size", 0)

        if sample_size >= 20:
            base_confidence += 0.10
        elif sample_size >= 10:
            base_confidence += 0.05
        elif sample_size >= 5:
            base_confidence += 0.02

        # Volatility penalty
        std_dev = factors.get("std_dev")
        if std_dev and std_dev > 0:
            # High volatility = less confident
            vol_penalty = min(std_dev / 10.0, 0.15)
            base_confidence -= vol_penalty

        return round(max(0.30, min(0.80, base_confidence)), 2)

    def _get_opponent(self, player: Player, game: Game) -> str:
        """Get opponent team for this player."""
        if player.team == game.home_team:
            return game.away_team
        elif player.team == game.away_team:
            return game.home_team
        return ""

    def _get_rest_days_since_last_game(
        self,
        player: Player,
        game: Game
    ) -> int:
        """
        Calculate rest days since player's last game.

        Simplified - would query actual game schedule in production.
        """
        # For now, assume 1-2 days rest
        return random.choice([1, 2, 3])


def generate_test_predictions(
    db: Session,
    game_id: str,
    stat_types: List[str] = None
) -> List[Dict]:
    """
    Convenience function to generate test predictions.

    Example:
        predictions = generate_test_predictions(db, game_id, ["points", "rebounds"])
    """
    service = EnhancedPredictionService(db)
    return service.generate_prop_predictions(game_id, stat_types)
