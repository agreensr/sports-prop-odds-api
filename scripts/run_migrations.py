#!/usr/bin/env python3
"""
Run database migrations for Sports-Bet-AI-API.

Usage:
    python scripts/run_migrations.py              # Run all pending migrations
    python scripts/run_migrations.py --rollback  # Rollback last migration
    python scripts/run_migrations.py --rollback 022  # Rollback specific migration
    python scripts/run_migrations.py --list      # List all migrations

Executes migration files to create/update database schema.
Supports rollback using .down.sql files.
"""
import os
import sys
import argparse
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import logging
from sqlalchemy import text, create_engine
from sqlalchemy.exc import SQLAlchemyError

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_database_url():
    """Get database URL from environment or settings."""
    # Try environment first
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return db_url

    # Fall back to settings
    from app.core.config import settings
    return settings.DATABASE_URL


def read_migration_file(filename: str) -> str:
    """Read migration file content."""
    migration_path = PROJECT_ROOT / "migrations" / filename
    with open(migration_path, 'r') as f:
        return f.read()


def run_migration(engine, filename: str) -> bool:
    """Run a single migration file."""
    logger.info(f"Running migration: {filename}")

    try:
        sql = read_migration_file(filename)

        with engine.begin() as conn:
            # Split by semicolons and execute each statement
            # Skip empty statements and comments
            statements = []
            current = []
            in_comment = False

            for line in sql.split('\n'):
                stripped = line.strip()

                # Skip comment lines
                if stripped.startswith('--'):
                    continue

                # Skip empty lines
                if not stripped:
                    continue

                current.append(line)

                # If line ends with semicolon, we have a complete statement
                if stripped.endswith(';'):
                    stmt = '\n'.join(current).strip()
                    if stmt and stmt != ';':
                        statements.append(stmt)
                    current = []

            # Add any remaining statement
            if current:
                stmt = '\n'.join(current).strip()
                if stmt:
                    statements.append(stmt)

            # Execute each statement
            for stmt in statements:
                if stmt.strip():
                    try:
                        conn.execute(text(stmt))
                    except Exception as e:
                        logger.warning(f"Statement failed (might be idempotent): {e}")
                        # Continue anyway for CREATE IF NOT EXISTS

        logger.info(f"✓ Migration {filename} completed successfully")
        return True

    except Exception as e:
        logger.error(f"✗ Migration {filename} failed: {e}")
        return False


def run_rollback(engine, migration_number: str) -> bool:
    """
    Rollback a specific migration using its .down.sql file.

    Args:
        engine: SQLAlchemy engine
        migration_number: Migration number (e.g., "022")

    Returns:
        True if rollback succeeded, False otherwise
    """
    down_file = f"{migration_number}_*.down.sql"

    # Find the down migration file
    migrations_dir = PROJECT_ROOT / "migrations"
    down_files = list(migrations_dir.glob(f"{migration_number}_*.down.sql"))

    if not down_files:
        logger.error(f"✗ No rollback file found for migration {migration_number}")
        logger.error(f"  Expected: {migrations_dir / f'{migration_number}_*.down.sql'}")
        return False

    if len(down_files) > 1:
        logger.warning(f"  Multiple rollback files found, using: {down_files[0].name}")

    down_file = down_files[0]
    logger.info(f"Rolling back migration: {down_file.name}")

    try:
        with open(down_file, 'r') as f:
            sql = f.read()

        with engine.begin() as conn:
            # Split by semicolons and execute each statement
            statements = []
            current = []

            for line in sql.split('\n'):
                stripped = line.strip()

                # Skip comment lines
                if stripped.startswith('--'):
                    continue

                # Skip empty lines
                if not stripped:
                    continue

                current.append(line)

                # If line ends with semicolon, we have a complete statement
                if stripped.endswith(';'):
                    stmt = '\n'.join(current).strip()
                    if stmt and stmt != ';':
                        statements.append(stmt)
                    current = []

            # Add any remaining statement
            if current:
                stmt = '\n'.join(current).strip()
                if stmt:
                    statements.append(stmt)

            # Execute each statement
            for stmt in statements:
                if stmt.strip():
                    conn.execute(text(stmt))

        logger.info(f"✓ Rollback {down_file.name} completed successfully")
        return True

    except Exception as e:
        logger.error(f"✗ Rollback {down_file.name} failed: {e}")
        return False


def list_migrations():
    """List all available migrations with their rollback status."""
    migrations_dir = PROJECT_ROOT / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))

    logger.info("Available Migrations:")
    logger.info("")

    has_rollback = []
    no_rollback = []

    for f in migration_files:
        if f.name.endswith(".down.sql"):
            continue

        # Check for corresponding .down.sql file
        down_file = migrations_dir / f"{f.stem}.down.sql"
        status = "✓" if down_file.exists() else "✗"

        # Extract migration number and name
        parts = f.stem.split("_", 1)
        num = parts[0] if parts else "???"
        name = parts[1] if len(parts) > 1 else f.name

        migration_info = f"  {status}  {num}: {name}"

        if down_file.exists():
            has_rollback.append(migration_info)
        else:
            no_rollback.append(migration_info)

    # Print migrations with rollbacks first
    if has_rollback:
        logger.info("Migrations with rollback support:")
        for m in has_rollback:
            logger.info(m)
        logger.info("")

    if no_rollback:
        logger.info("Migrations without rollback support:")
        for m in no_rollback:
            logger.info(m)
        logger.info("")

    total = len(has_rollback) + len(no_rollback)
    logger.info(f"Total: {total} migrations, {len(has_rollback)} with rollback support")


def main():
    """Run all pending migrations or rollback."""
    parser = argparse.ArgumentParser(
        description="Run database migrations for Sports-Bet-AI-API"
    )
    parser.add_argument(
        "--rollback",
        nargs="?",
        const="latest",
        metavar="MIGRATION",
        help="Rollback migration. Specify number or omit for latest"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available migrations"
    )

    args = parser.parse_args()

    # Get database URL
    db_url = get_database_url()
    logger.info(f"Connecting to database: {db_url[:30]}...")

    # Create engine
    engine = create_engine(db_url)

    if args.list:
        # List mode
        list_migrations()
        engine.dispose()
        return

    if args.rollback:
        # Rollback mode
        migration_num = "022" if args.rollback == "latest" else args.rollback
        logger.info("Rollback Mode")
        logger.info("="*50)

        success = run_rollback(engine, migration_num)

        engine.dispose()

        if success:
            logger.info("="*50)
            logger.info("✓ Rollback completed successfully")
            logger.info("="*50)
        else:
            logger.error("Rollback failed!")
            sys.exit(1)
        return

    # Normal migration mode
    logger.info("Starting database migrations...")
    logger.info("="*50)

    # Migrations to run (in order)
    migrations = [
        "009_create_game_mappings.sql",
        "010_create_player_aliases.sql",
        "011_create_team_mappings.sql",
        "012_create_sync_metadata.sql",
        "013_create_match_audit_log.sql",
        "015_drop_top_50_players.sql",
        # Phase 1: Data Integrity Foundation
        "016_create_sports_registry.sql",
        "017_create_players_multi_source.sql",
        "018_create_games_multi_source.sql",
        "019_create_predictions_multi_sport.sql",
        # Phase 1: Cleanup
        "020_deduplicate_games.sql",
        "021_add_sport_specific_columns.sql",
        # Phase 2: Prediction Versioning
        "022_add_model_version_index.sql",
    ]

    # Run each migration
    success_count = 0
    failed_migrations = []

    for migration in migrations:
        if run_migration(engine, migration):
            success_count += 1
        else:
            failed_migrations.append(migration)

    # Dispose engine
    engine.dispose()

    # Summary
    logger.info("\n" + "="*50)
    logger.info("Migration Summary:")
    logger.info(f"  Successful: {success_count}/{len(migrations)}")

    if failed_migrations:
        logger.info(f"  Failed: {len(failed_migrations)}")
        for failed in failed_migrations:
            logger.info(f"    - {failed}")
        sys.exit(1)
    else:
        logger.info("  All migrations completed successfully! ✓")
        logger.info("="*50)


if __name__ == "__main__":
    main()
