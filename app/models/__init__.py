"""
Sport-specific database models.

This module exports models from all sports. Import from sport-specific submodules:
- from app.models.nba.models import *  # NBA models
- from app.models.nfl.models import *  # NFL models (future)
- from app.models.mlb.models import *  # MLB models (future)
- from app.models.nhl.models import *  # NHL models (future)
"""
from app.models.nba.models import *  # Export all NBA models for backward compatibility

__all__ = [
    "Base",
    "Player",
    "Game",
    "Prediction",
    "PlayerStats",
    "PlayerSeasonStats",
    "GameOdds",
    "HistoricalOddsSnapshot",
    "PlayerInjury",
    "ExpectedLineup",
    "NewsEvent",
    "Parlay",
    "ParlayLeg",
    "PlacedBet",
    "PlacedBetLeg",
]
