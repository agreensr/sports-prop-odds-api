#!/usr/bin/env python3
"""
Deduplicate Game Entries

This script fixes duplicate game entries caused by multiple data sources
(NBA API and TheOddsAPI) creating separate entries for the same matchup.

Strategy:
1. Keep NBA API game (external_id like '0022500661')
2. Move predictions from duplicate to correct game
3. Delete duplicate TheOddsAPI entries (external_id is hash-like)

Run: python scripts/deduplicate_games.py --dry-run  # Preview changes
     python scripts/deduplicate_games.py --execute  # Apply changes
"""
import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.absolute()))

try:
    from app.core.database import SessionLocal
except ImportError:
    # Fallback for VPS where path might differ
    import os
    sys.path.insert(0, os.path.expanduser("~/sports-bet-ai-api"))
    from app.core.database import SessionLocal
from app.models.nba.models import Game, Prediction
from collections import defaultdict
from sqlalchemy.orm import joinedload


def is_nba_api_id(external_id: str) -> bool:
    """Check if external_id is from NBA API (numeric format like '0022500661')."""
    return external_id and external_id.isdigit() and len(external_id) == 10


def scan_duplicates(db):
    """Scan for duplicate game entries."""
    games = db.query(Game).options(
        joinedload(Game.predictions)
    ).all()

    # Group by matchup + date
    matchup_groups = defaultdict(list)
    for g in games:
        date_key = str(g.game_date)[:10]
        key = f"{g.away_team}@{g.home_team}_{date_key}"
        matchup_groups[key].append(g)

    # Find duplicates
    duplicates = {k: v for k, v in matchup_groups.items() if len(v) > 1}

    return duplicates


def deduplicate_game_group(db, games_list, dry_run=True):
    """
    Deduplicate a group of games for the same matchup.

    Returns: dict with action taken and counts
    """
    # Sort games: NBA API first, then by creation date
    sorted_games = sorted(games_list, key=lambda g: (
        not is_nba_api_id(g.external_id),  # NBA API first
        g.created_at  # Oldest first
    ))

    keep_game = sorted_games[0]
    delete_games = sorted_games[1:]

    # Count predictions to move
    predictions_to_move = 0

    for game in delete_games:
        predictions_to_move += len(game.predictions)

    result = {
        "keep_game_id": keep_game.id,
        "keep_ext_id": keep_game.external_id,
        "delete_count": len(delete_games),
        "predictions_to_move": predictions_to_move,
        "action": "none"
    }

    if dry_run:
        result["action"] = "DRY RUN: Would delete duplicates and move data"
        return result

    # Move predictions to keep game
    for game in delete_games:
        for pred in game.predictions:
            pred.game_id = keep_game.id

    db.flush()  # Flush to update foreign keys

    # Delete duplicate games
    for game in delete_games:
        db.delete(game)

    db.commit()

    result["action"] = f"Deleted {len(delete_games)} duplicate(s), moved {predictions_to_move} predictions"
    return result


def main():
    parser = argparse.ArgumentParser(description="Deduplicate game entries")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    parser.add_argument("--execute", action="store_true", help="Apply deduplication changes")
    parser.add_argument("--stats", action="store_true", help="Show statistics only")

    args = parser.parse_args()

    if args.stats:
        args.dry_run = True

    db = SessionLocal()
    try:
        duplicates = scan_duplicates(db)

        print(f"🔍 Total games in database: {db.query(Game).count()}")
        print(f"🔍 Duplicate matchups found: {len(duplicates)}")
        print()

        if not duplicates:
            print("✅ No duplicates found!")
            return

        # Separate critical (with predictions) from non-critical
        critical = []
        non_critical = []

        for key, games_list in sorted(duplicates.items()):
            total_preds = sum(len(g.predictions) for g in games_list)
            if total_preds > 0:
                critical.append((key, games_list))
            else:
                non_critical.append((key, games_list))

        print(f"🚨 CRITICAL duplicates (with predictions): {len(critical)}")
        print(f"📝 Non-critical duplicates (no predictions): {len(non_critical)}")
        print()

        # Process critical duplicates
        if critical:
            print("=" * 80)
            print("CRITICAL DUPLICATES (require manual review)")
            print("=" * 80)
            print()

            for key, games_list in critical:
                print(f"🏀 {key}")
                for i, g in enumerate(games_list, 1):
                    source = "NBA API" if is_nba_api_id(g.external_id) else "TheOddsAPI"
                    pred_count = len(g.predictions)
                    print(f"  {i}. {g.external_id} ({source}) | Status: {g.status:12s} | Predictions: {pred_count}")
                print()

                if args.execute:
                    result = deduplicate_game_group(db, games_list, dry_run=False)
                    print(f"  ✅ {result['action']}")
                    print()

        # Process non-critical duplicates
        if non_critical:
            print("=" * 80)
            print("NON-CRITICAL DUPLICATES")
            print("=" * 80)
            print()

            for key, games_list in non_critical[:10]:  # Show first 10
                print(f"🏀 {key}")
                for i, g in enumerate(games_list, 1):
                    source = "NBA API" if is_nba_api_id(g.external_id) else "TheOddsAPI"
                    print(f"  {i}. {g.external_id} ({source}) | Status: {g.status}")
                print()

                if args.execute:
                    result = deduplicate_game_group(db, games_list, dry_run=False)
                    print(f"  ✅ {result['action']}")
                    print()

            if len(non_critical) > 10:
                print(f"... and {len(non_critical) - 10} more")
                print()

        if args.dry_run:
            print("=" * 80)
            print("DRY RUN COMPLETE - No changes made")
            print("Run with --execute to apply changes")
            print("=" * 80)
        elif args.execute:
            print("=" * 80)
            print("DEDUPLICATION COMPLETE")
            print("=" * 80)

    finally:
        db.close()


if __name__ == "__main__":
    main()
