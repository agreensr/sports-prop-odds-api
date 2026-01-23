#!/usr/bin/env python3
"""
Daily Odds Fetch Service

Runs at 7:00 AM CST to:
1. Fetch upcoming games from The Odds API
2. Generate predictions for games without them
3. Fetch player props odds for games within 2 hours of start time

Only fetches player props close to game time to ensure odds are available.
"""
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone, UTC
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.nba.models import Game, Prediction, Player
from app.services.nba.prediction_service import PredictionService
from app.services.core.odds_api_service import OddsApiService
from app.services.data_sources.odds_mapper import OddsMapper
from app.services.nba.boxscore_import_service import BoxscoreImportService

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/daily_odds_fetch.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
FETCH_HOURS_AHEAD = 48  # Only fetch games within next 48 hours
PLAYER_PROPS_HOURS_BEFORE = 2  # Only fetch player props within 2 hours of game start
ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY", "8ad802abc3050bd7ff719830103602d6")

# Bookmaker priority for odds updates (BetMGM and Caesars removed per user request)
BOOKMAKER_PRIORITY = [
    "FanDuel", "DraftKings", "BetRivers", "PointsBet", "Unibet"
]


class DailyOddsFetchService:
    """Daily odds fetch and prediction generation service."""

    def __init__(self):
        self.db = SessionLocal()
        self.stats = {
            "games_resolved": 0,
            "predictions_resolved": 0,
            "games_fetched": 0,
            "predictions_generated": 0,
            "odds_updated": 0,
            "games_checked_for_props": 0,
            "errors": []
        }

    async def run(self):
        """Run the daily odds fetch process."""
        logger.info("=" * 60)
        logger.info("Starting Daily Odds Fetch Service")
        logger.info("=" * 60)

        # Step 0: Resolve predictions from completed games
        await self._resolve_completed_games()

        # Step 1: Fetch upcoming games from The Odds API
        await self._fetch_upcoming_games()

        # Step 2: Generate predictions for games without them
        await self._generate_predictions()

        # Step 3: Fetch player props odds (within 2 hours of game start)
        await self._fetch_player_props()

        # Log summary
        self._log_summary()

        # Cleanup
        self.db.close()

    async def _fetch_upcoming_games(self):
        """Fetch upcoming games from The Odds API."""
        logger.info("\n[Step 1] Fetching upcoming games from The Odds API...")

        try:
            service = OddsApiService(api_key=ODDS_API_KEY)
            mapper = OddsMapper(self.db)

            # Fetch games for next 3 days
            games_data = await service.get_upcoming_games_with_odds(days_ahead=3)

            if not games_data:
                logger.warning("No games returned from The Odds API")
                return

            logger.info(f"Found {len(games_data)} games from The Odds API")

            # Filter games within 48 hours
            cutoff = datetime.now(UTC) + timedelta(hours=FETCH_HOURS_AHEAD)
            games_to_process = []

            for game_data in games_data:
                commence_time = datetime.fromisoformat(
                    game_data["commence_time"].replace("Z", "+00:00")
                )

                if commence_time <= cutoff:
                    games_to_process.append(game_data)

                # Log each game
                cst_time = commence_time.astimezone(timezone(timedelta(hours=-6)))
                logger.info(f"  {cst_time.strftime('%a %m/%d %I:%M %p CST')} "
                           f"{game_data['away_team']} @ {game_data['home_team']}")

            logger.info(f"Games within {FETCH_HOURS_AHEAD} hours: {len(games_to_process)}")

            # Create/update games in database
            result = mapper.create_games_from_odds_schedule(games_to_process)
            self.stats["games_fetched"] = result["created"] + result["updated"]

            logger.info(f"Games created: {result['created']}, updated: {result['updated']}")

            if result["errors"]:
                logger.warning(f"Errors: {result['errors']}")
                self.stats["errors"].extend(result["errors"])

        except Exception as e:
            logger.error(f"Error fetching upcoming games: {e}")
            self.stats["errors"].append(f"Fetch games: {str(e)}")

    async def _resolve_completed_games(self):
        """Resolve predictions from completed games (last 48 hours)."""
        logger.info("\n[Step 0] Resolving completed games...")

        try:
            service = BoxscoreImportService(self.db)
            result = await service.resolve_predictions_for_completed_games(hours_back=48)

            self.stats["games_resolved"] = result["games_processed"]
            self.stats["predictions_resolved"] = result["predictions_resolved"]

            logger.info(f"Resolved: {result['games_processed']} games, "
                       f"{result['predictions_resolved']} predictions")

            if result["player_stats_created"] > 0:
                logger.info(f"Created: {result['player_stats_created']} PlayerStats records")
            if result["player_stats_updated"] > 0:
                logger.info(f"Updated: {result['player_stats_updated']} PlayerStats records")

            if result["errors"]:
                logger.warning(f"Errors: {result['errors']}")
                self.stats["errors"].extend([f"Resolve: {e}" for e in result["errors"]])

        except Exception as e:
            logger.error(f"Error resolving completed games: {e}")
            self.stats["errors"].append(f"Resolve: {str(e)}")

    async def _generate_predictions(self):
        """Generate predictions for games without them."""
        logger.info("\n[Step 2] Generating predictions...")

        try:
            # Get games within 48 hours that don't have predictions
            cutoff = datetime.now(UTC) + timedelta(hours=FETCH_HOURS_AHEAD)
            start = datetime.now(UTC)

            games = self.db.query(Game).filter(
                Game.game_date >= start,
                Game.game_date <= cutoff,
                Game.status == "scheduled"
            ).all()

            logger.info(f"Found {len(games)} scheduled games within {FETCH_HOURS_AHEAD} hours")

            prediction_service = PredictionService(self.db)

            for game in games:
                # Check if predictions exist
                existing_count = self.db.query(Prediction).filter(
                    Prediction.game_id == game.id
                ).count()

                if existing_count == 0:
                    logger.info(f"Generating predictions for {game.away_team} @ {game.home_team}")

                    try:
                        predictions = prediction_service.generate_predictions_for_game(game.id)
                        self.stats["predictions_generated"] += len(predictions)
                    except Exception as e:
                        logger.error(f"Error generating predictions for {game.id}: {e}")
                        self.stats["errors"].append(f"Predictions for {game.id}: {str(e)}")
                else:
                    logger.debug(f"Skipping {game.away_team} @ {game.home_team} "
                                f"({existing_count} predictions exist)")

        except Exception as e:
            logger.error(f"Error generating predictions: {e}")
            self.stats["errors"].append(f"Generate predictions: {str(e)}")

    async def _fetch_player_props(self):
        """Fetch player props odds for games within 2 hours of start time."""
        logger.info(f"\n[Step 3] Fetching player props odds (within {PLAYER_PROPS_HOURS_BEFORE} hours of game start)...")

        try:
            service = OddsApiService(api_key=ODDS_API_KEY)
            mapper = OddsMapper(self.db)

            # Get games with predictions - only those within 2 hours of start
            now = datetime.now(UTC)
            start_window = now - timedelta(hours=1)  # Started within last hour
            end_window = now + timedelta(hours=PLAYER_PROPS_HOURS_BEFORE)  # Starting within 2 hours

            games = self.db.query(Game).filter(
                Game.game_date >= start_window,
                Game.game_date <= end_window,
                Game.status == "scheduled"
            ).all()

            logger.info(f"Found {len(games)} games starting within {PLAYER_PROPS_HOURS_BEFORE} hours")

            if not games:
                logger.info("No games within 2 hours of start time - skipping player props fetch")
                return

            for game in games:
                # Only process games with The Odds API format IDs
                if len(game.external_id) != 32:
                    logger.debug(f"Skipping {game.away_team} @ {game.home_team} "
                                f"(not an Odds API game)")
                    continue

                # Check if predictions exist
                pred_count = self.db.query(Prediction).filter(
                    Prediction.game_id == game.id
                ).count()

                if pred_count == 0:
                    logger.debug(f"Skipping {game.away_team} @ {game.home_team} "
                                f"(no predictions)")
                    continue

                # Calculate time until game starts
                time_until_game = (game.game_date.replace(tzinfo=timezone.utc) - now).total_seconds() / 3600
                cst_time = game.game_date.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=-6)))
                
                logger.info(f"Fetching player props for {game.away_team} @ {game.home_team} "
                           f"({cst_time.strftime('%a %m/%d %I:%M %p CST')}, {time_until_game:.1f}h from now)")

                self.stats["games_checked_for_props"] += 1

                try:
                    # Fetch player props
                    props_data = await service.get_event_player_props(game.external_id)

                    # Map to prediction updates
                    updates = mapper.map_player_props_to_predictions(props_data, game)

                    # Apply updates with bookmaker priority
                    for update_data in updates:
                        prediction = self.db.query(Prediction).filter(
                            Prediction.id == update_data["prediction_id"]
                        ).first()

                        if prediction:
                            new_bookmaker = update_data.get("bookmaker_name")
                            current_bookmaker = prediction.bookmaker_name

                            # Determine if we should update
                            should_update = self._should_update_odds(
                                current_bookmaker, new_bookmaker,
                                prediction.over_price, prediction.under_price,
                                update_data.get("over_price"), update_data.get("under_price")
                            )

                            if should_update:
                                prediction.bookmaker_line = update_data.get("bookmaker_line")
                                prediction.bookmaker_name = new_bookmaker

                                if update_data.get("over_price") is not None:
                                    prediction.over_price = update_data.get("over_price")
                                if update_data.get("under_price") is not None:
                                    prediction.under_price = update_data.get("under_price")

                                prediction.odds_last_updated = update_data.get("odds_last_updated")

                                if not prediction.odds_fetched_at:
                                    prediction.odds_fetched_at = update_data.get("odds_last_updated")

                                self.stats["odds_updated"] += 1

                    self.db.commit()

                    # Count predictions with odds
                    odds_count = self.db.query(Prediction).filter(
                        Prediction.game_id == game.id,
                        Prediction.bookmaker_line.isnot(None)
                    ).count()

                    logger.info(f"  Updated {len(updates)} predictions "
                               f"({odds_count} total with odds)")

                except Exception as e:
                    logger.error(f"Error fetching player props for {game.external_id}: {e}")
                    self.stats["errors"].append(f"Player props {game.external_id}: {str(e)}")

        except Exception as e:
            logger.error(f"Error fetching player props: {e}")
            self.stats["errors"].append(f"Fetch player props: {str(e)}")

    def _should_update_odds(self, current_bookmaker, new_bookmaker,
                           current_over, current_under,
                           new_over, new_under):
        """Determine if odds should be updated based on bookmaker priority."""
        # Always update if no current odds
        if current_bookmaker is None:
            return True

        # Always update if same bookmaker (to fill in missing prices)
        if new_bookmaker == current_bookmaker:
            return True

        # Check if we're filling in missing over/under prices
        if current_over is None and new_over is not None:
            return True
        if current_under is None and new_under is not None:
            return True

        # Check bookmaker priority
        if new_bookmaker in BOOKMAKER_PRIORITY and current_bookmaker in BOOKMAKER_PRIORITY:
            new_priority = BOOKMAKER_PRIORITY.index(new_bookmaker)
            current_priority = BOOKMAKER_PRIORITY.index(current_bookmaker)
            return new_priority < current_priority

        # Don't update lower priority bookmakers
        return False

    def _log_summary(self):
        """Log execution summary."""
        logger.info("\n" + "=" * 60)
        logger.info("Daily Odds Fetch Complete")
        logger.info("=" * 60)
        logger.info(f"Games resolved: {self.stats['games_resolved']}")
        logger.info(f"Predictions resolved: {self.stats['predictions_resolved']}")
        logger.info(f"Games fetched: {self.stats['games_fetched']}")
        logger.info(f"Predictions generated: {self.stats['predictions_generated']}")
        logger.info(f"Games checked for props: {self.stats['games_checked_for_props']}")
        logger.info(f"Odds updated: {self.stats['odds_updated']}")

        if self.stats['errors']:
            logger.warning(f"Errors: {len(self.stats['errors'])}")
            for error in self.stats['errors'][:5]:  # Show first 5
                logger.warning(f"  - {error}")

        logger.info("=" * 60)


async def main():
    """Main entry point."""
    service = DailyOddsFetchService()
    await service.run()


if __name__ == "__main__":
    asyncio.run(main())
