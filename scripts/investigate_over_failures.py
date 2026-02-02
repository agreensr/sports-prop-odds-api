"""Investigate why OVER predictions fail while UNDER predictions succeed.

This script analyzes:
1. Projection vs actual differences for OVER vs UNDER
2. Whether high lines correlate with OVER failures
3. One-directional bias in the model
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal
from app.models import Prediction


def investigate_over_failures():
    """Analyze why OVER predictions fail."""
    db = SessionLocal()

    try:
        # Get all resolved predictions
        results = db.query(Prediction).filter(
            Prediction.actuals_resolved_at.isnot(None)
        ).all()

        print(f"Found {len(results)} resolved predictions")
        print()

        # Group by stat type and recommendation
        stats = {}
        for p in results:
            stat_type = p.stat_type
            rec = p.recommendation or 'PASS'
            if rec not in ['OVER', 'UNDER']:
                rec = 'PASS'

            key = (stat_type, rec)
            if key not in stats:
                stats[key] = {
                    'count': 0,
                    'wins': 0,
                    'predicted_vals': [],
                    'line_vals': [],
                    'actual_vals': [],
                    'errors': [],
                    'over_prices': [],
                    'confidences': []
                }

            # Determine if prediction was correct
            line = p.bookmaker_line
            actual = p.actual_value
            if actual is None or line is None:
                continue

            stats[key]['count'] += 1

            if rec == 'OVER':
                won = actual > line
            else:  # UNDER
                won = actual < line

            if won:
                stats[key]['wins'] += 1

            stats[key]['predicted_vals'].append(p.predicted_value)
            stats[key]['line_vals'].append(line)
            stats[key]['actual_vals'].append(actual)
            stats[key]['errors'].append(actual - p.predicted_value)
            stats[key]['over_prices'].append(p.over_price)
            stats[key]['confidences'].append(p.confidence or 0)

        # Analyze each stat type
        for stat in ['points', 'rebounds', 'assists', 'threes']:
            print(f"\n{'─' * 70}")
            print(f"  {stat.upper()}")
            print(f"{'─' * 70}")

            over_key = (stat, 'OVER')
            under_key = (stat, 'UNDER')

            over_data = stats.get(over_key)
            under_data = stats.get(under_key)

            if over_data and under_data and over_data['count'] > 0 and under_data['count'] > 0 and over_data['predicted_vals'] and under_data['predicted_vals']:
                # OVER stats
                over_win_rate = 100 * over_data['wins'] / over_data['count']
                avg_pred_over = sum(over_data['predicted_vals']) / len(over_data['predicted_vals'])
                avg_line_over = sum(over_data['line_vals']) / len(over_data['line_vals'])
                avg_actual_over = sum(over_data['actual_vals']) / len(over_data['actual_vals'])
                avg_error_over = sum(over_data['errors']) / len(over_data['errors'])

                # UNDER stats
                under_win_rate = 100 * under_data['wins'] / under_data['count']
                avg_pred_under = sum(under_data['predicted_vals']) / len(under_data['predicted_vals'])
                avg_line_under = sum(under_data['line_vals']) / len(under_data['line_vals'])
                avg_actual_under = sum(under_data['actual_vals']) / len(under_data['actual_vals'])
                avg_error_under = sum(under_data['errors']) / len(under_data['errors'])

                print(f"\n                OVER        UNDER")
                print(f"               ════        ═════")
                print(f"Count:          {over_data['count']:4d}        {under_data['count']:4d}")
                print(f"Win Rate:    {over_win_rate:5.1f}%      {under_win_rate:5.1f}%")
                print(f"Avg Line:    {avg_line_over:6.1f}      {avg_line_under:6.1f}")
                print(f"Avg Predict: {avg_pred_over:6.1f}      {avg_pred_under:6.1f}")
                print(f"Avg Actual:  {avg_actual_over:6.1f}      {avg_actual_under:6.1f}")
                print(f"Avg Error:   {avg_error_over:+6.2f}      {avg_error_under:+6.2f}")
                print(f"              (actual-predicted)")

                # Key insight analysis
                print(f"\n  🔍 Key Findings:")
                if avg_error_over < -1 and avg_error_under < -1:
                    print(f"     • Model UNDERESTIMES for both OVER and UNDER")
                    print(f"     • Systematic bias: projections are {-avg_error_over:.1f} below actual")
                elif avg_error_over < 0:
                    print(f"     • OVER fails because model is too conservative")
                    print(f"     • Projections are {-avg_error_over:.1f} below actual")
                elif avg_line_over > avg_line_under:
                    print(f"     • OVER has higher lines ({avg_line_over:.1f} vs {avg_line_under:.1f})")

                # Check if predicted value is consistently below line for OVER
                if avg_pred_over < avg_line_over - 2:
                    print(f"     • OVER predictions: projected {avg_pred_over:.1f} vs line {avg_line_over:.1f}")
                    print(f"       Model projects BELOW line but says OVER = contradiction")

        # Check directional bias
        print(f"\n{'=' * 70}")
        print("DIRECTIONAL BIAS ANALYSIS")
        print("=" * 70)

        all_errors = []
        for p in results:
            if p.actual_value is not None and p.predicted_value is not None:
                all_errors.append(p.actual_value - p.predicted_value)

        if all_errors:
            avg_error = sum(all_errors) / len(all_errors)
            over_estimates = sum(1 for e in all_errors if e > 0)
            under_estimates = sum(1 for e in all_errors if e < 0)
            total = len(all_errors)

            print(f"\nTotal predictions: {total}")
            print(f"Avg error (actual - predicted): {avg_error:+.2f}")
            print(f"Times actual > predicted: {over_estimates} ({100*over_estimates/total:.1f}%)")
            print(f"Times actual < predicted: {under_estimates} ({100*under_estimates/total:.1f}%)")

            if avg_error < -0.5:
                print(f"\n⚠️  MODEL BIAS: Projections too low by {-avg_error:.2f} points")
                print(f"   Actual exceeds prediction → UNDER wins, OVER loses")
            elif avg_error > 0.5:
                print(f"\n⚠️  MODEL BIAS: Projections too high by {avg_error:.2f} points")
            else:
                print(f"\n✓ Model projections are roughly unbiased")

        # Analyze prediction vs line relationship
        print(f"\n{'=' * 70}")
        print("PREDICTION vs LINE RELATIONSHIP")
        print("=" * 70)

        for stat in ['points', 'rebounds', 'assists', 'threes']:
            over_key = (stat, 'OVER')
            under_key = (stat, 'UNDER')
            over_data = stats.get(over_key)
            under_data = stats.get(under_key)

            if over_data and under_data and over_data['count'] > 0:
                if not over_data['predicted_vals'] or not under_data['predicted_vals']:
                    print(f"\n{stat.upper()}: Missing data (predictions without lines/actuals)")
                    continue

                avg_pred_over = sum(over_data['predicted_vals']) / len(over_data['predicted_vals'])
                avg_line_over = sum(over_data['line_vals']) / len(over_data['line_vals'])
                avg_pred_under = sum(under_data['predicted_vals']) / len(under_data['predicted_vals'])
                avg_line_under = sum(under_data['line_vals']) / len(under_data['line_vals'])

                print(f"\n{stat.upper()}:")
                print(f"  OVER:  predict {avg_pred_over:.1f} vs line {avg_line_over:.1f} (gap: {avg_pred_over - avg_line_over:+.1f})")
                print(f"  UNDER: predict {avg_pred_under:.1f} vs line {avg_line_under:.1f} (gap: {avg_pred_under - avg_line_under:+.1f})")

                if avg_pred_over < avg_line_over:
                    print(f"    ⚠️ OVER recommendation but projection BELOW line")
                if avg_pred_under > avg_line_under:
                    print(f"    ⚠️ UNDER recommendation but projection ABOVE line")

    finally:
        db.close()


if __name__ == '__main__':
    investigate_over_failures()
