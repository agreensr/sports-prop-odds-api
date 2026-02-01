"""Poll for completed games and show accuracy progress."""
import time
import subprocess

print("Monitoring for completed games...")
print("Checking every 3 minutes for up to 30 minutes")
print()

for i in range(10):
    timestamp = subprocess.run(['ssh', 'sean-ubuntu-vps',
        'cd /home/sean/sports-bet-ai-api && source venv/bin/activate && python3 -c "import sys; sys.path.insert(0, "/home/sean/sports-bet-ai-api"); from app.core.database import SessionLocal; from app.models import Prediction; db = SessionLocal(); total = db.query(Prediction).filter(Prediction.bookmaker_line.isnot(None), Prediction.actual_value.isnot(None)).count(); over = db.query(Prediction).filter(Prediction.bookmaker_line.isnot(None), Prediction.actual_value.isnot(None), Prediction.recommendation == \"OVER\", Prediction.was_correct == True).count(); over_total = db.query(Prediction).filter(Prediction.bookmaker_line.isnot(None), Prediction.actual_value.isnot(None), Prediction.recommendation == \"OVER\").count(); under = db.query(Prediction).filter(Prediction.bookmaker_line.isnot(None), Prediction.actual_value.isnot(None), Prediction.recommendation == \"UNDER\", Prediction.was_correct == True).count(); under_total = db.query(Prediction).filter(Prediction.bookmaker_line.isnot(None), Prediction.actual_value.isnot(None), Prediction.recommendation == \"UNDER\").count(); print(f\"{total} resolved: OVER {over}/{over_total} ({100*over/over_total:.0f}%) | UNDER {under}/{under_total} ({100*under/under_total:.0f}%)\"); db.close()"'],
        capture_output=True, text=True).stdout.strip()

    check_time = subprocess.run(['date', '+%H:%M'], capture_output=True, text=True).stdout.strip()
    print(f"[{check_time}] {timestamp}")

    if i < 9:
        print("  Waiting 3 minutes...")
        time.sleep(180)
