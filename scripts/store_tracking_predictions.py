"""Store high-confidence FanDuel predictions in prediction_tracking table.

This script:
1. Fetches enhanced predictions for all upcoming games
2. Stores high-confidence bets (70%+) in prediction_tracking table
3. Records projection, line, edge, recommendation for later comparison
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from sqlalchemy import text
from app.core.database import SessionLocal


async def store_high_confidence_predictions():
    """Store all high-confidence FanDuel predictions."""
    db = SessionLocal()

    try:
        # Get all upcoming games
        games_result = db.execute(text("""
            SELECT id, away_team, home_team, game_date::date
            FROM games
            WHERE game_date >= CURRENT_DATE
            ORDER BY game_date
        """))

        games = games_result.fetchall()

        print("=" * 80)
        print("STORING HIGH-CONFIDENCE FANDUEL PREDICTIONS")
        print("=" * 80)

        stored_count = 0

        async with httpx.AsyncClient(timeout=60) as client:
            for game_id, away_team, home_team, game_date in games:
                # Fetch enhanced predictions for this game
                url = f"http://localhost:8002/api/v1/nba/predictions/enhanced/game/{game_id}?bookmaker=fanduel&stat_types=points"
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue

                    data = resp.json()
                    predictions = data.get("predictions", [])

                    # Filter to high-confidence bets (70%+)
                    for pred in predictions:
                        confidence = pred.get("confidence", 0)
                        if confidence < 0.70:
                            continue

                        # Only store bets (not PASS)
                        if pred.get("recommendation") == "PASS":
                            continue

                        # Check if already exists
                        existing = db.execute(text("""
                            SELECT id FROM prediction_tracking
                            WHERE game_id = :game_id
                              AND player_name = :player_name
                              AND stat_type = :stat_type
                        """), {
                            "game_id": game_id,
                            "player_name": pred["player"],
                            "stat_type": pred["stat_type"]
                        }).fetchone()

                        if existing:
                            continue

                        # Insert new prediction
                        import uuid
                        db.execute(text("""
                            INSERT INTO prediction_tracking (
                                id, game_id, player_id,
                                game_date, away_team, home_team,
                                player_name, player_team,
                                stat_type, predicted_value, bookmaker_line,
                                bookmaker, edge, recommendation, confidence,
                                prediction_generated_at
                            ) VALUES (
                                :id, :game_id, :player_id,
                                :game_date, :away_team, :home_team,
                                :player_name, :player_team,
                                :stat_type, :predicted_value, :bookmaker_line,
                                :bookmaker, :edge, :recommendation, :confidence,
                                :prediction_generated_at
                            )
                        """), {
                            "id": str(uuid.uuid4()),
                            "game_id": game_id,
                            "player_id": pred.get("player_id"),
                            "game_date": game_date,
                            "away_team": away_team,
                            "home_team": home_team,
                            "player_name": pred["player"],
                            "player_team": pred["team"],
                            "stat_type": pred["stat_type"],
                            "predicted_value": pred["projected"],
                            "bookmaker_line": pred["line"],
                            "bookmaker": pred.get("line_source", "fanduel"),
                            "edge": pred["edge"],
                            "recommendation": pred["recommendation"],
                            "confidence": pred["confidence"],
                            "prediction_generated_at": datetime.now()
                        })

                        # Print the stored prediction
                        rec = pred["recommendation"]
                        conf = int(pred["confidence"] * 100)
                        edge = pred["edge"]
                        print(f"  {pred['player']:25} | {away_team}@{home_team} | "
                              f"Our: {pred['projected']:5.1f} vs FD: {pred['line']:5.1f} | "
                              f"Edge: {edge:+.1f} | {rec:4} | {conf}%")

                        stored_count += 1

                except Exception as e:
                    print(f"Error fetching {game_id}: {e}")
                    continue

        db.commit()

        print()
        print("=" * 80)
        print(f"✅ Stored {stored_count} high-confidence predictions")
        print("=" * 80)

        # Show summary
        summary = db.execute(text("""
            SELECT away_team || ' @ ' || home_team as game,
                   COUNT(*) as bets,
                   SUM(CASE WHEN recommendation = 'OVER' THEN 1 ELSE 0 END) as overs,
                   SUM(CASE WHEN recommendation = 'UNDER' THEN 1 ELSE 0 END) as unders
            FROM prediction_tracking
            WHERE actual_resolved_at IS NULL
            GROUP BY game
            ORDER BY game
        """))

        print("\nSummary by game:")
        for row in summary:
            print(f"  {row[0]:20} | {row[1]:2} bets | Over: {row[2]:2} | Under: {row[3]:2}")

    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(store_high_confidence_predictions())
