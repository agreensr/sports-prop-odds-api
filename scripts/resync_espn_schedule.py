"""
Fix NBA games timezone bug by deleting and resyncing with correct UTC times.

The bug: ESPN service was converting UTC to Central Time, then storing as UTC.
This caused game times to be 6 hours off when displayed.

Fix: ESPN service now returns UTC directly. This script:
1. Deletes all NBA games on/after 2026-01-29
2. Re-syncs from ESPN API with correct UTC times

Usage:
    python scripts/resync_espn_schedule.py
"""
import sys
import asyncio
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import and_
from app.core.database import SessionLocal
from app.services.core.espn_service import ESPNApiService
from app.models import Game


async def resync_schedule():
    """Delete and resync NBA games with correct UTC times."""
    db = SessionLocal()

    try:
        # Delete games from 2026-01-29 onwards (affected by the bug)
        cutoff_date = datetime(2026, 1, 29, 0, 0, 0)

        print(f"Deleting NBA games on/after {cutoff_date.date()}...")
        deleted = db.query(Game).filter(
            and_(
                Game.sport_id == 'nba',
                Game.game_date >= cutoff_date
            )
        ).delete()

        db.commit()
        print(f"Deleted {deleted} games")
        print()

        # Now sync from ESPN with the fixed service
        print("Syncing games from ESPN API...")
        service = ESPNApiService()

        # Get 7 days ahead
        games = await service.get_upcoming_games('nba', days_ahead=7)
        print(f"Fetched {len(games)} upcoming games from ESPN")
        print()

        # ESPN to NBA team abbreviation mapping (from sync_espn_schedule.py)
        ESPN_TO_NBA_TEAMS = {
            'ATL': 'ATL', 'BOS': 'BOS', 'BKN': 'BKN', 'CHA': 'CHA', 'CHI': 'CHI',
            'CLE': 'CLE', 'DAL': 'DAL', 'DEN': 'DEN', 'DET': 'DET', 'GSW': 'GSW',
            'HOU': 'HOU', 'IND': 'IND', 'LAC': 'LAC', 'LAL': 'LAL', 'MEM': 'MEM',
            'MIA': 'MIA', 'MIL': 'MIL', 'MIN': 'MIN', 'NOP': 'NOP', 'NYK': 'NYK',
            'OKC': 'OKC', 'ORL': 'ORL', 'PHI': 'PHI', 'PHX': 'PHX', 'POR': 'POR',
            'SAC': 'SAC', 'SAS': 'SAS', 'TOR': 'TOR', 'UTA': 'UTA', 'WAS': 'WAS',
            'SA': 'SAS', 'UTAH': 'UTA', 'NO': 'NOP', 'NY': 'NYK', 'GS': 'GSW',
        }

        def normalize_team_abbr(abbr: str) -> str:
            abbr = abbr.upper().strip()
            return ESPN_TO_NBA_TEAMS.get(abbr, abbr)

        created = 0
        for game_data in games:
            away_abbr = normalize_team_abbr(game_data.get('away_abbr', ''))
            home_abbr = normalize_team_abbr(game_data.get('home_abbr', ''))
            game_date = game_data.get('date')
            espn_id = game_data.get('id')

            if not away_abbr or not home_abbr or not game_date:
                continue

            # Create new game
            new_game = Game(
                id=f"espn_{espn_id}",
                sport_id='nba',
                external_id=str(espn_id),
                espn_game_id=str(espn_id),
                away_team=away_abbr,
                home_team=home_abbr,
                game_date=game_date,  # Now stored as UTC (not Central)
                status='scheduled',
                season=2025,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            db.add(new_game)
            created += 1

            # Display EST time for verification
            est_time = game_date - __import__('datetime').timedelta(hours=5)
            est_str = est_time.strftime('%Y-%m-%d %I:%M %p EST')
            print(f"  + {away_abbr} @ {home_abbr} | {est_str}")

        db.commit()
        print()
        print(f"Created {created} games with correct UTC times")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == '__main__':
    asyncio.run(resync_schedule())
