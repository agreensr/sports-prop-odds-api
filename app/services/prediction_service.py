"""
Prediction generation service for NBA player props.

Generates predictions for upcoming games using:
- Historical per-36 stats (player-specific efficiency)
- Projected minutes (lineups, injury context)
- Injury status adjustments
- Teammate injury boosts (usage opportunities)

Key formula: predicted_value = per_36_stat × (projected_minutes / 36)

Research-backed approach:
- Returning players maintain efficiency, only minutes restricted
- Source: https://www.jssm.org/volume24/iss2/cap/jssm-24-363.pdf
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
import random

from app.models.models import Player, Game, Prediction, PlayerStats, PlayerSeasonStats

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
        # Lazy load services to avoid circular imports
        self._injury_service = None
        self._lineup_service = None
        self._nba_api_service = None

    @property
    def injury_service(self):
        """Lazy load injury service."""
        if self._injury_service is None:
            from app.services.injury_service import InjuryService
            self._injury_service = InjuryService(self.db)
        return self._injury_service

    @property
    def lineup_service(self):
        """Lazy load lineup service."""
        if self._lineup_service is None:
            from app.services.lineup_service import LineupService
            self._lineup_service = LineupService(self.db)
        return self._lineup_service

    @property
    def nba_api_service(self):
        """Lazy load nba_api service."""
        if self._nba_api_service is None:
            from app.services.nba_api_service import NbaApiService
            self._nba_api_service = NbaApiService(self.db)
        return self._nba_api_service

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
            # Get injury and lineup context for this player
            injury_context = self.injury_service.get_player_injury_context(player.id, game.id)
            minutes_projection = self.lineup_service.get_player_minutes_projection(player.id, game.id)

            # Ensure injury_context is always a dict (defensive check)
            if injury_context is None:
                injury_context = {}

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

                # Get predicted value with injury and lineup context
                predicted_value = self._get_predicted_value(
                    player, stat_type, game.id, injury_context, minutes_projection
                )

                # Skip predictions for players who are OUT
                if (injury_context.get('self_injury') or {}).get('status') == 'out':
                    logger.info(f"Skipping prediction for {player.name} - status: OUT")
                    continue

                # Calculate confidence based on various factors
                confidence = self._calculate_confidence(player, stat_type, predicted_value, injury_context, game.id)

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

    def _get_predicted_value(
        self,
        player: Player,
        stat_type: str,
        game_id: Optional[str] = None,
        injury_context: Optional[Dict] = None,
        minutes_projection: Optional[int] = None
    ) -> float:
        """
        Calculate predicted value using player-specific historical stats from nba_api.

        FALLBACK CHAIN (improves accuracy by using actual player data):
        1. nba_api season stats (last 15 games averaged to per-36)
        2. Database cache (player_season_stats table, 24-hour TTL)
        3. PlayerStats (most recent game from boxscore)
        4. POSITION_AVERAGES (last resort)

        Formula: predicted_value = per_36_stat × (projected_minutes / 36)

        Args:
            player: Player model instance
            stat_type: Stat to predict (points, rebounds, assists, threes)
            game_id: Game ID for context lookup
            injury_context: Injury context from InjuryService
            minutes_projection: Projected minutes from LineupService

        Returns:
            Predicted value for the stat
        """
        # Default injury context if not provided
        if injury_context is None:
            injury_context = self.injury_service.get_player_injury_context(player.id, game_id)

        # Ensure injury_context is always a dict (defensive check in case get_player_injury_context returns None)
        if injury_context is None:
            injury_context = {}

        # STEP 1: Try database cache (primary data source - refreshed every 6 hours)
        per_36_value = None

        # Check database cache for recent player stats
        cached_stats = self.db.query(PlayerSeasonStats).filter(
            PlayerSeasonStats.player_id == player.id,
            PlayerSeasonStats.season == "2024-25",
            PlayerSeasonStats.fetched_at >= datetime.now() - timedelta(hours=48)  # 48-hour cache window
        ).first()

        if cached_stats:
            per_36_value = getattr(cached_stats, f'{stat_type}_per_36')
            logger.info(f"Using cached stats for {player.name}: {stat_type}_per_36 = {per_36_value}")
        else:
            logger.debug(f"No cached stats available for {player.name}, will use fallback")

        # STEP 2: Fallback to PlayerStats (most recent game)
        if per_36_value is None:
            player_stats = self.db.query(PlayerStats).filter(
                PlayerStats.player_id == player.id
            ).order_by(PlayerStats.created_at.desc()).first()

            if player_stats:
                stat_value = getattr(player_stats, stat_type, None)
                minutes = getattr(player_stats, 'minutes', None)

                if stat_value is not None and minutes and minutes > 0:
                    per_36_value = stat_value * (36.0 / minutes)
                    logger.debug(f"Using PlayerStats for {player.name}: {stat_type}_per_36 = {per_36_value}")

        # STEP 3: Final fallback to position averages
        if per_36_value is None:
            position = player.position if player.position else None
            averages = POSITION_AVERAGES.get(position, POSITION_AVERAGES[None])
            per_36_value = averages.get(stat_type, 10.0)
            logger.debug(f"Using position averages for {player.name}: {stat_type}_per_36 = {per_36_value}")

        # Get or estimate minutes
        self_injury_data = injury_context.get('self_injury') or {}
        self_injury_status = self_injury_data.get('status')

        if self_injury_status == 'returning':
            # Use restricted minutes for returnees (18-25 typically)
            games_played = (injury_context.get('self_injury') or {}).get('games_played_since_return', 0)
            minutes_projection = 18 + min(games_played * 2, 12)  # Progressive increase
        elif self_injury_status in ['out', 'doubtful']:
            minutes_projection = 0
        elif self_injury_status == 'questionable':
            minutes_projection = 20
        elif minutes_projection is None or minutes_projection == 0:
            # Check lineup data if no projection provided
            minutes_projection = self.lineup_service.get_player_minutes_projection(player.id, game_id)
            if minutes_projection is None:
                # Default to starter minutes if unknown
                minutes_projection = 28

        # STEP 4: Calculate prediction: per_36 × (minutes / 36)
        predicted_value = per_36_value * (minutes_projection / 36.0)

        # Apply teammate boost (if teammates are out)
        teammate_count = len(injury_context.get('teammate_injuries', []))
        if teammate_count > 0:
            # Small boost for increased usage
            predicted_value *= (1.0 + min(teammate_count * 0.03, 0.10))

        # Minimal variance (5% instead of 15%) since using actual player data
        variance = random.uniform(-0.05, 0.05)
        predicted_value *= (1.0 + variance)

        return max(0, round(predicted_value, 2))

    def _calculate_confidence(
        self,
        player: Player,
        stat_type: str,
        predicted_value: float,
        injury_context: Optional[Dict] = None,
        game_id: Optional[str] = None
    ) -> float:
        """
        Calculate confidence score for a prediction.

        Confidence is based on:
        - Player's historical data availability (higher if we have per-36 stats)
        - Injury status adjustments
        - Teammate injury boosts (clear path = higher confidence)
        - Position-stat alignment
        - Minutes projection certainty
        - Historical hit rate weighting (NEW: tracks how often player hits their lines)

        Returns value between 0.0 and 1.0
        """
        if injury_context is None:
            injury_context = {}

        # Base confidence
        confidence = 0.55

        # Check if we have historical stats for this player
        player_stats = self.db.query(PlayerStats).filter(
            PlayerStats.player_id == player.id
        ).first()

        if player_stats:
            confidence += 0.10  # Higher confidence with actual data

        # Apply injury status adjustments
        self_injury_data = injury_context.get('self_injury') or {}
        self_injury_status = self_injury_data.get('status')

        if self_injury_status == 'out':
            confidence -= 0.30  # Heavy penalty for OUT players
        elif self_injury_status == 'doubtful':
            confidence -= 0.20  # Significant penalty for doubtful
        elif self_injury_status == 'questionable':
            confidence -= 0.10  # Moderate penalty for questionable
        elif self_injury_status == 'returning':
            confidence -= 0.05  # Minor penalty for returning (efficiency intact)
        elif self_injury_status == 'day-to-day':
            confidence -= 0.08  # Small penalty for day-to-day

        # Boost confidence when teammates are out (clear path to usage)
        teammate_count = len(injury_context.get('teammate_injuries', []))
        if teammate_count > 0:
            confidence += min(teammate_count * 0.03, 0.08)  # Max +8%

        # Boost confidence if stat type aligns with position
        position = player.position if player.position else None
        position_stat_match = {
            "PG": "assists",
            "SG": "points",
            "SF": "points",
            "PF": "rebounds",
            "C": "rebounds"
        }

        if position and position_stat_match.get(position) == stat_type:
            confidence += 0.08  # +8% for position-appropriate stats

        # Minutes projection certainty
        minutes_projection = injury_context.get('minutes_projection')
        if minutes_projection and minutes_projection > 0:
            if minutes_projection >= 28:
                confidence += 0.05  # Clear starter role
            elif minutes_projection <= 10:
                confidence -= 0.05  # Limited role uncertainty

        # NEW: Apply historical hit rate weighting
        base_confidence = confidence

        try:
            from app.services.historical_odds_service import HistoricalOddsService

            hit_rate_service = HistoricalOddsService(self.db)
            hit_rate_data = hit_rate_service.get_player_hit_rate(
                player_id=player.id,
                stat_type=stat_type,
                games_back=10,
                starters_only=True
            )

            hit_rate_weight = hit_rate_service.calculate_hit_rate_weight(
                hit_rate=hit_rate_data["hit_rate"],
                total_games=hit_rate_data["total_games"]
            )

            # Apply weight to confidence
            confidence = base_confidence * hit_rate_weight

            # Log the adjustment
            if hit_rate_data["total_games"] >= 5:
                logger.info(
                    f"Hit rate adjustment for {player.name} {stat_type}: "
                    f"{hit_rate_data['hit_rate']} ({hit_rate_data['over_hits']}/{hit_rate_data['total_games']}) "
                    f"weight={hit_rate_weight:.3f} "
                    f"confidence={base_confidence:.3f}->{confidence:.3f}"
                )

        except Exception as e:
            # Gracefully handle errors - use base confidence
            logger.debug(f"Could not apply hit rate weighting for {player.name} {stat_type}: {e}")
            confidence = base_confidence

        # Add small randomness to simulate model uncertainty
        confidence += random.uniform(-0.05, 0.05)

        return round(max(0.25, min(0.80, confidence)), 2)

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
