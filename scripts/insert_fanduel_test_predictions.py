#!/usr/bin/env python3
"""
Insert test NBA predictions with FanDuel odds for upcoming games.

This script creates realistic test predictions with high confidence
to demonstrate the betting card functionality.
"""
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

# Add app directory to path
app_dir = Path(__file__).parent.parent
sys.path.insert(0, str(app_dir))

from sqlalchemy import create_engine, text
from app.core.config import settings


def insert_test_predictions():
    """Insert test NBA predictions with FanDuel odds."""

    # Create database engine
    engine = create_engine(settings.DATABASE_URL)

    # Test prediction data with high confidence
    # These are realistic player props with FanDuel odds
    test_predictions = [
        # High confidence (80%+) predictions
        {
            "player": "Luka Doncic",
            "stat_type": "points",
            "line": 28.5,
            "projected": 32.5,
            "recommendation": "OVER",
            "confidence": 0.82,
            "over_price": 1.91,  # -110 in decimal
            "under_price": 1.91,
        },
        {
            "player": "Luka Doncic",
            "stat_type": "assists",
            "line": 8.5,
            "projected": 10.2,
            "recommendation": "OVER",
            "confidence": 0.78,
            "over_price": 1.91,
            "under_price": 1.91,
        },
        {
            "player": "Shai Gilgeous-Alexander",
            "stat_type": "points",
            "line": 26.5,
            "projected": 30.1,
            "recommendation": "OVER",
            "confidence": 0.80,
            "over_price": 1.91,
            "under_price": 1.91,
        },
        {
            "player": "Giannis Antetokounmpo",
            "stat_type": "points",
            "line": 25.5,
            "projected": 29.8,
            "recommendation": "OVER",
            "confidence": 0.79,
            "over_price": 1.91,
            "under_price": 1.91,
        },
        {
            "player": "Giannis Antetokounmpo",
            "stat_type": "rebounds",
            "line": 11.5,
            "projected": 13.8,
            "recommendation": "OVER",
            "confidence": 0.76,
            "over_price": 1.91,
            "under_price": 1.91,
        },
        {
            "player": "Stephen Curry",
            "stat_type": "points",
            "line": 23.5,
            "projected": 27.2,
            "recommendation": "OVER",
            "confidence": 0.77,
            "over_price": 1.91,
            "under_price": 1.91,
        },
        {
            "player": "Stephen Curry",
            "stat_type": "threes",
            "line": 3.5,
            "projected": 4.8,
            "recommendation": "OVER",
            "confidence": 0.81,
            "over_price": 1.91,
            "under_price": 1.91,
        },
        {
            "player": "Nikola Jokic",
            "stat_type": "points",
            "line": 24.5,
            "projected": 28.3,
            "recommendation": "OVER",
            "confidence": 0.83,
            "over_price": 1.91,
            "under_price": 1.91,
        },
        {
            "player": "Nikola Jokic",
            "stat_type": "rebounds",
            "line": 10.5,
            "projected": 12.9,
            "recommendation": "OVER",
            "confidence": 0.80,
            "over_price": 1.91,
            "under_price": 1.91,
        },
        {
            "player": "Jayson Tatum",
            "stat_type": "points",
            "line": 25.5,
            "projected": 29.1,
            "recommendation": "OVER",
            "confidence": 0.75,
            "over_price": 1.91,
            "under_price": 1.91,
        },
        # Medium confidence (70-75%) predictions
        {
            "player": "Anthony Edwards",
            "stat_type": "points",
            "line": 24.5,
            "projected": 27.8,
            "recommendation": "OVER",
            "confidence": 0.72,
            "over_price": 1.91,
            "under_price": 1.91,
        },
        {
            "player": "Anthony Davis",
            "stat_type": "rebounds",
            "line": 11.5,
            "projected": 13.5,
            "recommendation": "OVER",
            "confidence": 0.74,
            "over_price": 1.91,
            "under_price": 1.91,
        },
        {
            "player": "Jalen Brunson",
            "stat_type": "points",
            "line": 22.5,
            "projected": 25.3,
            "recommendation": "OVER",
            "confidence": 0.71,
            "over_price": 1.91,
            "under_price": 1.91,
        },
        {
            "player": "Devin Booker",
            "stat_type": "points",
            "line": 23.5,
            "projected": 26.8,
            "recommendation": "OVER",
            "confidence": 0.73,
            "over_price": 1.91,
            "under_price": 1.91,
        },
        {
            "player": "Trae Young",
            "stat_type": "assists",
            "line": 9.5,
            "projected": 11.2,
            "recommendation": "OVER",
            "confidence": 0.70,
            "over_price": 1.91,
            "under_price": 1.91,
        },
    ]

    with engine.connect() as conn:
        # Get an upcoming game
        result = conn.execute(text("""
            SELECT id, home_team, away_team, game_date
            FROM games
            WHERE game_date >= CURRENT_DATE
              AND status = 'scheduled'
            ORDER BY game_date
            LIMIT 1
        """))

        game = result.fetchone()

        if not game:
            print("No upcoming games found!")
            # Update a game to have tomorrow's date
            conn.execute(text("""
                UPDATE games
                SET game_date = CURRENT_DATE + INTERVAL '1 day'
                WHERE id IN (SELECT id FROM games LIMIT 1)
            """))
            conn.commit()

            # Get the game again
            result = conn.execute(text("""
                SELECT id, home_team, away_team, game_date
                FROM games
                WHERE game_date >= CURRENT_DATE
                ORDER BY game_date
                LIMIT 1
            """))
            game = result.fetchone()

        if not game:
            print("Still no games found. Exiting.")
            return

        game_id, home_team, away_team, game_date = game
        print(f"Using game: {away_team} @ {home_team} on {game_date}")
        print(f"Game ID: {game_id}")
        print("=" * 60)

        # Get player IDs for our test predictions
        player_ids = {}
        for pred in test_predictions:
            player_name = pred["player"]
            result = conn.execute(text("""
                SELECT id FROM players WHERE name = :name LIMIT 1
            """), {"name": player_name})

            player = result.fetchone()
            if player:
                player_ids[player_name] = player[0]
            else:
                # Create a new player
                new_id = str(uuid.uuid4())
                conn.execute(text("""
                    INSERT INTO players (id, name, team, position, active, created_at, updated_at)
                    VALUES (:id, :name, :team, 'SF', true, NOW(), NOW())
                """), {"id": new_id, "name": player_name, "team": home_team})
                player_ids[player_name] = new_id

        conn.commit()

        # Insert predictions
        inserted = 0
        for pred in test_predictions:
            player_id = player_ids.get(pred["player"])
            if not player_id:
                continue

            # Check if prediction already exists
            existing = conn.execute(text("""
                SELECT id FROM predictions
                WHERE player_id = :player_id
                  AND game_id = :game_id
                  AND stat_type = :stat_type
            """), {
                "player_id": player_id,
                "game_id": str(game_id),
                "stat_type": pred["stat_type"]
            }).fetchone()

            if existing:
                # Update existing prediction
                conn.execute(text("""
                    UPDATE predictions
                    SET predicted_value = :projected,
                        bookmaker_line = :line,
                        bookmaker_name = 'FanDuel',
                        confidence = :confidence,
                        recommendation = :recommendation,
                        over_price = :over_price,
                        under_price = :under_price,
                        odds_fetched_at = NOW(),
                        created_at = NOW()
                    WHERE id = :id
                """), {
                    "id": existing[0],
                    "projected": pred["projected"],
                    "line": pred["line"],
                    "confidence": pred["confidence"],
                    "recommendation": pred["recommendation"],
                    "over_price": pred["over_price"],
                    "under_price": pred["under_price"]
                })
                print(f"✓ Updated: {pred['player']} {pred['stat_type']} @ {pred['confidence']:.1%}")
            else:
                # Insert new prediction
                new_id = str(uuid.uuid4())
                conn.execute(text("""
                    INSERT INTO predictions (
                        id, player_id, game_id, stat_type, predicted_value,
                        bookmaker_line, bookmaker_name, confidence, recommendation,
                        over_price, under_price, odds_fetched_at, created_at,
                        model_version
                    ) VALUES (
                        :id, :player_id, :game_id, :stat_type, :predicted_value,
                        :line, 'FanDuel', :confidence, :recommendation,
                        :over_price, :under_price, NOW(), NOW(), '2.0'
                    )
                """), {
                    "id": new_id,
                    "player_id": player_id,
                    "game_id": str(game_id),
                    "stat_type": pred["stat_type"],
                    "predicted_value": pred["projected"],
                    "line": pred["line"],
                    "confidence": pred["confidence"],
                    "recommendation": pred["recommendation"],
                    "over_price": pred["over_price"],
                    "under_price": pred["under_price"]
                })
                print(f"✓ Inserted: {pred['player']} {pred['stat_type']} @ {pred['confidence']:.1%}")

            inserted += 1

        conn.commit()

        print("\n" + "=" * 60)
        print(f"Total predictions inserted/updated: {inserted}")

        # Verify the predictions
        result = conn.execute(text("""
            SELECT
                pl.name,
                p.stat_type,
                p.recommendation,
                p.bookmaker_line,
                p.confidence,
                p.over_price
            FROM predictions p
            JOIN players pl ON p.player_id = pl.id
            WHERE p.game_id = :game_id
              AND p.bookmaker_name = 'FanDuel'
            ORDER BY p.confidence DESC
        """), {"game_id": str(game_id)})

        print("\nPredictions in database:")
        print("-" * 60)
        for row in result:
            print(f"{row.name}: {row.stat_type} {row.recommendation} "
                  f"{row.bookmaker_line} @ {row.confidence:.1%} "
                  f"(odds: {row.over_price})")


if __name__ == "__main__":
    insert_test_predictions()
