"""
Timezone utilities for the sports betting API.

All times are stored in UTC and converted to Eastern Time for display.
NBA games are typically scheduled in ET.

Eastern Time Zones:
- EST (Eastern Standard Time): UTC-5, November - March
- EDT (Eastern Daylight Time): UTC-4, March - November
- DST transitions: Second Sunday in March → First Sunday in November

Central Time Zones (legacy reference):
- CST (Central Standard Time): UTC-6, November - March
- CDT (Central Daylight Time): UTC-5, March - November
"""
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional

# UTC timezone for Python < 3.11 compatibility
try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc


# =============================================================================
# SEASON & CACHE TTL UTILITIES
# =============================================================================

# Sport-specific active season ranges (month is 1-indexed)
# Format: (start_month, start_day) to (end_month, end_day)
# Seasons span calendar years (e.g., NBA 2024-25 starts Oct 2024, ends June 2025)
SPORT_SEASONS = {
    "nba": {"start": (10, 1), "end": (6, 30)},    # Oct 1 - Jun 30 (NBA regular season + playoffs)
    "nfl": {"start": (9, 1), "end": (2, 15)},      # Sep 1 - Feb 15 (NFL regular season + playoffs/Super Bowl)
    "mlb": {"start": (3, 1), "end": (11, 15)},     # Mar 1 - Nov 15 (MLB regular season + playoffs/World Series)
    "nhl": {"start": (10, 1), "end": (6, 30)},    # Oct 1 - Jun 30 (NHL regular season + playoffs)
}

# Cache TTL settings (in seconds)
ACTIVE_SEASON_CACHE_TTL = {
    "nba": 300,      # 5 minutes during NBA season
    "nfl": 600,      # 10 minutes during NFL season
    "mlb": 300,      # 5 minutes during MLB season
    "nhl": 300,      # 5 minutes during NHL season
}

OFFSEASON_CACHE_TTL = {
    "nba": 86400,     # 24 hours during NBA offseason
    "nfl": 86400,     # 24 hours during NFL offseason
    "mlb": 86400,     # 24 hours during MLB offseason
    "nhl": 86400,     # 24 hours during NHL offseason
}


def is_in_season(sport_id: str, date: Optional[datetime] = None) -> bool:
    """
    Check if a given date is within the active season for a sport.

    Args:
        sport_id: Sport identifier ('nba', 'nfl', 'mlb', 'nhl')
        date: Date to check (datetime or date, defaults to current date if None)

    Returns:
        True if the date is within the active season, False otherwise

    Examples:
        >>> is_in_season('nba', datetime(2025, 1, 15))   # January = NBA season
        True
        >>> is_in_season('nba', datetime(2025, 8, 15))   # August = NBA offseason
        False
    """
    from datetime import date as DateType

    if sport_id not in SPORT_SEASONS:
        # Unknown sport - assume season is active for data freshness
        return True

    if date is None:
        date = datetime.now(UTC)

    # Handle date objects (convert to datetime)
    if isinstance(date, DateType) and not isinstance(date, datetime):
        date = datetime.combine(date, datetime.min.time())

    # Convert to naive datetime if timezone-aware for comparison
    if hasattr(date, 'tzinfo') and date.tzinfo is not None:
        date = date.replace(tzinfo=None)

    season_start = datetime(date.year, SPORT_SEASONS[sport_id]["start"][0],
                            SPORT_SEASONS[sport_id]["start"][1])
    season_end = datetime(date.year, SPORT_SEASONS[sport_id]["end"][0],
                          SPORT_SEASONS[sport_id]["end"][1])

    # Handle seasons that span calendar years (e.g., NBA Oct 2024 - Jun 2025)
    # If season starts later in the year than it ends, check cross-year
    if season_start > season_end:
        # Season spans two calendar years
        # We're in season if we're after the start date OR before the end date
        return date >= season_start or date <= season_end
    else:
        # Season is within a single calendar year
        return season_start <= date <= season_end


def get_cache_ttl(sport_id: str, default_ttl: int = 300, date: Optional[datetime] = None) -> int:
    """
    Get appropriate cache TTL based on whether the sport is in active season.

    During active season: Use shorter TTL for fresher data (player stats change daily)
    During offseason: Use longer TTL (less frequent data updates)

    Args:
        sport_id: Sport identifier ('nba', 'nfl', 'mlb', 'nhl')
        default_ttl: Fallback TTL if sport not found (default: 5 minutes)
        date: Specific date to check (defaults to current date if None)

    Returns:
        Cache TTL in seconds

    Examples:
        >>> # During NBA season (January)
        >>> get_cache_ttl('nba')
        300  # 5 minutes

        >>> # During NBA offseason (August)
        >>> from datetime import datetime
        >>> get_cache_ttl('nba', date=datetime(2025, 8, 15))
        86400  # 24 hours
    """
    if is_in_season(sport_id, date):
        return ACTIVE_SEASON_CACHE_TTL.get(sport_id, default_ttl)
    else:
        return OFFSEASON_CACHE_TTL.get(sport_id, default_ttl * 12)  # Much longer in offseason


# =============================================================================
# TIMEZONE CONVERSIONS
# =============================================================================
CENTRAL_STANDARD_OFFSET = timedelta(hours=-6)  # CST is UTC-6
CENTRAL_DAYLIGHT_OFFSET = timedelta(hours=-5)  # CDT is UTC-5

# Default Central Time offset (uses standard time as default)
# For accurate DST-aware conversion, use utc_to_central() function
CENTRAL_TIME_OFFSET = CENTRAL_STANDARD_OFFSET

# Eastern Time offsets (for NBA.com game times)
EASTERN_STANDARD_OFFSET = timedelta(hours=-5)  # EST is UTC-5
EASTERN_DAYLIGHT_OFFSET = timedelta(hours=-4)  # EDT is UTC-4


def et_to_utc(et_datetime: datetime) -> datetime:
    """
    Convert Eastern Time datetime to UTC.

    NBA.com game times are in Eastern Time. This function properly
    converts ET to UTC, handling both EST (UTC-5) and EDT (UTC-4).

    Args:
        et_datetime: Eastern Time datetime (timezone-aware or naive)

    Returns:
        UTC datetime as naive datetime (for database storage)

    Example:
        >>> et_to_utc(datetime(2026, 1, 23, 19, 0, 0))  # Assumes EST
        datetime(2026, 1, 24, 0, 0, 0)  # Midnight UTC (7 PM ET + 5 hours)
    """
    if et_datetime.tzinfo is None:
        # Assume EST if no timezone info (naive ET from NBA.com)
        et_datetime = et_datetime.replace(tzinfo=timezone(timedelta(hours=-5)))

    # Get the timezone offset
    tz_offset = et_datetime.utcoffset()

    # If no offset (GMT/UTC), assume EST for NBA games
    if tz_offset is None:
        tz_offset = EASTERN_STANDARD_OFFSET

    # Convert to UTC by subtracting the offset
    utc_datetime = et_datetime - tz_offset

    # Return as naive datetime (for database storage)
    return utc_datetime.replace(tzinfo=None)


def utc_to_eastern(utc_datetime: Optional[datetime]) -> Optional[datetime]:
    """
    Convert UTC datetime to Eastern Time (EST/EDT).

    Automatically handles daylight saving time:
    - EDT (UTC-4): Second Sunday in March → First Sunday in November
    - EST (UTC-5): First Sunday in November → Second Sunday in March

    Args:
        utc_datetime: UTC datetime (naive or timezone-aware)

    Returns:
        Eastern Time datetime as naive datetime (for JSON serialization)

    Example:
        Winter (EST):
        >>> utc_to_eastern(datetime(2026, 2, 1, 0, 30))
        datetime(2026, 1, 31, 19, 30)  # 5 hour difference

        Summer (EDT):
        >>> utc_to_eastern(datetime(2025, 7, 15, 23, 0))
        datetime(2025, 7, 15, 19, 0)  # 4 hour difference
    """
    if utc_datetime is None:
        return None

    # Ensure input is timezone-aware UTC
    if utc_datetime.tzinfo is None:
        utc_datetime = utc_datetime.replace(tzinfo=timezone.utc)

    # Determine if we're in daylight saving time
    dst_start, dst_end = _get_dst_transitions_eastern(utc_datetime.year)
    is_dst = dst_start <= utc_datetime <= dst_end

    # Apply the appropriate offset
    if is_dst:
        # EDT (UTC-4)
        eastern_datetime = utc_datetime + timedelta(hours=-4)
    else:
        # EST (UTC-5)
        eastern_datetime = utc_datetime + timedelta(hours=-5)

    # Return naive datetime (without tzinfo) for JSON serialization
    return eastern_datetime.replace(tzinfo=None)


def utc_to_central(utc_datetime: Optional[datetime]) -> Optional[datetime]:
    """
    Convert UTC datetime to Central Time (CST/CDT).

    Automatically handles daylight saving time:
    - CDT (UTC-5): Second Sunday in March → First Sunday in November
    - CST (UTC-6): First Sunday in November → Second Sunday in March

    Args:
        utc_datetime: UTC datetime (naive or timezone-aware)

    Returns:
        Central Time datetime as naive datetime (for JSON serialization)

    Example:
        Winter (CST):
        >>> utc_to_central(datetime(2025, 1, 28, 18, 0))
        datetime(2025, 1, 28, 12, 0)  # 6 hour difference

        Summer (CDT):
        >>> utc_to_central(datetime(2025, 7, 15, 18, 0))
        datetime(2025, 7, 15, 13, 0)  # 5 hour difference
    """
    if utc_datetime is None:
        return None

    # Ensure input is timezone-aware UTC
    if utc_datetime.tzinfo is None:
        utc_datetime = utc_datetime.replace(tzinfo=timezone.utc)

    # Determine if we're in daylight saving time
    dst_start, dst_end = _get_dst_transitions(utc_datetime.year)
    is_dst = dst_start <= utc_datetime <= dst_end

    # Apply the appropriate offset
    if is_dst:
        # CDT (UTC-5)
        central_datetime = utc_datetime + CENTRAL_DAYLIGHT_OFFSET
    else:
        # CST (UTC-6)
        central_datetime = utc_datetime + CENTRAL_STANDARD_OFFSET

    # Return naive datetime (without tzinfo) for JSON serialization
    return central_datetime.replace(tzinfo=None)


def _get_dst_transitions(year: int) -> Tuple[datetime, datetime]:
    """
    Get DST transition dates for a given year.

    DST starts: Second Sunday in March at 2:00 AM local time
    DST ends: First Sunday in November at 2:00 AM local time

    Args:
        year: Year to calculate transitions for

    Returns:
        Tuple of (dst_start, dst_end) as UTC datetimes
    """
    def find_nth_sunday(year: int, month: int, n: int) -> datetime:
        """Find the nth Sunday of the given month."""
        day = 1
        sunday_count = 0
        while True:
            dt = datetime(year, month, day)
            if dt.weekday() == 6:  # Sunday
                sunday_count += 1
                if sunday_count == n:
                    return dt
            day += 1

    # Second Sunday in March at 2:00 AM CST = 8:00 AM UTC
    dst_start_local = find_nth_sunday(year, 3, 2).replace(hour=2, minute=0, second=0, microsecond=0)
    dst_start_utc = (dst_start_local - CENTRAL_STANDARD_OFFSET).replace(tzinfo=timezone.utc)

    # First Sunday in November at 2:00 AM CDT = 7:00 AM UTC
    dst_end_local = find_nth_sunday(year, 11, 1).replace(hour=2, minute=0, second=0, microsecond=0)
    dst_end_utc = (dst_end_local - CENTRAL_DAYLIGHT_OFFSET).replace(tzinfo=timezone.utc)

    return dst_start_utc, dst_end_utc


def _get_dst_transitions_eastern(year: int) -> Tuple[datetime, datetime]:
    """
    Get DST transition dates for a given year (Eastern Time).

    DST starts: Second Sunday in March at 2:00 AM local time
    DST ends: First Sunday in November at 2:00 AM local time

    Args:
        year: Year to calculate transitions for

    Returns:
        Tuple of (dst_start, dst_end) as UTC datetimes
    """
    def find_nth_sunday(year: int, month: int, n: int) -> datetime:
        """Find the nth Sunday of the given month."""
        day = 1
        sunday_count = 0
        while True:
            dt = datetime(year, month, day)
            if dt.weekday() == 6:  # Sunday
                sunday_count += 1
                if sunday_count == n:
                    return dt
            day += 1

    # Second Sunday in March at 2:00 AM EST = 7:00 AM UTC
    dst_start_local = find_nth_sunday(year, 3, 2).replace(hour=2, minute=0, second=0, microsecond=0)
    dst_start_utc = (dst_start_local + timedelta(hours=5)).replace(tzinfo=timezone.utc)

    # First Sunday in November at 2:00 AM EDT = 6:00 AM UTC
    dst_end_local = find_nth_sunday(year, 11, 1).replace(hour=2, minute=0, second=0, microsecond=0)
    dst_end_utc = (dst_end_local + timedelta(hours=4)).replace(tzinfo=timezone.utc)

    return dst_start_utc, dst_end_utc


def format_game_time_eastern(utc_datetime: Optional[datetime]) -> str:
    """
    Format UTC datetime as Eastern Time string with timezone abbreviation.

    Args:
        utc_datetime: UTC datetime

    Returns:
        Formatted datetime string in Eastern Time with EST/EDT suffix

    Example:
        >>> format_game_time_eastern(datetime(2026, 2, 1, 0, 30))
        '2026-01-31 19:30:00 EST'
    """
    if utc_datetime is None:
        return "N/A"

    eastern_dt = utc_to_eastern(utc_datetime)
    tz_abbrev = _get_timezone_abbrev_eastern(eastern_dt)
    return f"{eastern_dt.strftime('%Y-%m-%d %H:%M:%S')} {tz_abbrev}"


def format_game_time_central(utc_datetime: Optional[datetime]) -> str:
    """
    Format UTC datetime as Central Time string with timezone abbreviation.

    Args:
        utc_datetime: UTC datetime

    Returns:
        Formatted datetime string in Central Time with CST/CDT suffix

    Example:
        >>> format_game_time_central(datetime(2026, 1, 21, 2, 0))
        '2026-01-20 20:00:00 CST'
    """
    if utc_datetime is None:
        return "N/A"

    central_dt = utc_to_central(utc_datetime)
    tz_abbrev = _get_timezone_abbrev(central_dt)
    return f"{central_dt.strftime('%Y-%m-%d %H:%M:%S')} {tz_abbrev}"


def format_central_time(utc_datetime: Optional[datetime], format_str: str = "%Y-%m-%d %I:%M %p") -> str:
    """
    Format a UTC datetime as a Central Time string.

    Args:
        utc_datetime: UTC datetime (naive or aware)
        format_str: strftime format string (default: "2025-01-28 07:30 PM")

    Returns:
        Formatted string with timezone abbreviation
    """
    central_dt = utc_to_central(utc_datetime)
    if central_dt is None:
        return "N/A"

    tz_abbrev = _get_timezone_abbrev(central_dt)
    formatted = central_dt.strftime(format_str)
    return f"{formatted} {tz_abbrev}"


def _get_timezone_abbrev_eastern(dt: datetime) -> str:
    """
    Get the timezone abbreviation for Eastern Time datetime.

    Args:
        dt: Datetime in Eastern Time (naive)

    Returns:
        "EST" or "EDT"
    """
    # DST is roughly March - November
    if 3 <= dt.month <= 11:
        if dt.month >= 4 or dt.month <= 10:
            return "EDT"
        elif dt.month == 3:
            # March: after second Sunday
            if dt.day >= 8:  # Approximation
                return "EDT"
            return "EST"
        elif dt.month == 11:
            # November: before first Sunday
            if dt.day <= 7:  # Approximation
                return "EDT"
            return "EST"

    return "EST"


def _get_timezone_abbrev(dt: datetime) -> str:
    """
    Get the timezone abbreviation for a datetime (CST or CDT).

    Args:
        dt: Datetime in Central Time (naive)

    Returns:
        "CST" or "CDT"
    """
    # Simplified check based on month
    # DST is roughly March - November
    if 3 <= dt.month <= 11:
        if dt.month >= 4 or dt.month <= 10:
            return "CDT"
        elif dt.month == 3:
            # March: after second Sunday
            if dt.day >= 8:  # Approximation
                return "CDT"
            return "CST"
        elif dt.month == 11:
            # November: before first Sunday
            if dt.day <= 7:  # Approximation
                return "CDT"
            return "CST"

    return "CST"


def format_game_time_central_readable(utc_datetime: Optional[datetime]) -> str:
    """
    Format UTC datetime as readable Central Time string.

    Args:
        utc_datetime: UTC datetime

    Returns:
        Readable datetime string like "Jan 20, 2026 at 8:00 PM CST"
    """
    if utc_datetime is None:
        return "N/A"

    central_dt = utc_to_central(utc_datetime)
    tz_abbrev = _get_timezone_abbrev(central_dt)
    return central_dt.strftime("%b %d, %Y at %-I:%M %p ") + tz_abbrev


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

    cutoff = datetime.now(UTC) - timedelta(hours=6)
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
    tz_abbrev = _get_timezone_abbrev(central_dt)

    return {
        "utc_time": game_date_utc,
        "central_time": central_dt,
        "central_time_str": format_game_time_central(game_date_utc),
        "readable_time": format_game_time_central_readable(game_date_utc),
        "time_only": central_dt.strftime("%-I:%M %p"),
        "time_only_with_tz": central_dt.strftime("%-I:%M %p ") + tz_abbrev,
        "date_only": central_dt.strftime("%Y-%m-%d"),
        "is_completed": is_game_completed(game_date_utc, status),
        "matchup": f"{away_team} @ {home_team}"
    }
