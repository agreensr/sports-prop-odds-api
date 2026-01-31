"""
Import Historical NBA Stats from ESPN API.

This script fetches historical boxscore data from ESPN for a specified date range
and imports player statistics into the database. This is useful for:
- Backfilling prediction accuracy data
- Training/calibrating the prediction model
- Analyzing historical trends

Usage:
    # Import last 7 days
    python scripts/import_historical_stats.py --days 7

    # Import specific date range
    python scripts/import_historical_stats.py --start-date 2026-01-20 --end-date 2026-01-27

    # Dry run (no database changes)
    python scripts/import_historical_stats.py --days 7 --dry-run
"""
import sys
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.core.database import SessionLocal
from app.models import Game, Player, PlayerStats
from app.services.core.espn_service import ESPNApiService
from app.services.nba.boxscore_import_service import BoxscoreImportService


class HistoricalStatsImporter:
    """Import historical stats from ESPN API."""

    def __init__(self, db: Session, dry_run: bool = False):
        self.db = db
        self.dry_run = dry_run
        self.espn_service = ESPNApiService()
        self.boxscore_service = BoxscoreImportService(db)

    async def import_date_range(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> dict:
        """
        Import stats for all games in a date range.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            Dictionary with import statistics
        """
        stats = {
            "days_processed": 0,
            "games_processed": 0,
            "games_skipped": 0,
            "player_stats_created": 0,
            "player_stats_updated": 0,
            "predictions_resolved": 0,
            "errors": []
        }

        current_date = start_date
        while current_date <= end_date:
            day_stats = await self.import_date(current_date)
            stats["days_processed"] += 1
            stats["games_processed"] += day_stats["games_processed"]
            stats["games_skipped"] += day_stats["games_skipped"]
            stats["player_stats_created"] += day_stats["player_stats_created"]
            stats["player_stats_updated"] += day_stats["player_stats_updated"]
            stats["predictions_resolved"] += day_stats["predictions_resolved"]
            stats["errors"].extend(day_stats.get("errors", []))

            current_date += timedelta(days=1)

        return stats

    async def import_date(self, date: datetime) -> dict:
        """
        Import stats for all games on a specific date.

        Args:
            date: Date to import

        Returns:
            Dictionary with day's statistics
        """
        date_str = date.strftime("%Y%m%d")
        print(f"\n{'='*60}")
        print(f"Importing stats for {date.strftime('%Y-%m-%d')}")
        print(f"{'='*60}")

        stats = {
            "games_processed": 0,
            "games_skipped": 0,
            "player_stats_created": 0,
            "player_stats_updated": 0,
            "predictions_resolved": 0,
            "errors": []
        }

        # Get games for this date from ESPN
        games_data = await self.espn_service.get_scoreboard(
            sport_id='nba',
            date=date_str
        )

        if not games_data:
            print(f"  No games found for {date_str}")
            return stats

        # Filter for completed games only
        completed_games = [g for g in games_data if g.get('status') in ['final', 'finished', 'post']]

        print(f"  Found {len(completed_games)} completed games (out of {len(games_data)} total)")

        for game_data in completed_games:
            espn_game_id = game_data.get('id')
            away_abbr = game_data.get('away_abbr')
            home_abbr = game_data.get('home_abbr')
            away_score = game_data.get('away_score')
            home_score = game_data.get('home_score')

            print(f"\n  {away_abbr} @ {home_abbr} ({away_score}-{home_score})")

            # Find or create game in database
            game = await self._get_or_create_game(game_data, date)

            if not game:
                print(f"    Skipped - could not find/create game")
                stats["games_skipped"] += 1
                continue

            # Import boxscore
            result = await self.boxscore_service._resolve_game(game, dry_run=self.dry_run)

            stats["games_processed"] += 1
            stats["player_stats_created"] += result.get("player_stats_created", 0)
            stats["player_stats_updated"] += result.get("player_stats_updated", 0)
            stats["predictions_resolved"] += result.get("predictions_resolved", 0)
            stats["errors"].extend(result.get("errors", []))

            if not self.dry_run:
                self.db.commit()

            print(f"    Stats created: {result.get('player_stats_created', 0)}, "
                  f"updated: {result.get('player_stats_updated', 0)}, "
                  f"predictions resolved: {result.get('predictions_resolved', 0)}")

        return stats

    async def _get_or_create_game(self, game_data: dict, game_date: datetime) -> Game:
        """Get existing game or create new one from ESPN data."""
        espn_id = game_data.get('id')
        away_abbr = game_data.get('away_abbr')
        home_abbr = game_data.get('home_abbr')

        # Try to find by ESPN ID
        game = self.db.query(Game).filter(
            Game.espn_game_id == str(espn_id)
        ).first()

        if game:
            # Update status if not final
            if game.status not in ['final', 'finished']:
                game.status = 'final'
                game.away_score = game_data.get('away_score')
                game.home_score = game_data.get('home_score')
            return game

        # Try to find by teams and date
        game = self.db.query(Game).filter(
            and_(
                Game.away_team == away_abbr,
                Game.home_team == home_abbr,
                Game.game_date >= game_date.replace(hour=0, minute=0, second=0),
                Game.game_date <= game_date.replace(hour=23, minute=59, second=59)
            )
        ).first()

        if game:
            # Update with ESPN ID
            game.espn_game_id = str(espn_id)
            game.status = 'final'
            game.away_score = game_data.get('away_score')
            game.home_score = game_data.get('home_score')
            return game

        # Create new game
        from app.models.unified import TEAM_ABBREVIATIONS

        # Normalize team abbreviations
        normalized_away = TEAM_ABBREVIATIONS.get(away_abbr, away_abbr)
        normalized_home = TEAM_ABBREVIATIONS.get(home_abbr, home_abbr)

        game = Game(
            id=f"espn_{espn_id}",
            sport_id='nba',
            external_id=str(espn_id),
            espn_game_id=str(espn_id),
            away_team=normalized_away,
            home_team=normalized_home,
            game_date=game_date,
            status='final',
            away_score=game_data.get('away_score'),
            home_score=game_data.get('home_score'),
            season=2025 if game_date.month < 10 else 2026,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        self.db.add(game)
        self.db.flush()

        print(f"    Created new game record: {game.id}")
        return game


async def main():
    parser = argparse.ArgumentParser(description="Import historical NBA stats from ESPN API")
    parser.add_argument('--days', type=int, default=7,
                        help='Number of past days to import (default: 7)')
    parser.add_argument('--start-date', type=str,
                        help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str,
                        help='End date (YYYY-MM-DD, default: today)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Simulate without making database changes')

    args = parser.parse_args()

    # Determine date range
    if args.start_date:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
    else:
        start_date = datetime.now() - timedelta(days=args.days)

    if args.end_date:
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
    else:
        end_date = datetime.now()

    # Ensure dates are timezone-aware
    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)

    print("="*60)
    print("HISTORICAL STATS IMPORTER")
    print("="*60)
    print(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"Days: {(end_date - start_date).days + 1}")
    print(f"Dry run: {args.dry_run}")
    print()

    db = SessionLocal()
    try:
        importer = HistoricalStatsImporter(db, dry_run=args.dry_run)

        stats = await importer.import_date_range(start_date, end_date)

        print()
        print("="*60)
        print("IMPORT SUMMARY")
        print("="*60)
        print(f"Days processed:     {stats['days_processed']}")
        print(f"Games processed:    {stats['games_processed']}")
        print(f"Games skipped:      {stats['games_skipped']}")
        print(f"Player stats created: {stats['player_stats_created']}")
        print(f"Player stats updated: {stats['player_stats_updated']}")
        print(f"Predictions resolved: {stats['predictions_resolved']}")

        if stats.get('errors'):
            print()
            print(f"Errors: {len(stats['errors'])}")
            for error in stats['errors'][:10]:
                print(f"  - {error}")

        if not args.dry_run:
            db.commit()

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
