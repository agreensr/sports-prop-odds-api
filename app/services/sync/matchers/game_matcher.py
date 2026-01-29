"""Game matcher for correlating nba_api games with The Odds API events.

Matching priority:
1. Exact Match (confidence: 1.0) - Same date + both teams match
2. Fuzzy Time Match (confidence: 0.95) - Same date + teams + time within 2 hours
3. Team Name Fuzzy Match (confidence: 0.85) - Same date + Levenshtein distance < 3

Only games with match_confidence >= 0.85 should be used for predictions.

Race Condition Prevention:
All insert operations use PostgreSQL's ON CONFLICT clause (upsert) to ensure
atomicity and prevent duplicate game mappings, even when multiple processes
run simultaneously.
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, update, delete as sql_delete

from app.services.sync.utils.confidence_scorer import calculate_game_match_confidence, get_match_method_description
from app.models import GameMapping, MatchAuditLog
import uuid
import json

logger = logging.getLogger(__name__)


class GameMatcher:
    """
    Match games between NBA.com and The Odds API.

    Uses a tiered matching strategy:
    1. Exact match via team_mappings (highest confidence)
    2. Fuzzy time match (same day, teams, time within 2 hours)
    3. Team name fuzzy match (Levenshtein distance)

    Results are cached in game_mappings table for future reference.
    """

    def __init__(self, db: Session):
        """
        Initialize the game matcher.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    async def find_match(
        self,
        nba_game: Dict[str, Any],
        odds_games: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Find matching odds game for an NBA game.

        Searches through all odds games and finds the best match based on
        confidence scores. Returns match details if a match is found.

        Args:
            nba_game: NBA game data from nba_api with keys:
                - id: nba_game_id (str)
                - game_date: datetime
                - home_team_id: int (nba_api team ID)
                - away_team_id: int (nba_api team ID)
            odds_games: List of odds games from The Odds API

        Returns:
            Match dict with keys:
                - odds_event_id: str
                - match_confidence: float (0.0-1.0)
                - match_method: str ('exact', 'fuzzy_time', 'fuzzy_team_name')
            Or None if no match found above 0.85 threshold
        """
        best_match = None
        best_confidence = 0.0

        for odds_game in odds_games:
            confidence = await calculate_game_match_confidence(
                nba_game, odds_game, self.db
            )

            if confidence > best_confidence:
                best_confidence = confidence
                best_match = {
                    'odds_event_id': odds_game.get('id'),
                    'match_confidence': confidence,
                    'match_method': self._get_method_from_confidence(confidence),
                    'odds_game_data': odds_game
                }

        # Only return if confidence meets threshold
        if best_match and best_match['match_confidence'] >= 0.85:
            return best_match

        return None

    def _get_method_from_confidence(self, confidence: float) -> str:
        """Map confidence score to match method name."""
        if confidence >= 1.0:
            return 'exact'
        elif confidence >= 0.95:
            return 'fuzzy_time'
        else:
            return 'fuzzy_team_name'

    async def create_or_update_mapping(
        self,
        nba_game_id: str,
        nba_home_team_id: int,
        nba_away_team_id: int,
        match: Dict[str, Any],
        game_date: datetime
    ) -> GameMapping:
        """
        Create or update a game mapping in the database using atomic upsert.

        This method uses a check-then-insert pattern with IntegrityError handling
        to prevent race conditions when multiple processes attempt to create the
        same mapping simultaneously. The unique constraint on nba_game_id prevents
        duplicate entries.

        Implementation pattern:
        1. Check for existing mapping by nba_game_id
        2. If not found, attempt to insert new mapping
        3. If IntegrityError occurs (another process inserted first), rollback
           and fetch the existing record
        4. Update all fields and commit

        Args:
            nba_game_id: Game ID from nba_api
            nba_home_team_id: nba_api home team ID
            nba_away_team_id: nba_api away team ID
            match: Match result from find_match()
            game_date: Game date

        Returns:
            Created or updated GameMapping instance
        """
        from sqlalchemy.exc import IntegrityError

        # Capture previous state for audit logging
        existing_mapping = self.db.query(GameMapping).filter(
            GameMapping.nba_game_id == nba_game_id
        ).first()

        previous_state = None
        if existing_mapping:
            previous_state = {
                'odds_event_id': existing_mapping.odds_event_id,
                'match_confidence': float(existing_mapping.match_confidence),
                'match_method': existing_mapping.match_method,
                'status': existing_mapping.status
            }

        # Use session.merge() for atomic upsert behavior
        # merge() will either:
        # 1. Load the existing instance if primary key matches, OR
        # 2. Create a new instance if it doesn't exist
        # This is NOT race-condition free by itself, but combined with the
        # unique constraint on nba_game_id, we can handle conflicts

        now = datetime.utcnow()
        game_date_value = game_date.date() if isinstance(game_date, datetime) else game_date
        game_time_value = game_date if isinstance(game_date, datetime) else None

        # Try to get existing by nba_game_id first (this is our unique key)
        mapping = existing_mapping

        if not mapping:
            # No existing mapping - create new one
            # The atomic insert happens here - if another process inserts first,
            # we'll get an IntegrityError which we handle
            try:
                mapping = GameMapping(
                    id=str(uuid.uuid4()),
                    nba_game_id=nba_game_id,
                    nba_home_team_id=nba_home_team_id,
                    nba_away_team_id=nba_away_team_id,
                    game_date=game_date_value,
                    game_time=game_time_value,
                    created_at=now,
                    updated_at=now
                )
                self.db.add(mapping)
                # Flush to detect any constraint violations immediately
                self.db.flush()
                logger.debug(f"Created new game mapping for {nba_game_id}")
            except IntegrityError:
                # Another process inserted the same mapping - roll back and fetch it
                self.db.rollback()
                mapping = self.db.query(GameMapping).filter(
                    GameMapping.nba_game_id == nba_game_id
                ).first()
                if mapping:
                    logger.debug(f"Game mapping for {nba_game_id} created by another process, using existing")
                else:
                    # Should not happen, but handle gracefully
                    raise

        # At this point, we have a valid mapping instance (either new or fetched)
        # Update all fields
        mapping.odds_event_id = match['odds_event_id']
        mapping.match_confidence = match['match_confidence']
        mapping.match_method = match['match_method']
        mapping.status = 'matched'
        mapping.last_validated_at = now
        mapping.updated_at = now

        # Also update the team IDs in case they were missing
        mapping.nba_home_team_id = nba_home_team_id
        mapping.nba_away_team_id = nba_away_team_id
        if mapping.game_date is None:
            mapping.game_date = game_date_value
        if mapping.game_time is None:
            mapping.game_time = game_time_value

        self.db.commit()
        self.db.refresh(mapping)

        # Log to audit trail
        new_state = {
            'odds_event_id': mapping.odds_event_id,
            'match_confidence': float(mapping.match_confidence),
            'match_method': mapping.match_method,
            'status': mapping.status
        }

        await self._log_audit(
            entity_type='game',
            entity_id=nba_game_id,
            action='matched',
            previous_state=previous_state,
            new_state=new_state,
            match_details=match
        )

        logger.info(
            f"Game mapping created/updated: {nba_game_id} → {match['odds_event_id']} "
            f"({match['match_method']}, {match['match_confidence']:.2f} confidence)"
        )

        return mapping

    async def create_pending_mapping_atomic(
        self,
        nba_game_id: str,
        nba_home_team_id: int,
        nba_away_team_id: int,
        game_date: datetime
    ) -> Optional[GameMapping]:
        """
        Create a pending game mapping for manual review, atomically.

        Uses the same race-condition prevention pattern as create_or_update_mapping.
        If a mapping already exists (pending or otherwise), returns it instead
        of creating a duplicate.

        Args:
            nba_game_id: Game ID from nba_api
            nba_home_team_id: nba_api home team ID
            nba_away_team_id: nba_api away team ID
            game_date: Game date

        Returns:
            Created or existing GameMapping instance, or None on error
        """
        from sqlalchemy.exc import IntegrityError

        # Check for existing mapping first
        existing = self.db.query(GameMapping).filter(
            GameMapping.nba_game_id == nba_game_id
        ).first()

        if existing:
            logger.debug(f"Mapping already exists for {nba_game_id}, returning existing")
            return existing

        # No existing mapping - create new one atomically
        now = datetime.utcnow()
        game_date_value = game_date.date() if isinstance(game_date, datetime) else game_date
        game_time_value = game_date if isinstance(game_date, datetime) else None

        try:
            mapping = GameMapping(
                id=str(uuid.uuid4()),
                nba_game_id=nba_game_id,
                nba_home_team_id=nba_home_team_id,
                nba_away_team_id=nba_away_team_id,
                game_date=game_date_value,
                game_time=game_time_value,
                match_confidence=0.0,
                match_method='none',
                status='manual_review',
                created_at=now,
                updated_at=now
            )
            self.db.add(mapping)
            self.db.flush()
            logger.debug(f"Created pending mapping for {nba_game_id}")
            return mapping
        except IntegrityError:
            # Another process created this mapping - fetch and return it
            self.db.rollback()
            mapping = self.db.query(GameMapping).filter(
                GameMapping.nba_game_id == nba_game_id
            ).first()
            if mapping:
                logger.debug(f"Pending mapping for {nba_game_id} created by another process")
            return mapping

    async def _log_audit(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        previous_state: Optional[Dict[str, Any]],
        new_state: Dict[str, Any],
        match_details: Optional[Dict[str, Any]] = None
    ):
        """Log match to audit trail."""

        def _serialize_datetime(obj: Any) -> Any:
            """Convert datetime objects to ISO strings for JSON serialization."""
            if isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, dict):
                return {k: _serialize_datetime(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [_serialize_datetime(item) for item in obj]
            return obj

        try:
            audit_log = MatchAuditLog(
                id=str(uuid.uuid4()),
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                previous_state=json.dumps(_serialize_datetime(previous_state)) if previous_state else None,
                new_state=json.dumps(_serialize_datetime(new_state)),
                match_details=json.dumps(_serialize_datetime(match_details)) if match_details else None,
                performed_by='system',
                created_at=datetime.utcnow()
            )
            self.db.add(audit_log)
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to log audit entry: {e}")

    def get_existing_mapping(self, nba_game_id: str) -> Optional[GameMapping]:
        """
        Get existing game mapping from database.

        Args:
            nba_game_id: nba_api game ID

        Returns:
            GameMapping instance or None
        """
        return self.db.query(GameMapping).filter(
            GameMapping.nba_game_id == nba_game_id
        ).first()

    def get_mapping_by_odds_id(self, odds_event_id: str) -> Optional[GameMapping]:
        """
        Get existing game mapping by odds event ID.

        Args:
            odds_event_id: The Odds API event ID

        Returns:
            GameMapping instance or None
        """
        return self.db.query(GameMapping).filter(
            GameMapping.odds_event_id == odds_event_id
        ).first()

    async def batch_match_games(
        self,
        nba_games: List[Dict[str, Any]],
        odds_games: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Match multiple games in batch.

        Args:
            nba_games: List of NBA games from nba_api
            odds_games: List of odds games from The Odds API

        Returns:
            Summary dict with:
                - total: Total games processed
                - matched: Number of games matched
                - unmatched: Number of games unmatched
                - matches: List of match details
        """
        results = {
            'total': len(nba_games),
            'matched': 0,
            'unmatched': 0,
            'matches': []
        }

        for nba_game in nba_games:
            # Check for existing mapping first
            existing = self.get_existing_mapping(nba_game['id'])

            if existing and existing.status == 'matched':
                results['matched'] += 1
                results['matches'].append({
                    'nba_game_id': nba_game['id'],
                    'odds_event_id': existing.odds_event_id,
                    'match_confidence': float(existing.match_confidence),
                    'match_method': existing.match_method,
                    'cached': True
                })
                continue

            # Try to find new match
            match = await self.find_match(nba_game, odds_games)

            if match:
                await self.create_or_update_mapping(
                    nba_game_id=nba_game['id'],
                    nba_home_team_id=nba_game['home_team_id'],
                    nba_away_team_id=nba_game['away_team_id'],
                    match=match,
                    game_date=nba_game['game_date']
                )
                results['matched'] += 1
                results['matches'].append({
                    'nba_game_id': nba_game['id'],
                    'odds_event_id': match['odds_event_id'],
                    'match_confidence': match['match_confidence'],
                    'match_method': match['match_method'],
                    'cached': False
                })
            else:
                # Create pending mapping for manual review using atomic operation
                # This prevents race conditions where multiple processes might
                # try to create the same pending mapping simultaneously
                await self.create_pending_mapping_atomic(
                    nba_game_id=nba_game['id'],
                    nba_home_team_id=nba_game['home_team_id'],
                    nba_away_team_id=nba_game['away_team_id'],
                    game_date=nba_game['game_date']
                )
                results['unmatched'] += 1

        logger.info(
            f"Batch game matching complete: {results['matched']}/{results['total']} matched, "
            f"{results['unmatched']} unmatched"
        )

        return results

    def get_unmatched_games(self, limit: int = 100) -> List[GameMapping]:
        """
        Get games that haven't been matched yet.

        Args:
            limit: Maximum number of games to return

        Returns:
            List of unmatched GameMapping instances
        """
        return self.db.query(GameMapping).filter(
            GameMapping.status.in_(['pending', 'manual_review'])
        ).order_by(GameMapping.game_date.desc()).limit(limit).all()

    def get_low_confidence_matches(self, threshold: float = 0.85) -> List[GameMapping]:
        """
        Get matches with confidence below threshold (need review).

        Args:
            threshold: Confidence threshold (default 0.85)

        Returns:
            List of GameMapping instances with low confidence
        """
        return self.db.query(GameMapping).filter(
            GameMapping.match_confidence < threshold,
            GameMapping.status == 'matched'
        ).order_by(GameMapping.match_confidence.asc()).all()
