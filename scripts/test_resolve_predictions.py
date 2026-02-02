"""Resolve predictions with boxscore data and check accuracy."""
import asyncio
from app.core.database import SessionLocal
from app.services.nba.boxscore_import_service import BoxscoreImportService

async def resolve_and_check():
    db = SessionLocal()
    try:
        service = BoxscoreImportService(db)

        print("Resolving predictions with boxscore data...")
        print()

        # Resolve predictions for completed games
        result = await service.resolve_predictions_for_completed_games(hours_back=48)

        print(f"Resolution Results:")
        print(f"  Games processed: {result['games_processed']}")
        print(f"  Predictions resolved: {result['predictions_resolved']}")
        print(f"  Player stats created: {result['player_stats_created']}")
        print(f"  Player stats updated: {result['player_stats_updated']}")

        if result.get('errors'):
            print()
            print("Errors:")
            for e in result['errors']:
                print(f"  - {e}")

        # Now check accuracy statistics
        from app.models import Prediction

        resolved = db.query(Prediction).filter(
            Prediction.actuals_resolved_at.isnot(None),
            Prediction.stat_type == "points"
        ).all()

        if resolved:
            import statistics
            from sqlalchemy import func

            # Get overall stats
            total = len(resolved)
            correct = len([p for p in resolved if p.was_correct is True])
            errors = [abs(p.predicted_value - p.actual_value) for p in resolved]

            print()
            print("=" * 60)
            print("PREDICTION ACCURACY (points)")
            print("=" * 60)
            print(f"Total predictions resolved: {total}")
            print(f"Correct predictions: {correct} ({100*correct/total:.1f}%)")
            print(f"Win rate: {100*correct/total:.1f}%")
            print(f"Average absolute error: {statistics.mean(errors):.2f} points")
            print(f"Predicted avg: {statistics.mean([p.predicted_value for p in resolved]):.2f}")
            print(f"Actual avg: {statistics.mean([p.actual_value for p in resolved]):.2f}")

            # Check by model version
            print()
            print("By model version:")
            by_model = {}
            for p in resolved:
                model = p.model_version or "unknown"
                if model not in by_model:
                    by_model[model] = []
                by_model[model].append(abs(p.predicted_value - p.actual_value))

            for model, errors in sorted(by_model.items()):
                print(f"  {model}: {len(by_model[model])} predictions, avg error: {statistics.mean(errors):.2f}")

        db.commit()

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(resolve_and_check())
