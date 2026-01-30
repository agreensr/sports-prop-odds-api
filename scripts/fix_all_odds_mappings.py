"""Fix all incorrect odds_api_event_id mappings and clear problematic entries."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from app.core.database import SessionLocal


def fix_all_odds_mappings():
    """Fix all odds event ID mappings."""
    db = SessionLocal()

    try:
        # 1. Clear the problematic event ID from all games except the correct one
        # The event ID 5dcf2dc23993f2a3e4cffc2b47b635e7 is for SAC@PHI
        result = db.execute(text("""
            UPDATE games
            SET odds_api_event_id = NULL,
                updated_at = NOW()
            WHERE odds_api_event_id = '5dcf2dc23993f2a3e4cffc2b47b635e7'
              AND NOT (away_team = 'SAC' AND home_team = 'PHI')
        """))
        print(f"Cleared wrong event ID from {result.rowcount} games")

        # 2. Set correct odds event ID for SAC@PHI
        result = db.execute(text("""
            UPDATE games
            SET odds_api_event_id = '5dcf2dc23993f2a3e4cffc2b47b635e7',
                updated_at = NOW()
            WHERE away_team = 'SAC' AND home_team = 'PHI'
              AND game_date >= CURRENT_DATE
        """))
        print(f"Set correct event ID for SAC@PHI: {result.rowcount} rows")

        # 3. Clear invalid internal game IDs from the odds_api_event_id column
        result = db.execute(text("""
            UPDATE games
            SET odds_api_event_id = NULL,
                updated_at = NOW()
            WHERE odds_api_event_id LIKE 'lal-gsw-%'
        """))
        print(f"Cleared internal game IDs from odds_api_event_id: {result.rowcount} rows")

        db.commit()
        print("✅ Fixed all odds mappings")

        # Show current state
        print("\nCurrent odds_api_event_id mappings:")
        result = db.execute(text("""
            SELECT external_id, away_team, home_team,
                   game_date::date, odds_api_event_id
            FROM games
            WHERE game_date >= CURRENT_DATE
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
    fix_all_odds_mappings()
