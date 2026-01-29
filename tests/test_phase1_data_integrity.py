"""
Phase 1 Data Integrity Tests.

Tests for multi-source ID resolution, data validation, and deduplication.
Run with: pytest tests/test_phase1_data_integrity.py -v
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.models.nba.models import Base, Sport, Player, Game, Prediction
from app.services.core.identity_resolver import (
    PlayerIdentityResolver,
    GameIdentityResolver
)
from app.services.core.data_validator import (
    DataValidator,
    ValidationResult
)


# Test database (use SQLite for testing)
TEST_DATABASE_URL = "sqlite:///./test_phase1.db"


@pytest.fixture
def db_session():
    """Create a test database session."""
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()
    engine.dispose()

    # Cleanup
    import os
    if os.path.exists("./test_phase1.db"):
        os.remove("./test_phase1.db")


class TestPlayerIdentityResolver:
    """Tests for PlayerIdentityResolver."""

    def test_resolve_new_player(self, db_session: Session):
        """Test resolving a new player creates a record."""
        resolver = PlayerIdentityResolver(db_session)

        player, created = resolver.resolve_player(
            sport_id='nba',
            name='Luka Doncic',
            team='DAL',
            odds_api_id='luka-doncic-123'
        )

        assert created is True
        assert player.name == 'Luka Doncic'
        assert player.team == 'DAL'
        assert player.odds_api_id == 'luka-doncic-123'
        assert player.sport_id == 'nba'
        assert player.canonical_name == 'luka doncic'

    def test_resolve_existing_player_by_odds_api_id(self, db_session: Session):
        """Test resolving an existing player by odds_api_id."""
        resolver = PlayerIdentityResolver(db_session)

        # Create initial player
        player1, created1 = resolver.resolve_player(
            sport_id='nba',
            name='Luka Doncic',
            team='DAL',
            odds_api_id='luka-doncic-123'
        )

        assert created1 is True

        # Resolve same player by odds_api_id
        player2, created2 = resolver.resolve_player(
            sport_id='nba',
            name='Luka Dončić',  # Different name format
            team='DAL',
            odds_api_id='luka-doncic-123'
        )

        assert created2 is False
        assert player1.id == player2.id

    def test_resolve_player_by_team_and_name(self, db_session: Session):
        """Test resolving player by team and canonical name."""
        resolver = PlayerIdentityResolver(db_session)

        # Create initial player
        player1, created1 = resolver.resolve_player(
            sport_id='nba',
            name='LeBron James',
            team='LAL'
        )

        assert created1 is True

        # Resolve same player by team + name (no API ID)
        player2, created2 = resolver.resolve_player(
            sport_id='nba',
            name='LeBron James',
            team='LAL'
        )

        assert created2 is False
        assert player1.id == player2.id

    def test_name_normalization(self, db_session: Session):
        """Test that player names are normalized consistently."""
        resolver = PlayerIdentityResolver(db_session)

        # Create player with accented character
        player1, _ = resolver.resolve_player(
            sport_id='nba',
            name='Luka Dončić',
            team='DAL'
        )

        # Try to resolve with plain ASCII
        player2, created = resolver.resolve_player(
            sport_id='nba',
            name='Luka Doncic',
            team='DAL'
        )

        assert created is False  # Should match existing
        assert player1.id == player2.id
        assert player1.canonical_name == 'luka doncic'


class TestGameIdentityResolver:
    """Tests for GameIdentityResolver."""

    def test_resolve_new_game(self, db_session: Session):
        """Test resolving a new game creates a record."""
        resolver = GameIdentityResolver(db_session)

        game_date = datetime(2026, 1, 27, 19, 0)

        game, created = resolver.resolve_game(
            sport_id='nba',
            game_date=game_date,
            away_team='LAL',
            home_team='BOS',
            odds_api_event_id='lal-bos-2026-01-27'
        )

        assert created is True
        assert game.away_team == 'LAL'
        assert game.home_team == 'BOS'
        assert game.odds_api_event_id == 'lal-bos-2026-01-27'
        assert game.sport_id == 'nba'

    def test_resolve_existing_game_by_natural_key(self, db_session: Session):
        """Test resolving an existing game by natural key."""
        resolver = GameIdentityResolver(db_session)

        game_date = datetime(2026, 1, 27, 19, 0)

        # Create initial game
        game1, created1 = resolver.resolve_game(
            sport_id='nba',
            game_date=game_date,
            away_team='LAL',
            home_team='BOS',
            odds_api_event_id='lal-bos-2026-01-27'
        )

        assert created1 is True

        # Resolve same game by natural key (different API ID)
        game2, created2 = resolver.resolve_game(
            sport_id='nba',
            game_date=game_date,
            away_team='LAL',
            home_team='BOS',
            espn_game_id=401234567
        )

        assert created2 is False
        assert game1.id == game2.id

    def test_natural_key_within_time_window(self, db_session: Session):
        """Test that natural key matching works within time window."""
        resolver = GameIdentityResolver(db_session)

        game_date1 = datetime(2026, 1, 27, 19, 0)
        game_date2 = datetime(2026, 1, 27, 20, 0)  # 1 hour later

        # Create initial game
        game1, created1 = resolver.resolve_game(
            sport_id='nba',
            game_date=game_date1,
            away_team='LAL',
            home_team='BOS'
        )

        assert created1 is True

        # Resolve with slightly different time (within 6-hour window)
        game2, created2 = resolver.resolve_game(
            sport_id='nba',
            game_date=game_date2,
            away_team='LAL',
            home_team='BOS'
        )

        assert created2 is False  # Should match due to time window
        assert game1.id == game2.id


class TestDataValidator:
    """Tests for DataValidator."""

    def test_validate_valid_player(self, db_session: Session):
        """Test validating a valid player."""
        validator = DataValidator(db_session)

        result = validator.validate_player({
            'sport_id': 'nba',
            'name': 'Luka Doncic',
            'team': 'DAL'
        })

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_player_missing_required_fields(self, db_session: Session):
        """Test that missing required fields fail validation."""
        validator = DataValidator(db_session)

        result = validator.validate_player({
            'sport_id': 'nba',
            # Missing 'name'
            'team': 'DAL'
        })

        assert result.is_valid is False
        assert 'Missing required field: name' in result.errors

    def test_validate_player_invalid_sport(self, db_session: Session):
        """Test that invalid sport_id fails validation."""
        validator = DataValidator(db_session)

        result = validator.validate_player({
            'sport_id': 'invalid',
            'name': 'John Doe',
            'team': 'TST'
        })

        assert result.is_valid is False
        assert 'Invalid sport_id' in result.errors[0]

    def test_validate_game_valid(self, db_session: Session):
        """Test validating a valid game."""
        validator = DataValidator(db_session)

        result = validator.validate_game({
            'sport_id': 'nba',
            'game_date': datetime(2026, 1, 27, 19, 0),
            'away_team': 'LAL',
            'home_team': 'BOS'
        })

        assert result.is_valid is True

    def test_validate_game_same_teams(self, db_session: Session):
        """Test that same away/home teams fail validation."""
        validator = DataValidator(db_session)

        result = validator.validate_game({
            'sport_id': 'nba',
            'game_date': datetime(2026, 1, 27, 19, 0),
            'away_team': 'LAL',
            'home_team': 'LAL'  # Same as away
        })

        assert result.is_valid is False
        assert 'away_team and home_team must be different' in result.errors

    def test_detect_duplicate_player(self, db_session: Session):
        """Test that duplicate players are detected."""
        validator = DataValidator(db_session)

        # Create initial player
        resolver = PlayerIdentityResolver(db_session)
        resolver.resolve_player(
            sport_id='nba',
            name='Luka Doncic',
            team='DAL',
            odds_api_id='luka-123'
        )

        # Try to validate duplicate
        result = validator.validate_player({
            'sport_id': 'nba',
            'name': 'Luka Doncic',
            'team': 'DAL',
            'odds_api_id': 'luka-123'
        })

        assert result.duplicate_of is not None
        assert len(result.warnings) > 0


class TestIntegrityReports:
    """Tests for data integrity reporting."""

    def test_generate_integrity_report(self, db_session: Session):
        """Test generating integrity report."""
        validator = DataValidator(db_session)

        # Create some test data
        resolver = PlayerIdentityResolver(db_session)
        resolver.resolve_player(sport_id='nba', name='Player 1', team='T1')
        resolver.resolve_player(sport_id='nba', name='Player 2', team='T2')

        report = validator.generate_integrity_report()

        assert 'players' in report
        assert 'games' in report
        assert 'predictions' in report
        assert report['players']['total'] >= 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
