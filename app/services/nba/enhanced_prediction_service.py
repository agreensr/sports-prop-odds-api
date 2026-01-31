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
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
import random
import numpy as np  # TIER 2: For robust EWMA calculations

from app.models import Player, Game, Prediction, PlayerSeasonStats, PlayerStats
from app.core.logging import get_logger

logger = get_logger(__name__)


# Known non-NBA players (college prospects, G-League only) who should be excluded
# These players have NBA.com IDs but don't actually play in the NBA
# Known non-NBA players (college prospects, G-League only) who should be excluded
# These players have NBA.com IDs but don't actually play in the NBA
KNOWN_NON_NBA_PLAYERS = {
    # 2025/2026 Draft prospects (college players)
    "Bronny James", "Justin Edwards", "Omari Moore", "Jamal Shead",
    # G-League/Two-Way players who don't get real NBA minutes
    "Moussa Diabaté", "Moussa Cisse", "Oso Ighodaro",
    "Brandon Williams", "Ryan Nembhard", "Miles Kelly", "Koby Brea",
    # Add more as needed
}


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

# TIER 4: Team locations for travel fatigue calculation
# Approximate coordinates for NBA teams (latitude, longitude)
TEAM_LOCATIONS = {
    # Eastern Conference
    "ATL": (33.7537, -84.3863),  # Atlanta
    "BOS": (42.3601, -71.0589),  # Boston
    "BKN": (40.6826, -73.9754),  # Brooklyn
    "CHA": (35.2271, -80.8431),  # Charlotte
    "CHI": (41.8827, -87.6233),  # Chicago
    "CLE": (41.4965, -81.6881),  # Cleveland
    "DET": (42.7802, -83.0675),  # Detroit
    "IND": (39.7639, -86.1558),  # Indiana
    "MIA": (25.7814, -80.1880),  # Miami
    "MIL": (43.0458, -87.9151),  # Milwaukee
    "NYK": (40.7505, -73.9934),  # New York
    "ORL": (28.5383, -81.3792),  # Orlando
    "PHI": (39.9012, -75.1717),  # Philadelphia
    "TOR": (43.6442, -79.3790),  # Toronto
    "WAS": (38.9072, -77.0369),  # Washington

    # Western Conference
    "DAL": (32.7767, -96.7970),  # Dallas
    "DEN": (39.7392, -104.9903), # Denver (altitude!)
    "GSW": (37.7707, -122.4421), # Golden State
    "HOU": (29.7604, -95.3698),  # Houston
    "LAC": (33.8712, -118.1205), # Los Angeles
    "LAL": (34.0430, -118.2673), # Los Angeles (Lakers)
    "MEM": (35.1493, -90.0490),  # Memphis
    "MIN": (44.9792, -93.2761),  # Minnesota
    "NOP": (29.9479, -90.0721),  # New Orleans
    "OKC": (35.4676, -97.5164),  # Oklahoma City
    "PHX": (33.4484, -112.0740), # Phoenix
    "POR": (45.5316, -122.6668), # Portland
    "SAC": (38.5758, -121.4908), # Sacramento
    "SAS": (29.4261, -98.4938),  # San Antonio
    "UTA": (40.7617, -111.8910),  # Utah (altitude!)
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


# STAT-SPECIFIC CALIBRATION FACTORS
# Based on historical accuracy analysis (828 resolved predictions)
# Model systematically over-predicts, so we apply downward correction
STAT_CALIBRATION = {
    'points': 0.78,      # Predicted 12.90 -> Actual 10.08 (22% over)
    'rebounds': 0.70,    # Predicted 5.50 -> Actual 3.83 (30% over)
    'assists': 0.81,     # Predicted 3.09 -> Actual 2.49 (19% over)
    'threes': 0.71,       # Predicted 1.56 -> Actual 1.10 (42% over)
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

        # Odds cache to prevent redundant API calls within same prediction run
        # Key: (game_id, stat_type), Value: (odds_response, fetched_at)
        self._odds_cache: Dict[tuple, tuple] = {}
        self._cache_ttl_seconds = 300  # 5 minutes cache

    @property
    def injury_service(self):
        """Lazy-load injury service."""
        if self._injury_service is None:
            from app.services.nba.injury_service import InjuryService
            self._injury_service = InjuryService(self.db)
        return self._injury_service

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
                # Only include predictions with real bookmaker lines
                # Exclude estimated/fallback lines
                if pred and pred.get("line_source") not in ("estimated", None):
                    predictions.append(pred)

        return predictions

    # Minimum games threshold for reliable predictions
    MIN_GAMES_THRESHOLD = 10  # Require at least 10 games of data
    ROOKIE_GAMES_THRESHOLD = 50  # Career games below this = rookie variance penalty
    RECENT_DAYS_THRESHOLD = 7  # Days without playing = likely injured/DNP

    def _get_active_players(self, game: Game) -> List[Player]:
        """Get active players for both teams in the game.

        Filters to only include real NBA players who are rotation players.
        This excludes:
        - Known college prospects (Cooper Flagg, etc.)
        - G-League only players
        - End-of-bench players who don't get meaningful minutes
        - Players with insufficient sample size (< 10 games)
        - Players who haven't played recently (likely injured/DNP)

        Real NBA players who get FanDuel prop bets typically:
        - Play 15+ minutes per game (rotation players)
        - Have at least 10 games of data
        - Have reasonable stats
        - Have played within the last 7 days (not injured)
        """
        from app.models import PlayerSeasonStats
        from datetime import datetime, timedelta

        # Calculate cutoff date for recent activity check
        recent_cutoff = datetime.now() - timedelta(days=self.RECENT_DAYS_THRESHOLD)

        # Get players on the teams
        players = self.db.query(Player).filter(
            Player.team.in_([game.home_team, game.away_team]),
            Player.active == True,
            Player.sport_id == "nba"
        ).all()

        # Filter to only rotation players (15+ minutes per game)
        # This eliminates college prospects and deep bench players
        valid_players = []
        for p in players:
            # Skip known non-NBA players
            if p.name in KNOWN_NON_NBA_PLAYERS:
                logger.debug(f"Skipping known non-NBA player: {p.name}")
                continue

            # Check if player has season stats with meaningful minutes
            stats = self.db.query(PlayerSeasonStats).filter(
                PlayerSeasonStats.player_id == p.id,
                PlayerSeasonStats.season == self.season
            ).first()

            # Require minimum games and minutes
            games_count = stats.games_count if stats else 0
            avg_mins = stats.avg_minutes if stats else 0

            if not (stats and avg_mins >= 15.0 and games_count >= self.MIN_GAMES_THRESHOLD):
                logger.debug(
                    f"Skipping player {p.name} ({p.team}) - "
                    f"games: {games_count}, avg_minutes: {avg_mins:.1f} "
                    f"(min: {self.MIN_GAMES_THRESHOLD} games, 15+ mins)"
                )
                continue

            # TIER 3: Filter by contract type (exclude two-way, 10-day, training camp)
            # Check if player has contract_type attribute
            if hasattr(p, 'contract_type'):
                if p.contract_type in ("two-way", "two_way", "10-day", "training_camp"):
                    logger.debug(
                        f"Skipping {p.name} ({p.team}) - contract type: {p.contract_type}"
                    )
                    continue
            else:
                # Fallback: Check for common two-way player patterns
                # Two-way players typically have < 10 games played despite being active
                if stats.games_count < 10 and avg_mins < 12:
                    # Likely a two-way player or deep bench
                    logger.debug(
                        f"Skipping {p.name} ({p.team}) - likely two-way/bench "
                        f"({stats.games_count} games, {avg_mins:.1f} mins)"
                    )
                    continue

            # **NEW**: Check if player has actually played recently
            # This filters out injured/DNP players like Jalen Williams
            # Use last_game_date from PlayerSeasonStats instead of empty PlayerStats table
            if stats.last_game_date:
                # Convert date to datetime for comparison
                from datetime import datetime as dt
                last_played = dt.combine(stats.last_game_date, dt.min.time())

                # If player hasn't played in RECENT_DAYS_THRESHOLD days, likely injured/DNP
                if last_played < recent_cutoff:
                    days_since = (datetime.now() - last_played).days
                    logger.debug(
                        f"Skipping player {p.name} ({p.team}) - "
                        f"last played {days_since:.0f} days ago (likely injured/DNP)"
                    )
                    continue

            valid_players.append(p)

        # **TIER 1 FIX**: Filter out injured players using injury service
        # This excludes players marked as OUT, DOUBTFUL, or QUESTIONABLE
        if valid_players:
            player_ids = [p.id for p in valid_players]
            healthy_ids = self.injury_service.filter_by_injury_status(player_ids)
            valid_players = [p for p in valid_players if p.id in healthy_ids]
            logger.debug(f"Injury filter: {len(player_ids)} → {len(valid_players)} healthy players")

        return valid_players

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
            "bookmaker": line_data.get("bookmaker", bookmaker),
            "line_source": line_data.get("bookmaker", "estimated"),
            "over_price": line_data.get("over_price"),
            "under_price": line_data.get("under_price"),
            "factors": projection_data.get("factors", {}),
            "odds_fetched_at": line_data.get("odds_fetched_at"),
            "odds_last_updated": line_data.get("odds_last_updated")
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
        factors["sample_size"] = recent_form.get("sample_size", 0)
        factors["std_dev"] = recent_form.get("std_dev")
        factors["career_games"] = recent_form.get("career_games", recent_form.get("sample_size", 0))

        # Apply adjustments (pass projected_minutes for fatigue scaling)
        projection, adj_factors = self._apply_adjustments(
            projection, player, game, stat_type, projected_minutes
        )
        factors.update(adj_factors)

        # Variance for uncertainty (reduced from ±3% to ±1% for consistency)
        variance = random.uniform(-0.01, 0.01)
        projection *= (1 + variance)

        # Apply stat-specific calibration to correct over-prediction bias
        # Based on 828 resolved predictions analysis:
        # - Points: 12.90 predicted vs 10.08 actual (22% over) → 0.78x
        # - Rebounds: 5.50 predicted vs 3.83 actual (30% over) → 0.70x
        # - Assists: 3.09 predicted vs 2.49 actual (19% over) → 0.81x
        # - Threes: 1.56 predicted vs 1.10 actual (42% over) → 0.71x
        calibration_factor = STAT_CALIBRATION.get(stat_type, 1.0)
        projection *= calibration_factor
        factors["calibration"] = calibration_factor

        return {
            "projected": round(float(max(0, projection)), 1),
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

        TIER 2 IMPROVEMENTS:
        - Outlier detection using Median Absolute Deviation (MAD)
        - Adaptive alpha based on volatility (Coefficient of Variation)
        - Robust to statistical anomalies

        Returns dict with ewma_per_36, avg_minutes, sample_size, std_dev, career_games

        Enhancements:
        - Tracks career games for rookie penalty
        - Detects new team transitions (recent trades/signings)
        - Boosts recent weight for players on new teams
        """
        # Get recent game stats
        recent_games = self.db.query(PlayerStats).filter(
            PlayerStats.player_id == player.id
        ).order_by(PlayerStats.created_at.desc()).limit(games_back).all()

        # Get season stats for career games total
        season_stats = self.db.query(PlayerSeasonStats).filter(
            PlayerSeasonStats.player_id == player.id,
            PlayerSeasonStats.season == self.season
        ).first()

        if not recent_games:
            # Fall back to season stats
            if season_stats:
                return {
                    "ewma_per_36": float(getattr(season_stats, f"{stat_type}_per_36", 10.0)),
                    "avg_minutes": float(season_stats.avg_minutes or 30.0),
                    "sample_size": season_stats.games_count or 0,
                    "std_dev": None,
                    "career_games": season_stats.games_count or 0,
                    "new_team": False
                }
            return None

        # Check if player is on a new team (recently traded/signed)
        career_games = season_stats.games_count if season_stats else 0
        new_team = False
        recent_boost = 0.0

        # If player has fewer than 20 games this season, likely new/rookie
        if career_games and career_games < 20:
            new_team = True
            recent_boost = 0.5

        # Extract per-36 values
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

        # TIER 2: Robust EWMA with outlier detection and adaptive alpha
        try:
            per_36_array = np.array(per_36_values)
            median = np.median(per_36_array)
            mad = np.median(np.abs(per_36_array - median))

            # Define outlier threshold (3 MAD)
            outlier_threshold = 3 * mad if mad > 0 else 0

            # Cap outliers at median ± threshold
            cleaned_values = np.clip(
                per_36_array,
                median - outlier_threshold if outlier_threshold > 0 else median,
                median + outlier_threshold if outlier_threshold > 0 else median
            )

            # TIER 2: Adaptive alpha based on volatility (CV)
            mean_val = np.mean(cleaned_values)
            cv = (np.std(cleaned_values) / mean_val) if mean_val > 0 else 0

            # Adaptive alpha: 0.2 (stable) to 0.5 (volatile)
            if cv < 0.15:
                adaptive_alpha = 0.2
            elif cv < 0.25:
                adaptive_alpha = 0.3
            else:
                adaptive_alpha = 0.5

            # Adjust for new team
            if new_team:
                adaptive_alpha = min(adaptive_alpha + recent_boost, 0.7)

            # Calculate EWMA with adaptive alpha
            games_to_use = min(games_back, len(cleaned_values))
            weights = [(1 - adaptive_alpha) ** i for i in range(games_to_use)]
            weights = [w / sum(weights) for w in reversed(weights)]

            ewma_per_36 = sum(w * v for w, v in zip(weights[:len(cleaned_values)], cleaned_values))

            # Track outliers capped
            outliers_capped = int(np.sum(per_36_array != cleaned_values))
        except Exception:
            # Fallback to simple calculation if numpy fails
            alpha = self.ewma_alpha + (recent_boost if new_team else 0)
            games_to_use = min(games_back, len(per_36_values))
            weights = [(1 - alpha) ** i for i in range(games_to_use)]
            weights = [w / sum(weights) for w in reversed(weights)]
            ewma_per_36 = sum(w * v for w, v in zip(weights[:len(per_36_values)], per_36_values))
            outliers_capped = 0
            cleaned_values = per_36_values

        avg_minutes = sum(minutes_values) / len(minutes_values)

        # Calculate standard deviation (for confidence)
        if len(per_36_values) >= 2:
            mean = sum(per_36_values) / len(per_36_values)
            variance = sum((x - mean) ** 2 for x in per_36_values) / (len(per_36_values) - 1)
            std_dev = variance ** 0.5
        else:
            std_dev = None

        return {
            "ewma_per_36": float(ewma_per_36),
            "avg_minutes": float(avg_minutes),
            "sample_size": len(per_36_values),
            "std_dev": float(std_dev) if std_dev is not None else None,
            "career_games": career_games,
            "new_team": new_team,
            "outliers_capped": outliers_capped
        }

    def _get_projected_minutes(
        self,
        player: Player,
        game: Game,
        base_minutes: float
    ) -> float:
        """
        Get projected minutes for a player considering game context.

        TIER 2 IMPROVEMENT: Age-adjusted rest days penalties
        """
        minutes = base_minutes

        # TIER 2: Apply age-adjusted rest penalty (replaces static REST_DAYS_PENALTY)
        rest_days = self._get_rest_days_since_last_game(player, game)
        rest_penalty = self._get_age_adjusted_rest_penalty(player, rest_days)
        minutes *= (1 + rest_penalty)

        return max(15.0, min(42.0, minutes))  # Reasonable bounds

    def _get_age_adjusted_rest_penalty(
        self,
        player: Player,
        rest_days: int
    ) -> float:
        """
        Calculate age-adjusted rest days penalty.

        TIER 2 IMPROVEMENT: Evidence-based model with age multipliers

        Age multipliers for B2B penalty:
        - 35+ years: 2.0x (veterans need more recovery)
        - 30-34 years: 1.5x (prime veterans)
        - 22-29 years: 1.0x (prime years)
        - <22 years: 0.7x (young players recover faster)

        Rest bonus for 2+ days increases with age.
        """
        # Get player age
        if not player.birth_date:
            age_multiplier = 1.0
        else:
            today = date.today()
            age = today.year - player.birth_date.year - (
                (today.month, today.day) < (player.birth_date.month, player.birth_date.day)
            )

            # Determine age multiplier
            if age >= 35:
                age_multiplier = 2.0
            elif age >= 30:
                age_multiplier = 1.5
            elif age >= 22:
                age_multiplier = 1.0
            else:
                age_multiplier = 0.7

        # Base penalties (with B2B multiplier)
        if rest_days == 0:  # Back-to-back
            base_penalty = -0.10 * age_multiplier  # Negative = reduction
        elif rest_days == 1:  # 1 day rest (normal)
            base_penalty = 0.0
        elif rest_days == 2:  # 2 days rest (optimal)
            base_penalty = 0.025  # Small bonus
        elif rest_days >= 3:  # 3+ days rest (rust effect increases)
            rust_penalty = -0.03 * min(rest_days - 2, 4)  # Max -12%
            base_penalty = rust_penalty
        else:
            base_penalty = 0.0

        return base_penalty

    def _apply_fatigue_scaling(
        self,
        projection: float,
        projected_minutes: float
    ) -> Tuple[float, float]:
        """
        Apply non-linear fatigue scaling for players with high minutes.

        TIER 2 IMPROVEMENT: Evidence-based fatigue model

        Research shows efficiency drops non-linearly with minutes:
        - 32 minutes: 100% efficiency (baseline)
        - 36 minutes: 95% efficiency (5% drop)
        - 40 minutes: 87% efficiency (13% drop)
        - 40+ minutes: 75% efficiency floor (25% drop max)

        This prevents over-projecting for starters playing heavy minutes.
        """
        if projected_minutes <= 32:
            # No fatigue penalty at 32 minutes or below
            fatigue_factor = 1.0
        elif projected_minutes <= 36:
            # Linear decay from 32-36 min: 100% → 95%
            ratio = (projected_minutes - 32) / 4  # 0 to 1
            fatigue_factor = 1.0 - (0.05 * ratio)
        elif projected_minutes <= 40:
            # Accelerated decay from 36-40 min: 95% → 87%
            ratio = (projected_minutes - 36) / 4  # 0 to 1
            fatigue_factor = 0.95 - (0.08 * ratio)
        else:
            # Floor at 75% for 40+ minutes
            fatigue_factor = 0.75

        adjusted_projection = projection * fatigue_factor
        return adjusted_projection, fatigue_factor

    def _calculate_travel_fatigue(
        self,
        player: Player,
        game: Game
    ) -> float:
        """
        Calculate travel fatigue penalty based on distance and time zone changes.

        TIER 4 IMPROVEMENT: Evidence-based travel fatigue model

        Research findings:
        - Cross-country trips (2000+ miles): -3% to -5% performance
        - 2+ time zone changes: -2% to -4% performance
        - East-to-West is harder than West-to-East
        - Altitude effects (DEN, UTA): additional -2% to -3%

        Returns:
            Penalty as negative multiplier (e.g., -0.03 = -3%)
        """
        from math import radians, cos, sin, asin, sqrt

        # Get player's team location
        player_team = player.team
        if player_team not in TEAM_LOCATIONS or game.home_team not in TEAM_LOCATIONS:
            return 0.0

        # Determine if this is home or away game
        if player_team == game.home_team:
            # Home game - minimal travel
            return 0.0

        # Away game - calculate travel
        from_coords = TEAM_LOCATIONS.get(player_team)
        to_coords = TEAM_LOCATIONS.get(game.home_team)

        if not from_coords or not to_coords:
            return 0.0

        # Calculate distance using Haversine formula
        lat1, lon1 = radians(from_coords[0]), radians(from_coords[1])
        lat2, lon2 = radians(to_coords[0]), radians(to_coords[1])

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        radius = 3959  # Earth's radius in miles

        distance_miles = radius * c

        # Calculate time zone difference
        tz_diff = abs((from_coords[1] - to_coords[1]) / 15)  # Rough estimate: 15° = 1 timezone

        # Base fatigue from distance
        if distance_miles < 500:
            distance_penalty = 0.0
        elif distance_miles < 1000:
            distance_penalty = -0.01  # -1%
        elif distance_miles < 1500:
            distance_penalty = -0.02  # -2%
        elif distance_miles < 2000:
            distance_penalty = -0.03  # -3%
        else:
            distance_penalty = -0.05  # -5% for cross-country

        # Time zone penalty
        if tz_diff < 1:
            tz_penalty = 0.0
        elif tz_diff < 2:
            tz_penalty = -0.01
        elif tz_diff < 3:
            tz_penalty = -0.02
        else:
            tz_penalty = -0.03

        # Altitude effects (DEN, UTA are high altitude)
        altitude_teams = ["DEN", "UTA"]
        if game.home_team in altitude_teams:
            # Playing at altitude = additional fatigue
            altitude_penalty = -0.02
        else:
            altitude_penalty = 0.0

        total_penalty = distance_penalty + tz_penalty + altitude_penalty

        # Clamp to reasonable bounds
        return max(-0.08, min(0.0, total_penalty))

    def _calculate_matchup_score(
        self,
        player: Player,
        game: Game,
        stat_type: str
    ) -> float:
        """
        Calculate matchup-specific adjustment factor.

        TIER 4 IMPROVEMENT: Game-specific context factors

        Factors:
        - Rest advantage: Compare team rest days
        - Pace mismatch: Fast team vs slow team
        - Altitude advantage: Home team at altitude

        Returns:
            Adjustment factor (e.g., 1.05 = +5% boost, 0.95 = -5% penalty)
        """
        opponent = self._get_opponent(player, game)

        # 1. Rest advantage calculation
        player_rest = self._get_rest_days_since_last_game(player, game)

        # Get opponent's average rest days (simplified)
        # In production, would query actual opponent's last game
        opponent_rest = 1  # Assume 1 day for comparison

        rest_advantage = player_rest - opponent_rest

        # Rest advantage factor
        if rest_advantage >= 2:
            rest_factor = 1.0 + (0.02 * min(rest_advantage - 1, 3))  # Max +6%
        elif rest_advantage <= -2:
            rest_factor = 1.0 - (0.02 * min(abs(rest_advantage) - 1, 3))  # Max -6%
        else:
            rest_factor = 1.0

        # 2. Pace mismatch
        player_team_pace = TEAM_PACE_RANK.get(player.team, 15)
        opponent_pace = TEAM_PACE_RANK.get(opponent, 15)

        # If both teams are fast-paced, high-scoring game (good for points)
        # If both slow, low-scoring game (bad for points)
        avg_pace = (player_team_pace + opponent_pace) / 2

        if avg_pace <= 10:  # Both slow
            pace_factor = 0.95  # -5% for points
        elif avg_pace >= 20:  # Both fast
            pace_factor = 1.08  # +8% for points
        else:
            pace_factor = 1.0

        # 3. Home court advantage with altitude
        if player.team == game.home_team:
            if player.team in ["DEN", "UTA"]:
                # Home team at altitude has advantage
                home_factor = 1.03
            else:
                # Normal home court (~1-2%)
                home_factor = 1.01
        else:
            home_factor = 1.0

        # Combine factors
        matchup_factor = rest_factor * pace_factor * home_factor

        # Clamp to reasonable bounds
        return max(0.90, min(1.10, matchup_factor))

    def _apply_line_movement_adjustment(
        self,
        edge: float,
        line_open: Optional[float],
        line_current: Optional[float],
        hours_until_game: int = 24
    ) -> float:
        """
        Adjust confidence/edge based on line movement direction.

        TIER 4 IMPROVEMENT: Market signal analysis

        Sharp money vs public money:
        - Early movement (first 2 hours) = sharp money
        - Late movement (last 2 hours) = public money

        Returns:
            Edge adjustment (positive = increase confidence)
        """
        if not line_open or not line_current:
            return 0.0

        movement = line_current - line_open

        # Early sharp money movement
        if hours_until_game > 22:
            if abs(movement) >= 0.5:
                # Sharp money moving in our direction = good
                if (edge > 0 and movement > 0) or (edge < 0 and movement < 0):
                    return 0.3  # Increase edge by 0.3
                else:
                    return -0.3  # Decrease edge

        # Late public money movement
        elif hours_until_game < 2:
            if abs(movement) >= 0.5:
                # Fade the public - if they move against us, that's good
                if (edge > 0 and movement < 0) or (edge < 0 and movement > 0):
                    return 0.2
                else:
                    return -0.2

        return 0.0

    def _apply_adjustments(
        self,
        projection: float,
        player: Player,
        game: Game,
        stat_type: str,
        projected_minutes: float = 30.0
    ) -> Tuple[float, Dict[str, float]]:
        """
        Apply all contextual adjustments to projection.

        TIER 2 IMPROVEMENT: Added fatigue scaling for high-minute players

        Args:
            projection: Base projection value
            player: Player object
            game: Game object
            stat_type: Type of stat (points, rebounds, etc.)
            projected_minutes: Projected minutes for fatigue scaling

        Returns (adjusted_projection, factors_dict)
        """
        factors = {}
        factors["projected_minutes"] = round(projected_minutes, 1)

        # 1. TIER 3: Dynamic opponent defensive adjustment
        # Replaces static TEAM_DEFENSIVE_RANK with actual data
        opponent = self._get_opponent(player, game)
        def_adj = self._get_dynamic_opponent_adjustment(player, opponent, stat_type)
        projection *= (1 + def_adj)
        factors["opponent_defense"] = round(def_adj, 3)

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

        # 3. TIER 2: Non-linear fatigue scaling for high-minute players
        projection, fatigue_factor = self._apply_fatigue_scaling(
            projection, projected_minutes
        )
        factors["fatigue_factor"] = round(fatigue_factor, 3)

        # 4. TIER 3: Usage boost from injured teammates
        # Calculate actual usage boost based on injured teammates' usage rates
        usage_boost = self._calculate_teammate_injury_boost(player, game, stat_type)
        projection *= (1 + usage_boost)
        factors["teammate_injuries"] = round(usage_boost, 3)

        # 5. TIER 4: Travel fatigue adjustment
        travel_penalty = self._calculate_travel_fatigue(player, game)
        projection *= (1 + travel_penalty)
        factors["travel_fatigue"] = round(travel_penalty, 3)

        # 6. TIER 4: Matchup-specific adjustments
        matchup_factor = self._calculate_matchup_score(player, game, stat_type)
        projection *= matchup_factor
        factors["matchup_score"] = round(matchup_factor, 3)

        return max(0, projection), factors

    def _get_dynamic_opponent_adjustment(
        self,
        player: Player,
        opponent: str,
        stat_type: str
    ) -> float:
        """
        Calculate position-specific opponent defensive adjustment.

        TIER 3 IMPROVEMENT: Uses actual stats allowed vs position
        instead of hardcoded rankings.

        Queries recent games to see what the opponent actually allows
        to players of the same position.
        """
        from sqlalchemy import text

        # Map stat_type to column name
        stat_column = {
            "points": "points",
            "rebounds": "rebounds",
            "assists": "assists",
            "threes": "threes"
        }.get(stat_type, "points")

        # Query opponent's average allowed for this position over last 30 days
        # This joins games with player_stats and filters by opponent
        query = text("""
            SELECT AVG(ps.{stat_col}) as avg_allowed,
                   COUNT(*) as sample_size
            FROM player_stats ps
            JOIN games g ON ps.game_id = g.id
            JOIN players p ON ps.player_id = p.id
            WHERE (g.home_team = :opponent OR g.away_team = :opponent)
              AND p.position = :position
              AND g.game_date >= CURRENT_DATE - INTERVAL '30 days'
              AND ps.minutes >= 15
        """.format(stat_col=stat_column))

        result = self.db.execute(query, {
            "opponent": opponent,
            "position": player.position or "G"
        }).fetchone()

        if not result or result.sample_size < 5:
            # Fallback to static rankings if insufficient data
            def_rank = TEAM_DEFENSIVE_RANK.get(opponent, 15)
            if stat_type == "points":
                if def_rank <= 5:
                    return -0.08
                elif def_rank <= 10:
                    return -0.04
                elif def_rank <= 20:
                    return 0.00
                elif def_rank <= 25:
                    return 0.04
                else:
                    return 0.08
            return 0.0

        # Get league average for this position
        league_avg_query = text("""
            SELECT AVG(ps.{stat_col}) as league_value
            FROM player_stats ps
            JOIN players p ON ps.player_id = p.id
            WHERE p.position = :position
              AND ps.minutes >= 15
              AND ps.created_at >= CURRENT_DATE - INTERVAL '30 days'
        """.format(stat_col=stat_column))

        league_result = self.db.execute(league_avg_query, {
            "position": player.position or "G"
        }).fetchone()

        if not league_result or not league_result.league_value:
            return 0.0

        # Extract league average
        league_avg = league_result.league_value

        # Calculate adjustment: (allowed - league_avg) / league_avg
        # If opponent allows MORE than average, positive adjustment (good for player)
        # If opponent allows LESS than average, negative adjustment (bad for player)
        opp_allowed = result.avg_allowed or league_avg

        if league_avg > 0:
            adj = (opp_allowed - league_avg) / league_avg
            # Clamp to reasonable bounds (-15% to +15%)
            adj = max(-0.15, min(0.15, adj))
        else:
            adj = 0.0

        return adj

    def _calculate_teammate_injury_boost(
        self,
        player: Player,
        game: Game,
        stat_type: str
    ) -> float:
        """
        Calculate usage boost from injured teammates.

        TIER 3 IMPROVEMENT: Uses actual usage rates instead of flat 3% boost.

        When a teammate is out, the remaining players absorb some of their
        usage rate. This is position-specific:
        - Guards get assist usage when ballhandlers are out
        - Bigs get rebound usage when other bigs are out
        - Same position = highest boost
        """
        from sqlalchemy import text

        # Get active injuries for this game
        player_team = player.team
        cutoff_date = date.today() - timedelta(days=7)

        injured_query = text("""
            SELECT DISTINCT p.id, p.position, p.name
            FROM player_injuries pi
            JOIN players p ON pi.player_id = p.id
            WHERE p.team = :team
              AND pi.reported_date >= :cutoff
              AND UPPER(pi.status) IN ('OUT', 'DOUBTFUL', 'QUESTIONABLE')
        """)

        injured = self.db.execute(injured_query, {
            "team": player_team,
            "cutoff": cutoff_date
        }).fetchall()

        if not injured:
            return 0.0

        # Get current player's estimated usage rate (from season stats)
        # Simplified: use points per 36 as proxy for usage
        season_stats = self.db.query(PlayerSeasonStats).filter(
            PlayerSeasonStats.player_id == player.id,
            PlayerSeasonStats.season == self.season
        ).first()

        if not season_stats:
            return 0.0

        current_usage_proxy = season_stats.points_per_36 or 15.0

        # Calculate total lost usage from injured teammates
        total_lost_usage = 0.0
        position_match_lost = 0.0

        for inj_player in injured:
            # Get injured player's stats
            inj_stats = self.db.query(PlayerSeasonStats).filter(
                PlayerSeasonStats.player_id == inj_player.id,
                PlayerSeasonStats.season == self.season
            ).first()

            if inj_stats:
                inj_usage = inj_stats.points_per_36 or 10.0

                # Position-specific boost calculation
                if player.position == inj_player.position:
                    # Same position = highest boost (direct replacement)
                    position_match_lost += inj_usage * 0.6
                elif self._positions_adjacent(player.position, inj_player.position):
                    # Adjacent positions (G/F, F/C) = medium boost
                    total_lost_usage += inj_usage * 0.3
                else:
                    # Different positions = minimal boost
                    total_lost_usage += inj_usage * 0.1

        total_lost_usage += position_match_lost

        # Calculate new usage (with diminishing returns)
        # Formula: new_usage = current + 0.5 * lost_usage
        # The 0.5 factor accounts for: some usage goes to other players, coaches adjust
        projected_usage_increase = 0.5 * total_lost_usage

        # Stat-specific adjustments
        if stat_type == "rebounds":
            # Only bigs benefit significantly from rebounding opportunities
            if player.position in ["PG", "SG", "G"]:
                projected_usage_increase *= 0.3  # Guards don't get many extra rebounds
            elif player.position in ["C", "PF", "F"]:
                projected_usage_increase *= 1.2  # Bigs get more rebound chances
        elif stat_type == "assists":
            # Only ballhandlers get assist boost
            if player.position in ["PG", "SG", "SF"]:
                projected_usage_increase *= 1.2
            else:
                projected_usage_increase *= 0.5

        # Calculate boost percentage
        if current_usage_proxy > 0:
            usage_boost = projected_usage_increase / current_usage_proxy
        else:
            usage_boost = 0.0

        # Cap at reasonable maximum (20% boost)
        return min(usage_boost, 0.20)

    def _positions_adjacent(self, pos1: str, pos2: str) -> bool:
        """Check if two positions are adjacent (G/F, F/C overlap)."""
        if not pos1 or not pos2:
            return False

        pos1, pos2 = pos1.upper(), pos2.upper()

        # Normalize position groups
        guards = {"PG", "SG", "G"}
        forwards = {"SF", "PF", "F"}
        centers = {"C"}

        # Same group = adjacent
        if (pos1 in guards and pos2 in guards) or \
           (pos1 in forwards and pos2 in forwards):
            return True

        # F/C are adjacent
        if (pos1 in forwards and pos2 in centers) or \
           (pos1 in centers and pos2 in forwards):
            return True

        return False

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
        2. Fetches player props for that event (with caching to avoid redundant calls)
        3. Extracts the specific player's line for the stat type
        4. Populates odds_fetched_at and odds_last_updated timestamps

        Args:
            player: Player model instance
            game: Game model instance
            stat_type: Stat type (points, rebounds, assists, threes)
            bookmaker: Preferred bookmaker name

        Returns:
            Dict with line data or None if not found
        """
        from datetime import datetime

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

            # Create parser with the requested bookmaker as top priority
            # This ensures we only return lines from the requested bookmaker
            if self._player_props_parser is None:
                self._player_props_parser = PlayerPropsParser(
                    bookmaker_priority=[bookmaker.lower()]
                )
            # Update priority if bookmaker changes between calls
            elif self._player_props_parser.bookmaker_priority[0] != bookmaker.lower():
                self._player_props_parser = PlayerPropsParser(
                    bookmaker_priority=[bookmaker.lower()]
                )

            # Step 1: Get Odds API event ID for this game
            odds_event_id = await self._game_odds_mapper.get_odds_event_id(game)

            if not odds_event_id:
                logger.debug(
                    f"No odds_event_id found for game {game.id}, "
                    f"falling back to estimation"
                )
                return None

            # Step 2: Check cache for existing odds data (prevents redundant API calls)
            cache_key = (game.id, stat_type)
            current_time = datetime.utcnow()

            if cache_key in self._odds_cache:
                cached_response, cached_at = self._odds_cache[cache_key]
                cache_age = (current_time - cached_at).total_seconds()

                if cache_age < self._cache_ttl_seconds:
                    logger.debug(
                        f"Using cached odds for game {game.id}, stat_type={stat_type} "
                        f"(age: {cache_age:.0f}s)"
                    )
                    odds_response = cached_response
                else:
                    # Cache expired, fetch fresh data
                    logger.debug(
                        f"Cache expired for game {game.id}, stat_type={stat_type}, "
                        f"fetching fresh odds"
                    )
                    odds_response = await self._fetch_and_cache_odds(
                        odds_event_id, cache_key, current_time
                    )
            else:
                # Cache miss, fetch from API
                logger.debug(
                    f"Cache miss for game {game.id}, stat_type={stat_type}, "
                    f"fetching from Odds API"
                )
                odds_response = await self._fetch_and_cache_odds(
                    odds_event_id, cache_key, current_time
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
                actual_bookmaker = line_data.get("bookmaker", bookmaker)
                fetched_at = line_data.get("fetched_at", current_time.isoformat())

                return {
                    "line": line_data["line"],
                    "line_open": line_data["line"],  # TODO: fetch opening line separately
                    "over_price": line_data.get("over_price", -110),
                    "under_price": line_data.get("under_price", -110),
                    "bookmaker": actual_bookmaker,
                    "line_source": actual_bookmaker,  # Track actual source
                    "fetched_at": fetched_at,
                    "odds_fetched_at": current_time,  # For database storage
                    "odds_last_updated": current_time  # For database storage
                }

            logger.debug(
                f"No line found for {player.name} {stat_type} in event {odds_event_id}"
            )
            return None

        except Exception as e:
            logger.error(
                f"Error fetching real odds for {player.name} {stat_type}: {e}",
                exc_info=True
            )
            return None

    async def _fetch_and_cache_odds(
        self,
        odds_event_id: str,
        cache_key: tuple,
        current_time: datetime
    ) -> Optional[Dict]:
        """
        Fetch odds from API and cache the response.

        Args:
            odds_event_id: The Odds API event ID
            cache_key: Cache key tuple (game_id, stat_type)
            current_time: Current datetime for cache timestamp

        Returns:
            Odds response dict or None
        """
        odds_response = await self._odds_api_service.get_event_player_props(
            odds_event_id
        )

        # Cache the response even if it's empty (to prevent repeated failed calls)
        if odds_response is not None:
            self._odds_cache[cache_key] = (odds_response, current_time)

        return odds_response

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
                    "bookmaker": "estimated",
                    "line_source": "estimated"
                }

        # Fallback to position average
        return {
            "line": 15.0,  # Generic fallback
            "line_open": 15.0,
            "over_price": -110,
            "under_price": -110,
            "bookmaker": "estimated",
            "line_source": "estimated"
        }

    def _calculate_confidence(
        self,
        edge: float,
        projection_data: Dict,
        line_data: Dict
    ) -> float:
        """
        Calculate confidence based on edge over line, sample size, and volatility.

        Confidence factors:
        - Base confidence: 0.50
        - Edge contribution: up to +0.30 (diminishing returns)
        - Sample size bonus: +0.02 to +0.15
        - Rookie penalty: -0.10 to -0.30 for players with < 50 career games
        - Volatility penalty: -0.05 to -0.25 for high std_dev
        - Maximum confidence: 0.85 (85%)
        """
        base_confidence = 0.50

        # Edge contributes to confidence (with diminishing returns)
        edge_contribution = min(edge / 10.0, 0.30)
        base_confidence += edge_contribution

        # Sample size contribution (more aggressive)
        factors = projection_data.get("factors", {})
        sample_size = factors.get("sample_size", 0)

        if sample_size >= 30:
            base_confidence += 0.15
        elif sample_size >= 20:
            base_confidence += 0.10
        elif sample_size >= 15:
            base_confidence += 0.05
        elif sample_size >= 10:
            base_confidence += 0.02
        else:
            # Small sample size penalty
            base_confidence -= 0.10

        # Volatility penalty (more aggressive)
        std_dev = factors.get("std_dev")
        if std_dev and std_dev > 0:
            # High volatility = much less confident
            # Std dev > 8 = very volatile (penalty up to 0.25)
            vol_penalty = min(std_dev / 8.0, 0.25)
            base_confidence -= vol_penalty

        # Rookie/inexperienced player penalty
        # Players with fewer than 50 career games have higher variance
        career_games = factors.get("career_games", sample_size)
        if career_games < self.ROOKIE_GAMES_THRESHOLD:
            # Scale penalty: 50 games = 0%, 10 games = -20%
            rookie_penalty = 0.20 * (1 - career_games / self.ROOKIE_GAMES_THRESHOLD)
            base_confidence -= rookie_penalty

        # **TIER 1 FIX**: Apply calibration correction based on actual performance data
        # Historical analysis showed:
        # - 70-79% confidence predictions: 100% accuracy (overconfident, need -5%)
        # - 80%+ confidence predictions: 50% accuracy (severely overconfident, need -15%)
        # The model systematically overstates confidence, especially at higher levels
        calibrated_confidence = self._calibrate_confidence(base_confidence)

        # Cap confidence at 80% (lowered from 85% due to calibration findings)
        # Also set a minimum of 40% for valid bets
        return round(max(0.40, min(0.80, calibrated_confidence)), 2)

    def _calibrate_confidence(self, raw_confidence: float) -> float:
        """
        Apply calibration correction based on historical prediction performance.

        Based on actual tracking data (14 predictions analyzed):
        - 70-79% raw confidence: 100% actual win rate → reduce by 5%
        - 80%+ raw confidence: 50% actual win rate → reduce by 15%
        - 60-69% raw confidence: Need more data, no adjustment

        This correction prevents overconfidence in betting decisions.
        """
        if raw_confidence >= 0.80:
            # Severe overconfidence - 80%+ predictions only win 50% of the time
            return raw_confidence - 0.15
        elif raw_confidence >= 0.70:
            # Moderate overconfidence - 70-79% predictions win 100% (unexpected)
            # Reduce by 5% to be more conservative
            return raw_confidence - 0.05
        else:
            # Lower confidence levels don't have enough data yet
            return raw_confidence

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
        Calculate ACTUAL rest days since player's last game.

        Uses PlayerSeasonStats.last_game_date to determine when the player
        last played, then calculates days between that and this game.
        """
        from datetime import date, datetime

        # Get player's season stats which has last_game_date
        season_stats = self.db.query(PlayerSeasonStats).filter(
            PlayerSeasonStats.player_id == player.id,
            PlayerSeasonStats.season == self.season
        ).first()

        if not season_stats or not season_stats.last_game_date:
            # No previous game found (rookie/first game)
            # Default to 2 days rest
            return 2

        # Calculate days between last_game_date and this game
        last_game_date = season_stats.last_game_date

        # Handle game.game_date which might be date or datetime
        if isinstance(game.game_date, datetime):
            game_date = game.game_date.date()
        else:
            game_date = game.game_date

        rest_days = (game_date - last_game_date).days

        # Sanity check: rest days should be reasonable (0-14)
        # Also ensure we're not getting negative rest days
        return max(0, min(rest_days, 14))


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
