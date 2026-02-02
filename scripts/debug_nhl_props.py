#!/usr/bin/env python3
"""
Debug NHL player props from Odds API.
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.nhl.models import Game
from app.services.core.odds_api_service import get_odds_service


async def debug_props():
    db = next(get_db())

    # Get a game with odds_event_id
    game = db.query(Game).filter(
        Game.status == 'scheduled',
        Game.odds_event_id.isnot(None)
    ).first()

    if not game:
        print("No games with odds_event_id found")
        db.close()
        return

    print(f"=== Game: {game.away_team} @ {game.home_team} ===")
    print(f"odds_event_id: {game.odds_event_id}")
    print(f"game_date: {game.game_date}")

    # Fetch player props from Odds API
    api_key = '8ad802abc3050bd7ff719830103602d6'
    odds_service = get_odds_service(api_key, sport="nhl")

    props = await odds_service.get_event_player_props(
        game.odds_event_id
    )

    print(f"\n=== Player Props Response ===")
    print(f"Type: {type(props)}")
    if isinstance(props, dict):
        print(f"Keys: {props.keys()}")

        if 'markets' in props:
            print(f"\nMarkets: {props['markets']}")

        if 'data' in props:
            print(f"\nData type: {type(props['data'])}")
            if isinstance(props['data'], list):
                print(f"Number of data items: {len(props['data'])}")
                for i, item in enumerate(props['data'][:3]):
                    print(f"\n  Item {i+1}:")
                    for k, v in item.items():
                        if k != 'outcomes':
                            print(f"    {k}: {v}")
                        else:
                            print(f"    outcomes: {len(v)} outcomes")
                            for outcome in v[:3]:
                                print(f"      - {outcome.get('name')}: {outcome.get('price')}")
            else:
                print(f"Data: {props['data']}")

        if 'error' in props:
            print(f"Error: {props['error']}")
        if 'message' in props:
            print(f"Message: {props['message']}")

    await odds_service.close()
    db.close()


if __name__ == "__main__":
    asyncio.run(debug_props())
