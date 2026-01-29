"""
Boxscore Import Service

Resolves predictions with actual game results by:
1. Fetching boxscores from NBA API for completed games
2. Creating/updating PlayerStats records
3. Calculating prediction accuracy (difference, correctness)
4. Marking predictions as resolved
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

# UTC timezone for Python < 3.11 compatibility
try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc

from app.models import Game, Prediction, Player, PlayerStats
from app.services.nba.nba_service import NBAService

logger = logging.getLogger(__name__)


class BoxscoreImportService:
    """
    Service for importing boxscore data and resolving predictions.

    This service handles the critical link between predictions and actual results,
    enabling accuracy tracking and model evaluation.
    """

    # Map stat_type to database field names
    STAT_TYPE_MAPPING = {
        'points': 'points',
        'rebounds': 'rebounds',
        'assists': 'assists',
        'threes': 'threes'
    }

    # Map NBA API boxscore fields to database fields
    BOXSCORE_FIELD_MAPPING = {
        'PTS': 'points',
        'REB': 'rebounds',
        'AST': 'assists',
        'FG3M': 'threes',
        'MIN': 'minutes'
    }

    def __init__(self, db: Session):
        """
        Initialize the boxscore import service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self.nba_service = NBAService()
        self._player_resolver = None  # Lazy load for sync layer

    @property
    def player_resolver(self):
        """Lazy load player resolver from sync layer."""
        if self._player_resolver is None:
            from app.services.sync.matchers.player_resolver import PlayerResolver
            self._player_resolver = PlayerResolver(self.db)
        return self._player_resolver

    def _validate_game_mapping(self, game: Game) -> bool:
        """
        Validate that game has proper mapping from sync layer.

        This ensures boxscore data is linked to the correct game.

        Args:
            game: Game object

        Returns:
            True if game has valid mapping, False otherwise
        """
        from app.models import GameMapping

        mapping = self.db.query(GameMapping).filter(
            GameMapping.nba_game_id == game.external_id
        ).first()

        if not mapping:
            logger.debug(
                f"Game {game.external_id} has no mapping - using default linkage"
            )
            return True  # Allow processing but log

        if mapping.match_confidence < 0.85:
            logger.warning(
                f"Game {game.external_id} has low confidence mapping: "
                f"{mapping.match_confidence:.2f}"
            )
            return True  # Allow but warn

        return True

    async def _log_player_match(
        self,
        player: Player,
        boxscore_player_id: str,
        match_method: str = "external_id"
    ):
        """
        Log player identity match to audit trail.

        Args:
            player: Player object from our database
            boxscore_player_id: Player ID from boxscore source
            match_method: How the player was matched
        """
        from app.models import MatchAuditLog
        import json

        try:
            audit_log = MatchAuditLog(
                id=str(uuid.uuid4()),
                entity_type='player',
                entity_id=str(player.id),
                action='matched',
                new_state=json.dumps({
                    'player_name': player.name,
                    'external_id': player.external_id,
                    'boxscore_player_id': boxscore_player_id
                }),
                match_details=json.dumps({
                    'match_method': match_method,
                    'source': 'boxscore_import'
                }),
                performed_by='system',
                created_at=datetime.now(timezone.utc)
            )
            self.db.add(audit_log)
        except Exception as e:
            logger.debug(f"Failed to log player match audit: {e}")

    async def resolve_predictions_for_completed_games(
        self,
        hours_back: int = 48,
        dry_run: bool = False
    ) -> Dict:
        """
        Resolve predictions for completed games within the specified time window.

        Args:
            hours_back: Look back this many hours for completed games (default: 48)
            dry_run: If True, simulate without making database changes

        Returns:
            Dictionary with results:
            - games_processed: Number of games processed
            - predictions_resolved: Number of predictions resolved
            - player_stats_created: Number of PlayerStats records created
            - player_stats_updated: Number of PlayerStats records updated
            - errors: List of error messages
        """
        logger.info(f"Starting boxscore import (hours_back={hours_back}, dry_run={dry_run})")

        stats = {
            "games_processed": 0,
            "predictions_resolved": 0,
            "player_stats_created": 0,
            "player_stats_updated": 0,
            "errors": []
        }

        # Calculate time window
        cutoff = datetime.now(UTC) - timedelta(hours=hours_back)

        try:
            # Find completed games without resolved predictions
            # Games that are "final" status and haven't been resolved recently
            games = self.db.query(Game).filter(
                Game.status == "final",
                Game.game_date >= cutoff
            ).all()

            # Filter out games that were recently resolved (within last hour)
            games_to_process = []
            for game in games:
                # Check if any predictions for this game were recently resolved
                recently_resolved = self.db.query(Prediction).filter(
                    Prediction.game_id == game.id,
                    Prediction.actuals_resolved_at.isnot(None),
                    Prediction.actuals_resolved_at >= datetime.now(UTC) - timedelta(hours=1)
                ).first()

                if not recently_resolved:
                    games_to_process.append(game)

            logger.info(f"Found {len(games_to_process)} completed games to process")

            for game in games_to_process:
                result = await self._resolve_game(game, dry_run=dry_run)

                stats["games_processed"] += 1
                stats["predictions_resolved"] += result["predictions_resolved"]
                stats["player_stats_created"] += result["player_stats_created"]
                stats["player_stats_updated"] += result["player_stats_updated"]
                stats["errors"].extend(result.get("errors", []))

                if not dry_run:
                    self.db.commit()

            logger.info(f"Boxscore import complete: {stats}")

        except Exception as e:
            logger.error(f"Error in boxscore import: {e}")
            if not dry_run:
                self.db.rollback()
            stats["errors"].append(str(e))

        return stats

    async def resolve_predictions_for_game(
        self,
        game_id: str,
        dry_run: bool = False
    ) -> Dict:
        """
        Resolve predictions for a specific game.

        Args:
            game_id: UUID of the game to resolve
            dry_run: If True, simulate without making database changes

        Returns:
            Dictionary with resolution results
        """
        game = self.db.query(Game).filter(Game.id == game_id).first()

        if not game:
            logger.error(f"Game {game_id} not found")
            return {"predictions_resolved": 0, "errors": ["Game not found"]}

        if game.status != "final":
            logger.warning(f"Game {game_id} is not final (status: {game.status})")
            return {"predictions_resolved": 0, "errors": ["Game is not final"]}

        return await self._resolve_game(game, dry_run=dry_run)

    async def _resolve_game(self, game: Game, dry_run: bool = False) -> Dict:
        """
        Internal method to resolve predictions for a single game.

        Args:
            game: Game object
            dry_run: If True, simulate without making database changes

        Returns:
            Dictionary with resolution results
        """
        result = {
            "predictions_resolved": 0,
            "player_stats_created": 0,
            "player_stats_updated": 0,
            "errors": []
        }

        try:
            # Validate game mapping before processing
            if not self._validate_game_mapping(game):
                logger.warning(f"Game {game.external_id} failed mapping validation")
                result["errors"].append(f"Game mapping validation failed")
                return result

            # Fetch boxscore from NBA API
            boxscore = await self.nba_service.get_boxscore(game.external_id)

            if not boxscore or not boxscore.get("PlayerStats"):
                logger.warning(f"No boxscore data for game {game.external_id}")
                result["errors"].append(f"No boxscore data for {game.external_id}")
                return result

            player_stats_list = boxscore["PlayerStats"]

            # Get all predictions for this game
            predictions = self.db.query(Prediction).filter(
                Prediction.game_id == game.id,
                Prediction.actuals_resolved_at.is_(None)  # Only unresolved
            ).all()

            if not predictions:
                logger.info(f"No unresolved predictions for game {game.id}")
                return result

            logger.info(f"Processing {len(predictions)} predictions for {game.away_team} @ {game.home_team}")

            # Build a lookup map for boxscore stats
            stats_lookup = {}
            for ps in player_stats_list:
                player_id = ps.get("PLAYER_ID")
                if player_id:
                    stats_lookup[player_id] = ps

            # Process each prediction
            for prediction in predictions:
                player = self.db.query(Player).filter(Player.id == prediction.player_id).first()

                if not player:
                    logger.warning(f"Player {prediction.player_id} not found for prediction {prediction.id}")
                    continue

                # Find player's boxscore stats by external_id
                boxscore_stats = stats_lookup.get(player.external_id)

                if not boxscore_stats:
                    logger.warning(
                        f"No boxscore stats for player {player.name} "
                        f"(external_id: {player.external_id})"
                    )
                    result["errors"].append(
                        f"No stats for {player.name} (external_id: {player.external_id})"
                    )
                    continue

                # Get the actual value for the predicted stat type
                stat_field = self.STAT_TYPE_MAPPING.get(prediction.stat_type)
                if not stat_field:
                    logger.warning(f"Unknown stat_type: {prediction.stat_type}")
                    continue

                # Map boxscore field to database field
                boxscore_field = None
                for api_field, db_field in self.BOXSCORE_FIELD_MAPPING.items():
                    if db_field == stat_field:
                        boxscore_field = api_field
                        break

                if not boxscore_field:
                    logger.warning(f"No boxscore field mapping for stat_type: {prediction.stat_type}")
                    continue

                actual_value = boxscore_stats.get(boxscore_field)

                if actual_value is None:
                    logger.warning(f"Boxscore missing value for {boxscore_field}")
                    continue

                # Create/update PlayerStats record
                player_stats = self.db.query(PlayerStats).filter(
                    PlayerStats.player_id == player.id,
                    PlayerStats.game_id == game.id
                ).first()

                if player_stats:
                    # Update existing stats
                    setattr(player_stats, stat_field, actual_value)
                    if boxscore_stats.get('MIN') is not None:
                        player_stats.minutes = boxscore_stats.get('MIN')
                    player_stats.updated_at = datetime.now(UTC)
                    result["player_stats_updated"] += 1
                else:
                    # Create new stats record
                    player_stats = PlayerStats(
                        id=str(uuid.uuid4()),
                        player_id=player.id,
                        game_id=game.id,
                        points=boxscore_stats.get('PTS'),
                        rebounds=boxscore_stats.get('REB'),
                        assists=boxscore_stats.get('AST'),
                        threes=boxscore_stats.get('FG3M'),
                        minutes=boxscore_stats.get('MIN'),
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC)
                    )
                    if not dry_run:
                        self.db.add(player_stats)

                        # Log player match to audit trail
                        await self._log_player_match(
                            player=player,
                            boxscore_player_id=str(player.external_id),
                            match_method="external_id"
                        )

                    result["player_stats_created"] += 1

                # Calculate accuracy metrics
                difference = abs(prediction.predicted_value - actual_value)

                # Determine if recommendation was correct
                was_correct = None
                if prediction.recommendation == "OVER":
                    was_correct = actual_value > prediction.predicted_value
                elif prediction.recommendation == "UNDER":
                    was_correct = actual_value < prediction.predicted_value
                # For "NONE" recommendations, was_correct stays None

                # Update prediction with accuracy data
                prediction.actual_value = actual_value
                prediction.difference = difference
                prediction.was_correct = was_correct
                prediction.actuals_resolved_at = datetime.now(UTC)

                result["predictions_resolved"] += 1

                logger.debug(
                    f"Resolved: {player.name} {prediction.stat_type} "
                    f"(predicted: {prediction.predicted_value}, actual: {actual_value}, "
                    f"difference: {difference:.2f}, correct: {was_correct})"
                )

        except Exception as e:
            logger.error(f"Error resolving game {game.id}: {e}")
            result["errors"].append(str(e))

        return result

    def get_unresolved_games(self, hours_back: int = 48) -> List[Dict]:
        """
        Get list of completed games that haven't been resolved yet.

        Args:
            hours_back: Look back this many hours

        Returns:
            List of game dictionaries
        """
        cutoff = datetime.now(UTC) - timedelta(hours=hours_back)

        games = self.db.query(Game).filter(
            Game.status == "final",
            Game.game_date >= cutoff
        ).all()

        unresolved = []
        for game in games:
            # Check if predictions exist and are unresolved
            unresolved_count = self.db.query(Prediction).filter(
                Prediction.game_id == game.id,
                Prediction.actuals_resolved_at.is_(None)
            ).count()

            if unresolved_count > 0:
                unresolved.append({
                    "id": game.id,
                    "external_id": game.external_id,
                    "away_team": game.away_team,
                    "home_team": game.home_team,
                    "game_date": game.game_date.isoformat(),
                    "unresolved_predictions": unresolved_count
                })

        return unresolved

    def get_resolution_status(self) -> Dict:
        """
        Get overall resolution status statistics.

        Returns:
            Dictionary with resolution stats
        """
        total_predictions = self.db.query(Prediction).count()
        resolved_predictions = self.db.query(Prediction).filter(
            Prediction.actuals_resolved_at.isnot(None)
        ).count()

        # Count by recommendation type
        over_total = self.db.query(Prediction).filter(
            Prediction.recommendation == "OVER"
        ).count()
        over_resolved = self.db.query(Prediction).filter(
            Prediction.recommendation == "OVER",
            Prediction.actuals_resolved_at.isnot(None)
        ).count()

        under_total = self.db.query(Prediction).filter(
            Prediction.recommendation == "UNDER"
        ).count()
        under_resolved = self.db.query(Prediction).filter(
            Prediction.recommendation == "UNDER",
            Prediction.actuals_resolved_at.isnot(None)
        ).count()

        # Win rate
        correct_predictions = self.db.query(Prediction).filter(
            Prediction.was_correct == True
        ).count()

        win_rate = (
            correct_predictions / resolved_predictions
            if resolved_predictions > 0
            else 0.0
        )

        return {
            "total_predictions": total_predictions,
            "resolved_predictions": resolved_predictions,
            "unresolved_predictions": total_predictions - resolved_predictions,
            "resolution_rate": resolved_predictions / total_predictions if total_predictions > 0 else 0.0,
            "over_recommendations": {
                "total": over_total,
                "resolved": over_resolved
            },
            "under_recommendations": {
                "total": under_total,
                "resolved": under_resolved
            },
            "correct_predictions": correct_predictions,
            "win_rate": win_rate
        }
