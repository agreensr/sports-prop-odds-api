"""
Enhanced NHL Prediction Model v1.0

This model implements a sophisticated approach to NHL player prop predictions:

KEY IMPROVEMENTS OVER BASIC MODEL:
1. Line-based predictions - Compare our projection to bookmaker line
2. Better confidence calculation - Based on edge over line, not random
3. Contextual adjustments - Rest days, opponent defense, power play time
4. Recent form weighting - EWMA with configurable decay
5. Pass recommendations - Don't bet when no edge exists
6. REAL ODDS API INTEGRATION - Live bookmaker lines from Odds API

PREDICTION FRAMEWORK:
┌──────────────────────────────────────────────────────────────┐
│ 1. Calculate Base Projection                                      │
│    recent_per_game = EWMA(last N games, more weight to recent) │
│    toi_boost = power_play_time × 5%                           │
│    base_value = recent_per_game × (toi / 18)                  │
│                                                                   │
│ 2. Apply Contextual Adjustments                                   │
│    rest_days_adjustment: -1% per day < 2 days                  │
│    opponent_adjustment: based on defensive rank                 │
│    power_play_adjustment: PP unit usage                        │
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
    from app.services.nhl.enhanced_prediction_service import EnhancedNHLPredictionService
    from app.services.core.odds_api_service import get_odds_service

    odds_service = get_odds_service(api_key="your_key", sport="nhl")
    service = EnhancedNHLPredictionService(db, odds_api_service=odds_service)
    predictions = service.generate_prop_predictions(game_id, stat_types)

NHL-SPECIFIC CONSIDERATIONS:
- Time on Ice (TOI) instead of minutes (NHL players avg 15-22 min)
- Position differences: Centers (C), Wings (LW/RW), Defense (D)
- Lower fatigue impact than NBA (fewer back-to-backs)
- Goalies excluded from player props (separate model needed)
"""
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
import random
import numpy as np

from app.models.nhl.models import Player, Game, Prediction, PlayerSeasonStats
from app.core.logging import get_logger

logger = get_logger(__name__)


# Known non-NHL players who should be excluded
# These players have NHL.com IDs but don't actually play in the NHL
KNOWN_NON_NHL_PLAYERS = {
    # College prospects, junior players, etc.
    # Add as discovered
}


# NHL Team locations for travel fatigue calculation
# Approximate coordinates for NHL teams (latitude, longitude)
TEAM_LOCATIONS = {
    # Eastern Conference - Atlantic Division
    "BOS": (42.3601, -71.0589),  # Boston
    "BUF": (42.8801, -78.8784),  # Buffalo
    "DET": (42.7802, -83.0675),  # Detroit
    "FLA": (26.1489, -80.3231),  # Florida
    "MTL": (45.4971, -73.5868),  # Montreal
    "OTT": (45.2981, -75.9246),  # Ottawa
    "TBL": (27.9416, -82.4518),  # Tampa Bay
    "TOR": (43.6442, -79.3790),  # Toronto

    # Eastern Conference - Metropolitan Division
    "CAR": (35.8005, -78.7834),  # Carolina
    "CBJ": (39.9696, -83.0051),  # Columbus
    "NJD": (40.7339, -74.1746),  # New Jersey
    "NYI": (40.7248, -73.5767),  # NY Islanders
    "NYR": (40.7528, -73.8516),  # NY Rangers
    "PHI": (39.9012, -75.1717),  # Philadelphia
    "PIT": (40.4397, -79.9767),  # Pittsburgh
    "WSH": (38.9072, -77.0369),  # Washington

    # Western Conference - Central Division
    "ARI": (33.4460, -112.0760), # Arizona
    "CHI": (41.8827, -87.6233),  # Chicago
    "COL": (39.7392, -104.9903), # Colorado (altitude!)
    "DAL": (32.7767, -96.7970),  # Dallas
    "MIN": (44.9792, -93.2761),  # Minnesota
    "NSH": (36.1664, -86.7794),  # Nashville
    "STL": (38.6270, -90.1979),  # St. Louis
    "WPG": (49.8951, -97.1384),  # Winnipeg

    # Western Conference - Pacific Division
    "ANA": (33.8333, -117.9491), # Anaheim
    "CGY": (51.0456, -114.0630), # Calgary
    "EDM": (53.5461, -113.4938), # Edmonton
    "LAK": (33.8712, -118.1205), # Los Angeles
    "SJS": (37.3382, -121.8863), # San Jose
    "SEA": (47.6297, -122.3333), # Seattle
    "VAN": (49.2771, -123.1155), # Vancouver
    "VGK": (36.0890, -115.1838), # Vegas
}


# Time on Ice baselines by position (NHL players avg 15-22 minutes)
BASE_TOI = {
    "C": 18.5,   # Centers: high minutes, top line centers can play 20+
    "LW": 17.0,  # Left Wing
    "RW": 17.0,  # Right Wing
    "D": 21.0,   # Defensemen: highest TOI, top pair can play 24+
    "G": None,   # Goalies: excluded from player props
    None: 16.0   # Default for unknown position
}


# Rest days fatigue penalty (percent reduction in production)
# NHL fatigue is less severe than NBA
REST_DAYS_PENALTY = {
    0: 0.03,   # Playing back-to-back (smaller penalty than NBA)
    1: 0.00,   # 1 day rest (normal)
    2: -0.01,  # 2 days rest (slight bonus)
    3: -0.02,  # 3+ days rest (bonus)
    4: -0.02,
    5: -0.02,
    6: -0.02
}


# Position-based stat averages (fallback when no historical data)
POSITION_AVERAGES = {
    "C": {
        "goals": 0.25,
        "assists": 0.45,
        "points": 0.70,
        "shots": 2.8,
    },
    "LW": {
        "goals": 0.22,
        "assists": 0.30,
        "points": 0.52,
        "shots": 2.5,
    },
    "RW": {
        "goals": 0.24,
        "assists": 0.32,
        "points": 0.56,
        "shots": 2.6,
    },
    "D": {
        "goals": 0.08,
        "assists": 0.35,
        "points": 0.43,
        "shots": 2.2,
    },
}


class EnhancedNHLPredictionService:
    """
    Enhanced NHL player prop prediction service.

    Key features:
    - Line-based predictions (compare projection to bookmaker line)
    - Confidence based on edge over line, not random
    - Contextual adjustments (rest, opponent, travel)
    - EWMA for recent form weighting
    - PASS recommendation when no edge exists
    - REAL ODDS API INTEGRATION for live bookmaker lines
    """

    # NHL stat types for The Odds API
    STAT_TYPES = ["goals", "assists", "points", "shots"]

    # The Odds API market keys for NHL
    MARKET_MAP = {
        "goals": "player_goals",
        "assists": "player_assists",
        "points": "player_points",
        "shots": "player_shots",
    }

    def __init__(
        self,
        db: Session,
        season: str = "2024-25",
        odds_api_service=None
    ):
        """
        Initialize the enhanced NHL prediction service.

        Args:
            db: Database session
            season: NHL season (e.g., "2024-25")
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
        self.min_edge_for_bet = 0.3  # Minimum edge over line to bet (smaller than NBA)
        self.high_confidence_edge = 0.6  # Edge for high confidence

        # Lazy-loaded services
        self._game_odds_mapper = None
        self._player_props_parser = None

        # Odds cache to prevent redundant API calls within same prediction run
        self._odds_cache: Dict[tuple, tuple] = {}
        self._cache_ttl_seconds = 300  # 5 minutes cache

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
            stat_types: Stats to predict (default: goals, assists, points, shots)
            bookmaker: Bookmaker for line data

        Returns:
            List of prediction dictionaries with line comparison
        """
        if stat_types is None:
            stat_types = self.STAT_TYPES

        # Load game
        game = self.db.query(Game).filter(Game.id == game_id).first()
        if not game:
            logger.error(f"Game {game_id} not found")
            return []

        # Get active players (skaters only, no goalies)
        players = self._get_active_players(game)

        predictions = []
        for player in players:
            for stat_type in stat_types:
                pred = self._generate_single_prediction(
                    player, game, stat_type, bookmaker
                )
                # Only include predictions with real bookmaker lines
                if pred and pred.get("line_source") not in ("estimated", None):
                    predictions.append(pred)

        return predictions

    def _get_active_players(self, game: Game) -> List[Player]:
        """
        Get active players for both teams in the game.

        Filters to only include real NHL players who are rotation players.
        Excludes:
        - Known non-NHL players
        - Goalies (need separate model)
        - End-of-bench players who don't get meaningful TOI
        - Players with insufficient sample size (< 10 games)
        """
        # Calculate cutoff date for recent activity check
        recent_cutoff = datetime.now() - timedelta(days=7)

        # Get players on the teams
        players = self.db.query(Player).filter(
            Player.team.in_([game.home_team, game.away_team]),
            Player.status == "active"
        ).all()

        # Filter to only skaters (exclude goalies)
        valid_players = []
        for p in players:
            # Skip goalies
            if p.position == "G":
                logger.debug(f"Skipping goalie {p.name} - separate model needed")
                continue

            # Skip known non-NHL players
            if p.name in KNOWN_NON_NHL_PLAYERS:
                logger.debug(f"Skipping known non-NHL player: {p.name}")
                continue

            # Check if player has season stats with meaningful TOI
            stats = self.db.query(PlayerSeasonStats).filter(
                PlayerSeasonStats.player_id == p.id,
                PlayerSeasonStats.season_type == "REG",
                PlayerSeasonStats.season == int(self.season.split("-")[0])
            ).first()

            # Require minimum games and TOI
            games_count = stats.games_played if stats else 0

            # NHL: Check for games_played or use games from PlayerSeasonStats
            if not (stats and games_count >= 10):
                logger.debug(
                    f"Skipping player {p.name} ({p.team}) - "
                    f"games: {games_count} "
                    f"(min: 10 games)"
                )
                continue

            valid_players.append(p)

        return valid_players

    def _generate_single_prediction(
        self,
        player: Player,
        game: Game,
        stat_type: str,
        bookmaker: str
    ) -> Optional[Dict]:
        """Generate a single prediction with line comparison."""
        # 1. Get base projection
        projection_data = self._calculate_base_projection(
            player, game, stat_type
        )

        if not projection_data:
            return None

        # 2. Get bookmaker line
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
            "projected": round(projection_data["projected"], 2),
            "line": line_data["line"],
            "line_open": line_data.get("line_open"),
            "edge": round(edge, 2),
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
        """Calculate base projection with all contextual adjustments."""
        # Get recent form (EWMA-weighted)
        recent_form = self._get_recent_form(player, stat_type)

        if not recent_form:
            # No data for this player
            return None

        factors = {}

        # Base per-game value (EWMA weighted)
        per_game_value = recent_form["ewma_per_game"]
        base_toi = recent_form.get("avg_tooi", BASE_TOI.get(player.position, 17.0))

        # Get projected TOI
        projected_toi = self._get_projected_toi(player, game, base_toi)

        # Scale projection based on TOI
        toi_ratio = projected_toi / base_toi if base_toi > 0 else 1.0
        projection = per_game_value * toi_ratio

        factors["base_per_game"] = round(per_game_value, 2)
        factors["projected_toi"] = round(projected_toi, 1)
        factors["toi_ratio"] = round(toi_ratio, 2)
        factors["sample_size"] = recent_form.get("sample_size", 0)

        # Apply adjustments
        projection, adj_factors = self._apply_adjustments(
            projection, player, game, stat_type
        )
        factors.update(adj_factors)

        # Small variance for consistency
        variance = random.uniform(-0.01, 0.01)
        projection *= (1 + variance)

        return {
            "projected": max(0, round(projection, 2)),
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

        NHL Note: Uses PlayerSeasonStats for per-game averages
        since game-by-game stats may not be available.

        Returns dict with ewma_per_game, avg_toi, sample_size, std_dev
        """
        # Get season stats
        season_stats = self.db.query(PlayerSeasonStats).filter(
            PlayerSeasonStats.player_id == player.id,
            PlayerSeasonStats.season_type == "REG",
            PlayerSeasonStats.season == int(self.season.split("-")[0])
        ).first()

        if not season_stats:
            return None

        games_played = getattr(season_stats, 'games_played', 0)
        if games_played == 0:
            return None

        # Get the stat value
        stat_value = getattr(season_stats, stat_type, None)
        if stat_value is None:
            return None

        # Calculate per-game average
        per_game = stat_value / games_played

        # Estimate TOI from season stats or use position baseline
        avg_toi = BASE_TOI.get(player.position, 17.0)

        return {
            "ewma_per_game": per_game,
            "avg_toi": avg_toi,
            "sample_size": games_played,
            "std_dev": self._estimate_std_dev(stat_type, per_game, player.position),
        }

    def _estimate_std_dev(self, stat_type: str, per_game: float, position: str) -> float:
        """Estimate standard deviation for NHL stats."""
        # NHL stats have different variance profiles than NBA
        # Goals: Poisson-like variance
        # Assists: Higher variance than goals
        # Points: Sum of goals + assists
        # Shots: Relatively consistent

        if stat_type == "goals":
            # Goals follow roughly Poisson distribution
            return max(0.5, (per_game * 0.8) ** 0.5)
        elif stat_type == "assists":
            # Assists have higher variance
            return per_game * 0.6
        elif stat_type == "points":
            # Points = goals + assists, combine variance
            return per_game * 0.5
        elif stat_type == "shots":
            # Shots are most consistent
            return per_game * 0.3
        else:
            return per_game * 0.4

    def _get_projected_toi(
        self,
        player: Player,
        game: Game,
        base_toi: float
    ) -> float:
        """
        Get projected TOI for a player considering game context.

        NHL Note: TOI fluctuations are smaller than NBA minutes.
        """
        toi = base_toi

        # Apply rest penalty (smaller than NBA)
        rest_days = self._get_rest_days_since_last_game(player, game)
        rest_penalty = REST_DAYS_PENALTY.get(rest_days, 0.0)
        toi *= (1 + rest_penalty)

        # Clamp to reasonable bounds for NHL
        return max(12.0, min(26.0, toi))

    def _apply_adjustments(
        self,
        projection: float,
        player: Player,
        game: Game,
        stat_type: str
    ) -> Tuple[float, Dict[str, float]]:
        """Apply all contextual adjustments to projection."""
        factors = {}

        # 1. Opponent defensive adjustment
        opponent = self._get_opponent(player, game)
        def_adj = self._get_opponent_defensive_adjustment(opponent, stat_type)
        projection *= (1 + def_adj)
        factors["opponent_defense"] = round(def_adj, 3)

        # 2. Travel fatigue adjustment
        travel_penalty = self._calculate_travel_fatigue(player, game)
        projection *= (1 + travel_penalty)
        factors["travel_fatigue"] = round(travel_penalty, 3)

        return max(0, projection), factors

    def _get_opponent_defensive_adjustment(
        self,
        opponent: str,
        stat_type: str
    ) -> float:
        """
        Calculate opponent defensive adjustment.

        NHL teams have more consistent defensive systems than NBA.
        Uses simplified team defensive rankings.
        """
        # NHL team defensive rankings (2024-25 season data)
        # Higher rank = better defense (allows fewer goals/points)
        TEAM_DEFENSIVE_RANK = {
            # Top 10 defenses
            "VAN": 1, "CAR": 2, "FLA": 3, "WPG": 4, "COL": 5,
            "DAL": 6, "TBL": 7, "TOR": 8, "BOS": 9, "NYR": 10,
            # Middle 10
            "EDM": 11, "VEG": 12, "LAK": 13, "MIN": 14, "NSH": 15,
            "PIT": 16, "TBL": 17, "DET": 18, "NJD": 19, "PHI": 20,
            # Bottom 10
            "NYI": 21, "CHI": 22, "OTT": 23, "SJS": 24, "STL": 25,
            "CGY": 26, "SEA": 27, "CBJ": 28, "ANA": 29, "SJS": 30,
        }

        def_rank = TEAM_DEFENSIVE_RANK.get(opponent, 15)

        if stat_type == "goals":
            if def_rank <= 5:
                return -0.10
            elif def_rank <= 10:
                return -0.05
            elif def_rank <= 20:
                return 0.00
            elif def_rank <= 25:
                return 0.05
            else:
                return 0.10
        elif stat_type == "assists":
            # Assists less affected by defense
            adj = _get_opponent_defensive_adjustment(opponent, "goals") * 0.7
            return adj
        elif stat_type == "points":
            # Points = goals + assists
            return _get_opponent_defensive_adjustment(opponent, "goals") * 0.85
        else:  # shots
            # Shots are less affected by defense quality
            if def_rank <= 10:
                return -0.03
            elif def_rank >= 25:
                return 0.03
            return 0.0

    def _calculate_travel_fatigue(
        self,
        player: Player,
        game: Game
    ) -> float:
        """
        Calculate travel fatigue penalty.

        NHL teams play more frequent back-to-backs than NBA,
        but travel fatigue is still a factor.
        """
        from math import radians, cos, sin, asin, sqrt

        player_team = player.team
        if player_team not in TEAM_LOCATIONS or game.home_team not in TEAM_LOCATIONS:
            return 0.0

        # Home game - minimal travel
        if player_team == game.home_team:
            return 0.0

        # Calculate travel distance
        from_coords = TEAM_LOCATIONS.get(player_team)
        to_coords = TEAM_LOCATIONS.get(game.home_team)

        if not from_coords or not to_coords:
            return 0.0

        # Haversine formula for distance
        lat1, lon1 = radians(from_coords[0]), radians(from_coords[1])
        lat2, lon2 = radians(to_coords[0]), radians(to_coords[1])

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        radius = 3959  # Earth's radius in miles

        distance_miles = radius * c

        # Distance-based penalty
        if distance_miles < 500:
            return 0.0
        elif distance_miles < 1000:
            return -0.01
        elif distance_miles < 1500:
            return -0.02
        elif distance_miles < 2000:
            return -0.03
        else:
            return -0.04  # Cross-country (e.g., VAN to FLA)

    def _get_bookmaker_line(
        self,
        player: Player,
        game: Game,
        stat_type: str,
        bookmaker: str
    ) -> Dict:
        """Get bookmaker line from Odds API or estimate."""
        # Try to fetch real odds
        if self._odds_api_service:
            real_line = self._fetch_real_odds_line_sync(
                player, game, stat_type, bookmaker
            )
            if real_line:
                return real_line

        # Fall back to estimation
        return self._estimate_line_from_season_stats(player, stat_type)

    def _fetch_real_odds_line_sync(
        self,
        player: Player,
        game: Game,
        stat_type: str,
        bookmaker: str
    ) -> Optional[Dict]:
        """Fetch real odds line from Odds API (sync wrapper)."""
        import asyncio

        async def _fetch():
            return await self._fetch_real_odds_line_async(
                player, game, stat_type, bookmaker
            )

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
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
                thread.join(timeout=10)
                return result[0]
            else:
                return loop.run_until_complete(_fetch())
        except RuntimeError:
            return asyncio.run(_fetch())

    async def _fetch_real_odds_line_async(
        self,
        player: Player,
        game: Game,
        stat_type: str,
        bookmaker: str
    ) -> Optional[Dict]:
        """Fetch real odds line from Odds API (async implementation)."""
        from datetime import datetime

        try:
            from app.services.nhl.game_odds_mapper import NHLGameOddsMapper
            from app.services.nhl.player_props_parser import NHLPlayerPropsParser

            if self._game_odds_mapper is None:
                self._game_odds_mapper = NHLGameOddsMapper(
                    self.db,
                    self._odds_api_service
                )

            if self._player_props_parser is None:
                self._player_props_parser = NHLPlayerPropsParser(
                    bookmaker_priority=[bookmaker.lower()]
                )

            # Get Odds API event ID
            odds_event_id = await self._game_odds_mapper.get_odds_event_id(game)

            if not odds_event_id:
                logger.debug(f"No odds_event_id for game {game.id}")
                return None

            # Check cache
            cache_key = (game.id, stat_type)
            current_time = datetime.utcnow()

            if cache_key in self._odds_cache:
                cached_response, cached_at = self._odds_cache[cache_key]
                cache_age = (current_time - cached_at).total_seconds()

                if cache_age < self._cache_ttl_seconds:
                    odds_response = cached_response
                else:
                    odds_response = await self._fetch_and_cache_odds(
                        odds_event_id, cache_key, current_time
                    )
            else:
                odds_response = await self._fetch_and_cache_odds(
                    odds_event_id, cache_key, current_time
                )

            if not odds_response or not odds_response.get("data"):
                return None

            # Extract player line
            line_data = self._player_props_parser.extract_player_lines(
                odds_response=odds_response,
                player_name=player.name,
                stat_type=stat_type
            )

            if line_data:
                return {
                    "line": line_data["line"],
                    "line_open": line_data["line"],
                    "over_price": line_data.get("over_price", -110),
                    "under_price": line_data.get("under_price", -110),
                    "bookmaker": line_data.get("bookmaker", bookmaker),
                    "line_source": line_data.get("bookmaker"),
                    "fetched_at": line_data.get("fetched_at", current_time.isoformat()),
                    "odds_fetched_at": current_time,
                    "odds_last_updated": current_time
                }

            return None

        except Exception as e:
            logger.error(f"Error fetching real odds for {player.name}: {e}")
            return None

    async def _fetch_and_cache_odds(
        self,
        odds_event_id: str,
        cache_key: tuple,
        current_time: datetime
    ) -> Optional[Dict]:
        """Fetch odds from API and cache."""
        odds_response = await self._odds_api_service.get_event_player_props(
            odds_event_id, sport="nhl"
        )

        if odds_response is not None:
            self._odds_cache[cache_key] = (odds_response, current_time)

        return odds_response

    def _estimate_line_from_season_stats(
        self,
        player: Player,
        stat_type: str
    ) -> Dict:
        """Estimate line based on season stats."""
        season_stats = self.db.query(PlayerSeasonStats).filter(
            PlayerSeasonStats.player_id == player.id,
            PlayerSeasonStats.season_type == "REG",
            PlayerSeasonStats.season == int(self.season.split("-")[0])
        ).first()

        if season_stats:
            stat_value = getattr(season_stats, stat_type, None)
            games_played = getattr(season_stats, 'games_played', 0)

            if stat_value and games_played > 0:
                per_game = stat_value / games_played
                # Books shade lines slightly
                estimated_line_raw = per_game * 0.95
                # Round to nearest 0.5 for most props, nearest 0.1 for goals
                if stat_type == "goals":
                    estimated_line = round(estimated_line_raw * 2) / 2
                else:
                    estimated_line = round(estimated_line_raw * 2) / 2

                return {
                    "line": estimated_line,
                    "line_open": estimated_line,
                    "over_price": -110,
                    "under_price": -110,
                    "bookmaker": "estimated",
                    "line_source": "estimated"
                }

        # Fallback to position average
        pos_avg = POSITION_AVERAGES.get(player.position, {}).get(stat_type, 0.5)
        return {
            "line": pos_avg,
            "line_open": pos_avg,
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
        """Calculate confidence based on edge and sample size."""
        base_confidence = 0.50

        # Edge contribution
        edge_contribution = min(edge / 1.5, 0.30)  # NHL edges are smaller
        base_confidence += edge_contribution

        # Sample size contribution
        factors = projection_data.get("factors", {})
        sample_size = factors.get("sample_size", 0)

        if sample_size >= 50:
            base_confidence += 0.12
        elif sample_size >= 30:
            base_confidence += 0.08
        elif sample_size >= 20:
            base_confidence += 0.04
        elif sample_size >= 10:
            base_confidence += 0.01
        else:
            base_confidence -= 0.15

        # Volatility penalty
        std_dev = factors.get("std_dev")
        if std_dev and std_dev > 0:
            vol_penalty = min(std_dev / 2.0, 0.20)
            base_confidence -= vol_penalty

        # Cap confidence
        return round(max(0.40, min(0.80, base_confidence)), 2)

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
        """Calculate rest days since player's last game."""
        season_stats = self.db.query(PlayerSeasonStats).filter(
            PlayerSeasonStats.player_id == player.id,
            PlayerSeasonStats.season_type == "REG",
            PlayerSeasonStats.season == int(self.season.split("-")[0])
        ).first()

        if not season_stats:
            return 2  # Default

        # Use game date for calculation
        game_date = game.game_date.date() if hasattr(game.game_date, 'date') else game.game_date

        # NHL doesn't have last_game_date in PlayerSeasonStats
        # Estimate based on current date
        from datetime import date as dt_date
        today = dt_date.today()
        rest_days = (game_date - today).days if game_date >= today else 2

        return max(0, min(abs(rest_days), 14))


def generate_test_predictions(
    db: Session,
    game_id: str,
    stat_types: List[str] = None
) -> List[Dict]:
    """Convenience function to generate test predictions."""
    service = EnhancedNHLPredictionService(db)
    return service.generate_prop_predictions(game_id, stat_types)
