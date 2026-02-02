"""
Unified Models Module - P1 #5 Model Architecture Decision

This module exports the unified models for all sports (NBA, NFL, MLB, NHL).

Architecture: Full Unification
- Single set of tables for all sports
- Sport-specific fields as nullable columns
- Filter by sport_id for sport-specific queries

Usage:
    from app.models import Player, Game, Prediction

    # Get all players
    all_players = Player.query.all()

    # Get NBA players only
    nba_players = Player.query.filter(Player.sport_id == 'nba').all()

    # Get players across multiple sports
    basketball = Player.query.filter(Player.sport_id.in_(['nba', 'wnba'])).all()

Migration Notes:
- Old imports still work: from app.models import Player
- New imports recommended: from app.models import Player
- All models now come from app.models.unified
"""

# Import all models from unified
from app.models.unified import (
    Base,
    Sport,
    Player,
    Game,
    Prediction,
    PlayerStats,
    GameOdds,
    PlayerInjury,
    ExpectedLineup,
    PlayerSeasonStats,
    HistoricalOddsSnapshot,
    Parlay,
    ParlayLeg,
    PlacedBet,
    PlacedBetLeg,
    NewsEvent,
    GameMapping,
    PlayerAlias,
    TeamMapping,
    SyncMetadata,
    MatchAuditLog,
)

# Keep backward compatibility by also exporting from nba.models
# This allows old imports to continue working
from app.models import *  # noqa: F401, F403

__all__ = [
    "Base",
    "Sport",
    "Player",
    "Game",
    "Prediction",
    "PlayerStats",
    "GameOdds",
    "PlayerInjury",
    "ExpectedLineup",
    "PlayerSeasonStats",
    "HistoricalOddsSnapshot",
    "Parlay",
    "ParlayLeg",
    "PlacedBet",
    "PlacedBetLeg",
    "NewsEvent",
    "GameMapping",
    "PlayerAlias",
    "TeamMapping",
    "SyncMetadata",
    "MatchAuditLog",
]
