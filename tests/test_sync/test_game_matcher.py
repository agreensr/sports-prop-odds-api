"""Integration tests for GameMatcher.

Test Strategy:
1. Test exact match scenario (find_match returns odds_event_id with 1.0 confidence)
2. Test fuzzy time match scenario (find_match returns with 0.95 confidence)
3. Test no match scenario (find_match returns None)
4. Test batch matching with multiple games
5. Test cache behavior (already matched games)
6. Test database persistence (GameMapping records created)

Each test follows the pattern:
- Given: Database with team mappings and sample games
- When: GameMatcher.match_game() or batch_match_games() is called
- Then: Correct match results and database state
"""
import pytest
import uuid
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.services.sync.matchers.game_matcher import GameMatcher
from app.models.nba.models import GameMapping, MatchAuditLog


class TestGameMatcher:
    """Integration tests for game matching functionality."""

    # Exact Match Tests
    # ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_find_exact_match(self, db_session: Session, sample_team_mappings):
        """Should find exact match when teams and time match perfectly."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        nba_game = {
            'id': '0022400001',
            'game_date': today.replace(hour=19, minute=0),
            'home_team_id': 1610612755,  # PHI
            'away_team_id': 1610612738,  # BOS
        }

        odds_games = [{
            'id': 'odds_event_001',
            'commence_time': today.replace(hour=19, minute=0),
            'home_team': 'Philadelphia 76ers',
            'away_team': 'Boston Celtics',
        }]

        matcher = GameMatcher(db_session)
        match = await matcher.find_match(nba_game, odds_games)

        assert match is not None
        assert match['odds_event_id'] == 'odds_event_001'
        assert match['match_confidence'] == 1.0
        assert match['match_method'] == 'exact'

    @pytest.mark.asyncio
    async def test_no_match_different_teams(self, db_session: Session, sample_team_mappings):
        """Should return None when teams don't match."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        nba_game = {
            'id': '0022400001',
            'game_date': today.replace(hour=19, minute=0),
            'home_team_id': 1610612755,  # PHI
            'away_team_id': 1610612738,  # BOS
        }

        odds_games = [{
            'id': 'odds_event_002',
            'commence_time': today.replace(hour=19, minute=0),
            'home_team': 'Golden State Warriors',  # Different teams
            'away_team': 'Los Angeles Lakers',
        }]

        matcher = GameMatcher(db_session)
        match = await matcher.find_match(nba_game, odds_games)

        assert match is None

    # Batch Matching Tests
    # ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_batch_match_all_games(self, db_session: Session, sample_team_mappings):
        """Should match all games when all have corresponding odds events."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        nba_games = [
            {
                'id': '0022400001',
                'game_date': today.replace(hour=19, minute=0),
                'home_team_id': 1610612755,  # PHI
                'away_team_id': 1610612738,  # BOS
            },
            {
                'id': '0022400002',
                'game_date': today.replace(hour=21, minute=30),
                'home_team_id': 1610612744,  # GSW
                'away_team_id': 1610612747,  # LAL
            },
        ]

        odds_games = [
            {
                'id': 'odds_event_001',
                'commence_time': today.replace(hour=19, minute=0),
                'home_team': 'Philadelphia 76ers',
                'away_team': 'Boston Celtics',
            },
            {
                'id': 'odds_event_002',
                'commence_time': today.replace(hour=21, minute=30),
                'home_team': 'Golden State Warriors',
                'away_team': 'Los Angeles Lakers',
            },
        ]

        matcher = GameMatcher(db_session)
        results = await matcher.batch_match_games(nba_games, odds_games)

        assert results['total'] == 2
        assert results['matched'] == 2
        assert results['unmatched'] == 0
        assert len(results['matches']) == 2

    @pytest.mark.asyncio
    async def test_batch_match_partial_games(self, db_session: Session, sample_team_mappings):
        """Should match only games with corresponding odds events."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        nba_games = [
            {
                'id': '0022400001',
                'game_date': today.replace(hour=19, minute=0),
                'home_team_id': 1610612755,  # PHI
                'away_team_id': 1610612738,  # BOS
            },
            {
                'id': '0022400002',
                'game_date': today.replace(hour=21, minute=30),
                'home_team_id': 1610612744,  # GSW
                'away_team_id': 1610612747,  # LAL
            },
        ]

        # Only one odds game (PHI @ BOS)
        odds_games = [
            {
                'id': 'odds_event_001',
                'commence_time': today.replace(hour=19, minute=0),
                'home_team': 'Philadelphia 76ers',
                'away_team': 'Boston Celtics',
            },
        ]

        matcher = GameMatcher(db_session)
        results = await matcher.batch_match_games(nba_games, odds_games)

        assert results['total'] == 2
        assert results['matched'] == 1
        assert results['unmatched'] == 1
        assert len(results['matches']) == 1

    # Database Persistence Tests
    # ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_creates_game_mapping_record(self, db_session: Session, sample_team_mappings):
        """Should create GameMapping record when match is found."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        nba_games = [{
            'id': '0022400001',
            'game_date': today.replace(hour=19, minute=0),
            'home_team_id': 1610612755,
            'away_team_id': 1610612738,
        }]

        odds_games = [{
            'id': 'odds_event_001',
            'commence_time': today.replace(hour=19, minute=0),
            'home_team': 'Philadelphia 76ers',
            'away_team': 'Boston Celtics',
        }]

        matcher = GameMatcher(db_session)
        await matcher.batch_match_games(nba_games, odds_games)

        # Verify GameMapping was created
        mapping = db_session.query(GameMapping).filter(
            GameMapping.nba_game_id == '0022400001'
        ).first()

        assert mapping is not None
        assert mapping.odds_event_id == 'odds_event_001'
        assert mapping.match_confidence == 1.0
        assert mapping.match_method == 'exact'
        assert mapping.status == 'matched'

    @pytest.mark.asyncio
    async def test_updates_existing_mapping(self, db_session: Session, sample_team_mappings):
        """Should preserve existing matched mapping (not update it)."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        # Create existing mapping with different odds_event_id
        existing_mapping = GameMapping(
            id=str(uuid.uuid4()),
            nba_game_id='0022400001',
            nba_home_team_id=1610612755,
            nba_away_team_id=1610612738,
            odds_event_id='old_odds_id',
            game_date=today.date(),
            match_confidence=0.85,
            match_method='manual',
            status='matched',
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db_session.add(existing_mapping)
        db_session.commit()

        nba_games = [{
            'id': '0022400001',
            'game_date': today.replace(hour=19, minute=0),
            'home_team_id': 1610612755,
            'away_team_id': 1610612738,
        }]

        odds_games = [{
            'id': 'new_odds_event_001',
            'commence_time': today.replace(hour=19, minute=0),
            'home_team': 'Philadelphia 76ers',
            'away_team': 'Boston Celtics',
        }]

        matcher = GameMatcher(db_session)
        results = await matcher.batch_match_games(nba_games, odds_games)

        # Should return cached match, not update existing mapping
        assert results['matches'][0]['cached'] is True
        assert results['matches'][0]['odds_event_id'] == 'old_odds_id'

        # Verify existing mapping was NOT updated
        mapping = db_session.query(GameMapping).filter(
            GameMapping.nba_game_id == '0022400001'
        ).first()

        assert mapping.odds_event_id == 'old_odds_id'  # Not updated
        assert mapping.match_confidence == 0.85  # Not updated
        assert mapping.match_method == 'manual'  # Not updated

    # Cache Behavior Tests
    # ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_returns_cached_match(self, db_session: Session, sample_team_mappings):
        """Should return cached match when game already matched."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        # Create existing mapping
        existing_mapping = GameMapping(
            id=str(uuid.uuid4()),
            nba_game_id='0022400001',
            nba_home_team_id=1610612755,
            nba_away_team_id=1610612738,
            odds_event_id='cached_odds_id',
            game_date=today.date(),
            match_confidence=1.0,
            match_method='exact',
            status='matched',
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db_session.add(existing_mapping)
        db_session.commit()

        nba_games = [{
            'id': '0022400001',
            'game_date': today.replace(hour=19, minute=0),
            'home_team_id': 1610612755,
            'away_team_id': 1610612738,
        }]

        odds_games = [{
            'id': 'new_odds_event',
            'commence_time': today.replace(hour=19, minute=0),
            'home_team': 'Philadelphia 76ers',
            'away_team': 'Boston Celtics',
        }]

        matcher = GameMatcher(db_session)
        results = await matcher.batch_match_games(nba_games, odds_games)

        # Should return cached match, not create new one
        assert results['matched'] == 1
        assert results['matches'][0]['cached'] is True
        assert results['matches'][0]['odds_event_id'] == 'cached_odds_id'

        # Verify database wasn't updated
        mapping = db_session.query(GameMapping).filter(
            GameMapping.nba_game_id == '0022400001'
        ).first()
        assert mapping.odds_event_id == 'cached_odds_id'

    # Audit Log Tests
    # ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_logs_match_to_audit_trail(self, db_session: Session, sample_team_mappings):
        """Should create MatchAuditLog entry when match is made."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        nba_games = [{
            'id': '0022400001',
            'game_date': today.replace(hour=19, minute=0),
            'home_team_id': 1610612755,
            'away_team_id': 1610612738,
        }]

        odds_games = [{
            'id': 'odds_event_001',
            'commence_time': today.replace(hour=19, minute=0),
            'home_team': 'Philadelphia 76ers',
            'away_team': 'Boston Celtics',
        }]

        matcher = GameMatcher(db_session)
        await matcher.batch_match_games(nba_games, odds_games)

        # Verify audit log was created
        audit_log = db_session.query(MatchAuditLog).filter(
            MatchAuditLog.entity_id == '0022400001',
            MatchAuditLog.entity_type == 'game'
        ).first()

        assert audit_log is not None
        assert audit_log.action == 'matched'
        assert audit_log.match_details is not None

    # Edge Cases
    # ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_handles_empty_games_list(self, db_session: Session):
        """Should handle empty NBA games list gracefully."""
        matcher = GameMatcher(db_session)
        results = await matcher.batch_match_games([], [])

        assert results['total'] == 0
        assert results['matched'] == 0
        assert results['unmatched'] == 0

    @pytest.mark.asyncio
    async def test_handles_no_odds_games(self, db_session: Session, sample_team_mappings):
        """Should handle empty odds games list gracefully."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        nba_games = [{
            'id': '0022400001',
            'game_date': today.replace(hour=19, minute=0),
            'home_team_id': 1610612755,
            'away_team_id': 1610612738,
        }]

        matcher = GameMatcher(db_session)
        results = await matcher.batch_match_games(nba_games, [])

        assert results['total'] == 1
        assert results['matched'] == 0
        assert results['unmatched'] == 1

    @pytest.mark.asyncio
    async def test_handles_duplicate_odds_events(self, db_session: Session, sample_team_mappings):
        """Should handle duplicate odds events without creating duplicate mappings."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        nba_games = [{
            'id': '0022400001',
            'game_date': today.replace(hour=19, minute=0),
            'home_team_id': 1610612755,
            'away_team_id': 1610612738,
        }]

        # Duplicate odds events
        odds_games = [
            {
                'id': 'odds_event_001',
                'commence_time': today.replace(hour=19, minute=0),
                'home_team': 'Philadelphia 76ers',
                'away_team': 'Boston Celtics',
            },
            {
                'id': 'odds_event_001',  # Duplicate ID
                'commence_time': today.replace(hour=19, minute=0),
                'home_team': 'Philadelphia 76ers',
                'away_team': 'Boston Celtics',
            },
        ]

        matcher = GameMatcher(db_session)
        results = await matcher.batch_match_games(nba_games, odds_games)

        # Should only match once
        assert results['matched'] == 1

        # Should only have one mapping
        mappings = db_session.query(GameMapping).filter(
            GameMapping.nba_game_id == '0022400001'
        ).all()
        assert len(mappings) == 1
