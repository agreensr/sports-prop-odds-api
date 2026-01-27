"""
FanDuel Verified Player Whitelist

Only players in this list should be used for parlay generation.
This ensures we only use props that are actually available on FanDuel.

To verify a player:
1. Go to FanDuel website
2. Find the NBA game
3. Check if player props are available for that player
4. Add player name to this list

Format: List of player names that are verified on FanDuel
"""

# VERIFIED FANDEL PLAYERS
# All players verified on FanDuel for LAL @ CHI game on 2026-01-27
VERIFIED_FANDEL_PLAYERS = [
    # Bulls (CHI)
    "Coby White",          # ✅ Verified
    "Josh Giddey",         # ✅ Verified
    "Nikola Vucevic",      # ✅ Verified
    "Jalen Smith",         # ✅ Verified
    "Kevin Huerter",       # ✅ Verified
    "Isaac Okoro",         # ✅ Verified
    "Matas Buzelis",       # ✅ Verified
    "Ayo Dosunmu",         # ✅ Verified (but threes prop may not be available)

    # Lakers (LAL)
    "LeBron James",        # ✅ Verified
    "Luka Doncic",         # ✅ Verified
    "Marcus Smart",        # ✅ Verified
    "Rui Hachimura",       # ✅ Verified
    "Jake LaRavia",        # ✅ Verified
    "Deandre Ayton",       # ✅ Verified
]


def is_fanduel_verified(player_name: str) -> bool:
    """
    Check if a player is verified on FanDuel.

    Args:
        player_name: Player name to check

    Returns:
        True if player is verified on FanDuel, False otherwise
    """
    return player_name in VERIFIED_FANDEL_PLAYERS


def get_verified_players() -> list:
    """Get list of all verified FanDuel players."""
    return VERIFIED_FANDEL_PLAYERS.copy()
