"""Unit tests for confidence_scorer utility.

Test Strategy:
1. Test exact match scenarios (confidence = 1.0)
2. Test fuzzy time match scenarios (confidence = 0.95)
3. Test fuzzy team name match scenarios (confidence = 0.85)
4. Test no match scenarios (confidence = 0.0)
5. Test edge cases (missing data, None values)

Each test follows the pattern:
- Given: NBA game data and odds game data with specific characteristics
- When: calculate_game_match_confidence() is called
- Then: Confidence score matches expected value
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.services.sync.utils.confidence_scorer import calculate_game_match_confidence


class TestConfidenceScorer:
    """Test suite for match confidence scoring."""

    # Exact Match Tests (Confidence = 1.0)
    # ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_exact_match_same_teams_same_time(self, db_session: Session, sample_team_mappings):
        """Should return 1.0 for identical teams and same start time."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        game_time = today.replace(hour=19, minute=0)

        nba_game = {
            'id': '0022400001',
            'game_date': game_time,
            'home_team_id': 1610612755,  # PHI
            'away_team_id': 1610612738,  # BOS
        }

        odds_game = {
            'id': 'odds_event_001',
            'commence_time': game_time,
            'home_team': 'Philadelphia 76ers',
            'away_team': 'Boston Celtics',
        }

        confidence = await calculate_game_match_confidence(nba_game, odds_game, db_session)
        assert confidence == 1.0

    @pytest.mark.asyncio
    async def test_exact_match_with_time_within_tolerance(self, db_session: Session, sample_team_mappings):
        """Should return 1.0 for teams match with time within 2 hours."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        nba_game = {
            'id': '0022400001',
            'game_date': today.replace(hour=19, minute=0),
            'home_team_id': 1610612755,  # PHI
            'away_team_id': 1610612738,  # BOS
        }

        # 30 minutes difference
        odds_game = {
            'id': 'odds_event_001',
            'commence_time': today.replace(hour=19, minute=30),
            'home_team': 'Philadelphia 76ers',
            'away_team': 'Boston Celtics',
        }

        confidence = await calculate_game_match_confidence(nba_game, odds_game, db_session)
        assert confidence == 1.0

    # Fuzzy Time Match Tests (Confidence = 0.95)
    # ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_fuzzy_time_match_over_2_hours(self, db_session: Session, sample_team_mappings):
        """Should return 0.95 for teams match with time > 2 hours difference."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        nba_game = {
            'id': '0022400001',
            'game_date': today.replace(hour=19, minute=0),
            'home_team_id': 1610612755,  # PHI
            'away_team_id': 1610612738,  # BOS
        }

        # 2.5 hours difference (> 120 minutes)
        odds_game = {
            'id': 'odds_event_001',
            'commence_time': today.replace(hour=21, minute=30),
            'home_team': 'Philadelphia 76ers',
            'away_team': 'Boston Celtics',
        }

        confidence = await calculate_game_match_confidence(nba_game, odds_game, db_session)
        assert confidence == 0.95

    # No Match Tests (Confidence = 0.0)
    # ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_no_match_different_dates(self, db_session: Session, sample_team_mappings):
        """Should return 0.0 for games on different dates."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)

        nba_game = {
            'id': '0022400001',
            'game_date': today.replace(hour=19, minute=0),
            'home_team_id': 1610612755,  # PHI
            'away_team_id': 1610612738,  # BOS
        }

        odds_game = {
            'id': 'odds_event_001',
            'commence_time': tomorrow.replace(hour=19, minute=0),
            'home_team': 'Philadelphia 76ers',
            'away_team': 'Boston Celtics',
        }

        confidence = await calculate_game_match_confidence(nba_game, odds_game, db_session)
        assert confidence == 0.0

    @pytest.mark.asyncio
    async def test_no_match_different_teams(self, db_session: Session, sample_team_mappings):
        """Should return 0.0 for games with different teams."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        nba_game = {
            'id': '0022400001',
            'game_date': today.replace(hour=19, minute=0),
            'home_team_id': 1610612755,  # PHI
            'away_team_id': 1610612738,  # BOS
        }

        odds_game = {
            'id': 'odds_event_001',
            'commence_time': today.replace(hour=19, minute=0),
            'home_team': 'Golden State Warriors',  # GSW
            'away_team': 'Los Angeles Lakers',  # LAL
        }

        confidence = await calculate_game_match_confidence(nba_game, odds_game, db_session)
        assert confidence == 0.0

    @pytest.mark.asyncio
    async def test_no_match_swapped_home_away(self, db_session: Session, sample_team_mappings):
        """Should return 0.0 when home and away teams are swapped."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        nba_game = {
            'id': '0022400001',
            'game_date': today.replace(hour=19, minute=0),
            'home_team_id': 1610612755,  # PHI (home)
            'away_team_id': 1610612738,  # BOS (away)
        }

        # Swapped: BOS listed as home, PHI as away
        odds_game = {
            'id': 'odds_event_001',
            'commence_time': today.replace(hour=19, minute=0),
            'home_team': 'Boston Celtics',
            'away_team': 'Philadelphia 76ers',
        }

        confidence = await calculate_game_match_confidence(nba_game, odds_game, db_session)
        assert confidence == 0.0

    # Edge Cases
    # ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_handles_missing_team_mapping(self, db_session: Session):
        """Should return 0.0 when team mapping is missing."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        nba_game = {
            'id': '0022400001',
            'game_date': today.replace(hour=19, minute=0),
            'home_team_id': 999999,  # Non-existent team
            'away_team_id': 1610612738,
        }

        odds_game = {
            'id': 'odds_event_001',
            'commence_time': today.replace(hour=19, minute=0),
            'home_team': 'Philadelphia 76ers',
            'away_team': 'Boston Celtics',
        }

        confidence = await calculate_game_match_confidence(nba_game, odds_game, db_session)
        assert confidence == 0.0

    @pytest.mark.asyncio
    async def test_handles_time_at_boundary(self, db_session: Session, sample_team_mappings):
        """Should handle time difference exactly at 2 hours boundary."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        nba_game = {
            'id': '0022400001',
            'game_date': today.replace(hour=19, minute=0),
            'home_team_id': 1610612755,
            'away_team_id': 1610612738,
        }

        # Exactly 2 hours difference = 120 minutes
        odds_game = {
            'id': 'odds_event_001',
            'commence_time': today.replace(hour=21, minute=0),
            'home_team': 'Philadelphia 76ers',
            'away_team': 'Boston Celtics',
        }

        confidence = await calculate_game_match_confidence(nba_game, odds_game, db_session)
        assert confidence == 1.0  # Within tolerance

    @pytest.mark.asyncio
    async def test_handles_one_second_over_boundary(self, db_session: Session, sample_team_mappings):
        """Should return 0.95 for time difference just over 2 hours."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        nba_game = {
            'id': '0022400001',
            'game_date': today.replace(hour=19, minute=0),
            'home_team_id': 1610612755,
            'away_team_id': 1610612738,
        }

        # 2 hours + 1 minute = 121 minutes (time comparison ignores seconds)
        odds_game = {
            'id': 'odds_event_001',
            'commence_time': today.replace(hour=21, minute=1),  # 21:01, not 21:00:01
            'home_team': 'Philadelphia 76ers',
            'away_team': 'Boston Celtics',
        }

        confidence = await calculate_game_match_confidence(nba_game, odds_game, db_session)
        assert confidence == 0.95

    # Real World Scenarios
    # ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_real_nba_game_exact_match(self, db_session: Session, sample_team_mappings):
        """Test with real NBA game data structure."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        nba_game = {
            'id': '0022400001',
            'game_date': today.replace(hour=19, minute=0),
            'home_team': 'PHI',
            'away_team': 'BOS',
            'home_team_id': 1610612755,
            'away_team_id': 1610612738,
        }

        odds_game = {
            'id': 'odds_event_001',
            'sport_key': 'basketball_nba',
            'commence_time': today.replace(hour=19, minute=0),
            'home_team': 'Philadelphia 76ers',
            'away_team': 'Boston Celtics',
        }

        confidence = await calculate_game_match_confidence(nba_game, odds_game, db_session)
        assert confidence == 1.0
