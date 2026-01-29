"""
Repository layer for data access.

The repository pattern provides:
1. Separation of data access logic from business logic
2. Single place for query logic (easier to maintain)
3. Easier testing (can mock repositories)
4. Consistent interface for data operations

Usage:
    from app.repositories.nba import PlayerRepository, GameRepository, PredictionRepository
    from app.core.database import SessionLocal

    db = SessionLocal()
    player_repo = PlayerRepository(db)
    player = player_repo.find_by_external_id("1628369")
    db.close()
"""

from app.repositories.base import BaseRepository

# NBA Repositories
from app.repositories.nba.player_repository import PlayerRepository
from app.repositories.nba.game_repository import GameRepository
from app.repositories.nba.prediction_repository import PredictionRepository

__all__ = [
    "BaseRepository",
    "PlayerRepository",
    "GameRepository",
    "PredictionRepository",
]
