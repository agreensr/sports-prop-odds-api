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
# Please check FanDuel and update this list with actual available players
VERIFIED_FANDEL_PLAYERS = [
    # Bulls (CHI)
    "Coby White",          # ✅ Verified - Points 20.5, Threes 2.5
    # "Josh Giddey",        # ? Needs verification
    # "Nikola Vucevic",     # ? Needs verification
    # "Jalen Smith",        # ? Needs verification
    # "Kevin Huerter",      # ? Needs verification
    # "Isaac Okoro",        # ? Needs verification
    # "Matas Buzelis",      # ? Needs verification
    # "Ayo Dosunmu",        # ❌ NOT on FanDuel for threes

    # Lakers (LAL)
    # "LeBron James",       # ? Needs verification
    # "Luka Doncic",        # ? Needs verification
    # "Marcus Smart",       # ? Needs verification
    # "Rui Hachimura",      # ? Needs verification
    # "Jake LaRavia",       # ? Needs verification
    # "Deandre Ayton",      # ? Needs verification
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
