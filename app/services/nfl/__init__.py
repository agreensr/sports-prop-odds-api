"""
NFL prediction services.

This module contains all NFL-specific prediction services.
"""
from app.services.nfl.prediction_service import PredictionService, get_prediction_service

__all__ = [
    "PredictionService",
    "get_prediction_service",
]
