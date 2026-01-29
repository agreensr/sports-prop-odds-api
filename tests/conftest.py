"""Shared pytest fixtures for sports-bet-ai-api tests."""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta, date
from typing import AsyncGenerator, Generator
import uuid
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from httpx import AsyncClient, ASGITransport

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Create fresh test database session with isolated in-memory database."""
    from app.models.unified import Base
    from app.models import Sport

    # Use shared cache for in-memory database to allow multiple connections
    # to see the same data. This is needed because TestClient may create
    # additional connections when processing requests.
    # See: https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#sqlite-foreign-keys
    engine = create_engine(
        "sqlite:///:memory:?cache=shared",
        connect_args={"check_same_thread": False}
    )

    # Create all tables - use checkfirst to handle repeated calls
    # In SQLite, CREATE TABLE IF NOT EXISTS handles this, but indexes don't
    # So we use try/except for index creation
    try:
        Base.metadata.create_all(bind=engine, checkfirst=True)
    except Exception as e:
        # Ignore duplicate index/index already exists errors
        if "already exists" not in str(e).lower() and "duplicate" not in str(e).lower():
            raise

    # Create session
    TestSessionLocal = sessionmaker(bind=engine)
    session = TestSessionLocal()

    # Initialize sport registry
    for sport_id, name in [("nba", "NBA"), ("nfl", "NFL"), ("mlb", "MLB"), ("nhl", "NHL")]:
        sport = Sport(
            id=sport_id,
            name=name,
            active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        session.add(sport)
    session.commit()

    yield session

    session.close()
    engine.dispose()


@pytest.fixture(scope="function")
async def async_client(db_session: Session) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for testing FastAPI endpoints."""
    from app.main import app
    from app.core.database import get_db

    # Override database dependency to use test session
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def sample_team_mappings(db_session: Session):
    """Create sample team mappings for testing."""
    from app.models import TeamMapping

    teams = [
        TeamMapping(
            id=str(uuid.uuid4()),
            nba_team_id=1610612738,
            nba_abbreviation="BOS",
            nba_full_name="Boston Celtics",
            nba_city="Boston",
            odds_api_name="Boston Celtics",
            odds_api_key="bostonceltics",
            alternate_names=json.dumps(["BOS", "Celtics", "Boston"]),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        ),
        TeamMapping(
            id=str(uuid.uuid4()),
            nba_team_id=1610612755,
            nba_abbreviation="PHI",
            nba_full_name="Philadelphia 76ers",
            nba_city="Philadelphia",
            odds_api_name="Philadelphia 76ers",
            odds_api_key="philadelphia76ers",
            alternate_names=json.dumps(["PHI", "76ers", "Philadelphia"]),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        ),
        TeamMapping(
            id=str(uuid.uuid4()),
            nba_team_id=1610612744,
            nba_abbreviation="GSW",
            nba_full_name="Golden State Warriors",
            nba_city="Golden State",
            odds_api_name="Golden State Warriors",
            odds_api_key="goldenstatewarriors",
            alternate_names=json.dumps(["GSW", "Warriors", "Golden State"]),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        ),
        TeamMapping(
            id=str(uuid.uuid4()),
            nba_team_id=1610612747,
            nba_abbreviation="LAL",
            nba_full_name="Los Angeles Lakers",
            nba_city="Los Angeles",
            odds_api_name="Los Angeles Lakers",
            odds_api_key="losangeleslakers",
            alternate_names=json.dumps(["LAL", "Lakers", "Los Angeles"]),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        ),
    ]

    for team in teams:
        db_session.add(team)
    db_session.commit()

    return teams


@pytest.fixture
def sample_player_aliases(db_session: Session):
    """Create sample player aliases for testing."""
    from app.models import PlayerAlias

    aliases = [
        PlayerAlias(
            id=str(uuid.uuid4()),
            nba_player_id=203954,
            canonical_name="Joel Embiid",
            alias_name="Joel Embiid",
            alias_source="odds_api",
            match_confidence=1.0,
            is_verified=False,
            created_at=datetime.utcnow()
        ),
        PlayerAlias(
            id=str(uuid.uuid4()),
            nba_player_id=203954,
            canonical_name="Joel Embiid",
            alias_name="Joel Embiid Jr.",
            alias_source="odds_api",
            match_confidence=0.95,
            is_verified=False,
            created_at=datetime.utcnow()
        ),
        PlayerAlias(
            id=str(uuid.uuid4()),
            nba_player_id=1628369,
            canonical_name="Jayson Tatum",
            alias_name="Jayson Tatum",
            alias_source="odds_api",
            match_confidence=1.0,
            is_verified=False,
            created_at=datetime.utcnow()
        ),
        PlayerAlias(
            id=str(uuid.uuid4()),
            nba_player_id=1628369,
            canonical_name="Jayson Tatum",
            alias_name="Jason Tatum",
            alias_source="odds_api",
            match_confidence=0.90,
            is_verified=False,
            created_at=datetime.utcnow()
        ),
        PlayerAlias(
            id=str(uuid.uuid4()),
            nba_player_id=203954,
            canonical_name="Joel Embiid",
            alias_name="Joel E",
            alias_source="odds_api",
            match_confidence=0.80,
            is_verified=False,
            created_at=datetime.utcnow()
        ),
    ]

    for alias in aliases:
        db_session.add(alias)
    db_session.commit()

    return aliases


@pytest.fixture
def sample_games(db_session: Session, sample_team_mappings):
    """Create sample NBA games for testing."""
    from app.models import Game

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    games = [
        Game(
            id=str(uuid.uuid4()),
            external_id="0022400001",
            id_source="nba",
            game_date=today.replace(hour=19, minute=0),
            away_team="BOS",
            home_team="PHI",
            season=2025,
            status="scheduled",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        ),
        Game(
            id=str(uuid.uuid4()),
            external_id="0022400002",
            id_source="nba",
            game_date=today.replace(hour=21, minute=30),
            away_team="LAL",
            home_team="GSW",
            season=2025,
            status="scheduled",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        ),
    ]

    for game in games:
        db_session.add(game)
    db_session.commit()

    return games


@pytest.fixture
def sample_odds_games():
    """Create sample odds API games for testing."""
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    return [
        {
            'id': 'odds_event_001',
            'sport_key': 'basketball_nba',
            'sport_title': 'NBA',
            'commence_time': today.replace(hour=19, minute=0),
            'home_team': 'Philadelphia 76ers',
            'away_team': 'Boston Celtics',
            'bookmakers': []
        },
        {
            'id': 'odds_event_002',
            'sport_key': 'basketball_nba',
            'sport_title': 'NBA',
            'commence_time': today.replace(hour=21, minute=30),
            'home_team': 'Golden State Warriors',
            'away_team': 'Los Angeles Lakers',
            'bookmakers': []
        },
        {
            'id': 'odds_event_003',
            'sport_key': 'basketball_nba',
            'sport_title': 'NBA',
            'commence_time': (today + timedelta(days=1)).replace(hour=20, minute=0),
            'home_team': 'New York Knicks',
            'away_team': 'Miami Heat',
            'bookmakers': []
        },
    ]


def create_game_mapping(**kwargs):
    """Helper function to create a valid GameMapping with all required fields.

    Usage:
        mapping = create_game_mapping(
            nba_game_id='0022400001',
            odds_event_id='odds_001',
            match_confidence=1.0
        )
    """
    from app.models import GameMapping

    defaults = {
        'id': str(uuid.uuid4()),
        'nba_game_id': 'test_game',
        'nba_home_team_id': 1610612755,
        'nba_away_team_id': 1610612738,
        'odds_event_id': None,
        'odds_sport_key': 'basketball_nba',
        'game_date': date.today(),
        'game_time': None,
        'match_confidence': 0.0,
        'match_method': 'pending',
        'status': 'pending',
        'last_validated_at': None,
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow(),
    }
    defaults.update(kwargs)
    return GameMapping(**defaults)


# =============================================================================
# FASTAPI TEST CLIENT FIXTURE
# =============================================================================

@pytest.fixture(scope="function")
def test_client(db_session):
    """
    Create FastAPI TestClient with a fresh database for each test.

    The TestClient provides a synchronous interface for testing FastAPI endpoints
    without making actual network calls. All requests are processed in-memory.

    Note: We don't use context manager (with TestClient) because it conflicts
    with Prometheus middleware that's added during app module initialization.

    Usage:
        def test_endpoint(test_client):
            response = test_client.get("/api/nba/players")
            assert response.status_code == 200
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.database import get_db
    from app.models import Player, Game

    # Ensure tables exist by querying once (this also helps with connection pooling)
    # This is needed because in-memory SQLite with cache=shared still needs
    # at least one query to properly initialize the connection
    db_session.query(Player).count()

    # Store reference to db_session in a closure
    # This ensures the same session is used for all requests
    test_db_session = db_session

    def override_get_db():
        try:
            yield test_db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Create client without context manager to avoid middleware conflict
    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()