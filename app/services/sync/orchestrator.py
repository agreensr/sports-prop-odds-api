"""Sync orchestrator for coordinating data sync between nba_api and The Odds API.

This orchestrator coordinates:
- Game fetching from both APIs
- Matching games via GameMatcher
- Player identity resolution via PlayerResolver
- Sync metadata tracking
- Health monitoring

Sync Schedule (recommended cron):
- nba_games_full: "0 6,18 * * *" (twice daily at 6am/6pm UTC)
- odds_current: "*/5 10-23 * * *" (every 5 min during games)
- nba_player_stats: "0 * * * *" (hourly)
- game_matching: "*/15 * * * *" (every 15 min)
- cleanup: "0 4 * * *" (daily at 4am UTC)
"""
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
import uuid
import json

from app.services.sync.matchers.game_matcher import GameMatcher
from app.services.sync.matchers.player_resolver import PlayerResolver
from app.services.sync.adapters.nba_api_adapter import NbaApiAdapter
from app.services.sync.adapters.odds_api_adapter import OddsApiAdapter
from app.models.nba.models import (
    GameMapping, PlayerAlias, TeamMapping, SyncMetadata, MatchAuditLog
)

logger = logging.getLogger(__name__)


class SyncOrchestrator:
    """
    Coordinates sync jobs between nba_api and odds_api.

    This is the main entry point for the data sync layer.
    All sync operations should go through this orchestrator.
    """

    def __init__(self, db: Session):
        """
        Initialize the sync orchestrator.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self.game_matcher = GameMatcher(db)
        self.player_resolver = PlayerResolver(db)
        self.nba_adapter = NbaApiAdapter(db)

        # Lazy load odds adapter (needs API key)
        self._odds_adapter = None

    @property
    def odds_adapter(self) -> OddsApiAdapter:
        """Lazy load odds adapter."""
        if self._odds_adapter is None:
            self._odds_adapter = OddsApiAdapter(self.db)
        return self._odds_adapter

    async def sync_games(
        self,
        lookback_days: int = 7,
        lookahead_days: int = 14,
        season: str = "2025-26"
    ) -> Dict:
        """
        Sync upcoming and recent games from nba_api and match with odds_api.

        This is the primary sync operation that:
        1. Fetches games from nba_api
        2. Fetches odds from odds_api
        3. Matches games via GameMatcher
        4. Stores matches in game_mappings
        5. Updates sync_metadata

        Args:
            lookback_days: How many days back to sync
            lookahead_days: How many days ahead to sync
            season: NBA season

        Returns:
            Sync results with counts
        """
        start_time = datetime.utcnow()
        logger.info(
            f"Starting games sync: {lookback_days} days back, "
            f"{lookahead_days} days ahead"
        )

        # Get or create sync metadata
        metadata = self._get_or_create_metadata('nba_api', 'games')
        metadata.last_sync_started_at = start_time
        self.db.flush()  # Flush instead of commit

        try:
            # Fetch games from nba_api
            nba_games = await self.nba_adapter.fetch_games(
                lookback_days=lookback_days,
                lookahead_days=lookahead_days,
                season=season
            )

            if not nba_games:
                logger.warning("No NBA games fetched")
                return {
                    'success': False,
                    'processed': 0,
                    'matched': 0,
                    'unmatched': 0,
                    'error': 'No games fetched from nba_api'
                }

            # Fetch odds from odds_api
            odds_games = await self.odds_adapter.fetch_odds(
                upcoming_only=False,
                days=lookback_days + lookahead_days
            )

            if not odds_games:
                logger.warning("No odds games fetched")
                # Continue anyway - games might still be cached

            # Batch match games
            match_results = await self.game_matcher.batch_match_games(
                nba_games=nba_games,
                odds_games=odds_games
            )

            # Calculate duration
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Update metadata with success
            metadata.last_sync_completed_at = datetime.utcnow()
            metadata.last_sync_status = 'success'
            metadata.records_processed = len(nba_games)
            metadata.records_matched = match_results['matched']
            metadata.records_failed = match_results['unmatched']
            metadata.sync_duration_ms = duration_ms
            self.db.commit()

            logger.info(
                f"Games sync complete: {match_results['matched']}/"
                f"{match_results['total']} matched, "
                f"{match_results['unmatched']} unmatched "
                f"({duration_ms}ms)"
            )

            return {
                'success': True,
                'processed': match_results['total'],
                'matched': match_results['matched'],
                'unmatched': match_results['unmatched'],
                'duration_ms': duration_ms,
                'matches': match_results['matches']
            }

        except Exception as e:
            logger.error(f"Games sync failed: {e}")
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            metadata.last_sync_status = 'failed'
            metadata.error_message = str(e)
            metadata.sync_duration_ms = duration_ms
            self.db.commit()

            raise

    async def sync_odds(
        self,
        upcoming_only: bool = True,
        days: int = 7
    ) -> Dict:
        """
        Sync odds from odds_api.

        Fetches current odds and caches them. This is a lightweight
        operation that should run frequently during games.

        Args:
            upcoming_only: Only fetch upcoming games
            days: Number of days ahead to fetch

        Returns:
            Sync results
        """
        start_time = datetime.utcnow()
        logger.info(f"Starting odds sync (upcoming_only={upcoming_only}, days={days})")

        # Get or create sync metadata
        metadata = self._get_or_create_metadata('odds_api', 'odds')
        metadata.last_sync_started_at = start_time
        self.db.commit()

        try:
            # Fetch odds
            odds_games = await self.odds_adapter.fetch_odds(
                upcoming_only=upcoming_only,
                days=days
            )

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Update metadata
            metadata.last_sync_completed_at = datetime.utcnow()
            metadata.last_sync_status = 'success'
            metadata.records_processed = len(odds_games)
            metadata.sync_duration_ms = duration_ms
            self.db.commit()

            logger.info(f"Odds sync complete: {len(odds_games)} games fetched ({duration_ms}ms)")

            return {
                'success': True,
                'processed': len(odds_games),
                'duration_ms': duration_ms
            }

        except Exception as e:
            logger.error(f"Odds sync failed: {e}")
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            metadata.last_sync_status = 'failed'
            metadata.error_message = str(e)
            metadata.sync_duration_ms = duration_ms
            self.db.commit()

            raise

    async def sync_player_stats(
        self,
        games_limit: int = 50,
        season: str = "2025-26"
    ) -> Dict:
        """
        Sync player boxscores from nba_api.

        Fetches per-36 stats for all active players and caches
        them in player_season_stats table.

        Args:
            games_limit: Number of games to average
            season: NBA season

        Returns:
            Sync results
        """
        start_time = datetime.utcnow()
        logger.info(f"Starting player stats sync (season={season})")

        # Get or create sync metadata
        metadata = self._get_or_create_metadata('nba_api', 'player_stats')
        metadata.last_sync_started_at = start_time
        self.db.commit()

        try:
            # Sync via nba_adapter
            results = await self.nba_adapter.sync_all_player_stats(
                games_limit=games_limit,
                season=season
            )

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Update metadata
            metadata.last_sync_completed_at = datetime.utcnow()
            metadata.last_sync_status = 'success'
            metadata.records_processed = results['total']
            metadata.records_matched = results['success']
            metadata.records_failed = results['errors'] + results['no_data']
            metadata.sync_duration_ms = duration_ms
            self.db.commit()

            logger.info(
                f"Player stats sync complete: {results['success']}/{results['total']} "
                f"successful ({duration_ms}ms)"
            )

            return results

        except Exception as e:
            logger.error(f"Player stats sync failed: {e}")
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            metadata.last_sync_status = 'failed'
            metadata.error_message = str(e)
            metadata.sync_duration_ms = duration_ms
            self.db.commit()

            raise

    async def reconcile_matches(
        self,
        limit: int = 100
    ) -> Dict:
        """
        Run matching engine on unmatched games.

        Called periodically to re-attempt matching for games
        that previously failed to match.

        Args:
            limit: Maximum number of games to process

        Returns:
            Reconciliation results
        """
        start_time = datetime.utcnow()
        logger.info(f"Starting match reconciliation (limit={limit})")

        try:
            # Get unmatched games
            unmatched = self.game_matcher.get_unmatched_games(limit=limit)

            if not unmatched:
                logger.info("No unmatched games to reconcile")
                return {
                    'success': True,
                    'processed': 0,
                    'reconciled': 0
                }

            # For each unmatched game, try to match again
            reconciled = 0
            for mapping in unmatched:
                # This would require fetching odds again and matching
                # For now, we'll just log it
                logger.debug(f"Would reconcile game {mapping.nba_game_id}")

            logger.info(f"Reconciliation complete: {reconciled}/{len(unmatched)} reconciled")

            return {
                'success': True,
                'processed': len(unmatched),
                'reconciled': reconciled
            }

        except Exception as e:
            logger.error(f"Reconciliation failed: {e}")
            raise

    def get_sync_status(self) -> Dict:
        """
        Return overall sync health status.

        Aggregates status from all sync_metadata entries.

        Returns:
            Dict with overall sync health
        """
        # Get all sync metadata
        all_metadata = self.db.query(SyncMetadata).all()

        # Count by status
        status_counts = {}
        last_sync_times = {}
        total_processed = 0
        total_matched = 0
        total_failed = 0

        for metadata in all_metadata:
            key = f"{metadata.source}_{metadata.data_type}"
            status_counts[key] = metadata.last_sync_status
            last_sync_times[key] = metadata.last_sync_completed_at
            total_processed += metadata.records_processed or 0
            total_matched += metadata.records_matched or 0
            total_failed += metadata.records_failed or 0

        # Get unmatched games count
        unmatched_count = self.db.query(GameMapping).filter(
            GameMapping.status.in_(['pending', 'manual_review'])
        ).count()

        # Get low confidence matches
        low_confidence_count = self.db.query(GameMapping).filter(
            GameMapping.match_confidence < 0.85,
            GameMapping.status == 'matched'
        ).count()

        # Determine overall health
        total_jobs = len(all_metadata)
        success_count = sum(1 for m in all_metadata if m.last_sync_status == 'success')
        health_status = 'healthy' if success_count == total_jobs else 'degraded' if success_count > 0 else 'unhealthy'

        return {
            'health_status': health_status,
            'total_jobs': total_jobs,
            'success_count': success_count,
            'status_by_job': status_counts,
            'last_sync_times': {
                k: v.isoformat() if v else None
                for k, v in last_sync_times.items()
            },
            'totals': {
                'processed': total_processed,
                'matched': total_matched,
                'failed': total_failed
            },
            'issues': {
                'unmatched_games': unmatched_count,
                'low_confidence_matches': low_confidence_count
            }
        }

    def get_matched_games(
        self,
        game_date: Optional[date] = None
    ) -> List[Dict]:
        """
        Get games with verified nba+odds mapping.

        Args:
            game_date: Filter by specific date (optional)

        Returns:
            List of matched game dicts
        """
        query = self.db.query(GameMapping).filter(
            GameMapping.status == 'matched',
            GameMapping.match_confidence >= 0.85
        )

        if game_date:
            query = query.filter(GameMapping.game_date == game_date)

        mappings = query.order_by(GameMapping.game_date.desc()).all()

        result = []
        for mapping in mappings:
            result.append({
                'nba_game_id': mapping.nba_game_id,
                'odds_event_id': mapping.odds_event_id,
                'game_date': mapping.game_date.isoformat(),
                'match_confidence': float(mapping.match_confidence),
                'match_method': mapping.match_method,
                'last_validated_at': mapping.last_validated_at.isoformat() if mapping.last_validated_at else None
            })

        return result

    def get_manual_review_queue(self) -> Dict:
        """
        Get games and players requiring manual review.

        Returns:
            Dict with unmatched games and low confidence matches
        """
        # Get unmatched games
        unmatched_games = self.db.query(GameMapping).filter(
            GameMapping.status.in_(['pending', 'manual_review'])
        ).order_by(GameMapping.game_date.desc()).limit(50).all()

        # Get low confidence matches
        low_confidence = self.db.query(GameMapping).filter(
            GameMapping.match_confidence < 0.85,
            GameMapping.status == 'matched'
        ).order_by(GameMapping.match_confidence.asc()).limit(20).all()

        return {
            'unmatched_games': [
                {
                    'nba_game_id': m.nba_game_id,
                    'game_date': m.game_date.isoformat(),
                    'status': m.status
                }
                for m in unmatched_games
            ],
            'low_confidence_matches': [
                {
                    'nba_game_id': m.nba_game_id,
                    'odds_event_id': m.odds_event_id,
                    'game_date': m.game_date.isoformat(),
                    'match_confidence': float(m.match_confidence),
                    'match_method': m.match_method
                }
                for m in low_confidence
            ]
        }

    def _get_or_create_metadata(
        self,
        source: str,
        data_type: str
    ) -> SyncMetadata:
        """Get or create sync metadata entry."""
        metadata = self.db.query(SyncMetadata).filter(
            SyncMetadata.source == source,
            SyncMetadata.data_type == data_type
        ).first()

        if not metadata:
            metadata = SyncMetadata(
                id=str(uuid.uuid4()),
                source=source,
                data_type=data_type
            )
            self.db.add(metadata)
            # Don't commit here - let the caller handle commit/rollback
            self.db.flush()

        return metadata

    async def cleanup(self):
        """Close any open connections."""
        if self._odds_adapter:
            await self._odds_adapter.close()
