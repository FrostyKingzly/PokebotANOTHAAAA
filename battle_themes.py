"""
Battle Theme Configuration
Contains all battle and victory themes for different battle types.
"""

from typing import Dict, List, Tuple
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


# Default themes for testing
DEFAULT_BATTLE_THEME = "https://youtu.be/ftGlGn4N1yQ"  # Gen 1 Battle
DEFAULT_VICTORY_THEME = "https://youtu.be/YGdCe1cU3gs"  # Gen 1 Victory


class BattleThemeSelector:
    """Helper class to select appropriate battle themes"""

    @staticmethod
    def get_casual_npc_theme() -> Tuple[str, str]:
        """
        Get a random casual NPC battle theme.
        Randomly selects from Gen 1-9 themes.
        """
        return random.choice(CASUAL_NPC_THEMES)

    @staticmethod
    def get_ranked_npc_theme() -> Tuple[str, str]:
        """
        Get a ranked NPC battle theme.
        Currently returns default, will be implemented later.
        """
        if RANKED_NPC_THEMES:
            return random.choice(RANKED_NPC_THEMES)
        # Fallback to casual themes for now
        return BattleThemeSelector.get_casual_npc_theme()

    @staticmethod
    def get_raid_theme() -> Tuple[str, str]:
        """
        Get a raid battle theme.
        Currently returns default, will be implemented later.
        """
        if RAID_THEMES:
            return random.choice(RAID_THEMES)
        # Fallback to Gen 6 theme (epic feel)
        return CASUAL_NPC_THEMES[5]  # Gen 6

    @staticmethod
    def get_player_theme(battle_theme_url: str = None, victory_theme_url: str = None) -> Tuple[str, str]:
        """
        Get a player's custom themes.
        Falls back to Gen 5 theme if not set.
        """
        battle = battle_theme_url or CASUAL_NPC_THEMES[4][0]  # Gen 5 Battle (default)
        victory = victory_theme_url or CASUAL_NPC_THEMES[4][1]  # Gen 5 Victory (default)
        return (battle, victory)

    @staticmethod
    def get_theme_for_battle_type(battle_type: str, is_ranked: bool = False,
                                   player_battle_theme: str = None,
                                   player_victory_theme: str = None) -> Tuple[str, str]:
        """
        Get appropriate theme based on battle type.

        Args:
            battle_type: "npc", "pvp", "raid"
            is_ranked: Whether this is a ranked battle
            player_battle_theme: Player's custom battle theme URL
            player_victory_theme: Player's custom victory theme URL

        Returns:
            Tuple of (battle_theme_url, victory_theme_url)
        """
        if battle_type == "pvp":
            # PvP battles use challenger's theme
            return BattleThemeSelector.get_player_theme(player_battle_theme, player_victory_theme)

        elif battle_type == "npc":
            # NPC battles - ranked or casual
            if is_ranked:
                return BattleThemeSelector.get_ranked_npc_theme()
            else:
                return BattleThemeSelector.get_casual_npc_theme()

        elif battle_type == "raid":
            # Raid battles use raid-specific themes
            return BattleThemeSelector.get_raid_theme()

        else:
            # Fallback to default
            return (DEFAULT_BATTLE_THEME, DEFAULT_VICTORY_THEME)


# Theme categories for trainer card customization
AVAILABLE_PLAYER_THEMES: Dict[str, Tuple[str, str]] = {
    "Gen 1 - Kanto Classic": (
        "https://youtu.be/ftGlGn4N1yQ",
        "https://youtu.be/YGdCe1cU3gs"
    ),
    "Gen 2 - Johto Journey": (
        "https://youtu.be/FsMOS00Betk",
        "https://youtu.be/yqoyUUuhtNo"
    ),
    "Gen 3 - Hoenn Adventure": (
        "https://youtu.be/_a83w6re0Q0",
        "https://youtu.be/Njnej-gi2tE"
    ),
    "Gen 4 - Sinnoh Symphony": (
        "https://youtu.be/NLRHydMEkgI",
        "https://youtu.be/SEP164w5HQI"
    ),
    "Gen 5 - Unova Epic": (
        "https://youtu.be/ql7rpfon02M",
        "https://youtu.be/RnzWt5bTaYw"
    ),
    "Gen 6 - Kalos Elegance": (
        "https://youtu.be/GsJ09FVIUoI",
        "https://youtu.be/m3ECMeipClc"
    ),
    "Gen 7 - Alola Vibes": (
        "https://youtu.be/iFsSqnhjQ7I",
        "https://youtu.be/jZAuud1C7II"
    ),
    "Gen 8 - Galar Glory": (
        "https://youtu.be/deX5NFmXDAo",
        "https://youtu.be/nfFZfp2AqoE"
    ),
    "Gen 9 - Paldea Power": (
        "https://youtu.be/jLlW_cszePs",
        "https://youtu.be/BLEahoZx8X4"
    ),
}


def get_theme_name_from_urls(battle_url: str, victory_url: str) -> str:
    """Get the theme name from URLs, returns 'Custom' if not found"""
    for name, (b_url, v_url) in AVAILABLE_PLAYER_THEMES.items():
        if b_url == battle_url and v_url == victory_url:
            return name
    return "Custom Theme"
