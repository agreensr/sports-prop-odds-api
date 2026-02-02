"""Update remaining games with correct odds API event IDs."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from app.core.database import SessionLocal


def update_remaining_odds_ids():
    """Update remaining games with correct odds event IDs."""
    db = SessionLocal()

    # Correct mappings from Odds API
    correct_mappings = {
        ("MIL", "WAS"): "4329ccf40a387789800b68750d2cd999",
        ("HOU", "ATL"): "84dfdb778c615c186f3f82fd5373a505",
        ("MIA", "CHI"): "259e7b23b4050164ea05f0aa17fb58e2",
        ("CHA", "DAL"): "c58a236ed49b0f0020b8c38070b69346",
        ("BKN", "DEN"): "cdf18e4dea3608573bbe51f6bfb181f5",
    }

    try:
        for (away, home), event_id in correct_mappings.items():
            result = db.execute(text("""
                UPDATE games
                SET odds_api_event_id = :event_id,
                    updated_at = NOW()
                WHERE away_team = :away_team
                  AND home_team = :home_team
                  AND game_date >= CURRENT_DATE
            """), {
                "event_id": event_id,
                "away_team": away,
                "home_team": home
            })
            print(f"Updated {away}@{home}: {result.rowcount} rows, Event ID: {event_id}")

        db.commit()
        print("✅ Updated all remaining odds event IDs")

        # Show final state
        print("\nFinal odds_api_event_id mappings:")
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
    update_remaining_odds_ids()
