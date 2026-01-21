#!/usr/bin/env python3
"""
Simplified NBA Migration Script (Schema Only)

Migrates the database from ESPN to NBA.com:
1. Adds id_source columns to players and games tables
2. Adds odds pricing columns to predictions table
3. Creates game_odds table

IMPORTANT: This script will modify your database schema.
Backup your database before running!
"""
import os
import sys
from datetime import datetime

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_backup_command(db_url: str) -> str:
    """Generate backup command based on database URL."""
    if "postgresql://" in db_url:
        db_name = db_url.rstrip("/").split("/")[-1]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"pg_dump -Fc {db_name} > /backups/pre_nba_migration_{timestamp}.dump"
    return "# Backup command not available for this database type"


def add_id_source_columns(session: Session) -> bool:
    """
    Add id_source columns to players and games tables.

    Returns True if successful, False otherwise.
    """
    try:
        logger.info("Adding id_source columns to players and games tables...")

        # Check if columns already exist
        result = session.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'players' AND column_name = 'id_source'
        """)).fetchone()

        if result:
            logger.info("id_source column already exists in players table")
        else:
            # Add id_source to players
            session.execute(text("""
                ALTER TABLE players ADD COLUMN id_source VARCHAR(10) DEFAULT 'espn'
            """))
            session.execute(text("""
                CREATE INDEX ix_players_id_source ON players(id_source)
            """))
            logger.info("Added id_source column to players table")

        result = session.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'games' AND column_name = 'id_source'
        """)).fetchone()

        if result:
            logger.info("id_source column already exists in games table")
        else:
            # Add id_source to games
            session.execute(text("""
                ALTER TABLE games ADD COLUMN id_source VARCHAR(10) DEFAULT 'espn'
            """))
            session.execute(text("""
                CREATE INDEX ix_games_id_source ON games(id_source)
            """))
            logger.info("Added id_source column to games table")

        session.commit()
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error adding id_source columns: {e}")
        return False


def add_odds_columns(session: Session) -> bool:
    """
    Add odds pricing columns to predictions table.

    Returns True if successful, False otherwise.
    """
    try:
        logger.info("Adding odds pricing columns to predictions table...")

        columns_to_add = [
            ("over_price", "FLOAT"),
            ("under_price", "FLOAT"),
            ("odds_fetched_at", "TIMESTAMP"),
            ("odds_last_updated", "TIMESTAMP")
        ]

        for col_name, col_type in columns_to_add:
            result = session.execute(text(f"""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'predictions' AND column_name = '{col_name}'
            """)).fetchone()

            if not result:
                session.execute(text(f"""
                    ALTER TABLE predictions ADD COLUMN {col_name} {col_type}
                """))
                logger.info(f"Added {col_name} column to predictions table")

        # Create index for odds_last_updated
        result = session.execute(text("""
            SELECT indexname FROM pg_indexes
            WHERE indexname = 'ix_predictions_odds_last_updated'
        """)).fetchone()

        if not result:
            session.execute(text("""
                CREATE INDEX ix_predictions_odds_last_updated ON predictions(odds_last_updated)
            """))
            logger.info("Created index on odds_last_updated")

        session.commit()
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error adding odds columns: {e}")
        return False


def create_game_odds_table(session: Session) -> bool:
    """
    Create game_odds table.

    Returns True if successful, False otherwise.
    """
    try:
        logger.info("Creating game_odds table...")

        # Check if table exists
        result = session.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_name = 'game_odds'
        """)).fetchone()

        if result:
            logger.info("game_odds table already exists")
            return True

        session.execute(text("""
            CREATE TABLE game_odds (
                id VARCHAR(36) PRIMARY KEY,
                game_id VARCHAR(36) NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                bookmaker_key VARCHAR(50) NOT NULL,
                bookmaker_title VARCHAR(100) NOT NULL,
                home_moneyline FLOAT,
                away_moneyline FLOAT,
                home_spread_point FLOAT,
                home_spread_price FLOAT,
                away_spread_point FLOAT,
                away_spread_price FLOAT,
                totals_point FLOAT,
                over_price FLOAT,
                under_price FLOAT,
                last_update TIMESTAMP NOT NULL,
                created_at TIMESTAMP NOT NULL
            )
        """))

        # Create indexes
        session.execute(text("""
            CREATE INDEX ix_game_odds_game_id ON game_odds(game_id)
        """))
        session.execute(text("""
            CREATE INDEX ix_game_odds_bookmaker ON game_odds(bookmaker_key)
        """))
        session.execute(text("""
            CREATE INDEX ix_game_odds_last_update ON game_odds(last_update)
        """))

        session.commit()
        logger.info("Created game_odds table successfully")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error creating game_odds table: {e}")
        return False


def validate_migration(session: Session) -> dict:
    """
    Validate the migration and return statistics.

    Returns dictionary with validation results.
    """
    logger.info("Validating migration...")

    # Check players table
    total_players = session.execute(text("SELECT COUNT(*) FROM players")).scalar()
    nba_players = session.execute(text("SELECT COUNT(*) FROM players WHERE id_source = 'nba'")).scalar()
    espn_players = session.execute(text("SELECT COUNT(*) FROM players WHERE id_source = 'espn'")).scalar()

    # Check games table
    total_games = session.execute(text("SELECT COUNT(*) FROM games")).scalar()
    nba_games = session.execute(text("SELECT COUNT(*) FROM games WHERE id_source = 'nba'")).scalar()
    espn_games = session.execute(text("SELECT COUNT(*) FROM games WHERE id_source = 'espn'")).scalar()

    # Check predictions table for orphaned records
    orphaned_predictions = session.execute(text("""
        SELECT COUNT(*) FROM predictions pred
        JOIN players p ON pred.player_id = p.id
        WHERE p.id_source = 'espn'
    """)).scalar()

    stats = {
        "players": {
            "total": total_players,
            "nba_source": nba_players,
            "espn_source": espn_players,
            "match_rate": f"{(nba_players / total_players * 100):.1f}%" if total_players > 0 else "N/A"
        },
        "games": {
            "total": total_games,
            "nba_source": nba_games,
            "espn_source": espn_games
        },
        "predictions": {
            "orphaned_espn": orphaned_predictions
        }
    }

    return stats


def main():
    """Main migration function."""
    print("=" * 60)
    print("NBA Migration Script (Schema Only)")
    print("=" * 60)
    print()
    print("⚠️  WARNING: This will modify your database schema!")
    print("⚠️  Make sure to backup your database before proceeding.")
    print()

    # Show backup command
    backup_cmd = get_backup_command(settings.DATABASE_URL)
    print(f"💾 Backup command:")
    print(f"   {backup_cmd}")
    print()

    # Prompt for confirmation
    response = input("Do you want to proceed? (yes/no): ")
    if response.lower() != "yes":
        print("Migration cancelled.")
        sys.exit(0)

    print()
    print("Starting migration...")
    print("-" * 60)

    # Create database session
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        # Step 1: Add id_source columns
        print()
        print("Step 1/4: Adding id_source columns...")
        if not add_id_source_columns(session):
            print("❌ Failed to add id_source columns")
            sys.exit(1)
        print("✅ Step 1 completed")

        # Step 2: Add odds columns
        print()
        print("Step 2/4: Adding odds pricing columns...")
        if not add_odds_columns(session):
            print("❌ Failed to add odds columns")
            sys.exit(1)
        print("✅ Step 2 completed")

        # Step 3: Create game_odds table
        print()
        print("Step 3/4: Creating game_odds table...")
        if not create_game_odds_table(session):
            print("❌ Failed to create game_odds table")
            sys.exit(1)
        print("✅ Step 3 completed")

        # Step 4: Validate migration
        print()
        print("Step 4/4: Validating migration...")
        stats = validate_migration(session)
        print("✅ Step 4 completed")

        # Print results
        print()
        print("=" * 60)
        print("MIGRATION COMPLETE!")
        print("=" * 60)
        print()
        print("Statistics:")
        print(f"  Players: {stats['players']['total']} total")
        print(f"    - NBA source: {stats['players']['nba_source']} ({stats['players']['match_rate']})")
        print(f"    - ESPN source: {stats['players']['espn_source']}")
        print()
        print(f"  Games: {stats['games']['total']} total")
        print(f"    - NBA source: {stats['games']['nba_source']}")
        print(f"    - ESPN source: {stats['games']['espn_source']}")
        print()
        print(f"  Predictions with ESPN players: {stats['predictions']['orphaned_espn']}")
        print()

        print("Next steps:")
        print("  1. Install nba_api: pip install nba_api>=1.4.1")
        print("  2. Restart the API service")
        print("  3. Test the new endpoints:")
        print("     - curl http://localhost:8001/api/players/search?name=lebron")
        print("     - curl http://localhost:8001/api/players/nba/2544")
        print("  4. Use POST /api/data/fetch/players to import NBA players")
        print("     which will update player IDs to NBA.com format")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
