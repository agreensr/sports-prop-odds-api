"""Confidence scoring for game and player matches.

Calculates confidence scores (0.0 to 1.0) for matching entities across APIs.
Higher scores indicate more reliable matches.
"""
from datetime import datetime, timedelta, time
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

from app.services.sync.utils.name_normalizer import normalize, normalize_team_name, are_names_equal


async def calculate_game_match_confidence(
    nba_game: Dict[str, Any],
    odds_game: Dict[str, Any],
    db: Session
) -> float:
    """
    Calculate confidence score for matching an NBA game to an odds game.

    Confidence levels:
    - 1.0: Exact match (same date + both teams match exactly)
    - 0.95: Fuzzy time match (same date + teams + time within 2 hours)
    - 0.85: Team name fuzzy match (same date + teams match fuzzily)
    - 0.0: No match

    Args:
        nba_game: Game data from nba_api with keys:
            - game_date: datetime
            - home_team_id: int (nba_api team ID)
            - away_team_id: int (nba_api team ID)
        odds_game: Game data from The Odds API with keys:
            - commence_time: datetime
            - home_team: str (team name)
            - away_team: str (team name)
        db: Database session for querying team_mappings

    Returns:
        Confidence score between 0.0 and 1.0
    """
    from app.models.nba.models import TeamMapping

    # Extract dates
    nba_date = nba_game['game_date']
    if isinstance(nba_date, datetime):
        nba_date = nba_date.date()

    odds_date = odds_game['commence_time']
    if isinstance(odds_date, datetime):
        odds_date = odds_date.date()

    # Date must match (within same day)
    if nba_date != odds_date:
        return 0.0

    # Get team mappings for odds API teams
    home_mapping = db.query(TeamMapping).filter(
        TeamMapping.odds_api_name == odds_game['home_team']
    ).first()

    away_mapping = db.query(TeamMapping).filter(
        TeamMapping.odds_api_name == odds_game['away_team']
    ).first()

    # Check if teams match exactly
    home_match = home_mapping and home_mapping.nba_team_id == nba_game['home_team_id']
    away_match = away_mapping and away_mapping.nba_team_id == nba_game['away_team_id']

    if home_match and away_match:
        # Exact match - check time
        nba_time = nba_game.get('game_date')
        odds_time = odds_game['commence_time']

        if nba_time and odds_time:
            if isinstance(nba_time, datetime):
                nba_time = nba_time.time()
            if isinstance(odds_time, datetime):
                odds_time = odds_time.time()

            # If times match closely (within 2 hours), it's exact
            time_diff = _time_difference_minutes(nba_time, odds_time)
            if time_diff is not None and time_diff <= 120:
                return 1.0
            else:
                # Same day and teams, but time differs significantly
                return 0.95
        else:
            # No time info available, but teams match
            return 0.95

    # Try fuzzy team name matching if exact match failed
    home_fuzzy_score = _fuzzy_team_match(
        nba_game['home_team_id'],
        odds_game['home_team'],
        db
    )
    away_fuzzy_score = _fuzzy_team_match(
        nba_game['away_team_id'],
        odds_game['away_team'],
        db
    )

    # Both teams must have at least decent fuzzy match
    if home_fuzzy_score >= 0.85 and away_fuzzy_score >= 0.85:
        # Average the two scores
        return (home_fuzzy_score + away_fuzzy_score) / 2

    return 0.0


def _time_difference_minutes(time1: time, time2: time) -> Optional[int]:
    """
    Calculate the difference in minutes between two times.

    Args:
        time1: First time
        time2: Second time

    Returns:
        Absolute difference in minutes, or None if times can't be compared
    """
    if not time1 or not time2:
        return None

    # Convert to minutes since midnight
    minutes1 = time1.hour * 60 + time1.minute
    minutes2 = time2.hour * 60 + time2.minute

    return abs(minutes1 - minutes2)


def _fuzzy_team_match(nba_team_id: int, odds_team_name: str, db: Session) -> float:
    """
    Fuzzy match a team name against NBA team IDs.

    Checks:
    1. Team mapping exists and matches
    2. Team name similarity (Levenshtein)
    3. Alternate names in team_mappings

    Args:
        nba_team_id: nba_api team ID
        odds_team_name: Team name from The Odds API
        db: Database session

    Returns:
        Confidence score 0.0 to 1.0
    """
    from app.models.nba.models import TeamMapping

    # Try exact match via team_mappings
    mapping = db.query(TeamMapping).filter(
        TeamMapping.nba_team_id == nba_team_id
    ).first()

    if not mapping:
        return 0.0

    # Check if odds name matches
    if are_names_equal(mapping.odds_api_name or "", odds_team_name):
        return 1.0

    # Check alternate names
    import json
    if mapping.alternate_names:
        try:
            alt_names = json.loads(mapping.alternate_names)
            normalized_odds = normalize(odds_team_name)
            for alt_name in alt_names:
                if are_names_equal(alt_name, odds_team_name):
                    return 0.95
                if normalize(alt_name) == normalized_odds:
                    return 0.90
        except (json.JSONDecodeError, TypeError):
            pass

    # Try fuzzy matching on team name
    from rapidfuzz import fuzz
    target_name = mapping.nba_full_name
    score = fuzz.WRatio(
        normalize(target_name),
        normalize(odds_team_name)
    )

    # Convert to 0-1 scale
    if score >= 90:
        return 0.85
    elif score >= 80:
        return 0.70
    else:
        return 0.0


async def calculate_player_match_confidence(
    name1: str,
    name2: str,
    context: Optional[Dict[str, Any]] = None
) -> float:
    """
    Calculate confidence score for matching two player names.

    Confidence levels:
    - 1.0: Exact match after normalization
    - 0.95: Normalized match (with suffix/punctuation differences)
    - 0.85: Fuzzy match (similar but not identical)
    - 0.0: No match

    Args:
        name1: First player name
        name2: Second player name
        context: Optional context dict with:
            - team_match: bool (whether teams match, boosts confidence)
            - position_match: bool (whether positions match)
            - similarity_score: float (from fuzzy matcher)

    Returns:
        Confidence score between 0.0 and 1.0
    """
    context = context or {}

    # Check exact match after normalization
    if are_names_equal(name1, name2):
        return 1.0

    # Check normalized match
    norm1 = normalize(name1)
    norm2 = normalize(name2)

    if norm1 == norm2:
        return 0.95

    # Try fuzzy matching
    from rapidfuzz import fuzz
    score = fuzz.WRatio(norm1, norm2)

    if score >= 90:
        confidence = 0.85
    elif score >= 80:
        confidence = 0.70
    else:
        return 0.0

    # Boost confidence if context supports the match
    if context.get('team_match'):
        confidence += 0.05
    if context.get('position_match'):
        confidence += 0.03

    return min(confidence, 1.0)


def get_match_method_description(confidence: float, method: str) -> str:
    """
    Get human-readable description of a match.

    Args:
        confidence: Confidence score (0.0 to 1.0)
        method: Match method identifier

    Returns:
        Human-readable description
    """
    confidence_pct = confidence * 100

    descriptions = {
        'exact': f'Exact match ({confidence_pct:.0f}% confidence)',
        'fuzzy_time': f'Time-adjusted match ({confidence_pct:.0f}% confidence)',
        'fuzzy_team_name': f'Team name fuzzy match ({confidence_pct:.0f}% confidence)',
        'normalized': f'Normalized name match ({confidence_pct:.0f}% confidence)',
        'fuzzy': f'Fuzzy name match ({confidence_pct:.0f}% confidence)',
        'manual': 'Manual match (user verified)',
    }

    return descriptions.get(method, f'Unknown method ({confidence_pct:.0f}% confidence)')
