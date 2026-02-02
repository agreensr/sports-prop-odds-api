"""
Database configuration and session management.
"""
import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

# Create engine when module loads using settings.DATABASE_URL
from app.core.config import settings

DATABASE_URL = settings.DATABASE_URL

# Create engine with connection pooling
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before using
    echo=os.getenv("SQL_ECHO", "false").lower() == "true"
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency that provides a database session.

    Usage in FastAPI:
    ```python
    @router.get("/endpoint")
    def endpoint(db: Session = Depends(get_db)):
        # Use db here
        pass
    ```
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    from app.models import Base
    # checkfirst=True will only create tables that don't exist
    Base.metadata.create_all(bind=engine, checkfirst=True)
