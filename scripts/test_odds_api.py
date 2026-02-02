"""Test Odds API integration."""
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.core.odds_api_service import OddsApiService

async def test():
    api_key = '8ad802abc3050bd7ff719830103602d6'
    odds = OddsApiService(api_key)

    # Get upcoming games with odds
    print("Fetching upcoming games from Odds API...")
    games = await odds.get_upcoming_games_with_odds('basketball_nba')
    print(f'Got {len(games)} upcoming games')

    if games:
        for g in games[:5]:
            home = g.get('home_team')
            away = g.get('away_team')
            eid = g.get('id')
            print(f"  Event: {eid} | {away} @ {home}")

        # Try to get player props for first game
        if games and games[0].get('id'):
            event_id = games[0]['id']
            print(f'\nFetching player props for event {event_id}...')
            props = await odds.get_event_player_props(event_id)
            print(f'Props response keys: {list(props.keys())}')

            # Check for player points
            if 'data' in props:
                data = props['data']
                bookmakers = data.get('bookmakers', [])
                print(f'  Bookmakers: {len(bookmakers)}')

                for bm in bookmakers[:2]:
                    bm_title = bm.get('title', 'Unknown')
                    print(f'  {bm_title} markets:')
                    for market in bm.get('markets', [])[:3]:
                        mkey = market.get('key')
                        print(f'    - {mkey}')

    # Check quota
    print(f'\nQuota Status:')
    print(f'  Remaining: {odds._requests_remaining}')
    print(f'  Used: {odds._requests_used}')

    await odds.close()

if __name__ == '__main__':
    asyncio.run(test())
