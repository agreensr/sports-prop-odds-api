"""
Historical Odds Service for tracking player prop hit rates.

This service captures historical bookmaker odds snapshots and resolves them
against actual game results to calculate hit rates.

Hit rates measure how consistently a player hits OVER/UNDER on their
betting lines, which is then used to weight prediction confidence.

Example: If LeBron James has hit his assist OVER in 8 of 10 games,
future assist predictions get a confidence boost.

Data Flow:
1. Capture odds snapshots from The Odds API (pre-game or backfill)
2. Resolve snapshots with actual boxscore results (post-game)
3. Calculate hit rates per (player, stat_type, bookmaker)
4. Apply hit rate weights to prediction confidence
"""
import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

# UTC timezone for Python < 3.11 compatibility
try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.nba.models import (
    HistoricalOddsSnapshot,
    Player,
    Game,
    PlayerStats,
    ExpectedLineup
)
from app.services.core.odds_api_service import get_odds_service

logger = logging.getLogger(__name__)


class HistoricalOddsService:
    """Service for tracking historical odds and calculating hit rates."""

    def __init__(self, db: Session):
        """
        Initialize historical odds service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self._odds_api = None

    @property
    def odds_api(self):
        """Lazy load odds API service."""
        if self._odds_api is None:
            api_key = os.getenv("THE_ODDS_API_KEY")
            if api_key:
                self._odds_api = get_odds_service(api_key)
        return self._odds_api

    async def capture_odds_snapshot(
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
        Capture a single odds snapshot.

        Args:
            game_id: Database UUID of the game
            player_id: Database UUID of the player
            stat_type: Stat type (points, rebounds, assists, threes)
            bookmaker_name: Name of bookmaker (FanDuel, DraftKings, etc.)
            bookmaker_line: The betting line (e.g., 23.5)
            over_price: American odds for OVER bet
            under_price: American odds for UNDER bet
            was_starter: Whether player was a starter
            snapshot_time: When odds were captured (defaults to now)

        Returns:
            Created HistoricalOddsSnapshot or None if error
        """
        try:
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
                was_starter=was_starter,
                created_at=datetime.now(UTC)
            )

            self.db.add(snapshot)
            self.db.commit()

            logger.debug(
                f"Captured snapshot: {stat_type} {bookmaker_line} "
                f"for player {player_id} from {bookmaker_name}"
            )

            return snapshot

        except Exception as e:
            logger.error(f"Error capturing odds snapshot: {e}")
            self.db.rollback()
            return None

    async def batch_capture_game_odds(
        self,
        game_id: str,
        starters_only: bool = True
    ) -> Dict[str, int]:
        """
        Capture odds for all players in a game from The Odds API.

        Args:
            game_id: Database UUID of the game
            starters_only: Only capture odds for players marked as starters

        Returns:
            Dict with capture results: {"captured": int, "errors": int}
        """
        game = self.db.query(Game).filter(Game.id == game_id).first()
        if not game:
            logger.error(f"Game {game_id} not found")
            return {"captured": 0, "errors": 1}

        # Only process games with Odds API format IDs (32 character hex)
        if len(game.external_id) != 32:
            logger.info(
                f"Skipping {game.away_team} @ {game.home_team}: "
                f"not an Odds API game ID format"
            )
            return {"captured": 0, "errors": 0}

        # Fetch player props from The Odds API
        if not self.odds_api:
            logger.error("Odds API service not available (missing API key)")
            return {"captured": 0, "errors": 1}

        try:
            props_data = await self.odds_api.get_event_player_props(game.external_id)

            if not props_data.get("data") or not props_data["data"].get("bookmakers"):
                logger.info(f"No player props available for game {game.external_id}")
                return {"captured": 0, "errors": 0}

            captured = 0
            errors = 0

            # Get starters for this game if filtering
            starter_ids = set()
            if starters_only:
                starters = self.db.query(ExpectedLineup).filter(
                    ExpectedLineup.game_id == game_id,
                    ExpectedLineup.starter_position.isnot(None)
                ).all()
                starter_ids = {s.player_id for s in starters}

            # Process each bookmaker's player props
            for bookmaker in props_data["data"].get("bookmakers", []):
                bookmaker_name = bookmaker.get("title", "Unknown")

                for market in bookmaker.get("markets", []):
                    market_key = market.get("key")  # e.g., "player_points"

                    # Map market key to stat_type
                    stat_type_map = {
                        "player_points": "points",
                        "player_rebounds": "rebounds",
                        "player_assists": "assists",
                        "player_threes": "threes"
                    }

                    stat_type = stat_type_map.get(market_key)
                    if not stat_type:
                        continue

                    for outcome in market.get("outcomes", []):
                        player_name = outcome.get("name")
                        if not player_name:
                            continue

                        # Find player by name and team
                        player = self.db.query(Player).filter(
                            Player.name.ilike(f"%{player_name}%"),
                            Player.team.in_([game.away_team, game.home_team])
                        ).first()

                        if not player:
                            logger.debug(f"Player not found: {player_name}")
                            errors += 1
                            continue

                        # Skip if starters_only and player not a starter
                        if starters_only and player.id not in starter_ids:
                            continue

                        # Check if snapshot already exists for this combination
                        existing = self.db.query(HistoricalOddsSnapshot).filter(
                            HistoricalOddsSnapshot.game_id == game_id,
                            HistoricalOddsSnapshot.player_id == player.id,
                            HistoricalOddsSnapshot.stat_type == stat_type,
                            HistoricalOddsSnapshot.bookmaker_name == bookmaker_name
                        ).first()

                        if existing:
                            logger.debug(
                                f"Snapshot already exists for {player_name} "
                                f"{stat_type} from {bookmaker_name}"
                            )
                            continue

                        # Parse odds
                        bookmaker_line = outcome.get("point")
                        over_price = outcome.get("price")  # For OVER outcome
                        # UNDER price would be in a different outcome

                        # Create snapshot
                        snapshot = await self.capture_odds_snapshot(
                            game_id=game_id,
                            player_id=player.id,
                            stat_type=stat_type,
                            bookmaker_name=bookmaker_name,
                            bookmaker_line=bookmaker_line,
                            over_price=over_price,
                            under_price=None,  # Would need to find UNDER outcome
                            was_starter=player.id in starter_ids if starters_only else False
                        )

                        if snapshot:
                            captured += 1
                        else:
                            errors += 1

            self.db.commit()
            logger.info(
                f"Captured {captured} odds snapshots for "
                f"{game.away_team} @ {game.home_team}"
            )

            return {"captured": captured, "errors": errors}

        except Exception as e:
            logger.error(f"Error batch capturing game odds: {e}")
            self.db.rollback()
            return {"captured": 0, "errors": 1}

    def resolve_snapshots_for_game(self, game_id: str) -> Dict[str, int]:
        """
        Resolve snapshots with actual game results.

        Fetches actual stats from PlayerStats and updates snapshots
        with hit_result (OVER, UNDER, PUSH).

        Args:
            game_id: Database UUID of the game

        Returns:
            Dict with resolution results: {"resolved": int, "errors": int}
        """
        # Get unresolved snapshots for this game
        snapshots = self.db.query(HistoricalOddsSnapshot).filter(
            HistoricalOddsSnapshot.game_id == game_id,
            HistoricalOddsSnapshot.hit_result.is_(None)
        ).all()

        resolved_count = 0
        error_count = 0

        for snapshot in snapshots:
            try:
                # Get actual stats from PlayerStats
                player_stat = self.db.query(PlayerStats).filter(
                    PlayerStats.player_id == snapshot.player_id,
                    PlayerStats.game_id == game_id
                ).first()

                if not player_stat:
                    logger.debug(
                        f"No player stats found for snapshot {snapshot.id} "
                        f"(player_id: {snapshot.player_id}, game_id: {game_id})"
                    )
                    error_count += 1
                    continue

                # Get actual value based on stat_type
                stat_to_field = {
                    "points": player_stat.points,
                    "rebounds": player_stat.rebounds,
                    "assists": player_stat.assists,
                    "threes": player_stat.threes
                }

                actual_value = stat_to_field.get(snapshot.stat_type)
                if actual_value is None:
                    logger.debug(
                        f"Stat value not found for {snapshot.stat_type} "
                        f"in player stats"
                    )
                    error_count += 1
                    continue

                # Determine hit result
                if actual_value > snapshot.bookmaker_line:
                    hit_result = "OVER"
                elif actual_value < snapshot.bookmaker_line:
                    hit_result = "UNDER"
                else:
                    hit_result = "PUSH"

                # Update snapshot
                snapshot.actual_value = actual_value
                snapshot.hit_result = hit_result
                snapshot.resolved_at = datetime.now(UTC)

                resolved_count += 1

                logger.debug(
                    f"Resolved snapshot: {snapshot.stat_type} "
                    f"line={snapshot.bookmaker_line} actual={actual_value} "
                    f"result={hit_result}"
                )

            except Exception as e:
                logger.error(f"Error resolving snapshot {snapshot.id}: {e}")
                error_count += 1

        try:
            self.db.commit()
            logger.info(
                f"Resolved {resolved_count} snapshots for game {game_id} "
                f"({error_count} errors)"
            )
        except Exception as e:
            logger.error(f"Error committing resolved snapshots: {e}")
            self.db.rollback()
            return {"resolved": 0, "errors": error_count}

        return {"resolved": resolved_count, "errors": error_count}

    def get_player_hit_rate(
        self,
        player_id: str,
        stat_type: str,
        bookmaker_name: Optional[str] = None,
        games_back: int = 10,
        starters_only: bool = True
    ) -> Dict[str, any]:
        """
        Calculate hit rate for a player.

        Returns statistics on how often player hits OVER on their lines.

        Args:
            player_id: Database UUID of the player
            stat_type: Stat type (points, rebounds, assists, threes)
            bookmaker_name: Optional filter by bookmaker
            games_back: Number of recent games to analyze
            starters_only: Only include games where player was a starter

        Returns:
            Dict with hit rate statistics:
            {
                "hit_rate": 0.667,  # 8 out of 12 OVER hits
                "total_games": 12,
                "over_hits": 8,
                "under_hits": 3,
                "pushes": 1,
                "sample_size_adjective": "moderate"  # strong, moderate, limited, very limited
            }
        """
        # Build query
        query = self.db.query(HistoricalOddsSnapshot).filter(
            HistoricalOddsSnapshot.player_id == player_id,
            HistoricalOddsSnapshot.stat_type == stat_type,
            HistoricalOddsSnapshot.hit_result.isnot(None),
            HistoricalOddsSnapshot.resolved_at.isnot(None)
        )

        if starters_only:
            query = query.filter(HistoricalOddsSnapshot.was_starter == True)

        if bookmaker_name:
            query = query.filter(HistoricalOddsSnapshot.bookmaker_name == bookmaker_name)

        # Calculate cutoff date (approximately games_back * 2 days to account for schedule)
        cutoff_date = datetime.now(UTC) - timedelta(days=games_back * 2)
        query = query.filter(HistoricalOddsSnapshot.snapshot_time >= cutoff_date)

        # Order by snapshot time descending and limit
        query = query.order_by(HistoricalOddsSnapshot.snapshot_time.desc())
        query = query.limit(games_back)

        snapshots = query.all()

        if not snapshots:
            return {
                "hit_rate": 0.500,  # Neutral when no data
                "total_games": 0,
                "over_hits": 0,
                "under_hits": 0,
                "pushes": 0,
                "sample_size_adjective": "very limited"
            }

        # Calculate hit rate
        over_hits = sum(1 for s in snapshots if s.hit_result == "OVER")
        under_hits = sum(1 for s in snapshots if s.hit_result == "UNDER")
        pushes = sum(1 for s in snapshots if s.hit_result == "PUSH")
        total = len(snapshots)

        hit_rate = over_hits / total if total > 0 else 0.5

        # Determine sample size adjective
        if total >= 10:
            sample_size = "strong"
        elif total >= 7:
            sample_size = "moderate"
        elif total >= 5:
            sample_size = "limited"
        else:
            sample_size = "very limited"

        return {
            "hit_rate": round(hit_rate, 3),
            "total_games": total,
            "over_hits": over_hits,
            "under_hits": under_hits,
            "pushes": pushes,
            "sample_size_adjective": sample_size
        }

    def calculate_hit_rate_weight(
        self,
        hit_rate: float,
        total_games: int
    ) -> float:
        """
        Convert hit rate to confidence multiplier.

        Formula: weight = 0.5 + (hit_rate - 0.5) * 2.0 * sample_multiplier

        Examples:
            - 0.8 hit rate, 15 games: 1.10 (+10% confidence boost)
            - 0.5 hit rate, 15 games: 1.00 (neutral)
            - 0.3 hit rate, 15 games: 0.90 (-10% confidence reduction)

        Args:
            hit_rate: OVER hit rate (0.0 to 1.0)
            total_games: Number of games in sample

        Returns:
            Confidence weight multiplier (clamped to 0.7-1.3)
        """
        if total_games < 5:
            return 1.0  # Insufficient data for weighting

        strength_factor = 2.0  # How much to weight deviation from 0.5

        # Sample multiplier based on games
        if total_games >= 10:
            sample_multiplier = 1.0
        elif total_games >= 7:
            sample_multiplier = 0.75
        else:
            sample_multiplier = 0.5

        deviation = hit_rate - 0.5
        weight = 0.5 + deviation * strength_factor * sample_multiplier

        # Clamp to reasonable range
        return round(max(0.7, min(1.3, weight)), 3)

    def get_batch_hit_rates(
        self,
        player_ids: List[str],
        stat_types: List[str],
        games_back: int = 10,
        starters_only: bool = True
    ) -> Dict[str, Dict[str, Dict]]:
        """
        Get hit rates for multiple players at once.

        Useful for generating predictions for multiple players.

        Args:
            player_ids: List of player database UUIDs
            stat_types: List of stat types to analyze
            games_back: Number of recent games to analyze
            starters_only: Only include games as starter

        Returns:
            Nested dict structure:
            {
                "player_id_1": {
                    "points": {"hit_rate": 0.667, "total_games": 12, ...},
                    "assists": {"hit_rate": 0.500, "total_games": 10, ...}
                },
                ...
            }
        """
        results = {}

        for player_id in player_ids:
            results[player_id] = {}
            for stat_type in stat_types:
                results[player_id][stat_type] = self.get_player_hit_rate(
                    player_id=player_id,
                    stat_type=stat_type,
                    games_back=games_back,
                    starters_only=starters_only
                )

        return results

    async def backfill_recent_games(
        self,
        games_limit: int = 5,
        starters_only: bool = True
    ) -> Dict[str, any]:
        """
        Backfill historical odds data for completed games.

        Fetches odds from completed games and resolves with actual results.

        Args:
            games_limit: Maximum number of games to process
            starters_only: Only capture odds for starters

        Returns:
            Dict with backfill results
        """
        # Find completed games without snapshots
        games_without_snapshots = (
            self.db.query(Game)
            .filter(Game.status == "final")
            .filter(~Game.id.in_(
                self.db.query(HistoricalOddsSnapshot.game_id).distinct()
            ))
            .order_by(Game.game_date.desc())
            .limit(games_limit)
            .all()
        )

        if not games_without_snapshots:
            return {
                "processed": 0,
                "captured": 0,
                "resolved": 0,
                "errors": [],
                "message": "No games to backfill"
            }

        captured_total = 0
        resolved_total = 0
        errors = []

        for game in games_without_snapshots:
            try:
                logger.info(
                    f"Processing game {game.external_id}: "
                    f"{game.away_team} @ {game.home_team}"
                )

                # Capture odds (using current API for historical event odds)
                capture_result = await self.batch_capture_game_odds(
                    game_id=str(game.id),
                    starters_only=starters_only
                )
                captured_total += capture_result.get("captured", 0)

                # Resolve with actual results
                resolve_result = self.resolve_snapshots_for_game(str(game.id))
                resolved_total += resolve_result.get("resolved", 0)

                if resolve_result.get("errors", 0) > 0:
                    errors.append(f"{game.external_id}: {resolve_result['errors']} errors")

            except Exception as e:
                errors.append(f"{game.external_id}: {str(e)}")
                logger.error(f"Error processing game {game.external_id}: {e}")

        return {
            "processed": len(games_without_snapshots),
            "captured": captured_total,
            "resolved": resolved_total,
            "errors": errors
        }

    def get_player_report(
        self,
        player_id: str,
        games_back: int = 10
    ) -> Dict[str, any]:
        """
        Get comprehensive hit rate report for a player.

        Returns hit rates for all stat types and bookmakers.

        Args:
            player_id: Database UUID of the player
            games_back: Number of recent games to analyze

        Returns:
            Dict with comprehensive hit rate data
        """
        stat_types = ["points", "rebounds", "assists", "threes"]
        hit_rates = {}

        for stat_type in stat_types:
            hit_rates[stat_type] = self.get_player_hit_rate(
                player_id=player_id,
                stat_type=stat_type,
                games_back=games_back,
                starters_only=True
            )

        return {
            "player_id": player_id,
            "games_back": games_back,
            "hit_rates": hit_rates
        }
