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
    from app.models.nba.models import Base

    # Use unique in-memory database for each test
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )

    # Create tables individually to handle duplicate index errors
    # The models have both index=True on columns AND explicit Index() in __table_args__
    for table in Base.metadata.sorted_tables:
        try:
            table.create(bind=engine, checkfirst=True)
        except Exception as e:
            # Ignore "index already exists" errors - the index was created by unique=True
            if "already exists" not in str(e) and "duplicate" not in str(e).lower():
                raise

    # Create session
    TestSessionLocal = sessionmaker(bind=engine)
    session = TestSessionLocal()

    yield session

    session.close()
    engine.dispose()


@pytest.fixture(scope="function")
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for testing FastAPI endpoints."""
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
def sample_team_mappings(db_session: Session):
    """Create sample team mappings for testing."""
    from app.models.nba.models import TeamMapping

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
    from app.models.nba.models import PlayerAlias

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
    from app.models.nba.models import Game

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
            status="scheduled"
        ),
        Game(
            id=str(uuid.uuid4()),
            external_id="0022400002",
            id_source="nba",
            game_date=today.replace(hour=21, minute=30),
            away_team="LAL",
            home_team="GSW",
            season=2025,
            status="scheduled"
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
    from app.models.nba.models import GameMapping

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