"""Debug ESPN status values."""
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.core.espn_service import ESPNApiService

async def check():
    espn = ESPNApiService()
    games = await espn.get_scores('nba', '20260130')
    print(f'Total games: {len(games)}')
    statuses = sorted(set(g.get('status', 'unknown') for g in games))
    print('Statuses:', statuses)
    for g in games[:10]:
        print(f"  {g.get('away_abbr')} @ {g.get('home_abbr')}: status={g.get('status')}, scores={g.get('home_score')}-{g.get('away_score')}")

asyncio.run(check())
