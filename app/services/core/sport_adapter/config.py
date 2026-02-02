"""
Sport Configuration for Multi-Sport Support.

This module centralizes all sport-specific configuration including:
- Sport identifiers and names
- ESPN API paths
- Position definitions and stat types
- Prediction thresholds
- Cache TTL settings
- Data source configurations

This enables the base adapter to work with any sport through configuration
rather than code duplication.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class PositionConfig:
    """Configuration for a position in a sport."""
    abbreviation: str
    name: str
    primary_stat: str  # Default stat for this position
    stat_types: List[str]  # All stat types this position can predict


@dataclass
class SportConfig:
    """
    Complete configuration for a sport.

    This class contains all sport-specific settings needed for:
    - Prediction generation
    - API data fetching
    - Stat type mapping
    - Position handling
    """
    # Sport identification
    sport_id: str
    name: str
    abbreviation: str

    # API paths
    espn_sport_path: str  # Path for ESPN API (e.g., "basketball/nba")
    odds_api_sport: str  # Sport key for The Odds API

    # Prediction settings
    recommendation_threshold: float  # Min confidence for OVER/UNDER recommendation
    variance_percent: int  # Variance to apply to predictions

    # Data source settings
    supports_per_36_stats: bool  # True if stats are per-36 minutes
    active_field_is_boolean: bool  # True if active is Boolean, False if string
    active_field_value: str  # Value for active players ("True" or "active")

    # Season stats settings
    uses_season_stats: bool  # Whether to use cached season stats
    season_stats_ttl_hours: int  # TTL for season stats cache

    # Cache TTL (seconds)
    cache_ttl_season: int  # During active season
    cache_ttl_offseason: int  # During offseason

    # Position configurations
    positions: Dict[str, PositionConfig]  # Abbreviation -> PositionConfig

    # Default stat types to predict
    default_stat_types: List[str]

    # Position to primary stat mapping
    position_primary_stats: Dict[str, str]  # position -> primary_stat


# =============================================================================
# SPORT CONFIGURATIONS
# =============================================================================

# NBA Configuration
NBA_CONFIG = SportConfig(
    sport_id="nba",
    name="National Basketball Association",
    abbreviation="NBA",
    espn_sport_path="basketball/nba",
    odds_api_sport="basketball_nba",
    recommendation_threshold=0.60,
    variance_percent=5,
    supports_per_36_stats=True,
    active_field_is_boolean=True,
    active_field_value="True",
    uses_season_stats=True,
    season_stats_ttl_hours=24,
    cache_ttl_season=300,
    cache_ttl_offseason=86400,
    positions={
        "PG": PositionConfig("PG", "Point Guard", "assists", ["points", "rebounds", "assists", "threes"]),
        "SG": PositionConfig("SG", "Shooting Guard", "points", ["points", "rebounds", "assists", "threes"]),
        "SF": PositionConfig("SF", "Small Forward", "points", ["points", "rebounds", "assists", "threes"]),
        "PF": PositionConfig("PF", "Power Forward", "rebounds", ["points", "rebounds", "assists", "threes"]),
        "C": PositionConfig("C", "Center", "rebounds", ["points", "rebounds", "assists", "threes"]),
        "G": PositionConfig("G", "Guard", "points", ["points", "rebounds", "assists", "threes"]),
        "F": PositionConfig("F", "Forward", "points", ["points", "rebounds", "assists", "threes"]),
    },
    default_stat_types=["points", "rebounds", "assists", "threes"],
    position_primary_stats={
        "PG": "assists",
        "SG": "points",
        "SF": "points",
        "PF": "rebounds",
        "C": "rebounds",
        "G": "points",
        "F": "points",
    },
)

# Position averages (fallback when no stats available)
NBA_POSITION_AVERAGES = {
    "PG": {"points": 15.2, "rebounds": 3.5, "assists": 6.8, "threes": 2.1},
    "SG": {"points": 16.5, "rebounds": 4.2, "assists": 3.8, "threes": 2.3},
    "SF": {"points": 14.8, "rebounds": 5.5, "assists": 3.2, "threes": 1.8},
    "PF": {"points": 13.5, "rebounds": 7.8, "assists": 2.8, "threes": 1.2},
    "C": {"points": 12.1, "rebounds": 8.5, "assists": 2.2, "threes": 0.5},
    "G": {"points": 15.8, "rebounds": 3.8, "assists": 5.3, "threes": 2.2},
    "F": {"points": 14.2, "rebounds": 6.5, "assists": 3.0, "threes": 1.8},
}


# NFL Configuration
NFL_CONFIG = SportConfig(
    sport_id="nfl",
    name="National Football League",
    abbreviation="NFL",
    espn_sport_path="football/nfl",
    odds_api_sport="americanfootball_nfl",
    recommendation_threshold=0.58,
    variance_percent=8,
    supports_per_36_stats=False,
    active_field_is_boolean=False,
    active_field_value="active",
    uses_season_stats=False,
    season_stats_ttl_hours=48,
    cache_ttl_season=600,
    cache_ttl_offseason=86400,
    positions={
        "QB": PositionConfig("QB", "Quarterback", "passing_yards", ["passing_yards", "rushing_yards"]),
        "RB": PositionConfig("RB", "Running Back", "rushing_yards", ["rushing_yards", "receptions", "touchdowns"]),
        "WR": PositionConfig("WR", "Wide Receiver", "receptions", ["receptions", "receiving_yards", "touchdowns"]),
        "TE": PositionConfig("TE", "Tight End", "receptions", ["receptions", "receiving_yards", "touchdowns"]),
        "K": PositionConfig("K", "Kicker", None, ["field_goals", "extra_points"]),  # Special case
        "DST": PositionConfig("DST", "Team Defense", None, ["sacks", "interceptions", "fumbles"]),  # Special case
    },
    default_stat_types=["passing_yards", "rushing_yards", "receptions", "touchdowns"],
    position_primary_stats={
        "QB": "passing_yards",
        "RB": "rushing_yards",
        "WR": "receptions",
        "TE": "receptions",
        "K": None,
        "DST": None,
    },
)

NFL_POSITION_AVERAGES = {
    "QB": {"passing_yards": 220.5, "rushing_yards": 15.2, "receptions": 0.5, "touchdowns": 1.2},
    "RB": {"passing_yards": 0, "rushing_yards": 65.8, "receptions": 2.5, "touchdowns": 0.4},
    "WR": {"passing_yards": 0, "rushing_yards": 8.2, "receptions": 5.2, "touchdowns": 0.5},
    "TE": {"passing_yards": 0, "rushing_yards": 5.5, "receptions": 4.1, "touchdowns": 0.3},
    "K": {"field_goals": 1.8, "extra_points": 4.1},
    "DST": {"sacks": 2.5, "interceptions": 1.0, "fumbles": 1.0},
}


# MLB Configuration
MLB_CONFIG = SportConfig(
    sport_id="mlb",
    name="Major League Baseball",
    abbreviation="MLB",
    espn_sport_path="baseball/mlb",
    odds_api_sport="baseball_mlb",
    recommendation_threshold=0.58,
    variance_percent=8,
    supports_per_36_stats=False,
    active_field_is_boolean=False,
    active_field_value="active",
    uses_season_stats=False,
    season_stats_ttl_hours=48,
    cache_ttl_season=300,
    cache_ttl_offseason=86400,
    positions={
        "P": PositionConfig("P", "Pitcher", "strikeouts", ["strikeouts", "wins", "era"]),  # Special case
        "C": PositionConfig("C", "Catcher", "hits", ["hits", "home_runs", "rbi"]),
        "1B": PositionConfig("1B", "First Baseman", "hits", ["hits", "home_runs", "rbi"]),
        "2B": PositionConfig("2B", "Second Baseman", "hits", ["hits", "home_runs", "rbi"]),
        "SS": PositionConfig("SS", "Shortstop", "hits", ["hits", "home_runs", "rbi"]),
        "3B": PositionConfig("3B", "Third Baseman", "hits", ["hits", "home_runs", "rbi"]),
        "OF": PositionConfig("OF", "Outfield", "hits", ["hits", "home_runs", "rbi"]),
        "DH": PositionConfig("DH", "Designated Hitter", "hits", ["hits", "home_runs", "rbi"]),
    },
    default_stat_types=["hits", "home_runs", "rbi", "strikeouts"],
    position_primary_stats={
        "P": "strikeouts",
        "C": "hits",
        "1B": "hits",
        "2B": "hits",
        "SS": "hits",
        "3B": "hits",
        "OF": "hits",
        "DH": "hits",
    },
)

MLB_POSITION_AVERAGES = {
    "P": {"strikeouts": 6.8, "wins": 0.12, "era": 4.25},
    "C": {"hits": 1.2, "home_runs": 0.08, "rbi": 0.5},
    "1B": {"hits": 1.5, "home_runs": 0.12, "rbi": 0.7},
    "2B": {"hits": 1.4, "home_runs": 0.10, "rbi": 0.6},
    "SS": {"hits": 1.3, "home_runs": 0.08, "rbi": 0.5},
    "3B": {"hits": 1.3, "home_runs": 0.10, "rbi": 0.6},
    "OF": {"hits": 1.2, "home_runs": 0.11, "rbi": 0.5},
    "DH": {"hits": 1.3, "home_runs": 0.13, "rbi": 0.6},
}


# NHL Configuration
NHL_CONFIG = SportConfig(
    sport_id="nhl",
    name="National Hockey League",
    abbreviation="NHL",
    espn_sport_path="hockey/nhl",
    odds_api_sport="icehockey_nhl",
    recommendation_threshold=0.58,
    variance_percent=8,
    supports_per_36_stats=False,
    active_field_is_boolean=False,
    active_field_value="active",
    uses_season_stats=False,
    season_stats_ttl_hours=48,
    cache_ttl_season=300,
    cache_ttl_offseason=86400,
    positions={
        "C": PositionConfig("C", "Center", "assists", ["goals", "assists", "shots", "points"]),
        "LW": PositionConfig("LW", "Left Wing", "goals", ["goals", "assists", "shots", "points"]),
        "RW": PositionConfig("RW", "Right Wing", "goals", ["goals", "assists", "shots", "points"]),
        "D": PositionConfig("D", "Defenseman", "assists", ["goals", "assists", "shots", "points"]),
        "G": PositionConfig("G", "Goalie", "saves", ["goals_against", "saves", "wins", "gaa"]),  # Special case
    },
    default_stat_types=["goals", "assists", "shots", "points"],
    position_primary_stats={
        "C": "goals",
        "LW": "goals",
        "RW": "goals",
        "D": "assists",
        "G": "saves",
    },
)

NHL_POSITION_AVERAGES = {
    "C": {"goals": 0.25, "assists": 0.35, "shots": 2.8, "points": 0.6},
    "LW": {"goals": 0.28, "assists": 0.32, "shots": 3.0, "points": 0.6},
    "RW": {"goals": 0.27, "assists": 0.33, "shots": 2.9, "points": 0.6},
    "D": {"goals": 0.08, "assists": 0.28, "shots": 1.8, "points": 0.36},
    "G": {"goals_against": 2.8, "saves": 25.5, "wins": 0.62, "gaa": 2.85},
}


# =============================================================================
# SPORT REGISTRY
# =============================================================================

SPORT_CONFIGS: Dict[str, SportConfig] = {
    "nba": NBA_CONFIG,
    "nfl": NFL_CONFIG,
    "mlb": MLB_CONFIG,
    "nhl": NHL_CONFIG,
}

# Position averages for fallback (when no historical data)
POSITION_AVERAGES: Dict[str, Dict[str, Dict[str, float]]] = {
    "nba": NBA_POSITION_AVERAGES,
    "nfl": NFL_POSITION_AVERAGES,
    "mlb": MLB_POSITION_AVERAGES,
    "nhl": NHL_POSITION_AVERAGES,
}


def get_sport_config(sport_id: str) -> SportConfig:
    """
    Get configuration for a sport.

    Args:
        sport_id: Sport identifier ('nba', 'nfl', 'mlb', 'nhl')

    Returns:
        SportConfig for the sport

    Raises:
        ValueError: If sport_id is not recognized
    """
    sport_id = sport_id.lower()
    if sport_id not in SPORT_CONFIGS:
        raise ValueError(f"Unknown sport: {sport_id}. Available: {list(SPORT_CONFIGS.keys())}")
    return SPORT_CONFIGS[sport_id]


def get_position_averages(sport_id: str, position: str) -> Dict[str, float]:
    """
    Get position averages for fallback prediction.

    Args:
        sport_id: Sport identifier
        position: Position abbreviation

    Returns:
        Dictionary of stat_type -> average_value
    """
    config = get_sport_config(sport_id)
    position = position.upper()

    if position not in config.positions:
        # Return generic averages if position not found
        return {}

    # Get the position config to find primary stat
    pos_config = config.positions.get(position)
    if not pos_config:
        return {}

    # Get position averages for the sport
    sport_averages = POSITION_AVERAGES.get(sport_id, {})
    return sport_averages.get(position, {})


def get_espn_sport_path(sport_id: str) -> str:
    """Get ESPN API path for a sport."""
    return get_sport_config(sport_id).espn_sport_path


def get_recommendation_threshold(sport_id: str) -> float:
    """Get confidence threshold for recommendation."""
    return get_sport_config(sport_id).recommendation_threshold


def get_variance_percent(sport_id: str) -> int:
    """Get variance percentage to apply to predictions."""
    return get_sport_config(sport_id).variance_percent


def supports_per_36_stats(sport_id: str) -> bool:
    """Check if sport uses per-36 stats."""
    return get_sport_config(sport_id).supports_per_36_stats


def get_active_field_value(sport_id: str) -> str:
    """Get the value for the active field."""
    return get_sport_config(sport_id).active_field_value


def get_active_field_is_boolean(sport_id: str) -> bool:
    """Check if the active field is boolean or string."""
    return get_sport_config(sport_id).active_field_is_boolean


def is_stat_relevant_for_position(
    sport_id: str,
    position: str,
    stat_type: str
) -> bool:
    """
    Check if a stat type is relevant for a position.

    Args:
        sport_id: Sport identifier
        position: Position abbreviation
        stat_type: Stat type to check

    Returns:
        True if the stat is relevant for the position
    """
    config = get_sport_config(sport_id)
    position = position.upper()
    stat_type = stat_type.lower()

    pos_config = config.positions.get(position)
    if not pos_config:
        return True  # If position not found, allow all stats

    # Check if stat_type is in the position's stat types
    return stat_type in pos_config.stat_types


def get_primary_stat_for_position(sport_id: str, position: str) -> Optional[str]:
    """Get the primary stat for a position."""
    config = get_sport_config(sport_id)
    position = position.upper()

    pos_config = config.positions.get(position)
    if pos_config:
        return pos_config.primary_stat

    # Fall back to position_primary_stats mapping
    return config.position_primary_stats.get(position)


def get_default_stat_types(sport_id: str) -> List[str]:
    """Get default stat types for a sport."""
    return get_sport_config(sport_id).default_stat_types


def get_cache_ttl(sport_id: str, in_season: bool = True) -> int:
    """
    Get cache TTL for a sport based on season status.

    Args:
        sport_id: Sport identifier
        in_season: Whether sport is in active season

    Returns:
        Cache TTL in seconds
    """
    config = get_sport_config(sport_id)
    if in_season:
        return config.cache_ttl_season
    else:
        return config.cache_ttl_offseason
