#!/usr/bin/env python3
"""
Generate NBA predictions with FanDuel odds for upcoming games.

This script:
1. Finds upcoming NBA games in the database
2. Fetches real FanDuel odds from the Odds API
3. Generates predictions with confidence calculations
4. Stores predictions in the database
"""
import asyncio
import os
import sys
from datetime import date, timedelta, datetime
from pathlib import Path

# Add app directory to path
app_dir = Path(__file__).parent.parent
sys.path.insert(0, str(app_dir))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import settings


def generate_nba_predictions_with_fanduel():
    """Generate NBA predictions with FanDuel odds."""

    # Create database engine and session
    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Get THE_ODDS_API_KEY from environment
        api_key = os.getenv("THE_ODDS_API_KEY")
        if not api_key:
            print("ERROR: THE_ODDS_API_KEY environment variable not set")
            return

        # Import prediction service
        from app.services.nba.enhanced_prediction_service import EnhancedPredictionService
        from app.services.core.odds_api_service import OddsApiService

        # Create odds service for NBA
        odds_service = OddsApiService(
            api_key=api_key,
            default_sport="nba"
        )

        # Create prediction service
        prediction_svc = EnhancedPredictionService(
            db=session,
            odds_api_service=odds_service
        )

        # Get upcoming games
        today = date.today()
        end_date = today + timedelta(days=7)

        result = session.execute(text("""
            SELECT id, home_team, away_team, game_date
            FROM games
            WHERE game_date >= :today
              AND game_date <= :end_date
              AND status = 'scheduled'
            ORDER BY game_date
            LIMIT 10
        """), {"today": today, "end_date": end_date})

        games = result.fetchall()

        if not games:
            print("No upcoming games found in database")
            return

        print(f"Found {len(games)} upcoming games")
        print("=" * 60)

        # Stat types to predict
        stat_types = ["points", "rebounds", "assists", "threes"]

        total_predictions = 0

        for game in games:
            game_id = game[0]
            home_team = game[1]
            away_team = game[2]
            game_date = game[3]

            print(f"\nGame: {away_team} @ {home_team} on {game_date}")

            try:
                # Generate predictions for this game
                predictions = prediction_svc.generate_prop_predictions(
                    game_id=str(game_id),
                    stat_types=stat_types,
                    bookmaker="fanduel"  # Only FanDuel
                )

                # Count high-confidence predictions
                high_conf = [p for p in predictions if p.get("confidence", 0) >= 0.70]

                print(f"  Generated {len(predictions)} predictions")
                print(f"  High confidence (70%+): {len(high_conf)}")

                # Show high-confidence predictions
                for pred in high_conf[:5]:  # Show top 5
                    print(f"    - {pred.get('player')}: {pred.get('stat_type')} "
                          f"{pred.get('recommendation')} {pred.get('line')} "
                          f"@ {pred.get('confidence'):.1%}")

                total_predictions += len(predictions)

            except Exception as e:
                print(f"  ERROR: {e}")
                continue

        print("\n" + "=" * 60)
        print(f"Total predictions generated: {total_predictions}")

        # Show summary of high-confidence FanDuel predictions
        result = session.execute(text("""
            SELECT
                pl.name,
                p.stat_type,
                p.recommendation,
                p.bookmaker_line,
                p.confidence,
                p.over_price,
                g.home_team,
                g.away_team,
                g.game_date
            FROM predictions p
            JOIN players pl ON p.player_id = pl.id
            JOIN games g ON p.game_id = g.id
            WHERE g.game_date >= :today
              AND p.bookmaker_name ILIKE 'fanduel'
              AND p.confidence >= 0.70
            ORDER BY p.confidence DESC
            LIMIT 20
        """), {"today": today})

        print("\nHigh-confidence FanDuel predictions in database:")
        print("-" * 60)
        for row in result:
            print(f"{row.name}: {row.stat_type} {row.recommendation} "
                  f"{row.bookmaker_line} @ {row.confidence:.1%} "
                  f"({row.over_price} odds)")

    finally:
        session.close()


if __name__ == "__main__":
    generate_nba_predictions_with_fanduel()
