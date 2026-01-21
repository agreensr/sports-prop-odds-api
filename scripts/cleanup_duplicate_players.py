#!/usr/bin/env python3
"""
Clean up duplicate players in the database.

Removes ESPN-sourced player entries when NBA.com versions exist.
Preserves prediction data by keeping players with predictions.
"""
import os
import sys

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def find_duplicates(session: Session):
    """Find duplicate players (same name + team, different IDs)."""
    query = text("""
        SELECT
            LOWER(name) as name_lower,
            LOWER(team) as team_lower,
            string_agg(id, ',') as all_ids,
            string_agg(external_id, ',') as all_external_ids,
            string_agg(id_source, ',') as all_id_sources,
            string_agg(id || '|' || external_id || '|' || id_source || '|' ||
                       coalesce((SELECT count(*)::text FROM predictions WHERE player_id = players.id), '0'), ',')
                as player_details,
            count(*) as count
        FROM players
        GROUP BY LOWER(name), LOWER(team)
        HAVING count(*) > 1
        ORDER BY LOWER(name)
    """)
    return session.execute(query).fetchall()


def get_player_details(session: Session, player_ids: list) -> list:
    """Get detailed info for specific player IDs."""
    placeholders = ','.join([f"'{pid}'" for pid in player_ids])
    query = text(f"""
        SELECT id, external_id, name, team, id_source,
               (SELECT count(*) FROM predictions WHERE player_id = players.id) as prediction_count
        FROM players
        WHERE id IN ({placeholders})
        ORDER BY prediction_count DESC, id_source DESC
    """)
    return session.execute(query).fetchall()


def cleanup_duplicates(session: Session, dry_run: bool = True):
    """Remove duplicate players, keeping NBA versions and those with predictions."""
    duplicates = find_duplicates(session)

    stats = {
        "total_duplicates": len(duplicates),
        "players_to_delete": 0,
        "players_kept": 0,
        "predictions_preserved": 0
    }

    logger.info(f"Found {len(duplicates)} duplicate player groups")

    for dup in duplicates:
        name_lower = dup[0]
        team_lower = dup[1]
        player_details = dup[5].split(',')
        count = dup[6]

        # Parse player details
        players = []
        for detail in player_details:
            player_id, external_id, id_source, pred_count = detail.split('|')
            players.append({
                'id': player_id,
                'external_id': external_id,
                'id_source': id_source,
                'prediction_count': int(pred_count)
            })

        # Sort by: has predictions first, then NBA source first
        players.sort(key=lambda p: (p['prediction_count'] == 0, p['id_source'] != 'nba'))

        keep = players[0]
        to_delete = players[1:]

        pred_count = keep['prediction_count']
        logger.info(f"\n{'DRY RUN' if dry_run else 'CLEANING'}: {name_lower} ({team_lower})")
        logger.info(f"  KEEP: {keep['external_id']} [{keep['id_source']}] - {pred_count} predictions")

        for delete in to_delete:
            delete_pred = delete['prediction_count']
            logger.info(f"  DELETE: {delete['external_id']} [{delete['id_source']}] - {delete_pred} predictions")

            if not dry_run:
                session.execute(text(f"DELETE FROM players WHERE id = '{delete['id']}'"))
                stats["players_to_delete"] += 1

        stats["players_kept"] += 1
        stats["predictions_preserved"] += pred_count

    if not dry_run:
        session.commit()
        logger.info(f"\n✅ Cleanup complete!")

    return stats


def show_summary(session: Session):
    """Show duplicate summary without cleanup."""
    duplicates = find_duplicates(session)

    print(f"\n{'='*60}")
    print(f"DUPLICATE PLAYER SUMMARY")
    print(f"{'='*60}\n")

    total_players = session.execute(text("SELECT count(*) FROM players")).scalar()
    print(f"Total players in database: {total_players}")
    print(f"Duplicate groups found: {len(duplicates)}\n")

    for dup in duplicates:
        name_lower = dup[0]
        team_lower = dup[1]
        player_details = dup[5].split(',')

        print(f"{name_lower} ({team_lower}):")
        for detail in player_details:
            player_id, external_id, id_source, pred_count = detail.split('|')
            pred_count = int(pred_count)
            pred_str = f"{pred_count} predictions" if pred_count > 0 else "no predictions"
            marker = "⭐" if id_source == "nba" else "  "
            print(f"  {marker} {external_id} [{id_source}] - {pred_str}")
        print()


def main():
    """Main cleanup function."""
    print("="*60)
    print("Duplicate Player Cleanup Script")
    print("="*60)
    print()

    # Create database session
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        # Show summary first
        show_summary(session)

        # Prompt for action
        print("\nOptions:")
        print("  1. Dry run cleanup (show what would be deleted)")
        print("  2. Perform cleanup (delete duplicates)")
        print("  3. Exit without changes")
        print()

        choice = input("Choose option (1/2/3): ").strip()

        if choice == "1":
            print("\n" + "="*60)
            print("DRY RUN - No changes will be made")
            print("="*60)
            stats = cleanup_duplicates(session, dry_run=True)

            print(f"\n{'='*60}")
            print("DRY RUN SUMMARY")
            print(f"{'='*60}")
            print(f"Duplicate groups: {stats['total_duplicates']}")
            print(f"Players to delete: {stats['players_to_delete']}")
            print(f"Players to keep: {stats['players_kept']}")
            print(f"Predictions preserved: {stats['predictions_preserved']}")

        elif choice == "2":
            confirm = input("\n⚠️  This will permanently delete duplicate players. Type 'yes' to confirm: ")
            if confirm.lower() == "yes":
                stats = cleanup_duplicates(session, dry_run=False)

                print(f"\n{'='*60}")
                print("CLEANUP SUMMARY")
                print(f"{'='*60}")
                print(f"Duplicate groups: {stats['total_duplicates']}")
                print(f"Players deleted: {stats['players_to_delete']}")
                print(f"Players kept: {stats['players_kept']}")
                print(f"Predictions preserved: {stats['predictions_preserved']}")

                # Verify final counts
                final_count = session.execute(text("SELECT count(*) FROM players")).scalar()
                print(f"\nFinal player count: {final_count}")
            else:
                print("Cleanup cancelled.")

        else:
            print("Exiting without changes.")

    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        session.rollback()
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
