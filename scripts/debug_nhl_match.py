#!/usr/bin/env python3
"""
Debug NHL game matching between database and Odds API.
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


async def debug():
    db = next(get_db())

    # Get our games
    games = db.query(Game).filter(
        Game.status == 'scheduled',
        Game.game_date >= datetime.now()
    ).order_by(Game.game_date).limit(5).all()

    print('=== OUR NHL GAMES ===')
    for g in games:
        print(f'{g.away_team} @ {g.home_team} - {g.game_date}')

    # Get Odds API games
    odds_service = get_odds_service(api_key='8ad802abc3050bd7ff719830103602d6', sport='nhl')
    odds_games = await odds_service.get_upcoming_games_with_odds(days_ahead=3)

    print('\n=== ODDS API GAMES ===')
    for og in odds_games[:5]:
        print(f"{og.get('away_team')} @ {og.get('home_team')} - {og.get('commence_time')}")

    await odds_service.close()
    db.close()


if __name__ == "__main__":
    asyncio.run(debug())
