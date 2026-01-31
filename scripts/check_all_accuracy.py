"""Check accuracy for all stat types."""
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal
from app.models import Prediction
import statistics

def check_accuracy():
    db = SessionLocal()

    # Get resolved predictions for all stat types
    resolved = db.query(Prediction).filter(
        Prediction.actuals_resolved_at.isnot(None)
    ).all()

    print('='*60)
    print('PREDICTION ACCURACY BY STAT TYPE')
    print('='*60)

    # Group by stat type
    by_stat = {}
    for p in resolved:
        stat = p.stat_type
        rec = p.recommendation or 'PASS'
        if rec not in ['OVER', 'UNDER', 'PASS']:
            rec = 'PASS'
        if stat not in by_stat:
            by_stat[stat] = {'OVER': {'correct': 0, 'total': 0}, 'UNDER': {'correct': 0, 'total': 0}, 'PASS': {'correct': 0, 'total': 0}, 'ALL': {'correct': 0, 'total': 0, 'errors': []}}

        if p.was_correct is True:
            by_stat[stat][rec]['correct'] += 1
            by_stat[stat]['ALL']['correct'] += 1
        by_stat[stat][rec]['total'] += 1
        by_stat[stat]['ALL']['total'] += 1
        by_stat[stat]['ALL']['errors'].append(abs(p.predicted_value - p.actual_value))

    # Print results
    for stat in ['points', 'rebounds', 'assists', 'threes']:
        if stat not in by_stat:
            print(f'\n{stat.upper()}: No resolved predictions')
            continue

        data = by_stat[stat]
        over = data['OVER']
        under = data['UNDER']
        all_data = data['ALL']

        overall_pct = 100 * all_data['correct'] / all_data['total'] if all_data['total'] > 0 else 0
        over_pct = 100 * over['correct'] / over['total'] if over['total'] > 0 else 0
        under_pct = 100 * under['correct'] / under['total'] if under['total'] > 0 else 0
        avg_error = statistics.mean(all_data['errors']) if all_data['errors'] else 0

        print(f'\n{stat.upper()} ({all_data["total"]} predictions)')
        print(f'  Overall:   {all_data["correct"]:3}/{all_data["total"]:3} = {overall_pct:5.1f}%')
        print(f'  OVER:      {over["correct"]:3}/{over["total"]:3} = {over_pct:5.1f}%')
        print(f'  UNDER:     {under["correct"]:3}/{under["total"]:3} = {under_pct:5.1f}%')
        print(f'  Avg Error: {avg_error:.2f}')

    db.close()

if __name__ == '__main__':
    check_accuracy()
