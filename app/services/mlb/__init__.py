"""
MLB prediction services.

This module contains all MLB-specific prediction services.
"""
from app.services.mlb.prediction_service import PredictionService, get_prediction_service

__all__ = [
    "PredictionService",
    "get_prediction_service",
]
