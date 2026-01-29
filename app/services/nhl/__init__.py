"""
NHL prediction services.

This module contains all NHL-specific prediction services.
"""
from app.services.nhl.prediction_service import PredictionService, get_prediction_service

__all__ = [
    "PredictionService",
    "get_prediction_service",
]
