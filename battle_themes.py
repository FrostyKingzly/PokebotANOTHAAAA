"""
Battle Theme Configuration
Contains all battle and victory themes for NPC battles.
"""

from typing import List, Tuple
import random


# Casual NPC Battle Themes - Organized by Generation
# Format: (Battle Theme URL, Victory Theme URL)
CASUAL_NPC_THEMES: List[Tuple[str, str]] = [
    # Generation 1
    (
        "https://youtu.be/ftGlGn4N1yQ",  # Gen 1 Battle
        "https://youtu.be/YGdCe1cU3gs"   # Gen 1 Victory
    ),
    # Generation 2
    (
        "https://youtu.be/FsMOS00Betk",  # Gen 2 Battle
        "https://youtu.be/yqoyUUuhtNo"   # Gen 2 Victory
    ),
    # Generation 3
    (
        "https://youtu.be/_a83w6re0Q0",  # Gen 3 Battle
        "https://youtu.be/Njnej-gi2tE"   # Gen 3 Victory
    ),
    # Generation 4
    (
        "https://youtu.be/NLRHydMEkgI",  # Gen 4 Battle
        "https://youtu.be/SEP164w5HQI"   # Gen 4 Victory
    ),
    # Generation 5
    (
        "https://youtu.be/ql7rpfon02M",  # Gen 5 Battle
        "https://youtu.be/RnzWt5bTaYw"   # Gen 5 Victory
    ),
    # Generation 6
    (
        "https://youtu.be/GsJ09FVIUoI",  # Gen 6 Battle
        "https://youtu.be/m3ECMeipClc"   # Gen 6 Victory
    ),
    # Generation 7
    (
        "https://youtu.be/iFsSqnhjQ7I",  # Gen 7 Battle
        "https://youtu.be/jZAuud1C7II"   # Gen 7 Victory
    ),
    # Generation 8
    (
        "https://youtu.be/deX5NFmXDAo",  # Gen 8 Battle
        "https://youtu.be/nfFZfp2AqoE"   # Gen 8 Victory
    ),
    # Generation 9
    (
        "https://youtu.be/jLlW_cszePs",  # Gen 9 Battle
        "https://youtu.be/BLEahoZx8X4"   # Gen 9 Victory
    ),
]


# Ranked NPC Battle Themes (To be added later)
RANKED_NPC_THEMES: List[Tuple[str, str]] = [
    # Placeholder - will be filled with ranked battle themes
]


# Raid Battle Themes (To be added later)
RAID_THEMES: List[Tuple[str, str]] = [
    # Placeholder - will be filled with raid-specific themes
]


def get_random_npc_theme() -> Tuple[str, str]:
    """
    Get a random casual NPC battle theme.
    Randomly selects from Gen 1-9 themes.
    Returns: (battle_theme_url, victory_theme_url)
    """
    return random.choice(CASUAL_NPC_THEMES)


def get_ranked_npc_theme() -> Tuple[str, str]:
    """
    Get a ranked NPC battle theme.
    Falls back to casual themes if ranked themes not set.
    Returns: (battle_theme_url, victory_theme_url)
    """
    if RANKED_NPC_THEMES:
        return random.choice(RANKED_NPC_THEMES)
    return get_random_npc_theme()


def get_raid_theme() -> Tuple[str, str]:
    """
    Get a raid battle theme.
    Falls back to Gen 6 theme (epic feel) if raid themes not set.
    Returns: (battle_theme_url, victory_theme_url)
    """
    if RAID_THEMES:
        return random.choice(RAID_THEMES)
    return CASUAL_NPC_THEMES[5]  # Gen 6
