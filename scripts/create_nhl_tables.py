#!/usr/bin/env python3
"""
Create NHL tables in the database.

Run this on the VPS to set up the NHL-specific tables.
"""
import os
import sys
from sqlalchemy import create_engine

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import models after path setup
from app.models.nhl.models import Base

# Database connection (via Docker port mapping)
DB_URL = "postgresql://postgres:nba_secure_pass_2026@localhost:5433/nba_props"

def main():
    print(f"Connecting to database: nba_props")

    # Create engine
    engine = create_engine(DB_URL, echo=True)

    # Create NHL tables
    print("\n=== Creating NHL tables ===")
    Base.metadata.create_all(bind=engine, checkfirst=True)

    print("\n=== NHL tables created successfully ===")

    # List created tables
    with engine.connect() as conn:
        result = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'nhl_%' ORDER BY tablename"
        )
        tables = [row[0] for row in result]
        print(f"\nCreated {len(tables)} NHL tables:")
        for table in tables:
            print(f"  - {table}")

    engine.dispose()

if __name__ == "__main__":
    main()
