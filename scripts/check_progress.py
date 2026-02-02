import sys
sys.path.insert(0, '/home/sean/sports-bet-ai-api')

from app.core.database import SessionLocal
from app.models import Prediction

db = SessionLocal()

resolved = db.query(Prediction).filter(
    Prediction.bookmaker_line.isnot(None),
    Prediction.actual_value.isnot(None)
).order_by(Prediction.actuals_resolved_at.desc()).all()

print(f'Total resolved with bookmaker_line: {len(resolved)}')

over_wins = sum(1 for p in resolved if p.recommendation == 'OVER' and p.was_correct)
over_total = sum(1 for p in resolved if p.recommendation == 'OVER')
under_wins = sum(1 for p in resolved if p.recommendation == 'UNDER' and p.was_correct)
under_total = sum(1 for p in resolved if p.recommendation == 'UNDER')

print(f'OVER: {over_wins}/{over_total} = {100*over_wins/over_total:.1f}%')
print(f'UNDER: {under_wins}/{under_total} = {100*under_wins/under_total:.1f}%')

db.close()
