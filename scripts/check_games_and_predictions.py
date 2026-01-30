"""Check games and their prediction counts."""
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from app.core.database import SessionLocal
from datetime import datetime, timedelta


async def check_games():
    """Check games and prediction counts."""
    db = SessionLocal()

    try:
        # Get all upcoming games
        result = db.execute(text("""
            SELECT g.id, g.external_id, g.away_team, g.home_team,
                   g.game_date, g.odds_api_event_id,
                   COUNT(p.id) as prediction_count
            FROM games g
            LEFT JOIN predictions p ON p.game_id = g.id
            WHERE g.game_date >= CURRENT_DATE
            GROUP BY g.id, g.external_id, g.away_team, g.home_team, g.game_date, g.odds_api_event_id
            ORDER BY g.game_date
        """))

        print("Upcoming Games and Prediction Counts:")
        print("=" * 80)
        for row in result:
            game_id, ext_id, away, home, game_date, odds_id, pred_count = row
            print(f"{away}@{home} | {ext_id} | {game_date.date()} | Predictions: {pred_count or 0}")
            print(f"  Game ID: {game_id}")
            print(f"  Odds Event ID: {odds_id}")
            print()

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(check_games())
