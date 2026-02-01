#!/usr/bin/env python3
"""
Test NHL prediction generation.

This script generates predictions for upcoming NHL games with real odds.
"""
import asyncio
import os
import sys
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.core.database import get_db, engine
from app.models.nhl.models import Game, Player, Prediction
from app.services.nhl.enhanced_prediction_service import EnhancedNHLPredictionService
from app.services.core.odds_api_service import get_odds_service
import uuid


async def main():
    print("=== NHL Prediction Generation Test ===\n")

    # Get database session
    db = next(get_db())

    # Get upcoming games with odds_event_id
    print("1. Fetching upcoming NHL games with odds data...")
    upcoming_games = (
        db.query(Game)
        .filter(Game.status == "scheduled")
        .filter(Game.game_date >= datetime.now())
        .filter(Game.odds_event_id.isnot(None))
        .order_by(Game.game_date)
        .limit(3)
        .all()
    )

    print(f"   Found {len(upcoming_games)} upcoming games with odds\n")

    if not upcoming_games:
        print("   No upcoming games with odds found. Exiting.")
        db.close()
        return

    # Initialize odds service
    print("2. Initializing Odds API service...")
    api_key = '8ad802abc3050bd7ff719830103602d6'
    odds_service = get_odds_service(api_key, sport="nhl")

    # Initialize prediction service
    print("3. Initializing Enhanced NHL Prediction Service...")
    prediction_service = EnhancedNHLPredictionService(db=db, odds_api_service=odds_service)
    print("   Service initialized\n")

    # Generate predictions for each game
    print("4. Generating predictions...\n")
    total_predictions = 0
    high_conf_count = 0

    for game in upcoming_games:
        print(f"   Game: {game.away_team} @ {game.home_team} ({game.game_date.strftime('%Y-%m-%d %H:%M')})")

        try:
            predictions = prediction_service.generate_prop_predictions(
                game_id=str(game.id),
                stat_types=["goals", "assists", "points"],
                bookmaker="draftkings"
            )

            print(f"   Generated {len(predictions)} predictions:")
            for pred in predictions[:5]:  # Show first 5
                player_name = pred.get('player', 'Unknown')
                stat_type = pred.get('stat_type', 'N/A')
                projected = pred.get('projected', pred.get('predicted_value', 0))
                line = pred.get('line', 0)
                recommendation = pred.get('recommendation', 'N/A')
                confidence = pred.get('confidence', 0)
                line_source = pred.get('line_source', 'unknown')

                print(f"     - {player_name} {stat_type}: {projected:.1f} vs {line:.1f} ({recommendation}) @ {confidence:.0%} [{line_source}]")

                # Save high confidence predictions to database
                if confidence >= 0.70:
                    new_pred = Prediction(
                        id=uuid.uuid4(),
                        game_id=game.id,
                        player_id=pred.get('player_id'),
                        stat_type=stat_type,
                        predicted_value=projected,
                        bookmaker_line=line,
                        bookmaker_name=line_source,
                        recommendation=recommendation,
                        confidence=confidence,
                        over_price=pred.get('over_price'),
                        under_price=pred.get('under_price')
                    )
                    db.add(new_pred)
                    high_conf_count += 1

            if len(predictions) > 5:
                print(f"     ... and {len(predictions) - 5} more")

            total_predictions += len(predictions)

        except Exception as e:
            print(f"   Error: {e}")
            import traceback
            traceback.print_exc()

        print()

    # Save to database
    print(f"5. Saving predictions to database...")
    db.commit()
    print(f"   Saved {high_conf_count} high-confidence predictions out of {total_predictions} total")

    # Show high confidence predictions from database
    print(f"\n6. High confidence (70%+) predictions from database:")
    high_conf = (
        db.query(Prediction)
        .filter(Prediction.confidence >= 0.70)
        .order_by(Prediction.confidence.desc())
        .limit(5)
        .all()
    )

    if not high_conf:
        print("   No high-confidence predictions found in database")
    else:
        for pred in high_conf:
            player = db.query(Player).filter(Player.id == pred.player_id).first()
            game = db.query(Game).filter(Game.id == pred.game_id).first()
            if player and game:
                print(f"   {player.name} ({player.team}) {pred.stat_type}: {pred.predicted_value:.1f} vs {pred.bookmaker_line:.1f} ({pred.recommendation}) @ {pred.confidence:.0%}")

    try:
        await odds_service.close()
    except Exception:
        pass

    db.close()


if __name__ == "__main__":
    asyncio.run(main())
