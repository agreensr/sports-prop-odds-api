"""Integration tests for SyncOrchestrator.

Test Strategy:
1. Test sync_games() with mocked adapters
2. Test sync_odds() with mocked adapters
3. Test get_sync_status() returns correct health
4. Test get_matched_games() filters correctly
5. Test get_manual_review_queue() returns unmatched games
6. Test metadata tracking updates correctly
7. Test error handling and rollback

Each test follows the pattern:
- Given: Database with sample data and mocked adapters
- When: SyncOrchestrator method is called
- Then: Correct results and database state
"""
import pytest
import uuid
from datetime import datetime, timedelta, date
from unittest.mock import AsyncMock, Mock

# Import helper from conftest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import create_game_mapping
from sqlalchemy.orm import Session

from app.services.sync.orchestrator import SyncOrchestrator
from app.models import (
    GameMapping, PlayerAlias, TeamMapping,
    SyncMetadata, MatchAuditLog
)


class TestSyncOrchestrator:
    """Integration tests for sync orchestration."""

    # sync_games() Tests
    # ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_sync_games_success(self, db_session: Session, sample_team_mappings):
        """Should successfully sync games and create mappings."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        # Mock nba_adapter.fetch_games()
        nba_games = [
            {
                'id': '0022400001',
                'game_date': today.replace(hour=19, minute=0),
                'home_team_id': 1610612755,
                'away_team_id': 1610612738,
            },
            {
                'id': '0022400002',
                'game_date': today.replace(hour=21, minute=30),
                'home_team_id': 1610612744,
                'away_team_id': 1610612747,
            },
        ]

        # Mock odds_adapter.fetch_odds()
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

        orchestrator = SyncOrchestrator(db_session)

        # Mock the adapter methods directly
        orchestrator.nba_adapter.fetch_games = AsyncMock(return_value=nba_games)
        orchestrator.odds_adapter.fetch_odds = AsyncMock(return_value=odds_games)

        results = await orchestrator.sync_games(
            lookback_days=7,
            lookahead_days=14
        )

        # Verify results
        assert results['success'] is True
        assert results['processed'] == 2
        assert results['matched'] == 2
        assert results['unmatched'] == 0
        assert 'duration_ms' in results

        # Verify GameMappings were created
        mappings = db_session.query(GameMapping).all()
        assert len(mappings) == 2

        # Verify SyncMetadata was updated
        metadata = db_session.query(SyncMetadata).filter(
            SyncMetadata.source == 'nba_api',
            SyncMetadata.data_type == 'games'
        ).first()

        assert metadata is not None
        assert metadata.last_sync_status == 'success'
        assert metadata.records_processed == 2
        assert metadata.records_matched == 2

    @pytest.mark.asyncio
    async def test_sync_games_with_no_nba_games(self, db_session: Session):
        """Should handle empty NBA games response."""
        orchestrator = SyncOrchestrator(db_session)

        # Mock the adapter method directly
        orchestrator.nba_adapter.fetch_games = AsyncMock(return_value=[])

        results = await orchestrator.sync_games()

        assert results['success'] is False
        assert results['error'] == 'No games fetched from nba_api'

    # sync_odds() Tests
    # ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_sync_odds_success(self, db_session: Session):
        """Should successfully sync odds."""
        odds_games = [
            {'id': 'odds_001', 'sport_key': 'basketball_nba'},
            {'id': 'odds_002', 'sport_key': 'basketball_nba'},
        ]

        orchestrator = SyncOrchestrator(db_session)

        # Mock the adapter method directly
        orchestrator.odds_adapter.fetch_odds = AsyncMock(return_value=odds_games)

        results = await orchestrator.sync_odds(upcoming_only=True, days=7)

        assert results['success'] is True
        assert results['processed'] == 2
        assert 'duration_ms' in results

        # Verify SyncMetadata
        metadata = db_session.query(SyncMetadata).filter(
            SyncMetadata.source == 'odds_api',
            SyncMetadata.data_type == 'odds'
        ).first()

        assert metadata is not None
        assert metadata.last_sync_status == 'success'
        assert metadata.records_processed == 2

    # get_sync_status() Tests
    # ─────────────────────────────────────────────────────────────

    def test_get_sync_status_healthy(self, db_session: Session):
        """Should return healthy status when all sync jobs successful."""
        # Create successful metadata entries
        metadata1 = SyncMetadata(
            id=str(uuid.uuid4()),
            source='nba_api',
            data_type='games',
            last_sync_status='success',
            last_sync_completed_at=datetime.utcnow(),
            records_processed=100,
            records_matched=95,
            records_failed=5
        )
        metadata2 = SyncMetadata(
            id=str(uuid.uuid4()),
            source='odds_api',
            data_type='odds',
            last_sync_status='success',
            last_sync_completed_at=datetime.utcnow(),
            records_processed=50,
        )
        db_session.add_all([metadata1, metadata2])
        db_session.commit()

        orchestrator = SyncOrchestrator(db_session)
        status = orchestrator.get_sync_status()

        assert status['health_status'] == 'healthy'
        assert status['total_jobs'] == 2
        assert status['success_count'] == 2
        assert status['totals']['processed'] == 150
        assert status['totals']['matched'] == 95
        assert status['totals']['failed'] == 5

    def test_get_sync_status_degraded(self, db_session: Session):
        """Should return degraded status when some jobs failed."""
        metadata1 = SyncMetadata(
            id=str(uuid.uuid4()),
            source='nba_api',
            data_type='games',
            last_sync_status='success',
        )
        metadata2 = SyncMetadata(
            id=str(uuid.uuid4()),
            source='odds_api',
            data_type='odds',
            last_sync_status='failed',
            error_message='API timeout'
        )
        db_session.add_all([metadata1, metadata2])
        db_session.commit()

        orchestrator = SyncOrchestrator(db_session)
        status = orchestrator.get_sync_status()

        assert status['health_status'] == 'degraded'
        assert status['success_count'] == 1

    def test_get_sync_status_includes_issues(self, db_session: Session, sample_team_mappings):
        """Should include unmatched games and low confidence matches."""
        # Add some game mappings using helper function
        mapping1 = create_game_mapping(
            nba_game_id='001',
            nba_home_team_id=1610612755,
            nba_away_team_id=1610612738,
            odds_event_id='odds_001',
            match_confidence=0.90,
            match_method='exact',
            status='matched'
        )
        mapping2 = create_game_mapping(
            nba_game_id='002',
            nba_home_team_id=1610612744,
            nba_away_team_id=1610612747,
            odds_event_id='odds_002',
            match_confidence=0.80,  # Low confidence
            match_method='fuzzy',
            status='matched'
        )
        mapping3 = create_game_mapping(
            nba_game_id='003',
            nba_home_team_id=1610612755,
            nba_away_team_id=1610612738,
            odds_event_id=None,
            match_confidence=0.0,
            match_method='pending',
            status='manual_review'  # Unmatched
        )
        db_session.add_all([mapping1, mapping2, mapping3])
        db_session.commit()

        orchestrator = SyncOrchestrator(db_session)
        status = orchestrator.get_sync_status()

        assert status['issues']['low_confidence_matches'] == 1
        assert status['issues']['unmatched_games'] == 1

    # get_matched_games() Tests
    # ─────────────────────────────────────────────────────────────

    def test_get_matched_games_all(self, db_session: Session, sample_team_mappings):
        """Should return all matched games with high confidence."""
        today = date.today()

        # Add matched games using helper function
        mapping1 = create_game_mapping(
            nba_game_id='001',
            nba_home_team_id=1610612755,
            nba_away_team_id=1610612738,
            odds_event_id='odds_001',
            match_confidence=1.0,
            match_method='exact',
            status='matched',
            game_date=today,
            last_validated_at=datetime.utcnow()
        )
        mapping2 = create_game_mapping(
            nba_game_id='002',
            nba_home_team_id=1610612744,
            nba_away_team_id=1610612747,
            odds_event_id='odds_002',
            match_confidence=0.90,
            match_method='fuzzy_time',
            status='matched',
            game_date=today,
            last_validated_at=datetime.utcnow()
        )
        # Low confidence match (should not be included)
        mapping3 = create_game_mapping(
            nba_game_id='003',
            nba_home_team_id=1610612755,
            nba_away_team_id=1610612738,
            odds_event_id='odds_003',
            match_confidence=0.80,  # Below 0.85 threshold
            match_method='fuzzy',
            status='matched',
            game_date=today
        )
        db_session.add_all([mapping1, mapping2, mapping3])
        db_session.commit()

        orchestrator = SyncOrchestrator(db_session)
        matched = orchestrator.get_matched_games()

        assert len(matched) == 2  # Only high confidence matches
        assert all(m['match_confidence'] >= 0.85 for m in matched)

    def test_get_matched_games_by_date(self, db_session: Session, sample_team_mappings):
        """Should filter matched games by date."""
        today = date.today()
        yesterday = today - timedelta(days=1)

        mapping1 = create_game_mapping(
            nba_game_id='001',
            nba_home_team_id=1610612755,
            nba_away_team_id=1610612738,
            odds_event_id='odds_001',
            match_confidence=1.0,
            match_method='exact',
            status='matched',
            game_date=today
        )
        mapping2 = create_game_mapping(
            nba_game_id='002',
            nba_home_team_id=1610612744,
            nba_away_team_id=1610612747,
            odds_event_id='odds_002',
            match_confidence=1.0,
            match_method='exact',
            status='matched',
            game_date=yesterday
        )
        db_session.add_all([mapping1, mapping2])
        db_session.commit()

        orchestrator = SyncOrchestrator(db_session)
        matched = orchestrator.get_matched_games(game_date=today)

        assert len(matched) == 1
        assert matched[0]['nba_game_id'] == '001'

    # get_manual_review_queue() Tests
    # ─────────────────────────────────────────────────────────────

    def test_get_manual_review_queue(self, db_session: Session, sample_team_mappings):
        """Should return unmatched and low confidence matches."""
        today = date.today()

        # Unmatched game
        mapping1 = create_game_mapping(
            nba_game_id='001',
            nba_home_team_id=1610612755,
            nba_away_team_id=1610612738,
            odds_event_id=None,
            match_confidence=0.0,
            match_method='pending',
            status='manual_review',
            game_date=today
        )
        # Low confidence match
        mapping2 = create_game_mapping(
            nba_game_id='002',
            nba_home_team_id=1610612744,
            nba_away_team_id=1610612747,
            odds_event_id='odds_002',
            match_confidence=0.75,  # Low confidence
            match_method='fuzzy',
            status='matched',
            game_date=today
        )
        # High confidence match (should not be included)
        mapping3 = create_game_mapping(
            nba_game_id='003',
            nba_home_team_id=1610612755,
            nba_away_team_id=1610612738,
            odds_event_id='odds_003',
            match_confidence=1.0,
            match_method='exact',
            status='matched',
            game_date=today
        )
        db_session.add_all([mapping1, mapping2, mapping3])
        db_session.commit()

        orchestrator = SyncOrchestrator(db_session)
        queue = orchestrator.get_manual_review_queue()

        assert len(queue['unmatched_games']) == 1
        assert queue['unmatched_games'][0]['nba_game_id'] == '001'

        assert len(queue['low_confidence_matches']) == 1
        assert queue['low_confidence_matches'][0]['nba_game_id'] == '002'

    # Error Handling Tests
    # ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_sync_games_error_handling(self, db_session: Session):
        """Should handle errors gracefully and update metadata."""
        orchestrator = SyncOrchestrator(db_session)

        # Mock the adapter method to raise exception
        orchestrator.nba_adapter.fetch_games = AsyncMock(side_effect=Exception("API Error"))

        with pytest.raises(Exception, match="API Error"):
            await orchestrator.sync_games()

        # Verify metadata recorded failure
        metadata = db_session.query(SyncMetadata).filter(
            SyncMetadata.source == 'nba_api',
            SyncMetadata.data_type == 'games'
        ).first()

        assert metadata is not None
        assert metadata.last_sync_status == 'failed'
        assert 'API Error' in metadata.error_message
        assert metadata.sync_duration_ms is not None

    # Cleanup Tests
    # ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_cleanup_closes_connections(self, db_session: Session):
        """Should close odds adapter connections on cleanup."""
        orchestrator = SyncOrchestrator(db_session)

        # Initialize the odds adapter by accessing it
        _ = orchestrator.odds_adapter

        # Mock the close method
        orchestrator._odds_adapter.close = AsyncMock()

        await orchestrator.cleanup()

        orchestrator._odds_adapter.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_with_no_adapter(self, db_session: Session):
        """Should handle cleanup when odds adapter not initialized."""
        orchestrator = SyncOrchestrator(db_session)

        # No exception should be raised
        await orchestrator.cleanup()

        assert orchestrator._odds_adapter is None
