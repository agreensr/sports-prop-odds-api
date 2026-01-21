"""
Odds data mapper for transforming The Odds API responses to database models.

This module handles the transformation of odds data from The Odds API format
to the database model format, including game odds and player props.
"""
import logging
from datetime import datetime
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

    def map_player_props_to_predictions(
        self,
        props_data: Dict,
        game: Game
    ) -> List[Dict]:
        """
        Map player props odds to existing predictions.

        Args:
            props_data: Player props data from The Odds API
            game: Game database model

        Returns:
            List of prediction update data
        """
        updates = []

        try:
            for market_key, market_data in props_data.get("markets", {}).items():
                if not market_data:
                    continue

                for bookmaker_data in market_data:
                    bookmaker_title = bookmaker_data.get("bookmaker", {})
                    if not isinstance(bookmaker_title, dict):
                        continue

                    bookmaker_key = bookmaker_title.get("key", "unknown")
                    bookmaker_name = bookmaker_title.get("title", "Unknown")

                    for outcome in bookmaker_data.get("outcomes", []):
                        player_name = outcome.get("description", "")
                        if not player_name:
                            continue

                        # Extract player name from description like "Ja Morant Over 45.5"
                        # Format varies, try to extract name
                        name_parts = player_name.split()
                        if len(name_parts) >= 2:
                            # Assume first two parts are first/last name
                            first_name = name_parts[0]
                            last_name = name_parts[1]
                            search_name = f"{first_name} {last_name}"

                            # Try to find player
                            player = self.find_player_by_name_and_team(search_name, game.home_team)
                            if not player:
                                player = self.find_player_by_name_and_team(search_name, game.away_team)

                            if player:
                                # Check if prediction exists
                                prediction = self.db.query(Prediction).filter(
                                    Prediction.player_id == player.id,
                                    Prediction.game_id == game.id
                                ).first()

                                if prediction:
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

        except Exception as e:
            logger.error(f"Error mapping player props: {e}")

        return updates

import uuid
