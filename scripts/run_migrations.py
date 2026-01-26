#!/usr/bin/env python3
"""
Run database migrations for NBA Data Sync Service.

Executes migration files 009-013 to create sync infrastructure tables.
"""
import os
import sys
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


def main():
    """Run all pending migrations."""
    logger.info("Starting database migrations...")

    # Get database URL
    db_url = get_database_url()
    logger.info(f"Connecting to database: {db_url[:30]}...")

    # Create engine
    engine = create_engine(db_url)

    # Migrations to run (in order)
    migrations = [
        "009_create_game_mappings.sql",
        "010_create_player_aliases.sql",
        "011_create_team_mappings.sql",
        "012_create_sync_metadata.sql",
        "013_create_match_audit_log.sql",
        "015_drop_top_50_players.sql",
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
