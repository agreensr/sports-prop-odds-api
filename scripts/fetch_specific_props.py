#!/usr/bin/env python3
"""Fetch player props for specific games."""
import asyncio
import httpx
import os

api_key = os.getenv('THE_ODDS_API_KEY')
if not api_key:
    api_key = os.popen('grep THE_ODDS_API_KEY .env | cut -d= -f2').read().strip()

async def fetch_deep_props():
    async with httpx.AsyncClient() as client:
        # Nets @ Jazz
        games = [
            ('Nets @ Jazz', '10ead7795e4b1b32d519a992f558d7a4'),
            ('Pistons @ Warriors', 'cef1ef4d62f50297bf725501038c36e2')
        ]

        for name, game_id in games:
            print(f'\n{"=" * 60}')
            print(f'GAME: {name}')
            print(f'Event ID: {game_id}')
            print('=' * 60)

            props_url = f'https://api.the-odds-api.com/v4/sports/basketball_nba/events/{game_id}/odds'
            params = {
                'apiKey': api_key,
                'bookmakers': 'fanduel,draftkings,betmgm,pointsbet,caesars',
                'markets': 'player_points,player_rebounds,player_assists,player_threes'
            }

            resp = await client.get(props_url, params=params)

            if resp.status_code == 200:
                data = resp.json()

                if 'bookmakers' in data:
                    found_props = False
                    for bm in data['bookmakers']:
                        bm_key = bm.get('key')
                        print(f'\n--- Bookmaker: {bm_key} ---')

                        for market in bm.get('markets', []):
                            market_key = market.get('key')
                            outcomes = market.get('outcomes', [])

                            if outcomes:
                                print(f'  {market_key}: {len(outcomes)} props')
                                found_props = True

                                for outcome in outcomes[:10]:
                                    desc = outcome.get('description')
                                    price = outcome.get('price')
                                    point = outcome.get('point')
                                    print(f'    {desc} | Line: {point} | Price: {price}')

                    if not found_props:
                        print('\nNo player props found')
                else:
                    print(f'Unexpected response format')
                    print(f'Keys: {list(data.keys())}')
            else:
                print(f'Error: {resp.status_code}')
                print(resp.text[:300])

if __name__ == '__main__':
    asyncio.run(fetch_deep_props())
