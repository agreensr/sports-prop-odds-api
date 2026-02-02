"""Debug ESPN NHL API response structure."""
import asyncio
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.core.espn_service import ESPNApiService

async def debug_nhl():
    espn = ESPNApiService()

    # Get today's NHL games
    from datetime import datetime
    date_str = datetime.now().strftime('%Y%m%d')

    print(f"Fetching NHL games for {date_str}...")
    games = await espn.get_scores('nhl', date_str)

    print(f"\nGot {len(games)} games")

    if games:
        game = games[0]
        print(f"\n=== First game structure ===")
        print(f"Game keys: {list(game.keys())}")
        print(f"\nCompetitors type: {type(game.get('competitors'))}")
        print(f"Competitors: {json.dumps(game.get('competitors'), indent=2, default=str)}")

        # Check raw event if available
        if 'raw_data' in game:
            print(f"\n=== Raw data keys ===")
            print(f"Raw keys: {list(game['raw_data'].keys())}")

    await espn.close()

if __name__ == '__main__':
    asyncio.run(debug_nhl())
