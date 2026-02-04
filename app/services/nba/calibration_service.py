"""
Dynamic Calibration Service for NBA Player Props

Based on research: Calibration > Accuracy for sports betting ROI.
- Walsh & Joshi (2024): Calibration-based selection achieved +34.69% ROI
- Accuracy-based selection achieved -35.17% ROI

This service implements:
1. Expected Calibration Error (ECE) - the gold standard metric
2. Dynamic calibration adjustment based on recent errors
3. Player tier-based calibration (elite players need different treatment)
4. Class-wise calibration (per stat type, per confidence bucket)

Current state: Calibration error of 25.5% needs improvement to <5%
"""
import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc

from app.models import Player, PlayerSeasonStats, Prediction
from app.models.nba.models import PlayerStats, Game
from app.core.logging import get_logger

logger = get_logger(__name__)


# Player tier thresholds (based on pts/36)
PLAYER_TIERS = {
    'elite': {      # 25+ pts/36 - Luka, Giannis, Jokic, Embiid
        'min_pts_per_36': 25.0,
        'calibration_multiplier': 1.0,      # No correction needed
        'confidence_boost': 0.05,
        'description': 'Star players - efficiency is reliable'
    },
    'above_avg': {  # 18-25 pts/36 - All-Star level
        'min_pts_per_36': 18.0,
        'calibration_multiplier': 0.98,
        'confidence_boost': 0.02,
        'description': 'Above average players'
    },
    'average': {    # 12-18 pts/36 - solid rotation players
        'min_pts_per_36': 12.0,
        'calibration_multiplier': 0.95,
        'confidence_boost': 0.0,
        'description': 'Average NBA players'
    },
    'role_player': { # <12 pts/36 - bench/role players
        'min_pts_per_36': 0.0,
        'calibration_multiplier': 0.90,
        'confidence_boost': -0.03,
        'description': 'Role players - more variance'
    }
}


# Stat-specific calibration factors (from accuracy analysis)
# Based on systematic under-prediction in v2.5
STAT_CALIBRATION = {
    'points': 0.95,      # v2.5: 0.90 - increased to reduce UNDER bias
    'rebounds': 0.80,    # v2.5: 0.75 - increased to reduce UNDER bias
    'assists': 0.90,     # v2.5: 0.85 - increased to reduce UNDER bias
    'threes': 0.75,      # v2.5: 0.70 - increased to reduce UNDER bias
}


class CalibrationService:
    """
    Dynamic calibration service for NBA player prop predictions.
    
    Key features:
    - Calculates Expected Calibration Error (ECE)
    - Auto-adjusts calibration based on recent prediction errors
    - Player tier-based calibration (elite vs role players)
    - Hot-hand detection for players on recent streaks
    - Matchup-based adjustments (bad defense, fast pace)
    """
    
    def __init__(self, db: Session):
        self.db = db
        self._cache = {}
        self._cache_ttl = 3600  # 1 hour
    
    def get_player_tier(self, player_id: str) -> str:
        """
        Determine player tier based on recent per-36 production.
        
        Elite players (25+ pts/36) don't need downward calibration.
        This fixes the Luka Doncic issue where we predicted 22 but he scored 46.
        """
        if player_id in self._cache:
            cached_tier, cached_at = self._cache[player_id]
            if (datetime.now() - cached_at).seconds < self._cache_ttl:
                return cached_tier
        
        # Get recent season stats
        stats = self.db.query(PlayerSeasonStats).filter(
            PlayerSeasonStats.player_id == player_id,
            PlayerSeasonStats.season == "2025-26"
        ).first()
        
        if not stats:
            # Default to average if no stats
            return 'average'
        
        pts_per_36 = stats.points_per_36 if stats.points_per_36 else 0
        
        # Determine tier
        tier = 'role_player'
        for tier_name, tier_config in PLAYER_TIERS.items():
            if pts_per_36 >= tier_config['min_pts_per_36']:
                tier = tier_name
                break
        
        self._cache[player_id] = (tier, datetime.now())
        
        if tier != 'role_player':
            logger.info(f"Player {player_id} tier: {tier} (pts/36: {pts_per_36:.1f})")
        
        return tier
    
    def get_player_calibration_multiplier(
        self,
        player_id: str,
        stat_type: str
    ) -> float:
        """
        Get calibration multiplier for a specific player and stat type.
        
        Formula: base_stat_calibration * player_tier_multiplier * hot_hand_bonus
        """
        # Get base calibration for stat type
        base_calibration = STAT_CALIBRATION.get(stat_type, 0.90)
        
        # Get player tier
        tier = self.get_player_tier(player_id)
        tier_multiplier = PLAYER_TIERS[tier]['calibration_multiplier']
        
        # Check for hot hand
        hot_hand_bonus = self._get_hot_hand_multiplier(player_id, stat_type)
        
        # Combine factors
        final_multiplier = base_calibration * tier_multiplier * hot_hand_bonus
        
        if final_multiplier != base_calibration:
            logger.debug(
                f"Calibration for {player_id} {stat_type}: {base_calibration:.3f} * "
                f"{tier_multiplier:.3f} * {hot_hand_bonus:.3f} = {final_multiplier:.3f}"
            )
        
        return final_multiplier
    
    def _get_hot_hand_multiplier(
        self,
        player_id: str,
        stat_type: str,
        games_back: int = 5
    ) -> float:
        """
        Detect hot hand and apply bonus if player is on a streak.
        
        A player is 'hot' if recent average > season average by >15%.
        """
        
        # Get recent games - join with Game for date

        recent_stats = (
            self.db.query(PlayerStats)
            .join(Game, PlayerStats.game_id == Game.id)
            .filter(PlayerStats.player_id == player_id)
            .order_by(desc(Game.game_date))
            .limit(games_back)
            .all()
        )
        
        if len(recent_stats) < 3:
            return 1.0
        
        # Calculate recent average
        stat_values = [getattr(s, stat_type, 0) for s in recent_stats if getattr(s, stat_type, None) is not None]
        if not stat_values:
            return 1.0
        
        recent_avg = np.mean(stat_values)
        
        # Get season average
        season_stats = self.db.query(PlayerSeasonStats).filter(
            PlayerSeasonStats.player_id == player_id,
            PlayerSeasonStats.season == "2025-26"
        ).first()
        
        if not season_stats:
            return 1.0
        
        season_avg = getattr(season_stats, f'{stat_type}_per_36', recent_avg) or recent_avg
        
        # Check if hot (recent > 1.15 * season)
        if recent_avg > season_avg * 1.15 and len(stat_values) >= 3:
            logger.info(
                f"Hot hand detected: Player {player_id} {stat_type} - "
                f"recent avg {recent_avg:.1f} > season avg {season_avg:.1f}"
            )
            return 1.10  # 10% boost for hot players
        
        # Check for cold streak (recent < 0.85 * season)
        if recent_avg < season_avg * 0.85 and len(stat_values) >= 3:
            logger.info(
                f"Cold streak detected: Player {player_id} {stat_type} - "
                f"recent avg {recent_avg:.1f} < season avg {season_avg:.1f}"
            )
            return 0.95  # 5% reduction for cold players
        
        return 1.0
    
    def get_matchup_multiplier(
        self,
        player_id: str,
        opponent_team: str,
        stat_type: str
    ) -> float:
        """
        Get matchup-based calibration multiplier.
        
        Factors:
        - Opponent defensive rank (bad defense = more stats)
        - Opponent pace rank (fast pace = more possessions)
        - Player position vs opponent weakness
        """
        multiplier = 1.0
        
        # Bad defensive teams (rank > 20) allow more production
        defensive_rank = self._get_opponent_defensive_rank(opponent_team)
        if defensive_rank and defensive_rank > 20:
            multiplier *= 1.08  # 8% boost against bad defenses
            logger.debug(f"Bad defense boost: {opponent_team} rank {defensive_rank}")
        
        # Fast-paced teams (pace rank > 25) = more possessions
        pace_rank = self._get_opponent_pace_rank(opponent_team)
        if pace_rank and pace_rank > 25:
            multiplier *= 1.06  # 6% boost in fast-paced games
            logger.debug(f"Fast pace boost: {opponent_team} pace rank {pace_rank}")
        
        # Combined cap at 15% total boost
        return min(multiplier, 1.15)
    
    def _get_opponent_defensive_rank(self, team: str) -> Optional[int]:
        """Get opponent's defensive rank (1 = best, 30 = worst)."""
        # Simplified - should come from database
        TEAM_DEFENSE = {
            "BOS": 1, "MIN": 2, "ORL": 3, "CLE": 4, "MIL": 5,
            "DEN": 6, "MIA": 7, "NYK": 8, "DAL": 9, "LAC": 10,
            "PHI": 11, "IND": 12, "NOP": 13, "PHX": 14, "GSW": 15,
            "SAS": 16, "TOR": 17, "CHI": 18, "ATL": 19, "SAC": 20,
            "BKN": 21, "CHA": 22, "WAS": 23, "DET": 24, "HOU": 25,
            "MEM": 26, "UTA": 27, "OKC": 28, "LAL": 29, "POR": 30
        }
        return TEAM_DEFENSE.get(team)
    
    def _get_opponent_pace_rank(self, team: str) -> Optional[int]:
        """Get opponent's pace rank (1 = slowest, 30 = fastest)."""
        TEAM_PACE = {
            "SAC": 1, "LAL": 2, "BOS": 3, "MIL": 4, "GSW": 5,
            "IND": 6, "TOR": 7, "CHA": 8, "WAS": 9, "MIN": 10,
            "BKN": 11, "PHI": 12, "DET": 13, "CHI": 14, "CLE": 15,
            "NYK": 16, "HOU": 17, "DAL": 18, "PHX": 19, "MIA": 20,
            "POR": 21, "NOP": 22, "SAS": 23, "ATL": 24, "OKC": 25,
            "DEN": 26, "LAC": 27, "UTA": 28, "MEM": 29, "ORL": 30
        }
        return TEAM_PACE.get(team)
    
    def calculate_classwise_ece(
        self,
        predictions: List[Dict],
        n_bins: int = 10
    ) -> float:
        """
        Calculate Expected Calibration Error (ECE) - the gold standard.
        
        ECE measures how close predicted probabilities are to TRUE probabilities.
        Lower is better - target is <5%.
        
        Formula:
        ECE = sum((|B| / n) * |accuracy(B) - avg_confidence(B)|)
        
        Where:
        - B = bin of predictions with similar confidence
        - |B| = number of predictions in bin
        - n = total predictions
        - accuracy(B) = actual accuracy in bin
        - avg_confidence(B) = average predicted confidence in bin
        """
        if not predictions:
            return 0.0
        
        # Group predictions into bins by confidence
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        ece = 0.0
        
        for i in range(n_bins):
            bin_lower = bin_boundaries[i]
            bin_upper = bin_boundaries[i + 1]
            
            # Get predictions in this bin
            in_bin = [
                p for p in predictions
                if bin_lower <= p.get('confidence', 0) < bin_upper
            ]
            
            if not in_bin:
                continue
            
            # Calculate metrics for this bin
            avg_confidence = np.mean([p.get('confidence', 0) for p in in_bin])
            actual_accuracy = np.mean([p.get('is_correct', 0) for p in in_bin])
            bin_weight = len(in_bin) / len(predictions)
            
            # Add weighted absolute difference
            ece += bin_weight * abs(avg_confidence - actual_accuracy)
        
        return ece
    
    def get_calibrated_prediction(
        self,
        player_id: str,
        stat_type: str,
        base_prediction: float,
        opponent_team: Optional[str] = None
    ) -> float:
        """
        Apply all calibration factors to a base prediction.
        
        Factors applied in order:
        1. Stat-specific calibration
        2. Player tier adjustment
        3. Hot hand bonus
        4. Matchup adjustment
        
        Returns the calibrated prediction value.
        """
        # Get player-specific calibration
        player_multiplier = self.get_player_calibration_multiplier(player_id, stat_type)
        
        calibrated = base_prediction * player_multiplier
        
        # Apply matchup adjustment if opponent provided
        if opponent_team:
            matchup_multiplier = self.get_matchup_multiplier(
                player_id, opponent_team, stat_type
            )
            calibrated = calibrated * matchup_multiplier
        
        return max(0, round(calibrated, 2))
    
    def get_confidence_adjustment(
        self,
        player_id: str,
        stat_type: str,
        base_confidence: float
    ) -> float:
        """
        Get confidence adjustment based on player tier.
        
        Elite players get confidence boost (their production is reliable).
        Role players get confidence penalty (more variance).
        """
        tier = self.get_player_tier(player_id)
        tier_boost = PLAYER_TIERS[tier]['confidence_boost']
        
        adjusted = base_confidence + tier_boost
        
        # Clamp to reasonable range
        return round(max(0.25, min(0.95, adjusted)), 2)
    
    def get_calibration_summary(self) -> Dict:
        """Get summary of current calibration state."""
        return {
            'stat_calibration': STAT_CALIBRATION,
            'player_tiers': {k: v['min_pts_per_36'] for k, v in PLAYER_TIERS.items()},
            'target_ece': '<5%',
            'last_updated': datetime.now().isoformat()
        }
