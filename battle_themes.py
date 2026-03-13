"""
Battle Theme Configuration
Contains all battle and victory themes for NPC battles.
"""

from typing import List, Tuple
import random


DEFAULT_VICTORY_THEME = "https://youtu.be/C7Dle4j_UBc"


# Casual NPC Battle Themes
# Format: (Battle Theme URL, Victory Theme URL)
CASUAL_NPC_THEMES: List[Tuple[str, str]] = [
    ("https://youtu.be/4PvtJJFIrkg", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/JK1hTHPdFCM", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/tMUd7gi0fnI", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/dYdInYCl0UQ", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/4AGPM4pVyOo", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/41dOCyUfXA4", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/dYdInYCl0UQ", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/o5b6uvn7InA", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/w111-Y4B4zU", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/tMUd7gi0fnI", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/lmB0HdM4BNQ", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/M6zHP70_Rpg", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/OBpFdpxcWxc", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/afDvaQFWQko", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/QSJnQKQtHcQ", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/hFo1ZBckmyk", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/MPbvY0mItto", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/mogQFRYo1rM", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/HgoabpaZfxQ", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/WURgaH62jpc", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/DnZNtdXqArk", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/C3coMLSuzH8", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/VkTARsXK4JE", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/Mqr5DXIR35A", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/vzXzbMhzeJc", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/ldA9Ww8O070", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/_Yg0e5FzJ7w", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/3w7o3fEy-7U", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/bTRzkMNBUsY", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/d4JLyVhgtZ0", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/pbLZltv4FF4", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/ED_eA2lw4LU", DEFAULT_VICTORY_THEME),
]


# Ranked NPC Battle Themes
RANKED_NPC_THEMES: List[Tuple[str, str]] = [
    ("https://youtu.be/XV6p9pGmgfk", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/S8OzzEBvTg0", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/7Z6ssqxmh_k", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/dYdInYCl0UQ", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/PGlR13ygNfA", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/cKpNr180siE", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/M6zHP70_Rpg", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/5n7b3_snV2Q", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/L5HMPIpAO6o", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/o9Cqm_vm-xk", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/wsT6KqVujVg", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/3-UiSxd4jB0", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/fFsnDqBqhhQ", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/epjy2RRGS5Y", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/ziQKtCRd4hI", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/M4-AtLF9DnI", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/7dwEtY0aGbs", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/txsoc3npa_w", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/b4CnahB1RAg", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/hHrFMI8ZFZA", DEFAULT_VICTORY_THEME),
    ("https://youtu.be/t1qA4b68Ghk", DEFAULT_VICTORY_THEME),
]


# Raid Battle Themes (To be added later)
RAID_THEMES: List[Tuple[str, str]] = [
    # Placeholder - will be filled with raid-specific themes
]


def get_random_npc_theme() -> Tuple[str, str]:
    """
    Get a random casual NPC battle theme.
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
    Falls back to first casual theme if raid themes not set.
    Returns: (battle_theme_url, victory_theme_url)
    """
    if RAID_THEMES:
        return random.choice(RAID_THEMES)
    return CASUAL_NPC_THEMES[0]
