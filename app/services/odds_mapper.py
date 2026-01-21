"""
Odds data mapper for transforming The Odds API responses to database models.

This module handles the transformation of odds data from The Odds API format
to the database model format, including game odds and player props.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from sqlalchemy.orm import Session

from app.models.models import Game, GameOdds, Player, Prediction

logger = logging.getLogger(__name__)

# Team name mapping: The Odds API full names -> 3-letter abbreviations
TEAM_NAME_TO_ABBREV = {
    "Atlanta Hawks": "ATL",
    "Boston Celtics": "BOS",
    "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI",
    "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL",
    "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW",
    "Houston Rockets": "HOU",
    "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC",
    "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC",
    "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA",
    "Washington Wizards": "WAS"
}


class OddsMapper:
    """Map odds API data to database models."""

    def __init__(self, db: Session):
        """
        Initialize the odds mapper.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def _team_name_to_abbrev(self, team_name: str) -> str:
        """
        Convert full team name to 3-letter abbreviation.

        Args:
            team_name: Full team name from The Odds API

        Returns:
            3-letter team abbreviation, or first 3 chars if not found
        """
        return TEAM_NAME_TO_ABBREV.get(team_name, team_name[:3].upper())

    def find_game_by_external_id(self, external_id: str) -> Optional[Game]:
        """
        Find a game by its external ID (from The Odds API).

        Args:
            external_id: The Odds API game ID

        Returns:
            Game object if found, None otherwise
        """
        return self.db.query(Game).filter(
            Game.external_id == external_id
        ).first()

    def find_game_by_teams(
        self,
        home_team: str,
        away_team: str,
        game_date: datetime
    ) -> Optional[Game]:
        """
        Find a game by team names and date.

        Args:
            home_team: Home team abbreviation
            away_team: Away team abbreviation
            game_date: Game date/time

        Returns:
            Game object if found, None otherwise
        """
        # Query for game on the same date with matching teams
        start_of_day = game_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = game_date.replace(hour=23, minute=59, second=59, microsecond=999999)

        return self.db.query(Game).filter(
            Game.home_team == home_team,
            Game.away_team == away_team,
            Game.game_date >= start_of_day,
            Game.game_date <= end_of_day
        ).first()

    def map_game_odds(
        self,
        odds_data: Dict,
        game: Game
    ) -> List[GameOdds]:
        """
        Transform odds API response to GameOdds models.

        Args:
            odds_data: Game odds data from The Odds API
            game: Game database model

        Returns:
            List of GameOdds models ready to insert
        """
        game_odds_list = []

        try:
            for bookmaker in odds_data.get("bookmakers", []):
                bookmaker_key = bookmaker.get("key")
                bookmaker_title = bookmaker.get("title")
                last_update = bookmaker.get("last_update")

                # Process each market
                for market in bookmaker.get("markets", []):
                    market_key = market.get("key")

                    if market_key == "h2h":
                        # Moneyline odds
                        outcome_name = market.get("outcomes", [{}])[0].get("name")
                        if outcome_name == game.home_team:
                            home_moneyline = market.get("outcomes", [{}])[0].get("price")
                        else:
                            away_moneyline = market.get("outcomes", [{}])[0].get("price")

                    elif market_key == "spreads":
                        # Point spread
                        for outcome in market.get("outcomes", []):
                            outcome_name = outcome.get("name")
                            price = outcome.get("price")
                            point = outcome.get("point")

                            if outcome_name == game.home_team:
                                home_spread_point = point
                                home_spread_price = price
                            else:
                                away_spread_point = point
                                away_spread_price = price

                    elif market_key == "totals":
                        # Over/Under total
                        for outcome in market.get("outcomes", []):
                            outcome_name = outcome.get("name")
                            price = outcome.get("price")
                            point = outcome.get("point")

                            if outcome_name == "Over":
                                totals_point = point
                                over_price = price
                            else:
                                under_price = price

                # Create GameOdds record
                game_odds = GameOdds(
                    id=str(uuid.uuid4()),
                    game_id=game.id,
                    bookmaker_key=bookmaker_key,
                    bookmaker_title=bookmaker_title,
                    home_moneyline=home_moneyline if 'home_moneyline' in locals() else None,
                    away_moneyline=away_moneyline if 'away_moneyline' in locals() else None,
                    home_spread_point=home_spread_point if 'home_spread_point' in locals() else None,
                    home_spread_price=home_spread_price if 'home_spread_price' in locals() else None,
                    away_spread_point=away_spread_point if 'away_spread_point' in locals() else None,
                    away_spread_price=away_spread_price if 'away_spread_price' in locals() else None,
                    totals_point=totals_point if 'totals_point' in locals() else None,
                    over_price=over_price if 'over_price' in locals() else None,
                    under_price=under_price if 'under_price' in locals() else None,
                    last_update=datetime.fromisoformat(last_update.replace("Z", "+00:00")) if last_update else datetime.utcnow(),
                    created_at=datetime.utcnow()
                )

                game_odds_list.append(game_odds)

        except Exception as e:
            logger.error(f"Error mapping game odds: {e}")

        return game_odds_list

    def find_player_by_name_and_team(
        self,
        player_name: str,
        team: str
    ) -> Optional[Player]:
        """
        Find a player by name and team.

        Args:
            player_name: Player full name
            team: Team abbreviation

        Returns:
            Player object if found, None otherwise
        """
        # Try exact match first
        player = self.db.query(Player).filter(
            Player.name == player_name,
            Player.team == team
        ).first()

        if player:
            return player

        # Try partial match
        player = self.db.query(Player).filter(
            Player.name.ilike(f"%{player_name}%"),
            Player.team == team
        ).first()

        return player

    def _market_to_stat_type(self, market_key: str) -> str:
        """
        Convert Odds API market key to database stat_type.

        Args:
            market_key: The Odds API market key (e.g., "player_points")

        Returns:
            Database stat_type value (e.g., "points")
        """
        mapping = {
            "player_points": "points",
            "player_rebounds": "rebounds",
            "player_assists": "assists",
            "player_threes": "threes"
        }
        return mapping.get(market_key, market_key.replace("player_", ""))

    def map_player_props_to_predictions(
        self,
        props_data: Dict,
        game: Game
    ) -> List[Dict]:
        """
        Map player props odds to existing predictions.

        Args:
            props_data: Player props data from The Odds API
                Structure: {
                    "event_id": str,
                    "markets": "player_points,player_rebounds,...",
                    "data": {full API response with bookmakers and markets}
                }
            game: Game database model

        Returns:
            List of prediction update data
        """
        updates = []
        outcomes_processed = 0

        try:
            # Extract the game data from the response
            game_data = props_data.get("data", {})

            if not game_data:
                logger.warning(f"No data returned for event {props_data.get('event_id')}")
                return updates

            logger.info(f"Starting player props mapping for game {game.id} ({game.away_team} @ {game.home_team})")

            # Get bookmakers from the API response
            bookmakers = game_data.get("bookmakers", [])

            if not bookmakers:
                logger.info(f"No bookmakers with player props data (not available yet)")
                return updates

            logger.info(f"Processing {len(bookmakers)} bookmakers with player props")

            # Define the player props markets we're looking for
            player_props_markets = ["player_points", "player_rebounds", "player_assists", "player_threes"]
            markets_found = set()

            for bookmaker_data in bookmakers:
                bookmaker_name = bookmaker_data.get("title", "Unknown")
                bookmaker_key = bookmaker_data.get("key", "unknown")

                # Each bookmaker has multiple markets
                for market in bookmaker_data.get("markets", []):
                    market_key = market.get("key")

                    # Skip non-player-props markets (h2h, spreads, totals, etc.)
                    if market_key not in player_props_markets:
                        continue

                    markets_found.add(market_key)

                    # Process player props outcomes
                    outcomes = market.get("outcomes", [])

                    if not outcomes:
                        continue

                    logger.info(f"  {bookmaker_name}: {market_key} - {len(outcomes)} outcomes")

                    for outcome in outcomes:
                        outcomes_processed += 1
                        player_name = outcome.get("description", "")

                        if not player_name or player_name == "None":
                            continue

                        # Try to find player by exact name match
                        player = self.find_player_by_name_and_team(player_name, game.home_team)
                        if not player:
                            player = self.find_player_by_name_and_team(player_name, game.away_team)

                        if not player:
                            logger.debug(f"    Player not found: {player_name}")
                            continue

                        # Check if prediction exists for this player, game, and stat_type
                        prediction = self.db.query(Prediction).filter(
                            Prediction.player_id == player.id,
                            Prediction.game_id == game.id,
                            Prediction.stat_type == self._market_to_stat_type(market_key)
                        ).first()

                        if not prediction:
                            logger.debug(f"    No prediction found for {player_name} - {market_key}")
                            continue

                        # Extract line and price
                        line = outcome.get("point")
                        price = outcome.get("price")
                        outcome_name = outcome.get("name", "")

                        # Determine if over or under
                        is_over = "over" in outcome_name.lower()

                        update_data = {
                            "prediction_id": str(prediction.id),
                            "bookmaker_line": line,
                            "bookmaker_name": bookmaker_name,
                            "over_price": price if is_over else None,
                            "under_price": price if not is_over else None,
                            "odds_last_updated": datetime.utcnow()
                        }

                        updates.append(update_data)
                        logger.info(f"    Mapped: {player.name} {market_key} {outcome_name} {line} @ {price}")

            # Log summary
            if markets_found:
                logger.info(f"Player props markets found: {', '.join(sorted(markets_found))}")
            else:
                logger.info(f"No player props markets available yet (requested: {', '.join(player_props_markets)})")

            logger.info(f"Player props mapping complete: {outcomes_processed} outcomes processed, {len(updates)} updates generated")

        except Exception as e:
            logger.error(f"Error mapping player props: {e}")

        return updates

    def create_games_from_odds_schedule(
        self,
        schedule_data: List[Dict]
    ) -> Dict[str, Any]:
        """
        Create or update Game records from The Odds API schedule data.

        This is the primary method for creating games in the hybrid approach.
        The Odds API becomes the single source of truth for game schedule.

        Args:
            schedule_data: List of game data from The Odds API

        Returns:
            Dictionary with created, updated, and skipped counts
        """
        created = 0
        updated = 0
        skipped = 0
        errors = []

        for game_data in schedule_data:
            try:
                # Extract basic game info
                external_id = game_data.get("id")
                sport_key = game_data.get("sport_key")
                home_team_name = game_data.get("home_team")
                away_team_name = game_data.get("away_team")
                commence_time_str = game_data.get("commence_time")

                if not all([external_id, home_team_name, away_team_name, commence_time_str]):
                    logger.warning(f"Skipping game with missing required fields: {game_data}")
                    skipped += 1
                    continue

                # Convert team names to abbreviations
                home_team = self._team_name_to_abbrev(home_team_name)
                away_team = self._team_name_to_abbrev(away_team_name)

                # Parse commence time (ISO format with timezone)
                commence_time = datetime.fromisoformat(commence_time_str.replace("Z", "+00:00"))

                # The Odds API has a 10-minute offset bug - subtract 10 minutes to get correct tip-off time
                commence_time = commence_time - timedelta(minutes=10)

                # Determine season from game date (NBA season spans calendar years)
                game_year = commence_time.year
                if commence_time.month >= 10:
                    season = game_year + 1
                else:
                    season = game_year

                # Check if game exists
                existing_game = self.find_game_by_external_id(external_id)

                if existing_game:
                    # Update existing game
                    existing_game.home_team = home_team
                    existing_game.away_team = away_team
                    existing_game.game_date = commence_time
                    existing_game.season = season
                    existing_game.status = "scheduled"  # Odds API only returns scheduled games
                    existing_game.updated_at = datetime.utcnow()
                    updated += 1
                    logger.debug(f"Updated game: {away_team} @ {home_team}")

                else:
                    # Create new game
                    import uuid
                    new_game = Game(
                        id=str(uuid.uuid4()),
                        external_id=external_id,
                        id_source="odds_api",  # Track that this came from The Odds API
                        game_date=commence_time,
                        away_team=away_team,
                        home_team=home_team,
                        status="scheduled",
                        season=season,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    self.db.add(new_game)
                    created += 1
                    logger.debug(f"Created game: {away_team} @ {home_team} on {commence_time}")

            except Exception as e:
                logger.error(f"Error processing game {game_data.get('id')}: {e}")
                errors.append(f"{game_data.get('id', 'unknown')}: {str(e)}")
                skipped += 1

        try:
            self.db.commit()
            logger.info(f"Game schedule sync: {created} created, {updated} updated, {skipped} skipped")
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error committing games: {e}")
            raise

        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors
        }

import uuid
