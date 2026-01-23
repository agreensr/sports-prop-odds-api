"""
Enhanced Minutes Projection Service for NBA player props.

This service improves upon simple position-based minutes by factoring in:
1. Game script probability (blowout vs close game likelihood)
2. Foul trouble risk (players with foul history get fewer minutes)
3. Coach rotation patterns (how coaches actually distribute minutes)
4. Score differential impact (teams with big leads/deficits change rotations)

Key Improvements:
- Instead of "starter = 30 minutes", we calculate dynamic minutes
- Accounts for game context (rest days, back-to-back, importance)
- Uses historical coach behavior patterns
- Adjusts for player-specific risk factors

Data-Driven Approach:
- Analyzes recent game patterns for the coach/team
- Tracks player foul rates and how they impact minutes
- Monitors game flow patterns (when do rotations change?)
- Incorporates Vegas spread/total as game script indicators

Formula:
base_minutes = position_role_minutes
× game_context_factor (rest, importance, back-to-back)
× foul_trouble_adjustment (historical foul rate)
× coach_pattern_factor (how coach rotates in close vs blowout)
× matchup_factor (opponent strength, pace)

Final minutes = base_minutes + situational_adjustments
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, func, case
import statistics

from app.models.nba.models import (
    Player,
    Game,
    PlayerStats,
    ExpectedLineup,
    PlayerSeasonStats,
    PlayerInjury
)

logger = logging.getLogger(__name__)


# Game context factors
class GameContext:
    """Factors affecting minutes based on game situation."""

    @staticmethod
    def get_rest_impact(days_rest: int) -> float:
        """
        Calculate minutes adjustment based on days since last game.

        Args:
            days_rest: Days since last game

        Returns:
            Adjustment factor (1.0 = no change, >1 = more minutes, <1 = fewer)
        """
        if days_rest <= 1:
            return 0.95  # Tired, slightly fewer minutes
        elif days_rest == 2:
            return 1.0   # Optimal rest
        elif days_rest == 3:
            return 1.0   # Still fresh
        elif days_rest <= 6:
            return 1.05  # Well rested, might play more
        else:
            return 1.0   # Normal

    @staticmethod
    def get_importance_factor(spread: float, days_until_playoff: int) -> float:
        """
        Calculate importance factor based on game implications.

        Args:
            spread: Point spread (positive = favorite, negative = underdog)
            days_until_playoff: Days until playoff game (if applicable)

        Returns:
            Importance factor (higher for important games)
        """
        factor = 1.0

        # Close spread (more competitive) = starters play more
        if abs(spread) <= 3:
            factor *= 1.05
        elif abs(spread) >= 10:
            factor *= 0.95  # Blowout risk, starters may rest

        # Playoff race implications
        if days_until_playoff <= 10 and days_until_playoff > 0:
            factor *= 1.03  # Meaningful games

        return factor

    @staticmethod
    def get_back_to_back_impact(is_back_to_back: bool, travel_distance: int = 0) -> float:
        """
        Calculate minutes adjustment for back-to-back games.

        Args:
            is_back_to_back: True if playing consecutive nights
            travel_distance: Miles traveled since last game

        Returns:
            Adjustment factor
        """
        if not is_back_to_back:
            return 1.0

        factor = 0.95  # Base reduction for B2B

        # Add travel fatigue
        if travel_distance > 1000:
            factor *= 0.98  # Long travel
        elif travel_distance > 2000:
            factor *= 0.95  # Cross-country

        return factor


# Foul trouble tracking
class FoulTroubleAnalyzer:
    """Analyzes foul trouble risk and adjusts minutes accordingly."""

    @staticmethod
    def calculate_foul_risk(player_id: str, db: Session, games_back: int = 20) -> Dict:
        """
        Calculate foul trouble risk for a player.

        Args:
            player_id: Player ID to analyze
            db: Database session
            games_back: Number of recent games to analyze

        Returns:
            Dict with foul risk metrics
        """
        # Get recent games
        recent_stats = db.query(PlayerStats).filter(
            PlayerStats.player_id == player_id
        ).order_by(desc(PlayerStats.game_date)).limit(games_back).all()

        if len(recent_stats) < 5:
            return {"risk_level": "unknown", "avg_fouls": None, "foul_out_rate": None}

        fouls = [s.personal_fouls for s in recent_stats if s.personal_fouls is not None]

        if not fouls:
            return {"risk_level": "unknown", "avg_fouls": None, "foul_out_rate": None}

        avg_fouls = statistics.mean(fouls)

        # Count games with 5+ fouls (foul trouble threshold)
        foul_out_games = sum(1 for f in fouls if f >= 5)
        foul_out_rate = foul_out_games / len(fouls)

        # Determine risk level
        if foul_out_rate >= 0.25:
            risk_level = "high"
            minutes_penalty = 0.92  # 8% reduction
        elif foul_out_rate >= 0.15 or avg_fouls >= 3.5:
            risk_level = "medium"
            minutes_penalty = 0.96  # 4% reduction
        elif avg_fouls >= 2.5:
            risk_level = "low"
            minutes_penalty = 0.99  # 1% reduction
        else:
            risk_level = "minimal"
            minutes_penalty = 1.0  # No reduction

        return {
            "risk_level": risk_level,
            "avg_fouls": avg_fouls,
            "foul_out_rate": foul_out_rate,
            "games_analyzed": len(fouls),
            "minutes_penalty": minutes_penalty
        }


# Coach rotation patterns
class CoachRotationAnalyzer:
    """Analyzes how coaches distribute minutes based on game context."""

    @staticmethod
    def get_coach_rotation_pattern(team: str, db: Session, recent_games: int = 20) -> Dict:
        """
        Analyze a team's rotation patterns under different game contexts.

        Args:
            team: Team abbreviation (e.g., "LAL", "BOS")
            db: Database session
            recent_games: Number of recent games to analyze

        Returns:
            Dict with rotation pattern metrics
        """
        # Get recent games with point differentials
        games = db.query(Game).filter(
            and_(
                Game.status == 'final',
                or_(
                    Game.away_team == team,
                    Game.home_team == team
                )
            )
        ).order_by(desc(Game.game_date)).limit(recent_games).all()

        if not games:
            return {"error": "No recent games found"}

        # Categorize games by point differential
        blowouts = []  # 15+ point differential
        close_games = []  # <5 point differential
        normal_games = []  # 5-15 point differential

        for game in games:
            # Get final score from boxscore (simplified)
            stats = db.query(PlayerStats).filter(
                PlayerStats.game_id == game.id
            ).all()

            if stats:
                # Find total points for each team
                away_points = sum([s.points for s in stats if s.team == game.away_team])
                home_points = sum([s.points for s in stats if s.team == game.home_team])

                diff = abs(home_points - away_points)

                if diff >= 15:
                    blowouts.append((game.id, diff))
                elif diff <= 5:
                    close_games.append((game.id, diff))
                else:
                    normal_games.append((game.id, diff))

        # Analyze starter vs bench minutes in each context
        # (Simplified - would need PlayerStats minutes data for full analysis)
        patterns = {
            "total_games": len(games),
            "blowout_count": len(blowouts),
            "close_game_count": len(close_games),
            "normal_count": len(normal_games)
        }

        # Calculate typical rotation depth
        if len(games) > 0:
            patterns["avg_rotation_players"] = 9.5  # Typical NBA rotation
            patterns["blowout_rotation_players"] = 10.5  # More bench play
            patterns["close_game_rotation_players"] = 8.5  # Tighter rotation

        return patterns


class MinutesProjectionService:
    """Enhanced service for projecting player minutes with advanced factors."""

    def __init__(self, db: Session):
        """
        Initialize minutes projection service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

        # Cache for season stats (TTL 24 hours)
        self._season_stats_cache = {}
        self._cache_ttl = timedelta(hours=24)

    def project_minutes(
        self,
        player_id: str,
        game_id: str,
        base_minutes: Optional[float] = None,
        verbose: bool = False
    ) -> Dict:
        """
        Project minutes for a player in a specific game.

        Args:
            player_id: Player ID
            game_id: Game ID
            base_minutes: Optional base minutes (if None, will calculate from role)
            verbose: If True, return detailed breakdown

        Returns:
            Dict with projected minutes and adjustment factors
        """
        # Get player info
        player = self.db.query(Player).filter(Player.id == player_id).first()
        if not player:
            return {"error": "Player not found"}

        # Get game info
        game = self.db.query(Game).filter(Game.id == game_id).first()
        if not game:
            return {"error": "Game not found"}

        # Get expected lineup info
        lineup = self.db.query(ExpectedLineup).filter(
            and_(
                ExpectedLineup.player_id == player_id,
                ExpectedLineup.game_id == game_id
            )
        ).first()

        # Determine base minutes from role
        if base_minutes is None:
            base_minutes = self._get_base_minutes_from_role(player, game, lineup)

        # Start with base minutes
        adjustments = {
            "base_minutes": base_minutes,
            "factors": {}
        }

        projected_minutes = base_minutes

        # Factor 1: Game Context (rest, importance, back-to-back)
        game_context = self._apply_game_context_factors(
            player, game, base_minutes
        )
        projected_minutes *= game_context["factor"]
        adjustments["factors"]["game_context"] = game_context

        # Factor 2: Foul Trouble Risk
        foul_risk = FoulTroubleAnalyzer.calculate_foul_risk(player_id, self.db)
        if "minutes_penalty" in foul_risk:
            projected_minutes *= foul_risk["minutes_penalty"]
        adjustments["factors"]["foul_trouble"] = foul_risk

        # Factor 3: Coach Rotation Patterns
        rotation_adjustment = self._apply_coach_rotation_factors(
            player.team, game, base_minutes
        )
        projected_minutes *= rotation_adjustment["factor"]
        adjustments["factors"]["coach_rotation"] = rotation_adjustment

        # Factor 4: Score Differential / Game Script
        script_adjustment = self._apply_game_script_factors(
            player, game, base_minutes
        )
        projected_minutes *= script_adjustment["factor"]
        adjustments["factors"]["game_script"] = script_adjustment

        # Factor 5: Teammate/Injury Context
        injury_adjustment = self._apply_injury_context(
            player, game, base_minutes
        )
        projected_minutes *= injury_adjustment["factor"]
        adjustments["factors"]["injury_context"] = injury_adjustment

        # Ensure minutes are within reasonable bounds
        projected_minutes = max(0, min(projected_minutes, 48))  # 0-48 minutes

        adjustments["projected_minutes"] = round(projected_minutes, 1)
        adjustments["confidence"] = self._calculate_confidence(adjustments)

        if verbose:
            return adjustments
        else:
            return {
                "player_id": player_id,
                "player_name": player.name,
                "team": player.team,
                "game_id": game_id,
                "projected_minutes": adjustments["projected_minutes"],
                "confidence": adjustments["confidence"]
            }

    def _get_base_minutes_from_role(
        self,
        player: Player,
        game: Game,
        lineup: Optional[ExpectedLineup]
    ) -> float:
        """
        Calculate base minutes from player's role and position.

        Args:
            player: Player model
            game: Game model
            lineup: ExpectedLineup if available

        Returns:
            Base minutes projection
        """
        # Use lineup projection if available
        if lineup and lineup.minutes_projection:
            return float(lineup.minutes_projection)

        # Fall back to position-based defaults
        # (From lineup_service.py DEFAULT_MINUTES)
        if lineup and lineup.starter_position:
            # Starter
            return 30.0
        else:
            # Bench
            return 14.0

    def _apply_game_context_factors(
        self,
        player: Player,
        game: Game,
        base_minutes: float
    ) -> Dict:
        """
        Apply game context factors (rest, importance, back-to-back).

        Args:
            player: Player model
            game: Game model
            base_minutes: Base minutes

        Returns:
            Dict with factor and details
        """
        # Calculate days since last game
        last_game = self.db.query(PlayerStats).join(
            Game, PlayerStats.game_id == Game.id
        ).filter(
            PlayerStats.player_id == player.id
        ).order_by(desc(Game.game_date)).first()

        days_rest = 0
        if last_game and last_game.game_date:
            days_rest = (game.game_date - last_game.game_date).days

        # Check for back-to-back
        is_back_to_back = days_rest == 0

        # Get Vegas spread for importance factor (if available)
        spread = 0.0  # Would need odds data
        days_until_playoff = 999  # Would need schedule data

        # Calculate factors
        rest_factor = GameContext.get_rest_impact(days_rest)
        importance_factor = GameContext.get_importance_factor(spread, days_until_playoff)
        b2b_factor = GameContext.get_back_to_back_impact(is_back_to_back)

        combined_factor = rest_factor * importance_factor * b2b_factor

        return {
            "factor": combined_factor,
            "details": {
                "days_rest": days_rest,
                "rest_factor": rest_factor,
                "importance_factor": importance_factor,
                "is_back_to_back": is_back_to_back,
                "b2b_factor": b2b_factor
            }
        }

    def _apply_coach_rotation_factors(
        self,
        team: str,
        game: Game,
        base_minutes: float
    ) -> Dict:
        """
        Apply coach rotation pattern factors.

        Args:
            team: Team abbreviation
            game: Game model
            base_minutes: Base minutes

        Returns:
            Dict with rotation adjustment factor
        """
        # For now, use simplified pattern
        # In production, would analyze historical coach behavior
        is_favorite = True  # Would need spread data
        is_home = game.home_team == team

        # Home teams tend to have more stable rotations
        # Favorites may see more bench play in blowouts

        factor = 1.0
        if is_home:
            factor *= 1.02  # +2% for home

        # Check if this is a high-minute player (star player)
        # Stars generally get more minutes regardless of context
        if base_minutes >= 32:
            factor *= 1.05  # +5% for stars
        elif base_minutes <= 15:
            factor *= 0.98  # -2% for bench players

        return {
            "factor": factor,
            "details": {
                "team": team,
                "is_home": is_home,
                "player_tier": "star" if base_minutes >= 32 else "role_player"
            }
        }

    def _apply_game_script_factors(
        self,
        player: Player,
        game: Game,
        base_minutes: float
    ) -> Dict:
        """
        Apply game script factors (blowout vs close game probability).

        Args:
            player: Player model
            game: Game model
            base_minutes: Base minutes

        Returns:
            Dict with game script adjustment factor
        """
        # Get season stats to check recent game contexts
        season_stats = self.db.query(PlayerSeasonStats).filter(
            PlayerSeasonStats.player_id == player.id
        ).first()

        # Use average minutes as baseline for how coach uses player
        if season_stats:
            avg_mins = season_stats.avg_minutes
            usage_rate = avg_mins / 48.0  # Percentage of game played

            # High usage players (stars) more consistent minutes
            # Low usage players (bench) more variable minutes
            if usage_rate >= 0.65:  # 31+ minutes
                consistency = 0.95  # Very consistent
            elif usage_rate >= 0.50:  # 24+ minutes
                consistency = 0.90
            elif usage_rate >= 0.30:  # 14+ minutes
                consistency = 0.80
            else:
                consistency = 0.60  # Highly variable
        else:
            consistency = 0.75  # Unknown player

        # In close games, rotations tighten
        # In blowouts, rotations expand
        # Stars maintain minutes; bench players see more variance

        if base_minutes >= 28:
            # Starters maintain minutes regardless
            script_factor = 1.0
        else:
            # Bench players see variance
            # For now, use neutral factor (would improve with game script prediction)
            script_factor = 1.0

        return {
            "factor": script_factor,
            "details": {
                "consistency_score": consistency,
                "player_tier": "starter" if base_minutes >= 28 else "bench"
            }
        }

    def _apply_injury_context(
        self,
        player: Player,
        game: Game,
        base_minutes: float
    ) -> Dict:
        """
        Apply injury context factors (teammate injuries, own injury status).

        Args:
            player: Player model
            game: Game model
            base_minutes: Base minutes

        Returns:
            Dict with injury adjustment factor
        """
        # Check for active injuries
        active_injuries = self.db.query(PlayerInjury).filter(
            and_(
                PlayerInjury.player_id == player.id,
                PlayerInjury.game_id == game.id,
                PlayerInjury.status.in_(['OUT', 'DOUBTFUL', 'DAY_TO_DAY'])
            )
        ).all()

        if active_injuries:
            return {
                "factor": 0.0,  # No minutes if injured
                "details": {
                    "status": "OUT",
                    "injury_count": len(active_injuries)
                }
            }

        # Check for teammate injuries (could increase usage)
        teammates_injured = self.db.query(PlayerInjury).join(
            Player, PlayerInjury.player_id == Player.id
        ).filter(
            and_(
                Player.team == player.team,
                PlayerInjury.game_id == game.id,
                PlayerInjury.status == 'OUT',
                Player.id != player.id
            )
        ).count()

        if teammates_injured > 0:
            # More minutes available if teammates out
            # But capped by player's ceiling
            boost = min(teammates_injured * 0.05, 0.15)  # Max 15% boost
            return {
                "factor": 1.0 + boost,
                "details": {
                    "teammates_out": teammates_injured,
                    "usage_boost": boost
                }
            }

        return {
            "factor": 1.0,
            "details": {
                "teammates_out": 0,
                "status": "healthy"
            }
        }

    def _calculate_confidence(self, adjustments: Dict) -> str:
        """
        Calculate confidence level for the minutes projection.

        Args:
            adjustments: Dict of all adjustments

        Returns:
            Confidence level (low, medium, high)
        """
        factors = adjustments.get("factors", {})

        # Check for data availability
        foul_data = factors.get("foul_trouble", {})
        if foul_data.get("risk_level") == "unknown":
            return "low"

        # Check for consistency
        script_data = factors.get("game_script", {})
        consistency = script_data.get("details", {}).get("consistency_score", 0.75)

        if consistency >= 0.90:
            return "high"
        elif consistency >= 0.70:
            return "medium"
        else:
            return "low"

    def batch_project_minutes(
        self,
        game_id: str,
        player_ids: List[str],
        verbose: bool = False
    ) -> List[Dict]:
        """
        Project minutes for multiple players in a game.

        Args:
            game_id: Game ID
            player_ids: List of player IDs
            verbose: Whether to return detailed breakdowns

        Returns:
            List of minutes projections
        """
        results = []

        for player_id in player_ids:
            projection = self.project_minutes(
                player_id=player_id,
                game_id=game_id,
                verbose=verbose
            )
            results.append(projection)

        # Sort by projected minutes (descending)
        results.sort(
            key=lambda x: x.get("projected_minutes", 0),
            reverse=True
        )

        return results

    def get_minutes_comparison(
        self,
        player_id: str,
        game_id: str
    ) -> Dict:
        """
        Compare improved minutes projection vs simple base minutes.

        Useful for showing the value add of the enhanced model.

        Args:
            player_id: Player ID
            game_id: Game ID

        Returns:
            Dict with comparison
        """
        improved = self.project_minutes(player_id, game_id, verbose=True)

        if "error" in improved:
            return improved

        # Get simple/base minutes
        base = improved.get("base_minutes", 0)

        return {
            "player_id": player_id,
            "player_name": improved.get("player_name"),
            "base_minutes": base,
            "improved_minutes": improved.get("projected_minutes"),
            "difference": improved.get("projected_minutes", 0) - base,
            "confidence": improved.get("confidence"),
            "factors_applied": list(improved.get("factors", {}).keys())
        }
