"""
NHL Player Props Parser for Odds API response data.

This service parses NHL player prop odds from The Odds API and extracts
line data for specific players and stat types.

NHL-SPECIFIC MARKETS:
- player_goals: Goal scorer props
- player_assists: Assist props
- player_points: Point (goals + assists) props
- player_shots: Shots on goal props

The Odds API returns player props in a nested structure similar to NBA,
but with NHL-specific market keys and player names.
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from app.core.logging import get_logger

logger = get_logger(__name__)


class NHLPlayerPropsParser:
    """
    Parse NHL player props from Odds API response.

    Features:
    - Map NHL stat types to Odds API market keys
    - Extract line data for specific player and stat type
    - Support multiple bookmakers with priority order
    - Handle name normalization for player matching
    """

    # Map stat types to Odds API market keys for NHL
    MARKET_MAP = {
        "goals": "player_goals",
        "assists": "player_assists",
        "points": "player_points",
        "shots": "player_shots",
    }

    # Bookmaker priority (highest to lowest)
    DEFAULT_BOOKMAKER_PRIORITY = [
        "draftkings",
        "fanduel",
        "betmgm",
        "caesars",
        "pointsbetus",
    ]

    # Common name variations for NHL player matching
    NAME_NORMALIZATION_MAP = {
        "j": "j.",
        "jr": "jr.",
        "sr": "sr.",
        "ii": "ii",
        "iii": "iii",
        "iv": "iv",
    }

    def __init__(
        self,
        bookmaker_priority: Optional[List[str]] = None
    ):
        """
        Initialize the NHL player props parser.

        Args:
            bookmaker_priority: Ordered list of preferred bookmakers.
                              If None, uses DEFAULT_BOOKMAKER_PRIORITY.
        """
        self.bookmaker_priority = bookmaker_priority or self.DEFAULT_BOOKMAKER_PRIORITY

    def extract_player_lines(
        self,
        odds_response: Dict,
        player_name: str,
        stat_type: str
    ) -> Optional[Dict]:
        """
        Extract line data for a specific NHL player and stat type.

        This method searches through the Odds API response to find
        the best available line for the specified player and stat.

        Args:
            odds_response: The full response from Odds API's get_event_player_props()
            player_name: Player name to search for (e.g., "Connor McDavid")
            stat_type: Stat type (goals, assists, points, shots)

        Returns:
            {
                "line": 0.5,
                "over_price": -110,
                "under_price": -110,
                "bookmaker": "draftkings",
                "fetched_at": "2025-01-29T12:00:00Z"
            }
            Or None if no line found

        Example:
            >>> parser = NHLPlayerPropsParser()
            >>> line = parser.extract_player_lines(odds_response, "Connor McDavid", "points")
            >>> print(line["line"])  # 1.5
        """
        if not odds_response or not odds_response.get("data"):
            logger.warning("Empty odds response provided")
            return None

        market_key = self.MARKET_MAP.get(stat_type)
        if not market_key:
            logger.warning(f"Unknown NHL stat type: {stat_type}")
            return None

        game_data = odds_response["data"]
        bookmakers = game_data.get("bookmakers", [])

        if not bookmakers:
            logger.warning("No bookmakers found in odds response")
            return None

        # Normalize player name for matching
        normalized_search_name = self._normalize_player_name(player_name)

        # Collect all available lines from all bookmakers
        all_lines = []

        for bookmaker in bookmakers:
            bookmaker_key = bookmaker.get("key", "")
            bookmaker_title = bookmaker.get("title", bookmaker_key)

            # Find the market for this stat type
            markets = bookmaker.get("markets", [])
            target_market = None

            for market in markets:
                if market.get("key") == market_key:
                    target_market = market
                    break

            if not target_market:
                continue

            # Extract outcomes (OVER/UNDER) for this market
            outcomes = target_market.get("outcomes", [])

            over_outcome = None
            under_outcome = None

            for outcome in outcomes:
                outcome_name = outcome.get("name", "")
                outcome_description = outcome.get("description", "")

                # Check if this outcome matches our player
                if self._player_matches(outcome_name, outcome_description, normalized_search_name):
                    # Determine if it's OVER or UNDER
                    if "over" in outcome_name.lower():
                        over_outcome = outcome
                    elif "under" in outcome_name.lower():
                        under_outcome = outcome

            # If we found both OVER and UNDER, extract the line
            if over_outcome and under_outcome:
                line_data = self._extract_line_from_outcomes(
                    over_outcome,
                    under_outcome,
                    bookmaker_key,
                    bookmaker_title
                )
                if line_data:
                    # Add priority based on bookmaker preference
                    priority = self._get_bookmaker_priority(bookmaker_key)
                    line_data["priority"] = priority
                    all_lines.append(line_data)

        if not all_lines:
            logger.debug(
                f"No NHL lines found for player={player_name}, stat_type={stat_type}"
            )
            return None

        # Sort by priority (lower number = higher priority)
        all_lines.sort(key=lambda x: x.get("priority", 999))

        # Return the highest priority line
        best_line = all_lines[0]
        logger.info(
            f"Found NHL line for {player_name} {stat_type}: {best_line['line']} "
            f"({best_line['bookmaker']})"
        )

        return best_line

    def extract_all_player_lines(
        self,
        odds_response: Dict,
        stat_type: str
    ) -> Dict[str, Dict]:
        """
        Extract all NHL player lines for a specific stat type from a game.

        Useful for bulk fetching all lines for a game at once.

        Args:
            odds_response: The full response from Odds API's get_event_player_props()
            stat_type: Stat type (goals, assists, points, shots)

        Returns:
            Dict mapping player names to line data:
            {
                "Connor McDavid": {
                    "line": 1.5,
                    "over_price": -110,
                    "under_price": -110,
                    "bookmaker": "draftkings"
                },
                ...
            }
        """
        if not odds_response or not odds_response.get("data"):
            return {}

        market_key = self.MARKET_MAP.get(stat_type)
        if not market_key:
            return {}

        game_data = odds_response["data"]
        bookmakers = game_data.get("bookmakers", [])

        if not bookmakers:
            return {}

        all_player_lines = {}

        # Process each bookmaker in priority order
        for bookmaker in bookmakers:
            bookmaker_key = bookmaker.get("key", "")
            bookmaker_title = bookmaker.get("title", bookmaker_key)

            # Skip if we've already found lines from a higher-priority bookmaker
            markets = bookmaker.get("markets", [])

            for market in markets:
                if market.get("key") != market_key:
                    continue

                outcomes = market.get("outcomes", [])

                # Group outcomes by player
                player_outcomes: Dict[str, Dict] = {}

                for outcome in outcomes:
                    outcome_name = outcome.get("name", "")
                    outcome_description = outcome.get("description", "")

                    # Extract player name from description
                    player_name = self._extract_player_name_from_description(
                        outcome_description
                    )

                    if not player_name:
                        continue

                    # Skip if we already have this player from a higher-priority bookmaker
                    if player_name in all_player_lines:
                        continue

                    if player_name not in player_outcomes:
                        player_outcomes[player_name] = {}

                    if "over" in outcome_name.lower():
                        player_outcomes[player_name]["over"] = outcome
                    elif "under" in outcome_name.lower():
                        player_outcomes[player_name]["under"] = outcome

                # Create line data for each player
                for player_name, outcomes_dict in player_outcomes.items():
                    if "over" in outcomes_dict and "under" in outcomes_dict:
                        line_data = self._extract_line_from_outcomes(
                            outcomes_dict["over"],
                            outcomes_dict["under"],
                            bookmaker_key,
                            bookmaker_title
                        )
                        if line_data:
                            all_player_lines[player_name] = line_data

        return all_player_lines

    def _extract_line_from_outcomes(
        self,
        over_outcome: Dict,
        under_outcome: Dict,
        bookmaker_key: str,
        bookmaker_title: str
    ) -> Optional[Dict]:
        """
        Extract line data from OVER and UNDER outcomes.

        Args:
            over_outcome: The OVER outcome dict
            under_outcome: The UNDER outcome dict
            bookmaker_key: Bookmaker API key
            bookmaker_title: Bookmaker display name

        Returns:
            Line data dict or None if extraction fails
        """
        # Both outcomes should have the same point value
        over_point = over_outcome.get("point")
        under_point = under_outcome.get("point")

        if over_point is None or under_point is None:
            return None

        # Validate that points match
        if abs(over_point - under_point) > 0.01:
            logger.warning(
                f"OVER/UNDER points don't match: {over_point} vs {under_point}"
            )
            # Use the average
            line_point = (over_point + under_point) / 2
        else:
            line_point = over_point

        return {
            "line": line_point,
            "over_price": over_outcome.get("price"),
            "under_price": under_outcome.get("price"),
            "bookmaker": bookmaker_key,
            "bookmaker_title": bookmaker_title,
            "fetched_at": datetime.utcnow().isoformat()
        }

    def _normalize_player_name(self, name: str) -> str:
        """
        Normalize NHL player name for matching.

        Converts to lowercase and handles common variations.
        NHL names often have accents and special characters.
        """
        if not name:
            return ""

        normalized = name.lower().strip()

        # Remove common suffixes and punctuation for comparison
        for suffix in [" jr.", " sr.", " ii", " iii", " iv"]:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)].strip()

        return normalized

    def _player_matches(
        self,
        outcome_name: str,
        outcome_description: str,
        normalized_search_name: str
    ) -> bool:
        """
        Check if an outcome matches the searched player.

        Args:
            outcome_name: The outcome name (e.g., "Connor McDavid OVER 1.5 Points")
            outcome_description: The outcome description (e.g., "Connor McDavid - Points")
            normalized_search_name: The normalized player name we're searching for

        Returns:
            True if this outcome matches the player
        """
        # Check both name and description fields
        for text in [outcome_name, outcome_description]:
            if not text:
                continue

            normalized_text = self._normalize_player_name(text)

            # Direct match
            if normalized_search_name in normalized_text:
                return True

            # Split by common separators and check each part
            # This handles "McDavid Connor" vs "Connor McDavid"
            parts = normalized_text.replace("-", " ").replace(".", " ").split()
            for part in parts:
                if len(part) > 2 and part in normalized_search_name:
                    return True

        return False

    def _extract_player_name_from_description(
        self,
        description: str
    ) -> Optional[str]:
        """
        Extract player name from NHL outcome description.

        Expected format: "Player Name - Stat Type"
        Example: "Connor McDavid - Points"

        Args:
            description: The outcome description string

        Returns:
            Player name or None
        """
        if not description:
            return None

        # Split by common delimiters
        for delimiter in [" - ", " | ", "-", "|"]:
            if delimiter in description:
                parts = description.split(delimiter)
                if parts:
                    name_part = parts[0].strip()
                    if len(name_part) > 2:
                        return name_part

        # If no delimiter found, try to parse the whole string
        text = description.strip()

        # Remove stat type references
        for stat in ["goals", "assists", "points", "shots", "points "]:
            text = text.lower().replace(stat, "")

        # Remove over/under indicators
        for indicator in ["over", "under", "o/", "u/"]:
            text = text.lower().replace(indicator, "")

        # Clean up and return if reasonable
        cleaned = text.strip().strip("-").strip()
        if len(cleaned) > 2 and len(cleaned) < 50:
            return cleaned

        return None

    def _get_bookmaker_priority(self, bookmaker_key: str) -> int:
        """
        Get priority score for a bookmaker.

        Lower number = higher priority.

        Args:
            bookmaker_key: The bookmaker's API key

        Returns:
            Priority score (0-999, where 0 is highest priority)
        """
        try:
            return self.bookmaker_priority.index(bookmaker_key.lower())
        except ValueError:
            return 999  # Lowest priority for unknown bookmakers

    def get_market_key(self, stat_type: str) -> Optional[str]:
        """
        Get the Odds API market key for an NHL stat type.

        Args:
            stat_type: Internal stat type name

        Returns:
            Odds API market key or None if not found
        """
        return self.MARKET_MAP.get(stat_type)

    def get_supported_stat_types(self) -> List[str]:
        """
        Get list of supported NHL stat types.

        Returns:
            List of stat type names
        """
        return list(self.MARKET_MAP.keys())


# Singleton instance for convenience
_default_nhl_parser: Optional[NHLPlayerPropsParser] = None


def get_nhl_player_props_parser(
    bookmaker_priority: Optional[List[str]] = None
) -> NHLPlayerPropsParser:
    """
    Get or create the singleton NHLPlayerPropsParser instance.

    Args:
        bookmaker_priority: Optional custom bookmaker priority list

    Returns:
        NHLPlayerPropsParser instance
    """
    global _default_nhl_parser
    if _default_nhl_parser is None or bookmaker_priority is not None:
        _default_nhl_parser = NHLPlayerPropsParser(bookmaker_priority)
    return _default_nhl_parser
