
"""
Ruleset Handler
Loads rulesets.json and exposes simple validators for common clauses.
Default target: Standard NatDex ("standardnatdex").
"""

from typing import Dict, List, Optional
import json
from pathlib import Path

BANNED_OHKO_MOVES = {"sheercold","fissure","guillotine","horndrill"}
BANNED_EVASION_MOVES = {"doubleteam","minimize"}

# Moves that don't work on raid bosses (similar to Dynamax raid restrictions)
BANNED_RAID_MOVES = {
    # Instant defeat moves
    "perishsong", "destinybond", "grudge", "curse",

    # Self-KO moves
    "explosion", "selfdestruct", "mistyexplosion", "healingwish", "lunardance", "memento", "finalgambit",

    # Forced switch moves (force the ROGUE to switch/leave)
    "roar", "whirlwind", "dragontail", "circleethrow",

    # Item manipulation
    "knockoff", "trick", "switcheroo", "bestow", "magicroom", "recycle", "fling", "covet", "thief", "bugbite", "pluck",

    # Ability manipulation
    "skillswap", "roleplay", "entrainment", "worryseed", "simplebeam", "gastroacid", "coreenforcer",

    # Other problematic moves
    "disable", "torment", "imprison", "snatch",
}

class RulesetHandler:
    def __init__(self, rulesets_file: str = 'rulesets.json'):
        # Try several paths
        candidates = [
            rulesets_file,
            str(Path(__file__).parent / 'data' / 'rulesets.json'),
            str(Path(__file__).parent / rulesets_file),
            str((Path(__file__).parent / '..' / rulesets_file).resolve()),
        ]
        self.rulesets: Dict = {}
        for c in candidates:
            try:
                with open(c, 'r', encoding='utf-8') as f:
                    self.rulesets = json.load(f)
                break
            except Exception:
                continue

    def resolve_default_ruleset(self, preference: str = "nat") -> str:
        # Map "nat" to our Standard NatDex id in your file
        # Using Showdown's name "standardnatdex" if present
        if "standardnatdex" in self.rulesets:
            return "standardnatdex"
        # Fallback to "standard" if not found
        if "standard" in self.rulesets:
            return "standard"
        # Last resort: use any one key
        return next(iter(self.rulesets.keys()), "standard")

    def is_move_allowed(self, move_id: str, ruleset_id: str) -> (bool, Optional[str]):
        mid = (move_id or "").replace(" ", "").replace("-", "").lower()

        # Apply common clauses for "standard" family rulesets
        if ruleset_id.lower().startswith("standard"):
            if mid in BANNED_OHKO_MOVES:
                return False, "OHKO Clause active (move is banned)"
            if mid in BANNED_EVASION_MOVES:
                return False, "Evasion Moves Clause active (move is banned)"

        # Additional clauses can be applied here based on the loaded ruleset
        return True, None
