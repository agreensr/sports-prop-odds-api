#!/usr/bin/env python3
"""
Initialize database tables from SQLAlchemy models.

Creates all tables defined in the models using SQLAlchemy.
"""
import os
import sys
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Create all database tables from models."""
    from app.core.database import engine
    from app.models.nba.models import Base

    logger.info("Creating database tables from SQLAlchemy models...")

    # Create all tables
    Base.metadata.create_all(bind=engine, checkfirst=True)

    logger.info("✓ All database tables created successfully!")


if __name__ == "__main__":
    main()
