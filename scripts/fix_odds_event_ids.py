"""Fix incorrect odds_api_event_id mappings in the games table.

The sync process incorrectly mapped SAC@PHI event ID to DET@PHX and OKC@MIN games.
This script updates them with the correct event IDs from the Odds API.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from app.core.database import SessionLocal


async def fix_odds_event_ids():
    """Fix the incorrect odds_api_event_id values."""
    db = SessionLocal()

    try:
        # Correct event IDs from Odds API
        correct_mappings = {
            # DET @ PHX should use this event ID (not SAC@PHI)
            ("DET", "PHX"): "0c174f6428575aa93dadc9a2ea7bb3a7",
            # OKC @ MIN should use this event ID
            ("OKC", "MIN"): "6f87ca60fa0d3ec900b23a3e1d2fb336",
        }

        # Update DET @ PHX
        result = db.execute(text("""
            UPDATE games
            SET odds_api_event_id = :event_id,
                updated_at = NOW()
            WHERE away_team = :away_team
              AND home_team = :home_team
              AND game_date >= CURRENT_DATE
        """), {
            "event_id": correct_mappings[("DET", "PHX")],
            "away_team": "DET",
            "home_team": "PHX"
        })
        print(f"Updated DET@PHX: {result.rowcount} rows")

        # Update OKC @ MIN
        result = db.execute(text("""
            UPDATE games
            SET odds_api_event_id = :event_id,
                updated_at = NOW()
            WHERE away_team = :away_team
              AND home_team = :home_team
              AND game_date >= CURRENT_DATE
        """), {
            "event_id": correct_mappings[("OKC", "MIN")],
            "away_team": "OKC",
            "home_team": "MIN"
        })
        print(f"Updated OKC@MIN: {result.rowcount} rows")

        # Clear the wrong event ID from any other games
        result = db.execute(text("""
            UPDATE games
            SET odds_api_event_id = NULL,
                updated_at = NOW()
            WHERE odds_api_event_id = :wrong_event_id
              AND away_team NOT IN ('SAC', 'PHI')
        """), {"wrong_event_id": "5dcf2dc23993f2a3e4cffc2b47b635e7"})
        print(f"Cleared wrong event ID from: {result.rowcount} rows")

        db.commit()
        print("✅ Fixed odds_api_event_id mappings")

        # Show current state
        print("\nCurrent games with odds_api_event_id:")
        result = db.execute(text("""
            SELECT external_id, away_team, home_team,
                   game_date::date, odds_api_event_id
            FROM games
            WHERE game_date >= CURRENT_DATE
              AND odds_api_event_id IS NOT NULL
            ORDER BY game_date
        """))
        for row in result:
            print(f"  {row[0]} | {row[1]}@{row[2]} | {row[3]} | {row[4]}")

    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(fix_odds_event_ids())
