"""Store high-confidence predictions from database in prediction_tracking table.

This script:
1. Fetches high-confidence predictions (70%+) directly from the database
2. Stores them in prediction_tracking table for accuracy monitoring
3. Records projection, line, edge, recommendation for later comparison
"""
import sys
from datetime import datetime
from pathlib import Path
import uuid

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from app.core.database import SessionLocal


def store_high_confidence_predictions():
    """Store all high-confidence predictions from database."""
    db = SessionLocal()

    try:
        print("=" * 80)
        print("STORING HIGH-CONFIDENCE PREDICTIONS FROM DATABASE")
        print("=" * 80)
        print()

        # Get all high-confidence predictions for upcoming games
        # that haven't been resolved yet
        predictions_result = db.execute(text("""
            SELECT
                p.id as prediction_id,
                p.player_id,
                p.game_id,
                pl.name as player_name,
                pl.team as player_team,
                p.stat_type,
                p.predicted_value,
                p.bookmaker_line,
                p.bookmaker_name,
                p.recommendation,
                p.confidence,
                p.over_price,
                p.under_price,
                g.away_team,
                g.home_team,
                g.game_date::date
            FROM predictions p
            JOIN players pl ON p.player_id = pl.id
            JOIN games g ON p.game_id = g.id
            WHERE p.confidence >= 0.70
              AND g.game_date >= CURRENT_DATE
              AND p.actuals_resolved_at IS NULL
            ORDER BY g.game_date, p.confidence DESC
        """))

        predictions = predictions_result.fetchall()

        if not predictions:
            print("No high-confidence predictions found for upcoming games.")
            return

        print(f"Found {len(predictions)} high-confidence predictions to process")
        print()

        stored_count = 0
        skipped_count = 0
        error_count = 0

        for pred in predictions:
            # Unpack prediction data using dict-like access by column name
            pred_dict = dict(pred._mapping)
            prediction_id = pred_dict['prediction_id']
            player_id = pred_dict['player_id']
            game_id = pred_dict['game_id']
            player_name = pred_dict['player_name']
            player_team = pred_dict['player_team']
            stat_type = pred_dict['stat_type']
            predicted_value = pred_dict['predicted_value']
            bookmaker_line = pred_dict['bookmaker_line']
            bookmaker = pred_dict['bookmaker_name'] or "unknown"
            recommendation = pred_dict['recommendation']
            confidence = pred_dict['confidence']
            away_team = pred_dict['away_team']
            home_team = pred_dict['home_team']
            game_date = pred_dict['game_date']

            # Only store bets (not PASS)
            if recommendation == "PASS":
                skipped_count += 1
                continue

            # Check if already exists in tracking table
            existing = db.execute(text("""
                SELECT id FROM prediction_tracking
                WHERE game_id = :game_id
                  AND player_name = :player_name
                  AND stat_type = :stat_type
                  AND prediction_generated_at::date = CURRENT_DATE
            """), {
                "game_id": game_id,
                "player_name": player_name,
                "stat_type": stat_type
            }).fetchone()

            if existing:
                skipped_count += 1
                continue

            # Calculate edge
            edge = predicted_value - bookmaker_line

            # Insert into prediction_tracking table
            try:
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
                    "player_id": player_id,
                    "game_date": game_date,
                    "away_team": away_team,
                    "home_team": home_team,
                    "player_name": player_name,
                    "player_team": player_team,
                    "stat_type": stat_type,
                    "predicted_value": predicted_value,
                    "bookmaker_line": bookmaker_line,
                    "bookmaker": bookmaker,
                    "edge": edge,
                    "recommendation": recommendation,
                    "confidence": confidence,
                    "prediction_generated_at": datetime.now()
                })

                # Print the stored prediction
                conf_pct = int(confidence * 100)
                print(f"  {player_name:25} | {away_team}@{home_team:3} | "
                      f"Our: {predicted_value:5.1f} vs {bookmaker:3}: {bookmaker_line:5.1f} | "
                      f"Edge: {edge:+.1f} | {recommendation:4} | {conf_pct}%")

                stored_count += 1

            except Exception as e:
                print(f"  ERROR storing {player_name} {stat_type}: {e}")
                error_count += 1
                continue

        db.commit()

        print()
        print("=" * 80)
        print(f"✅ Stored {stored_count} high-confidence predictions")
        if skipped_count > 0:
            print(f"⏭️  Skipped {skipped_count} (PASS or already tracked)")
        if error_count > 0:
            print(f"❌ {error_count} errors")
        print("=" * 80)

        # Show summary by game
        if stored_count > 0:
            summary = db.execute(text("""
                SELECT away_team || ' @ ' || home_team as game,
                       COUNT(*) as bets,
                       SUM(CASE WHEN recommendation = 'OVER' THEN 1 ELSE 0 END) as overs,
                       SUM(CASE WHEN recommendation = 'UNDER' THEN 1 ELSE 0 END) as unders,
                       AVG(confidence) as avg_confidence
                FROM prediction_tracking
                WHERE actual_resolved_at IS NULL
                  AND prediction_generated_at::date = CURRENT_DATE
                GROUP BY game
                ORDER BY game
            """))

            print("\nSummary by game:")
            print(f"  {'Game':20} | {'Bets':4} | {'Over':4} | {'Under':4} | {'Avg Conf':8}")
            print("  " + "-" * 62)
            for row in summary:
                avg_conf = int(row[4] * 100) if row[4] else 0
                print(f"  {row[0]:20} | {row[1]:4} | {row[2]:4} | {row[3]:4} | {avg_conf}%")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    store_high_confidence_predictions()
