#!/usr/bin/env python3
"""
Test NHL prediction logic with real odds.
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.nhl.models import Game, Player
from app.services.nhl.enhanced_prediction_service import EnhancedNHLPredictionService
from app.services.core.odds_api_service import get_odds_service


async def test_prediction():
    db = next(get_db())

    # Get a game with odds_event_id and players
    game = db.query(Game).filter(
        Game.status == 'scheduled',
        Game.odds_event_id.isnot(None)
    ).first()

    if not game:
        print("No games with odds_event_id found")
        db.close()
        return

    print(f"=== Game: {game.away_team} @ {game.home_team} ===")
    print(f"odds_event_id: {game.odds_event_id}")

    # Get players for this game
    away_players = db.query(Player).filter(Player.team == game.away_team).all()
    home_players = db.query(Player).filter(Player.team == game.home_team).all()
    all_players = away_players + home_players

    print(f"\nPlayers in database:")
    for p in all_players:
        print(f"  {p.name} ({p.team}) - {p.position}")

    # Initialize service with odds API
    api_key = '8ad802abc3050bd7ff719830103602d6'
    odds_service = get_odds_service(api_key, sport="nhl")
    prediction_service = EnhancedNHLPredictionService(db=db, odds_api_service=odds_service)

    # Generate predictions
    print(f"\n=== Generating predictions ===")
    predictions = prediction_service.generate_prop_predictions(
        game_id=str(game.id),
        stat_types=["goals", "assists", "points"],
        bookmaker="draftkings"
    )

    print(f"\nGenerated {len(predictions)} predictions:")
    for pred in predictions:
        print(f"  {pred['player']} {pred['stat_type']}: {pred['projected']:.1f} vs {pred['line']:.1f} (edge: {pred['edge']:.1f}) -> {pred['recommendation']} @ {pred['confidence']:.0%} [{pred['line_source']}]")
    db.close()


if __name__ == "__main__":
    asyncio.run(test_prediction())
