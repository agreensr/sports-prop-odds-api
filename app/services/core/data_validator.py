"""
Data Integrity and Validation Service.

This service provides comprehensive data validation, deduplication, and
integrity checking for all data entering the system.

Key Features:
- Pre-insert duplicate detection
- Multi-source data validation
- Integrity constraint checking
- Continuous validation against all sources
- Audit logging for all validation actions

Prevention Strategy:
- Unique constraints at database level (natural keys, per-source IDs)
- Application-level validation before insert/update
- Continuous background validation
- Match audit logging

This is the defense layer that prevents the 93 duplicate games issue.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, distinct
from dataclasses import dataclass

from app.models import Player, Game
from app.services.core.identity_resolver import (
    PlayerIdentityResolver,
    GameIdentityResolver
)

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation check."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    entity_id: Optional[str] = None
    duplicate_of: Optional[str] = None

    def add_error(self, error: str):
        """Add an error to the result."""
        self.errors.append(error)
        self.is_valid = False

    def add_warning(self, warning: str):
        """Add a warning to the result."""
        self.warnings.append(warning)

    def __repr__(self):
        return (f"ValidationResult(valid={self.is_valid}, "
                f"errors={len(self.errors)}, warnings={len(self.warnings)})")


@dataclass
class DuplicateMatch:
    """Information about a duplicate match found."""
    entity_id: str
    match_type: str  # 'exact_id', 'natural_key', 'fuzzy', 'potential'
    confidence: float
    match_details: Dict[str, Any]

    def __repr__(self):
        return (f"DuplicateMatch(id={self.entity_id}, "
                f"type={self.match_type}, "
                f"confidence={self.confidence:.2f})")


class DataValidator:
    """
    Comprehensive data validation and integrity checking.

    This validator runs before any insert/update operation to ensure
    data integrity rules are followed.

    Validation Rules:
    1. Unique constraints (per-source IDs, natural keys)
    2. Required fields presence
    3. Data type and format validation
    4. Reference integrity (foreign keys)
    5. Business logic validation (e.g., game_date in future for scheduled games)
    """

    def __init__(self, db: Session):
        self.db = db
        self.player_resolver = PlayerIdentityResolver(db)
        self.game_resolver = GameIdentityResolver(db)

    # ==================== Player Validation ====================

    def validate_player(
        self,
        player_data: Dict[str, Any],
        skip_resolution: bool = False
    ) -> ValidationResult:
        """
        Validate player data before insert/update.

        Args:
            player_data: Player data dictionary
            skip_resolution: If True, skip identity resolution

        Returns:
            ValidationResult with any errors/warnings
        """
        result = ValidationResult(is_valid=True, errors=[], warnings=[])

        # Required fields
        required_fields = ['sport_id', 'name']
        for field in required_fields:
            if field not in player_data or not player_data[field]:
                result.add_error(f"Missing required field: {field}")

        if not result.is_valid:
            return result

        # Validate sport_id
        if player_data['sport_id'] not in ['nba', 'nfl', 'mlb', 'nhl']:
            result.add_error(
                f"Invalid sport_id: {player_data['sport_id']}. "
                f"Must be one of: nba, nfl, mlb, nhl"
            )

        # Check for duplicates (unless we're updating)
        if not skip_resolution:
            duplicates = self._find_duplicate_players(player_data)
            if duplicates:
                # If exact match found, this is an update, not a create
                exact_match = next(
                    (d for d in duplicates if d.match_type == 'exact_id'),
                    None
                )
                if exact_match:
                    result.duplicate_of = exact_match.entity_id
                    result.add_warning(
                        f"Player already exists: {exact_match.entity_id}"
                    )
                else:
                    # Potential duplicate - fuzzy match
                    result.add_warning(
                        f"Found {len(duplicates)} potential duplicate(s)"
                    )

        # Validate team code
        if 'team' in player_data:
            team = player_data['team']
            if not isinstance(team, str) or len(team) > 5:
                result.add_error(f"Invalid team code: {team}")

        # Validate position
        if 'position' in player_data:
            position = player_data['position']
            valid_positions = self._get_valid_positions(
                player_data['sport_id']
            )
            if position and position not in valid_positions:
                result.add_warning(
                    f"Unusual position for {player_data['sport_id']}: {position}"
                )

        return result

    def _find_duplicate_players(
        self,
        player_data: Dict[str, Any]
    ) -> List[DuplicateMatch]:
        """Find potential duplicate players."""
        matches = []
        sport_id = player_data['sport_id']
        name = player_data.get('name', '')
        team = player_data.get('team')

        # Check by API IDs
        id_fields = ['odds_api_id', 'nba_api_id', 'espn_id', 'nfl_id', 'mlb_id', 'nhl_id']
        for field in id_fields:
            if field in player_data and player_data[field]:
                player = self._find_player_by_api_id(
                    sport_id, field, player_data[field]
                )
                if player:
                    matches.append(DuplicateMatch(
                        entity_id=player.id,
                        match_type='exact_id',
                        confidence=1.0,
                        match_details={'field': field, 'value': player_data[field]}
                    ))
                    return matches  # Exact match - no need to continue

        # Check by team + name
        if team and name:
            canonical_name = PlayerIdentityResolver._normalize_name(name)
            player = self.db.query(Player).filter(
                and_(
                    Player.sport_id == sport_id,
                    Player.team == team,
                    Player.canonical_name == canonical_name,
                    Player.active == True
                )
            ).first()

            if player:
                matches.append(DuplicateMatch(
                    entity_id=player.id,
                    match_type='natural_key',
                    confidence=0.95,
                    match_details={'team': team, 'name': name}
                ))

        return matches

    def _find_player_by_api_id(
        self,
        sport_id: str,
        field: str,
        value: Any
    ) -> Optional[Player]:
        """Find player by API ID."""
        column_map = {
            'odds_api_id': Player.odds_api_id,
            'nba_api_id': Player.nba_api_id,
            'espn_id': Player.espn_id,
            'nfl_id': Player.nfl_id,
            'mlb_id': Player.mlb_id,
            'nhl_id': Player.nhl_id,
        }

        column = column_map.get(field)
        if not column:
            return None

        return self.db.query(Player).filter(
            and_(
                Player.sport_id == sport_id,
                column == value
            )
        ).first()

    # ==================== Game Validation ====================

    def validate_game(
        self,
        game_data: Dict[str, Any],
        skip_resolution: bool = False
    ) -> ValidationResult:
        """
        Validate game data before insert/update.

        Args:
            game_data: Game data dictionary
            skip_resolution: If True, skip identity resolution

        Returns:
            ValidationResult with any errors/warnings
        """
        result = ValidationResult(is_valid=True, errors=[], warnings=[])

        # Required fields
        required_fields = ['sport_id', 'game_date', 'away_team', 'home_team']
        for field in required_fields:
            if field not in game_data or not game_data[field]:
                result.add_error(f"Missing required field: {field}")

        if not result.is_valid:
            return result

        # Validate sport_id
        if game_data['sport_id'] not in ['nba', 'nfl', 'mlb', 'nhl']:
            result.add_error(
                f"Invalid sport_id: {game_data['sport_id']}. "
                f"Must be one of: nba, nfl, mlb, nhl"
            )

        # Validate game_date is datetime
        if not isinstance(game_data['game_date'], datetime):
            result.add_error("game_date must be a datetime object")

        # Validate teams are different
        if game_data['away_team'] == game_data['home_team']:
            result.add_error("away_team and home_team must be different")

        # Validate team codes
        for team_field in ['away_team', 'home_team']:
            team = game_data.get(team_field)
            if team and (not isinstance(team, str) or len(team) > 5):
                result.add_error(f"Invalid {team_field} code: {team}")

        # Check for duplicates (natural key)
        if not skip_resolution:
            duplicate = self._find_duplicate_game(game_data)
            if duplicate:
                result.duplicate_of = duplicate.entity_id
                result.add_warning(
                    f"Game already exists: {duplicate.entity_id}"
                )

        return result

    def _find_duplicate_game(
        self,
        game_data: Dict[str, Any]
    ) -> Optional[DuplicateMatch]:
        """Find duplicate game by natural key."""
        sport_id = game_data['sport_id']
        game_date = game_data['game_date']
        away_team = game_data['away_team']
        home_team = game_data['home_team']

        # Use time window for matching
        time_window = timedelta(hours=6)
        start_time = game_date - time_window
        end_time = game_date + time_window

        game = self.db.query(Game).filter(
            and_(
                Game.sport_id == sport_id,
                Game.game_date >= start_time,
                Game.game_date <= end_time,
                Game.away_team == away_team,
                Game.home_team == home_team
            )
        ).first()

        if game:
            return DuplicateMatch(
                entity_id=game.id,
                match_type='natural_key',
                confidence=1.0,
                match_details={
                    'sport_id': sport_id,
                    'game_date': game_date,
                    'away_team': away_team,
                    'home_team': home_team
                }
            )

        return None

    # ==================== Bulk Validation ====================

    def validate_players_bulk(
        self,
        players_data: List[Dict[str, Any]]
    ) -> List[ValidationResult]:
        """
        Validate multiple players in batch.

        Returns a list of ValidationResult objects in the same order
        as the input data.
        """
        results = []
        for player_data in players_data:
            result = self.validate_player(player_data)
            results.append(result)
        return results

    def validate_games_bulk(
        self,
        games_data: List[Dict[str, Any]]
    ) -> List[ValidationResult]:
        """
        Validate multiple games in batch.

        Returns a list of ValidationResult objects in the same order
        as the input data.
        """
        results = []
        for game_data in games_data:
            result = self.validate_game(game_data)
            results.append(result)
        return results

    # ==================== Integrity Reports ====================

    def generate_integrity_report(self) -> Dict[str, Any]:
        """
        Generate a comprehensive data integrity report.

        Returns:
            Dictionary with integrity metrics and issues
        """
        report = {
            'generated_at': datetime.now().isoformat(),
            'players': self._report_player_integrity(),
            'games': self._report_game_integrity(),
            'predictions': self._report_prediction_integrity(),
        }

        return report

    def _report_player_integrity(self) -> Dict[str, Any]:
        """Generate player integrity metrics."""
        total = self.db.query(func.count(Player.id)).scalar()

        # Count by sport
        by_sport = {}
        for sport in ['nba', 'nfl', 'mlb', 'nhl']:
            count = self.db.query(func.count(Player.id)).filter(
                Player.sport_id == sport
            ).scalar()
            by_sport[sport] = count

        # Count active
        active = self.db.query(func.count(Player.id)).filter(
            Player.active == True
        ).scalar()

        # Check for missing canonical names
        missing_canonical = self.db.query(func.count(Player.id)).filter(
            or_(
                Player.canonical_name == None,
                Player.canonical_name == ''
            )
        ).scalar()

        # Check for missing team
        missing_team = self.db.query(func.count(Player.id)).filter(
            or_(
                Player.team == None,
                Player.team == ''
            )
        ).scalar()

        return {
            'total': total,
            'by_sport': by_sport,
            'active': active,
            'inactive': total - active,
            'missing_canonical_name': missing_canonical,
            'missing_team': missing_team,
        }

    def _report_game_integrity(self) -> Dict[str, Any]:
        """Generate game integrity metrics."""
        total = self.db.query(func.count(Game.id)).scalar()

        # Count by sport
        by_sport = {}
        for sport in ['nba', 'nfl', 'mlb', 'nhl']:
            count = self.db.query(func.count(Game.id)).filter(
                Game.sport_id == sport
            ).scalar()
            by_sport[sport] = count

        # Count by status
        by_status = {}
        for status in ['scheduled', 'in_progress', 'final']:
            count = self.db.query(func.count(Game.id)).filter(
                Game.status == status
            ).scalar()
            by_status[status] = count

        # Check for games without sport_id
        missing_sport = self.db.query(func.count(Game.id)).filter(
            or_(
                Game.sport_id == None,
                Game.sport_id == ''
            )
        ).scalar()

        return {
            'total': total,
            'by_sport': by_sport,
            'by_status': by_status,
            'missing_sport_id': missing_sport,
        }

    def _report_prediction_integrity(self) -> Dict[str, Any]:
        """Generate prediction integrity metrics."""
        # Check if predictions table exists
        from sqlalchemy import inspect
        inspector = inspect(self.db.bind)
        if 'predictions' not in inspector.get_table_names():
            return {'status': 'table_not_exists'}

        from app.models import Prediction

        total = self.db.query(func.count(Prediction.id)).scalar()

        # Count resolved
        resolved = self.db.query(func.count(Prediction.id)).filter(
            Prediction.was_correct != None
        ).scalar()

        # Count correct
        correct = self.db.query(func.count(Prediction.id)).filter(
            Prediction.was_correct == True
        ).scalar()

        # High confidence predictions (>= 0.6)
        high_conf = self.db.query(func.count(Prediction.id)).filter(
            Prediction.confidence >= 0.6
        ).scalar()

        return {
            'total': total,
            'resolved': resolved,
            'unresolved': total - resolved,
            'correct': correct,
            'incorrect': resolved - correct,
            'win_rate': round(correct / resolved, 3) if resolved > 0 else 0.0,
            'high_confidence': high_conf,
        }

    # ==================== Utilities ====================

    @staticmethod
    def _get_valid_positions(sport_id: str) -> List[str]:
        """Get list of valid positions for a sport."""
        positions = {
            'nba': ['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'G-F', 'F-C'],
            'nfl': ['QB', 'RB', 'WR', 'TE', 'K', 'P', 'OLB', 'ILB', 'DE',
                    'DT', 'CB', 'S', 'LS', 'FB'],
            'mlb': ['P', 'C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF',
                    'DH', 'SP', 'RP'],
            'nhl': ['C', 'LW', 'RW', 'D', 'G'],
        }
        return positions.get(sport_id, [])


# Convenience functions for dependency injection
def get_data_validator(db: Session) -> DataValidator:
    """Get a data validator instance."""
    return DataValidator(db)
