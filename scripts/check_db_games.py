"""Check games stored in database for today."""
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal
from datetime import datetime, timedelta, timezone
from sqlalchemy import text

db = SessionLocal()

# Check today's games in database
today = datetime.now().strftime('%Y-%m-%d')
result = db.execute(text('''
    SELECT id, away_team, home_team, game_date, status, espn_id
    FROM games
    WHERE DATE(game_date) = :today
    ORDER BY game_date
'''), {'today': today})

rows = result.fetchall()
print(f'Database games for {today}:')
print()

for row in rows:
    espn_id = row[0]
    away = row[1]
    home = row[2]
    game_date = row[3]
    status = row[4]

    # Convert to EST for display
    if game_date:
        est_time = game_date - timedelta(hours=5)
        est_str = est_time.strftime('%Y-%m-%d %I:%M %p EST')
        utc_str = game_date.strftime('%Y-%m-%d %H:%M:%S UTC')
    else:
        est_str = 'N/A'
        utc_str = 'N/A'

    print(f'{espn_id}: {away} @ {home}')
    print(f'  UTC: {utc_str}')
    print(f'  EST: {est_str}')
    print(f'  Status: {status}')
    print()

db.close()
