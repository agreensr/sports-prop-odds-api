"""
Timezone utilities for NBA games.

All times are displayed in Central Time (CST/CDT).
Game times are stored in UTC and converted to Central for display.
"""
from datetime import datetime, timezone, timedelta
from typing import Tuple

# Central Time is UTC-6 (standard) or UTC-5 (daylight saving)
# We'll use a fixed offset approach for simplicity
CENTRAL_TIME_OFFSET = timedelta(hours=-6)  # CST is UTC-6
# During daylight saving (Mar-Nov), it's UTC-5

def utc_to_central(utc_datetime: datetime) -> datetime:
    """
    Convert UTC datetime to Central Time.

    Args:
        utc_datetime: UTC datetime (naive or timezone-aware)

    Returns:
        Central Time datetime (naive)

    Example:
        >>> utc_to_central(datetime(2026, 1, 21, 2, 0))
        datetime(2026, 1, 20, 20, 0)
    """
    # Ensure input is timezone-aware UTC
    if utc_datetime.tzinfo is None:
        utc_datetime = utc_datetime.replace(tzinfo=timezone.utc)

    # Apply Central Time offset (UTC-6 for CST)
    # For daylight saving, this would be UTC-5, but we'll use fixed CST-6 for now
    central_datetime = utc_datetime + CENTRAL_TIME_OFFSET

    # Return naive datetime (without tzinfo) for JSON serialization
    return central_datetime.replace(tzinfo=None)


def format_game_time_central(utc_datetime: datetime) -> str:
    """
    Format UTC datetime as Central Time string.

    Args:
        utc_datetime: UTC datetime

    Returns:
        Formatted datetime string in Central Time

    Example:
        >>> format_game_time_central(datetime(2026, 1, 21, 2, 0))
        '2026-01-20 20:00:00 CST'
    """
    central_dt = utc_to_central(utc_datetime)
    return f"{central_dt.strftime('%Y-%m-%d %H:%M:%S')} CST"


def format_game_time_central_readable(utc_datetime: datetime) -> str:
    """
    Format UTC datetime as readable Central Time string.

    Args:
        utc_datetime: UTC datetime

    Returns:
        Readable datetime string like "Jan 20, 2026 at 8:00 PM CST"
    """
    central_dt = utc_to_central(utc_datetime)
    return central_dt.strftime("%b %d, %Y at %-I:%M %p CST")


def is_game_completed(game_date_utc: datetime, status: str) -> bool:
    """
    Check if a game is completed based on UTC date and status.

    Args:
        game_date_utc: Game date in UTC
        status: Game status from database

    Returns:
        True if game is completed (final status or past date)
    """
    if status in ("final", "completed", "Final"):
        return True

    # Check if game date is in the past (more than 6 hours ago to account for late games)
    if game_date_utc.tzinfo is None:
        game_date_utc = game_date_utc.replace(tzinfo=timezone.utc)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
    return game_date_utc < cutoff


def get_game_display_info(game_date_utc: datetime, away_team: str, home_team: str, status: str) -> dict:
    """
    Get display information for a game with times in Central Time.

    Args:
        game_date_utc: Game date in UTC
        away_team: Away team abbreviation
        home_team: Home team abbreviation
        status: Game status

    Returns:
        Dictionary with display information including Central time
    """
    central_dt = utc_to_central(game_date_utc)

    return {
        "utc_time": game_date_utc,
        "central_time": central_dt,
        "central_time_str": format_game_time_central(game_date_utc),
        "readable_time": format_game_time_central_readable(game_date_utc),
        "time_only": central_dt.strftime("%-I:%M %p"),
        "date_only": central_dt.strftime("%Y-%m-%d"),
        "is_completed": is_game_completed(game_date_utc, status),
        "matchup": f"{away_team} @ {home_team}"
    }
