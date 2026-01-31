"""Regenerate predictions with the updated enhanced model.

This script:
1. Deletes old predictions for upcoming games
2. Generates new predictions with improved confidence calculation
3. Stores results in the database
"""
import sys
import uuid
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from app.core.database import SessionLocal
from app.services.nba.enhanced_prediction_service import EnhancedPredictionService
from app.models import Game, Prediction


def regenerate_predictions(include_estimated_lines: bool = True):
    """Regenerate predictions for all upcoming games.

    Args:
        include_estimated_lines: If True, include predictions with estimated lines
                                 (when real Odds API data isn't available)
    """
    db = SessionLocal()

    try:
        print("=" * 80)
        print("REGENERATING PREDICTIONS WITH UPDATED MODEL")
        print("=" * 80)
        print()

        # Get upcoming games
        games = db.query(Game).filter(
            Game.game_date >= "2026-01-30"
        ).order_by(Game.game_date).all()

        print(f"Found {len(games)} upcoming games")
        if include_estimated_lines:
            print("Note: Including estimated lines (Odds API data unavailable)")
        print()

        # Delete old predictions for these games
        game_ids = [g.id for g in games]
        deleted = db.query(Prediction).filter(
            Prediction.game_id.in_(game_ids)
        ).delete()

        db.commit()
        print(f"Deleted {deleted} old predictions")
        print()

        # Initialize service
        service = EnhancedPredictionService(db)

        # Generate predictions for each game
        total_generated = 0
        high_confidence = 0

        for game in games:
            print(f"{game.away_team} @ {game.home_team} ({game.game_date.strftime('%Y-%m-%d %H:%M')})")
            print("-" * 60)

            predictions = service.generate_prop_predictions(
                game_id=game.id,
                stat_types=["points"],
                bookmaker="fanduel"
            )

            # If including estimated lines, we need to generate them directly
            if include_estimated_lines and len(predictions) == 0:
                # Get active players and generate predictions with estimated lines
                players = service._get_active_players(game)

                for player in players:
                    try:
                        projection_data = service._calculate_base_projection(
                            player, game, "points"
                        )

                        if not projection_data:
                            continue

                        line_data = service._get_bookmaker_line(
                            player, game, "points", "fanduel"
                        )

                        # Calculate edge and recommendation
                        projected = projection_data["projected"]
                        line = line_data["line"]
                        edge = projected - line

                        if edge >= service.min_edge_for_bet:
                            recommendation = "OVER"
                        elif edge <= -service.min_edge_for_bet:
                            recommendation = "UNDER"
                        else:
                            recommendation = "PASS"

                        # Calculate confidence
                        if recommendation != "PASS":
                            confidence = service._calculate_confidence(
                                abs(edge), projection_data, line_data
                            )
                        else:
                            confidence = 0.0

                        if recommendation == "PASS" or confidence < 0.50:
                            continue

                        # Create prediction dict
                        pred = {
                            "player": player.name,
                            "player_id": player.id,
                            "team": player.team,
                            "stat_type": "points",
                            "projected": projected,
                            "line": line,
                            "edge": edge,
                            "recommendation": recommendation,
                            "confidence": confidence,
                            "bookmaker": line_data.get("bookmaker", "estimated"),
                            "line_source": "estimated"
                        }
                        predictions.append(pred)

                    except Exception as e:
                        print(f"  Error generating for {player.name}: {e}")
                        continue

            # Store predictions
            for pred in predictions:
                new_pred = Prediction(
                    id=str(uuid.uuid4()),
                    sport_id="nba",
                    game_id=game.id,
                    player_id=pred.get("player_id"),
                    stat_type=pred["stat_type"],
                    predicted_value=pred["projected"],
                    bookmaker_line=pred["line"],
                    bookmaker_name=pred.get("bookmaker", "fanduel"),
                    recommendation=pred["recommendation"],
                    confidence=pred["confidence"],
                    model_version="2.1.0-calibrated",
                    created_at=datetime.now()
                )
                db.add(new_pred)

                total_generated += 1
                if pred["confidence"] >= 0.70:
                    high_confidence += 1

                # Show prediction
                conf_pct = int(pred["confidence"] * 100)
                rec = pred["recommendation"]
                line_source = pred.get("line_source", "estimated")

                print(f"  {pred['player']:20} | {pred['projected']:5.1f} vs {pred['line']:5.1f} | "
                      f"{rec:4} | {conf_pct}% | Edge: {pred.get('edge', 0):+5.1f} | [{line_source}]")

            db.commit()
            print()

        # Summary
        print("=" * 80)
        print("REGENERATION COMPLETE")
        print("=" * 80)
        print(f"Total predictions generated: {total_generated}")
        print(f"High confidence (70%+): {high_confidence}")

        # Show distribution by confidence
        summary = db.execute(text("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN confidence >= 0.80 THEN 1 ELSE 0 END) as very_high,
                SUM(CASE WHEN confidence >= 0.70 AND confidence < 0.80 THEN 1 ELSE 0 END) as high,
                SUM(CASE WHEN confidence >= 0.60 AND confidence < 0.70 THEN 1 ELSE 0 END) as medium,
                SUM(CASE WHEN confidence < 0.60 THEN 1 ELSE 0 END) as low
            FROM predictions
            WHERE game_id IN (
                SELECT id FROM games WHERE game_date >= CURRENT_DATE
            )
        """)).fetchone()

        if summary and summary[0]:
            print()
            print("Confidence Distribution:")
            print(f"  80%+:  {summary[1]:4} (very high)")
            print(f"  70-79%: {summary[2]:4} (high)")
            print(f"  60-69%: {summary[3]:4} (medium)")
            print(f"  <60%:   {summary[4]:4} (low)")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    regenerate_predictions(include_estimated_lines=True)
