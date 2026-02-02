"""Unit tests for name_normalizer utility.

Test Strategy:
1. Test suffix removal (Jr, Sr, II, III, IV)
2. Test punctuation normalization (P.J. → PJ)
3. Test accent removal (José → Jose)
4. Test lowercase conversion
5. Test whitespace trimming
6. Test edge cases (empty strings, None, already normalized names)

Each test follows the pattern:
- Given: An input name with specific issues
- When: normalize() is called
- Then: Output matches expected normalized form
"""
import pytest
from app.services.sync.utils.name_normalizer import normalize


class TestNameNormalizer:
    """Test suite for name normalization functionality."""

    # Suffix Removal Tests
    # ─────────────────────────────────────────────────────────────

    def test_removes_jr_suffix(self):
        """Should remove 'Jr' suffix from player names."""
        assert normalize("Joel Embiid Jr.") == "joel embiid"
        assert normalize("LeBron James Jr") == "lebron james"

    def test_removes_sr_suffix(self):
        """Should remove 'Sr' suffix from player names."""
        assert normalize("Dale Ellis Sr.") == "dale ellis"
        assert normalize("Kenyon Martin Sr") == "kenyon martin"

    def test_removes_roman_numerals(self):
        """Should remove Roman numeral suffixes (II, III, IV)."""
        assert normalize("John Smith II") == "john smith"
        assert normalize("John Smith III") == "john smith"
        assert normalize("John Smith IV") == "john smith"

    def test_removes_mixed_suffixes(self):
        """Should handle multiple suffix variations (removes last suffix)."""
        # Normalizer removes suffixes from right to left, one at a time
        assert normalize("Player Jr. III") == "player jr"

    # Punctuation Normalization Tests
    # ─────────────────────────────────────────────────────────────

    def test_removes_periods_between_initials(self):
        """Should convert 'P.J.' to 'PJ' (common NBA naming)."""
        assert normalize("P.J. Tucker") == "pj tucker"
        assert normalize("P.J. Washington") == "pj washington"
        assert normalize("A.J. Green") == "aj green"

    def test_removes_all_punctuation(self):
        """Should remove all punctuation characters."""
        assert normalize("O'Neal") == "oneal"
        assert normalize("D'Angelo Russell") == "dangelo russell"
        assert normalize("Luc Richard Mbah a Moute") == "luc richard mbah a moute"

    # Accent Removal Tests
    # ─────────────────────────────────────────────────────────────

    def test_removes_accents(self):
        """Should remove diacritical marks from names."""
        assert normalize("José Alvarado") == "jose alvarado"
        assert normalize("Nikola Jokić") == "nikola jokic"
        assert normalize("Luka Dončić") == "luka doncic"

    # Case Conversion Tests
    # ─────────────────────────────────────────────────────────────

    def test_converts_to_lowercase(self):
        """Should convert all characters to lowercase."""
        assert normalize("STEPHEN CURRY") == "stephen curry"
        assert normalize("LeBron James") == "lebron james"

    # Whitespace Tests
    # ─────────────────────────────────────────────────────────────

    def test_trims_whitespace(self):
        """Should remove leading and trailing whitespace."""
        assert normalize("  Joel Embiid  ") == "joel embiid"
        assert normalize("\tJaylen Brown\n") == "jaylen brown"

    def test_normalizes_internal_whitespace(self):
        """Should collapse multiple spaces to single space."""
        assert normalize("Joel   Embiid") == "joel embiid"
        assert normalize("Jayson  Tatum  Jaylen") == "jayson tatum jaylen"

    # Edge Cases
    # ─────────────────────────────────────────────────────────────

    def test_handles_empty_string(self):
        """Should return empty string for empty input."""
        assert normalize("") == ""

    def test_handles_single_word(self):
        """Should handle single word names."""
        assert normalize("Giannis") == "giannis"
        assert normalize("SHAQ") == "shaq"

    def test_handles_special_characters_only(self):
        """Should handle strings with only punctuation."""
        assert normalize("' . -") == ""

    def test_handles_mixed_case_with_punctuation(self):
        """Should handle complex combinations."""
        assert normalize("P.J. Tucker Jr.") == "pj tucker"
        assert normalize("D'Angelo Russell Sr.") == "dangelo russell"

    # Real NBA Player Names
    # ─────────────────────────────────────────────────────────────

    def test_nba_player_names(self):
        """Should normalize common NBA player names correctly."""
        test_cases = [
            ("Joel Embiid", "joel embiid"),
            ("Jayson Tatum", "jayson tatum"),
            ("P.J. Tucker", "pj tucker"),
            ("Nikola Jokić", "nikola jokic"),
            ("D'Angelo Russell", "dangelo russell"),
            ("LeBron James Jr.", "lebron james"),
            ("Gary Trent Jr.", "gary trent"),
            ("Lonnie Walker IV", "lonnie walker"),
            ("Kelly Oubre Jr.", "kelly oubre"),
            ("Marvin Bagley III", "marvin bagley"),
        ]

        for input_name, expected in test_cases:
            result = normalize(input_name)
            assert result == expected, f"Failed for {input_name}: got '{result}', expected '{expected}'"

    # Identity Property Tests
    # ─────────────────────────────────────────────────────────────

    def test_idempotent_on_normalized_names(self):
        """Should return same result when called twice on same input."""
        name = "P.J. Tucker Jr."
        first = normalize(name)
        second = normalize(first)
        assert first == second

    def test_preserves_normalized_form(self):
        """Should not change already normalized names."""
        normalized = "joel embiid"
        assert normalize(normalized) == normalized
