"""Recalculate historical prediction accuracy using correct logic.

The bug: was_correct was comparing actual vs predicted_value
The fix: was_correct should compare actual vs bookmaker_line

This script recalculates was_correct for all resolved predictions
using the correct logic (actual vs line).

Usage:
    python scripts/recalculate_accuracy.py
"""
import sys
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import and_, or_
from app.core.database import SessionLocal
from app.models import Prediction


def recalculate_accuracy():
    """Recalculate was_correct for all resolved predictions."""
    db = SessionLocal()

    try:
        # Get all predictions that have been resolved (have actual_value)
        predictions = db.query(Prediction).filter(
            Prediction.actual_value.isnot(None)
        ).all()

        print(f"Found {len(predictions)} resolved predictions to recalculate")
        print()

        changes = {
            'total': len(predictions),
            'changed': 0,
            'to_correct': 0,
            'to_incorrect': 0,
            'no_line': 0,
            'by_stat': {}
        }

        for p in predictions:
            # Skip predictions without recommendation
            if not p.recommendation or p.recommendation not in ['OVER', 'UNDER']:
                continue

            actual = p.actual_value
            old_was_correct = p.was_correct

            # Use bookmaker_line if available, fall back to predicted_value
            line = p.bookmaker_line if p.bookmaker_line is not None else p.predicted_value

            if p.bookmaker_line is None:
                changes['no_line'] += 1

            # Calculate was_correct using the correct logic
            new_was_correct = None
            if p.recommendation == "OVER":
                new_was_correct = actual > line
            elif p.recommendation == "UNDER":
                new_was_correct = actual < line

            # Track by stat type
            stat = p.stat_type
            if stat not in changes['by_stat']:
                changes['by_stat'][stat] = {
                    'total': 0,
                    'changed': 0,
                    'over_correct': 0,
                    'over_total': 0,
                    'under_correct': 0,
                    'under_total': 0
                }

            changes['by_stat'][stat]['total'] += 1
            if p.recommendation == 'OVER':
                changes['by_stat'][stat]['over_total'] += 1
                if new_was_correct:
                    changes['by_stat'][stat]['over_correct'] += 1
            elif p.recommendation == 'UNDER':
                changes['by_stat'][stat]['under_total'] += 1
                if new_was_correct:
                    changes['by_stat'][stat]['under_correct'] += 1

            # Update if changed
            if old_was_correct != new_was_correct:
                p.was_correct = new_was_correct
                changes['changed'] += 1
                changes['by_stat'][stat]['changed'] += 1

                if new_was_correct:
                    changes['to_correct'] += 1
                else:
                    changes['to_incorrect'] += 1

        # Commit changes
        db.commit()

        # Print summary
        print("=" * 70)
        print("RECALCULATION COMPLETE")
        print("=" * 70)
        print()
        print(f"Total predictions processed: {changes['total']}")
        print(f"Predictions changed:       {changes['changed']}")
        print(f"  Changed to correct:     {changes['to_correct']}")
        print(f"  Changed to incorrect:   {changes['to_incorrect']}")
        print(f"  No bookmaker_line:       {changes['no_line']} (used predicted_value)")
        print()

        # Print breakdown by stat type
        print("BREAKDOWN BY STAT TYPE")
        print("-" * 70)
        for stat in ['points', 'rebounds', 'assists', 'threes']:
            if stat not in changes['by_stat']:
                continue

            data = changes['by_stat'][stat]
            over_rate = 100 * data['over_correct'] / data['over_total'] if data['over_total'] > 0 else 0
            under_rate = 100 * data['under_correct'] / data['under_total'] if data['under_total'] > 0 else 0

            print(f"\n{stat.upper()}:")
            print(f"  Total:   {data['total']}")
            print(f"  Changed: {data['changed']}")
            print(f"  OVER:    {data['over_correct']}/{data['over_total']} = {over_rate:.1f}%")
            print(f"  UNDER:   {data['under_correct']}/{data['under_total']} = {under_rate:.1f}%")

        print()
        print("✓ Database updated with correct was_correct values")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == '__main__':
    recalculate_accuracy()
