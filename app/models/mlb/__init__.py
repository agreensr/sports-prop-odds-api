"""
MLB database models.

⚠️  ARCHITECTURE CHANGE (P1 #5 - Full Unification):
As of 2025-01-29, this module now re-exports from the unified models.
All sports (NBA, NFL, MLB, NHL) now share the same database tables.

Query MLB-specific data:
    from app.models import Player, Game

    mlb_players = Player.query.filter(Player.sport_id == 'mlb').all()
    mlb_games = Game.query.filter(Game.sport_id == 'mlb').all()

This import maintains backward compatibility with existing code.
"""
# Re-export from unified models for backward compatibility
from app.models import *  # noqa: F401, F403

# Sport identifier for filtering
SPORT_ID = "mlb"

__all__ = [
    "SPORT_ID",
    "Base",
    "Sport",
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
    "GameMapping",
    "PlayerAlias",
    "TeamMapping",
    "SyncMetadata",
    "MatchAuditLog",
]
