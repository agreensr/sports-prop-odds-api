"""
Ensemble Prediction Service for NBA Player Props

Combines multiple prediction models for robustness:
1. Heuristic model (current enhanced model)
2. XGBoost model (ML-based)
3. Calibration service (dynamic adjustments)

Weights are dynamically adjusted based on recent performance.

Research shows ensemble methods outperform single models by:
- Reducing overfitting
- Capturing different signal patterns
- Providing more stable predictions
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.core.logging import get_logger

logger = get_logger(__name__)


class EnsemblePredictionService:
    """
    Ensemble prediction service combining multiple models.
    
    The ensemble uses weighted averaging where weights are adjusted
    based on recent model performance.
    """
    
    def __init__(self, db: Session):
        self.db = db
        self._heuristic_service = None
        self._xgboost_service = None
        self._calibration_service = None
        
        # Dynamic model weights (adjusted based on recent accuracy)
        self.weights = {
            'heuristic': 0.35,      # Current model with calibration
            'xgboost': 0.50,         # ML model
            'adjustment': 0.15       # Calibration adjustments
        }
        
        # Track recent performance for weight adjustment
        self._recent_performance = {
            'heuristic': [],
            'xgboost': []
        }
    
    @property
    def heuristic_service(self):
        if self._heuristic_service is None:
            from app.services.nba.enhanced_prediction_service import EnhancedPredictionService
            self._heuristic_service = EnhancedPredictionService(self.db)
        return self._heuristic_service
    
    @property
    def xgboost_service(self):
        if self._xgboost_service is None:
            from app.services.nba.xgboost_prediction_service import XGBoostPredictionService
            self._xgboost_service = XGBoostPredictionService(self.db)
        return self._xgboost_service
    
    @property
    def calibration_service(self):
        if self._calibration_service is None:
            from app.services.nba.calibration_service import CalibrationService
            self._calibration_service = CalibrationService(self.db)
        return self._calibration_service
    
    def predict(
        self,
        player_id: str,
        game_id: str,
        stat_type: str = 'points'
    ) -> Dict:
        """
        Generate ensemble prediction for a player prop.
        
        Returns:
            Dict with:
            - prediction: final predicted value
            - confidence: prediction confidence
            - recommendation: OVER/UNDER/PASS
            - components: individual model predictions
            - edge: edge over bookmaker line (if available)
        """
        components = {}
        
        # Get prediction from heuristic model
        try:
            heuristic_pred, heuristic_conf = self._get_heuristic_prediction(
                player_id, game_id, stat_type
            )
            components['heuristic'] = {
                'prediction': heuristic_pred,
                'confidence': heuristic_conf,
                'weight': self.weights['heuristic']
            }
        except Exception as e:
            logger.debug(f"Heuristic prediction failed: {e}")
            heuristic_pred = 10.0
            heuristic_conf = 0.50
            components['heuristic'] = {
                'prediction': heuristic_pred,
                'confidence': heuristic_conf,
                'weight': 0.0,
                'error': str(e)
            }
        
        # Get prediction from XGBoost model
        try:
            xgb_pred, xgb_conf = self.xgboost_service.predict(
                player_id, game_id, stat_type
            )
            components['xgboost'] = {
                'prediction': xgb_pred,
                'confidence': xgb_conf,
                'weight': self.weights['xgboost']
            }
        except Exception as e:
            logger.debug(f"XGBoost prediction failed: {e}")
            xgb_pred = heuristic_pred  # Fallback
            xgb_conf = heuristic_conf
            components['xgboost'] = {
                'prediction': xgb_pred,
                'confidence': xgb_conf,
                'weight': 0.0,
                'error': str(e)
            }
        
        # Calculate weighted prediction
        total_weight = sum(c['weight'] for c in components.values())
        if total_weight > 0:
            weighted_pred = sum(
                c['prediction'] * c['weight'] for c in components.values()
            ) / total_weight
        else:
            weighted_pred = heuristic_pred
        
        # Apply calibration adjustments
        try:
            opponent_team = self._get_opponent_team(player_id, game_id)
            calibrated_pred = self.calibration_service.get_calibrated_prediction(
                player_id, stat_type, weighted_pred, opponent_team
            )
            
            # Adjust confidence based on player tier
            base_confidence = max(
                components['heuristic']['confidence'],
                components.get('xgboost', {}).get('confidence', 0.5)
            )
            calibrated_conf = self.calibration_service.get_confidence_adjustment(
                player_id, stat_type, base_confidence
            )
            
            components['calibration'] = {
                'raw_prediction': weighted_pred,
                'calibrated_prediction': calibrated_pred,
                'confidence_adjustment': calibrated_conf - base_confidence
            }
        except Exception as e:
            logger.debug(f"Calibration failed: {e}")
            calibrated_pred = weighted_pred
            calibrated_conf = max(
                components['heuristic']['confidence'],
                components.get('xgboost', {}).get('confidence', 0.5)
            )
        
        # Determine recommendation
        recommendation = self._get_recommendation(calibrated_pred, calibrated_conf)
        
        # Calculate edge (if line available)
        edge = self._calculate_edge(calibrated_pred)
        
        return {
            'prediction': round(calibrated_pred, 2),
            'confidence': round(calibrated_conf, 2),
            'recommendation': recommendation,
            'edge': edge,
            'components': components,
            'player_id': player_id,
            'stat_type': stat_type,
            'generated_at': datetime.now().isoformat()
        }
    
    def _get_heuristic_prediction(
        self,
        player_id: str,
        game_id: str,
        stat_type: str
    ) -> Tuple[float, float]:
        """Get prediction from heuristic model."""
        # For now, use XGBoost service's heuristic prediction
        # This can be replaced with the full enhanced prediction service
        return self.xgboost_service._heuristic_prediction(
            self.xgboost_service._extract_player_features(player_id, game_id, stat_type),
            stat_type
        )
    
    def _get_opponent_team(self, player_id: str, game_id: str) -> Optional[str]:
        """Get opponent team for a player in a game."""
        from app.models import Player, Game
        
        player = self.db.query(Player).filter(Player.id == player_id).first()
        game = self.db.query(Game).filter(Game.id == game_id).first()
        
        if not player or not game:
            return None
        
        if player.team == game.home_team:
            return game.away_team
        elif player.team == game.away_team:
            return game.home_team
        
        return None
    
    def _get_recommendation(self, prediction: float, confidence: float) -> str:
        """
        Generate OVER/UNDER/PASS recommendation.
        
        Based on:
        - Confidence level
        - Edge over market (simplified here)
        """
        if confidence >= 0.65:
            return "OVER"  # Simplified - should compare to line
        elif confidence >= 0.60:
            return "UNDER"
        else:
            return "PASS"
    
    def _calculate_edge(self, prediction: float) -> Dict:
        """
        Calculate edge over bookmaker line.
        
        Edge = (Prediction - Line) / Line
        
        For now, returns placeholder since we need the actual line.
        """
        return {
            'value': 0.0,
            'percent': 0.0,
            'description': 'Line comparison not available'
        }
    
    def update_weights(self, recent_results: List[Dict]):
        """
        Update model weights based on recent performance.
        
        Args:
            recent_results: List of dicts with 'model' and 'accuracy' keys
        """
        # Calculate recent accuracy for each model
        model_accuracy = {'heuristic': [], 'xgboost': []}
        
        for result in recent_results:
            model = result.get('model', 'unknown')
            accuracy = result.get('accuracy', 0.0)
            
            if model in model_accuracy:
                model_accuracy[model].append(accuracy)
        
        # Adjust weights based on recent performance
        for model_name, accuracies in model_accuracy.items():
            if accuracies:
                avg_accuracy = sum(accuracies) / len(accuracies)
                
                # Increase weight for better performing models
                if avg_accuracy > 0.60:
                    self.weights[model_name] = min(0.60, self.weights[model_name] * 1.1)
                elif avg_accuracy < 0.50:
                    self.weights[model_name] = max(0.20, self.weights[model_name] * 0.9)
        
        # Normalize weights
        total_weight = sum(self.weights.values())
        if total_weight > 0:
            for key in self.weights:
                self.weights[key] = self.weights[key] / total_weight
        
        logger.info(f"Updated ensemble weights: {self.weights}")
    
    def get_ensemble_info(self) -> Dict:
        """Get information about the ensemble configuration."""
        return {
            'models': list(self.weights.keys()),
            'weights': self.weights,
            'description': 'Weighted ensemble of heuristic and ML models'
        }


def create_ensemble_service(db: Session) -> EnsemblePredictionService:
    """Factory function to create ensemble service."""
    return EnsemblePredictionService(db)
