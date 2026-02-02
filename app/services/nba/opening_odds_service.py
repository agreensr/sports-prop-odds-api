"""
Opening Odds Service for tracking opening lines and finding value opportunities.

This service captures the first odds posted for each player prop (opening lines)
and compares them to current odds to identify value opportunities.

Key Concept:
- Opening lines are set when odds first appear (usually 24-48 hours before game)
- Line movements indicate where smart money is going
- If line moves significantly but our prediction doesn't change = VALUE

Value Detection Strategy:
1. Opening line: 23.5 points (first snapshot)
2. Current line: 25.5 points (line moved up 2 points)
3. Our prediction: 26.0 points (unchanged)
4. Edge: We predicted 26.0, market now says 25.5 = still value on OVER

Data Flow:
1. Capture opening odds when first snapshot is created
2. Track subsequent line movements
3. Compare predictions to opening vs current lines
4. Alert when opening line creates better value than current line
"""
import logging
import uuid
from datetime import datetime, timedelta

# UTC timezone for Python < 3.11 compatibility
try:
    from datetime import UTC
except ImportError:
    from datetime import timezone
    UTC = timezone.utc
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, func

from app.models import (
    HistoricalOddsSnapshot,
    Player,
    Game,
    Prediction
)

logger = logging.getLogger(__name__)


class OpeningOddsService:
    """Service for tracking opening odds and detecting line movement value."""

    def __init__(self, db: Session):
        """
        Initialize opening odds service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def capture_opening_odds(
        self,
        game_id: str,
        player_id: str,
        stat_type: str,
        bookmaker_name: str,
        bookmaker_line: float,
        over_price: Optional[float] = None,
        under_price: Optional[float] = None,
        was_starter: bool = False,
        snapshot_time: Optional[datetime] = None
    ) -> Optional[HistoricalOddsSnapshot]:
        """
        Capture opening odds (first snapshot for this game/player/stat/bookmaker).

        Args:
            game_id: Database UUID of the game
            player_id: Database UUID of the player
            stat_type: Stat type (points, rebounds, assists, threes)
            bookmaker_name: Bookmaker name (FanDuel, DraftKings, etc.)
            bookmaker_line: The betting line (e.g., 23.5)
            over_price: American odds for OVER bet
            under_price: American odds for UNDER bet
            was_starter: Whether player was projected starter
            snapshot_time: When odds were captured (defaults to now)

        Returns:
            Created HistoricalOddsSnapshot or None if already exists
        """
        # Check if opening odds already exist for this combination
        existing = self.db.query(HistoricalOddsSnapshot).filter(
            and_(
                HistoricalOddsSnapshot.game_id == game_id,
                HistoricalOddsSnapshot.player_id == player_id,
                HistoricalOddsSnapshot.stat_type == stat_type,
                HistoricalOddsSnapshot.bookmaker_name == bookmaker_name,
                HistoricalOddsSnapshot.is_opening_line == True
            )
        ).first()

        if existing:
            logger.debug(
                f"Opening odds already exist for {player_id}/{stat_type}/{bookmaker_name}"
            )
            return existing

        # Create opening odds snapshot
        snapshot = HistoricalOddsSnapshot(
            id=str(uuid.uuid4()),
            game_id=game_id,
            player_id=player_id,
            stat_type=stat_type,
            bookmaker_name=bookmaker_name,
            bookmaker_line=bookmaker_line,
            over_price=over_price,
            under_price=under_price,
            snapshot_time=snapshot_time or datetime.now(UTC),
            is_opening_line=True,
            line_movement=0.0,  # Opening line has no movement yet
            was_starter=was_starter,
            created_at=datetime.now(UTC)
        )

        self.db.add(snapshot)
        self.db.commit()
        self.db.refresh(snapshot)

        logger.info(
            f"Captured opening odds: {stat_type} {bookmaker_line} "
            f"for player {player_id} in game {game_id}"
        )

        return snapshot

    def update_line_movement(self, snapshot_id: str, current_line: float) -> bool:
        """
        Update line_movement for a snapshot based on opening line.

        Args:
            snapshot_id: ID of the current snapshot to update
            current_line: Current betting line

        Returns:
            True if updated, False if opening line not found
        """
        # Get the current snapshot
        current_snapshot = self.db.query(HistoricalOddsSnapshot).filter(
            HistoricalOddsSnapshot.id == snapshot_id
        ).first()

        if not current_snapshot:
            return False

        # Find the opening line for comparison
        opening_snapshot = self.db.query(HistoricalOddsSnapshot).filter(
            and_(
                HistoricalOddsSnapshot.game_id == current_snapshot.game_id,
                HistoricalOddsSnapshot.player_id == current_snapshot.player_id,
                HistoricalOddsSnapshot.stat_type == current_snapshot.stat_type,
                HistoricalOddsSnapshot.bookmaker_name == current_snapshot.bookmaker_name,
                HistoricalOddsSnapshot.is_opening_line == True
            )
        ).first()

        if not opening_snapshot:
            logger.warning(
                f"No opening line found for {current_snapshot.player_id}/"
                f"{current_snapshot.stat_type}/{current_snapshot.bookmaker_name}"
            )
            return False

        # Calculate line movement
        line_movement = current_line - opening_snapshot.bookmaker_line
        current_snapshot.line_movement = line_movement
        self.db.commit()

        logger.debug(
            f"Line movement: {opening_snapshot.bookmaker_line} → "
            f"{current_line} ({line_movement:+.1f})"
        )

        return True

    def get_opening_vs_current_odds(
        self,
        game_id: str,
        player_id: Optional[str] = None,
        stat_type: Optional[str] = None
    ) -> List[Dict]:
        """
        Get opening odds compared to current odds for value detection.

        Args:
            game_id: Game ID to check
            player_id: Optional player filter
            stat_type: Optional stat type filter

        Returns:
            List of dicts with opening vs current odds comparison
        """
        # Find all opening odds for the game
        query = self.db.query(HistoricalOddsSnapshot).filter(
            and_(
                HistoricalOddsSnapshot.game_id == game_id,
                HistoricalOddsSnapshot.is_opening_line == True
            )
        )

        if player_id:
            query = query.filter(HistoricalOddsSnapshot.player_id == player_id)
        if stat_type:
            query = query.filter(HistoricalOddsSnapshot.stat_type == stat_type)

        opening_odds = query.all()

        comparisons = []
        for opening in opening_odds:
            # Find the most recent snapshot for this same prop
            current = self.db.query(HistoricalOddsSnapshot).filter(
                and_(
                    HistoricalOddsSnapshot.game_id == game_id,
                    HistoricalOddsSnapshot.player_id == opening.player_id,
                    HistoricalOddsSnapshot.stat_type == opening.stat_type,
                    HistoricalOddsSnapshot.bookmaker_name == opening.bookmaker_name,
                    HistoricalOddsSnapshot.snapshot_time > opening.snapshot_time
                )
            ).order_by(desc(HistoricalOddsSnapshot.snapshot_time)).first()

            comparisons.append({
                'player_id': opening.player_id,
                'player_name': opening.player.name,
                'stat_type': opening.stat_type,
                'bookmaker': opening.bookmaker_name,
                'opening_line': opening.bookmaker_line,
                'current_line': current.bookmaker_line if current else opening.bookmaker_line,
                'line_movement': current.line_movement if current else 0.0,
                'opening_over': opening.over_price,
                'current_over': current.over_price if current else opening.over_price,
                'opening_under': opening.under_price,
                'current_under': current.under_price if current else opening.under_price,
                'opening_time': opening.snapshot_time,
                'last_update': current.snapshot_time if current else opening.snapshot_time
            })

        return comparisons

    def find_value_from_line_movements(
        self,
        game_id: str,
        min_movement: float = 2.0,
        hours_before_game: int = 24
    ) -> List[Dict]:
        """
        Find value opportunities created by line movements.

        Strategy:
        1. Get predictions for the game
        2. Compare opening vs current lines
        3. If line moved significantly (>= min_movement) but prediction unchanged = VALUE

        Args:
            game_id: Game ID to analyze
            min_movement: Minimum line movement to consider (default: 2.0 points)
            hours_before_game: Only look at games within this many hours (default: 24)

        Returns:
            List of value opportunities with edge calculation
        """
        # Get game info
        game = self.db.query(Game).filter(Game.id == game_id).first()
        if not game:
            return []

        # Get all predictions for this game
        predictions = self.db.query(Prediction).filter(
            Prediction.game_id == game_id
        ).all()

        opportunities = []
        for pred in predictions:
            # Get opening vs current odds for this prediction
            opening_odds = self.db.query(HistoricalOddsSnapshot).filter(
                and_(
                    HistoricalOddsSnapshot.game_id == game_id,
                    HistoricalOddsSnapshot.player_id == pred.player_id,
                    HistoricalOddsSnapshot.stat_type == pred.stat_type,
                    HistoricalOddsSnapshot.bookmaker_name == pred.bookmaker_name or 'FanDuel',
                    HistoricalOddsSnapshot.is_opening_line == True
                )
            ).first()

            if not opening_odds:
                continue

            # Get current odds (most recent snapshot)
            current_odds = self.db.query(HistoricalOddsSnapshot).filter(
                and_(
                    HistoricalOddsSnapshot.game_id == game_id,
                    HistoricalOddsSnapshot.player_id == pred.player_id,
                    HistoricalOddsSnapshot.stat_type == pred.stat_type,
                    HistoricalOddsSnapshot.bookmaker_name == pred.bookmaker_name or 'FanDuel',
                    HistoricalOddsSnapshot.snapshot_time > opening_odds.snapshot_time
                )
            ).order_by(desc(HistoricalOddsSnapshot.snapshot_time)).first()

            current_line = current_odds.bookmaker_line if current_odds else opening_odds.bookmaker_line
            line_movement = current_line - opening_odds.bookmaker_line

            # Only consider significant line movements
            if abs(line_movement) < min_movement:
                continue

            # Calculate edge against current line
            edge_vs_current = pred.predicted_value - current_line

            # Calculate edge against opening line
            edge_vs_opening = pred.predicted_value - opening_odds.bookmaker_line

            # Value condition: line moved toward our prediction
            # OR line moved away but we still have edge
            value_score = 0
            value_reason = ""

            if line_movement > 0:  # Line moved up
                if pred.recommendation == "UNDER":
                    # Line moved up (harder to go over) = better for UNDER
                    value_score = line_movement
                    value_reason = f"Line moved up {line_movement:+.1f} to {current_line}, better for UNDER"
                elif edge_vs_current > 0:
                    # Still have edge despite higher line
                    value_score = edge_vs_current
                    value_reason = f"Edge {edge_vs_current:+.1f} remains despite line increase"

            elif line_movement < 0:  # Line moved down
                if pred.recommendation == "OVER":
                    # Line moved down (easier to go over) = better for OVER
                    value_score = abs(line_movement)
                    value_reason = f"Line moved down {line_movement:+.1f} to {current_line}, better for OVER"
                elif edge_vs_current > 0:
                    # Still have edge despite lower line
                    value_score = edge_vs_current
                    value_reason = f"Edge {edge_vs_current:+.1f} remains despite line decrease"

            if value_score > 0:
                opportunities.append({
                    'player': pred.player.name,
                    'team': pred.player.team,
                    'stat_type': pred.stat_type,
                    'prediction': pred.predicted_value,
                    'recommendation': pred.recommendation,
                    'confidence': pred.confidence,
                    'bookmaker': pred.bookmaker_name or opening_odds.bookmaker_name,
                    'opening_line': opening_odds.bookmaker_line,
                    'current_line': current_line,
                    'line_movement': line_movement,
                    'edge_vs_opening': edge_vs_opening,
                    'edge_vs_current': edge_vs_current,
                    'value_score': value_score,
                    'value_reason': value_reason,
                    'over_odds_opening': opening_odds.over_price,
                    'over_odds_current': current_odds.over_price if current_odds else opening_odds.over_price,
                })

        # Sort by value score
        opportunities.sort(key=lambda x: x['value_score'], reverse=True)

        return opportunities

    def get_line_movement_stats(
        self,
        player_id: str,
        stat_type: Optional[str] = None,
        last_n_games: int = 20
    ) -> Dict:
        """
        Get statistics on how this player's lines typically move.

        Args:
            player_id: Player ID to analyze
            stat_type: Optional stat type filter
            last_n_games: Number of recent games to analyze

        Returns:
            Dict with line movement statistics
        """
        # Get recent games with opening odds
        query = self.db.query(
            HistoricalOddsSnapshot.game_id,
            HistoricalOddsSnapshot.stat_type,
            HistoricalOddsSnapshot.bookmaker_line.label('opening_line'),
        ).filter(
            and_(
                HistoricalOddsSnapshot.player_id == player_id,
                HistoricalOddsSnapshot.is_opening_line == True
            )
        )

        if stat_type:
            query = query.filter(HistoricalOddsSnapshot.stat_type == stat_type)

        # Get resolved games (with actual results)
        resolved_opening = query.join(
            Game,
            HistoricalOddsSnapshot.game_id == Game.id
        ).filter(
            Game.status == 'final'
        ).order_by(
            Game.game_date.desc()
        ).limit(last_n_games * 2).all()  # Get more to filter by stat type if needed

        movements = []
        for game_id, stat, opening_line in resolved_opening:
            # Get final line (last snapshot before game)
            final_snapshot = self.db.query(HistoricalOddsSnapshot).filter(
                and_(
                    HistoricalOddsSnapshot.game_id == game_id,
                    HistoricalOddsSnapshot.player_id == player_id,
                    HistoricalOddsSnapshot.stat_type == stat,
                    HistoricalOddsSnapshot.snapshot_time < Game.game_date
                )
            ).order_by(
                desc(HistoricalOddsSnapshot.snapshot_time)
            ).first()

            if final_snapshot:
                movement = final_snapshot.bookmaker_line - opening_line
                movements.append(movement)

        if not movements:
            return {'error': 'No line movement data found'}

        import statistics
        return {
            'player_id': player_id,
            'stat_type': stat_type,
            'total_movements': len(movements),
            'avg_movement': statistics.mean(movements),
            'median_movement': statistics.median(movements),
            'max_positive': max(movements),
            'max_negative': min(movements),
            'movement_std': statistics.stdev(movements) if len(movements) > 1 else 0,
            'movements_distribution': {
                'moved_up_2plus': sum(1 for m in movements if m >= 2.0),
                'moved_up_1plus': sum(1 for m in movements if m >= 1.0),
                'moved_down_1plus': sum(1 for m in movements if m <= -1.0),
                'moved_down_2plus': sum(1 for m in movements if m <= -2.0),
                'stable': sum(1 for m in movements if abs(m) < 1.0)
            }
        }
