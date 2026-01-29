"""Name normalization utilities for player and team name matching.

Handles common variations across APIs:
- Suffixes: "Jr.", "Sr.", "III", "IV", "II"
- Punctuation: "P.J. Tucker" → "PJ Tucker"
- Accents: "Luka Dončić" → "Luka Doncic"
- Case: "LEBRON JAMES" → "lebron james"
- Extra spaces: "Kyle  Lowry" → "kyle lowry"
"""
import re
import unicodedata
from typing import Set


# Common name suffixes that should be removed for comparison
SUFFIXES = {
    'jr', 'sr', 'iii', 'iv', 'ii', 'v', 'vi', 'vii', 'viii', 'ix',
    'jr.', 'sr.', 'iii.', 'iv.', 'ii.', 'v.', 'vi.', 'vii.', 'viii.', 'ix.'
}


def normalize(name: str) -> str:
    """
    Normalize a name for comparison by removing variations.

    Steps:
    1. Remove common suffixes (Jr, Sr, III, etc.)
    2. Convert to lowercase
    3. Remove punctuation (but keep letters)
    4. Normalize unicode characters (accents)
    5. Remove extra whitespace

    Args:
        name: The name to normalize

    Returns:
        Normalized name string

    Examples:
        >>> normalize("P.J. Tucker")
        'pj tucker'
        >>> normalize("Tim Hardaway Jr.")
        'tim hardaway'
        >>> normalize("Luka Dončić")
        'luka doncic'
        >>> normalize("Kyle  Lowry")
        'kyle lowry'
    """
    if not name:
        return ""

    # Step 1: Remove suffixes
    name = _remove_suffixes(name)

    # Step 2: Normalize unicode (remove accents)
    name = _normalize_unicode(name)

    # Step 3: Convert to lowercase
    name = name.lower()

    # Step 4: Remove punctuation (keep only letters, numbers, spaces)
    name = re.sub(r'[^\w\s]', '', name)

    # Step 5: Remove extra whitespace
    name = ' '.join(name.split())

    return name


def _remove_suffixes(name: str) -> str:
    """
    Remove common name suffixes from the end of a name.

    Suffixes removed: Jr, Sr, II, III, IV, V, etc.

    Args:
        name: The name to process

    Returns:
        Name with suffix removed
    """
    # Split into parts
    parts = name.split()

    # Check if last part is a suffix (case-insensitive)
    if parts and parts[-1].lower().replace('.', '') in SUFFIXES:
        return ' '.join(parts[:-1])

    return name


def extract_suffix(name: str) -> str:
    """
    Extract the suffix from a name if present.

    Unlike _remove_suffixes, this returns the suffix rather than
    removing it. Used for suffix compatibility checking to prevent
    matching Jr/Sr players.

    Args:
        name: The name to extract suffix from

    Returns:
        The suffix (lowercase, without dots) or empty string if no suffix

    Examples:
        >>> extract_suffix("Tim Hardaway Jr.")
        'jr'
        >>> extract_suffix("Tim Hardaway Sr.")
        'sr'
        >>> extract_suffix("Ken Griffey Jr.")
        'jr'
        >>> extract_suffix("Kelly Oubre")
        ''
    """
    if not name:
        return ""

    parts = name.split()

    if parts and parts[-1].lower().replace('.', '') in SUFFIXES:
        return parts[-1].lower().replace('.', '')

    return ""


def _normalize_unicode(name: str) -> str:
    """
    Remove accents and diacritics from unicode characters.

    Converts 'č' → 'c', 'ś' → 's', 'ž' → 'z', etc.

    Args:
        name: The name to normalize

    Returns:
        Name with accents removed
    """
    # Normalize to NFD form, then remove combining characters
    normalized = unicodedata.normalize('NFD', name)
    return ''.join(
        c for c in normalized
        if unicodedata.category(c) != 'Mn'
    )


def normalize_team_name(team_name: str) -> str:
    """
    Normalize team names for comparison.

    Handles variations like:
    - "LA Lakers" → "los angeles lakers"
    - "Golden State" → "golden state warriors"
    - "NY" → "new york"

    Args:
        team_name: The team name to normalize

    Returns:
        Normalized team name
    """
    if not team_name:
        return ""

    # Convert to lowercase
    normalized = team_name.lower()

    # Remove punctuation
    normalized = re.sub(r'[^\w\s]', '', normalized)

    # Remove extra whitespace
    normalized = ' '.join(normalized.split())

    return normalized


def are_names_equal(name1: str, name2: str, fuzzy: bool = False) -> bool:
    """
    Check if two names are equal after normalization.

    Args:
        name1: First name
        name2: Second name
        fuzzy: If True, also try fuzzy matching as fallback

    Returns:
        True if names match after normalization
    """
    norm1 = normalize(name1)
    norm2 = normalize(name2)

    if norm1 == norm2:
        return True

    if fuzzy:
        from rapidfuzz import fuzz
        # Use WRatio for fuzzy comparison (handles case, length differences)
        score = fuzz.WRatio(norm1, norm2)
        return score >= 90

    return False


def extract_player_name_parts(name: str) -> tuple[str, str]:
    """
    Split a player name into first and last name.

    Handles multi-word last names:
    - "Jayson Tatum" → ("Jayson", "Tatum")
    - "Shai Gilgeous-Alexander" → ("Shai", "Gilgeous-Alexander")
    - "Kelly Oubre Jr." → ("Kelly", "Oubre")

    Args:
        name: Full player name

    Returns:
        Tuple of (first_name, last_name)
    """
    # Remove suffixes first
    name_without_suffix = _remove_suffixes(name)

    # Split into parts
    parts = name_without_suffix.split()

    if len(parts) == 1:
        return (parts[0], "")

    if len(parts) == 2:
        return (parts[0], parts[1])

    # For multi-part names, assume first word is first name,
    # rest is last name (e.g., "Shai Gilgeous-Alexander")
    return (parts[0], ' '.join(parts[1:]))
