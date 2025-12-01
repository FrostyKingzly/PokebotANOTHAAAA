"""Utilities and metadata for the social stat system."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

POINTS_PER_RANK = 50
MAX_RANK = 5
STANDARD_MAX_POINTS = POINTS_PER_RANK * MAX_RANK  # 250
BOON_MAX_POINTS = 200
BANE_MAX_POINTS = 300

# Stamina tuning
# Rank 0 should start at 3 stamina and gain +2 per Fortitude rank
BASE_STAMINA = 3
STAMINA_PER_FORTITUDE_RANK = 2


@dataclass(frozen=True)
class SocialStatDefinition:
    """Metadata about a social stat."""

    key: str
    display_name: str
    description: str


SOCIAL_STAT_DEFINITIONS: Dict[str, SocialStatDefinition] = {
    "heart": SocialStatDefinition(
        key="heart",
        display_name="Heart",
        description="Empathy and connection. Helps with bonds and emotional moments.",
    ),
    "insight": SocialStatDefinition(
        key="insight",
        display_name="Insight",
        description="Perception and intellect. Helps with puzzles, research, and tactics.",
    ),
    "charisma": SocialStatDefinition(
        key="charisma",
        display_name="Charisma",
        description="Charm and influence. Helps with negotiations and leadership.",
    ),
    "fortitude": SocialStatDefinition(
        key="fortitude",
        display_name="Fortitude",
        description="Strength and willpower. Fuels travel, athletics, and stamina.",
    ),
    "will": SocialStatDefinition(
        key="will",
        display_name="Clarity",
        description="Focus and discipline. Helps you push through adversity.",
    ),
}

SOCIAL_STAT_ORDER: List[str] = [
    "heart",
    "insight",
    "charisma",
    "fortitude",
    "will",
]


def get_stat_cap(stat_key: str, boon_stat: Optional[str] = None, bane_stat: Optional[str] = None) -> int:
    """Return the total points a stat can accumulate for a specific trainer."""

    if stat_key == boon_stat:
        return BOON_MAX_POINTS
    if stat_key == bane_stat:
        return BANE_MAX_POINTS
    return STANDARD_MAX_POINTS


def rank_to_points(rank: int, stat_cap: int) -> int:
    """Convert a rank value (0-5) into the minimum points for that rank."""

    if rank <= 0:
        return 0
    if rank >= MAX_RANK:
        return stat_cap
    return int((stat_cap / MAX_RANK) * rank)


def points_to_rank(points: int, stat_cap: int) -> int:
    """Convert raw points to a rank using the appropriate cap."""

    if stat_cap <= 0:
        return 0
    normalized_points = (points / stat_cap) * STANDARD_MAX_POINTS
    rank = int(normalized_points // POINTS_PER_RANK)
    return max(0, min(MAX_RANK, rank))


def clamp_points(points: int, stat_cap: int) -> int:
    """Clamp raw points to the valid range for the stat."""

    return max(0, min(stat_cap, points))


def calculate_max_stamina(fortitude_rank: int) -> int:
    """Calculate the total stamina a trainer has based on Fortitude."""

    if fortitude_rank < 0:
        fortitude_rank = 0
    return BASE_STAMINA + (fortitude_rank * STAMINA_PER_FORTITUDE_RANK)


def build_stat_line(display_name: str, rank: int, points: int, cap: int) -> str:
    """Format a readable stat line for embeds."""

    return f"**{display_name}:** Rank {rank} ({points}/{cap} pts)"
