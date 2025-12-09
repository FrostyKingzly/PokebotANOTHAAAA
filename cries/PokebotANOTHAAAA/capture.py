
"""
capture.py
-----------
Modern-style Pokémon capture mechanics with shake checks (Gen VI+ style).

This module exposes:
- BallBonus: mapping of ball ids/names to multipliers (baseline set; extend as needed)
- StatusBonus: mapping of non-volatile status to multipliers
- modified_catch_rate(max_hp, cur_hp, species_catch_rate, ball_bonus, status_bonus) -> int
- shake_threshold(a) -> int
- simulate_throw(max_hp, cur_hp, species_catch_rate, ball_bonus, status_bonus, rng=None) -> dict
- guaranteed_capture() -> dict

Notes:
- Uses the Gen VI+ "a" value and shake probability formula.
- Critical capture is not implemented (can be added later).
"""

from typing import Optional, Dict
import math
import random

# --- Baseline status bonuses ---
StatusBonus: Dict[Optional[str], float] = {
    None: 1.0,
    "healthy": 1.0,
    "": 1.0,
    "paralyze": 1.5,
    "paralysis": 1.5,
    "poison": 1.5,
    "burn": 1.5,
    "sleep": 2.0,
    "freeze": 2.0,
}


def modified_catch_rate(max_hp: int, cur_hp: int, species_catch_rate: int, ball_bonus: float, status_bonus: float) -> int:
    """
    Gen VI+ modified catch rate 'a' (without critical capture).

    a = floor( ((3*MaxHP - 2*HP) * rate * ball * status) / (3*MaxHP) )

    If ball_bonus is effectively infinite (Master Ball), returns a very large number.
    """
    if math.isinf(ball_bonus):
        return 10**9  # guarantee path

    max_hp = max(1, int(max_hp))
    cur_hp = max(0, int(cur_hp))
    rate = max(1, int(species_catch_rate))

    numerator = (3 * max_hp - 2 * cur_hp) * rate * ball_bonus * status_bonus
    denom = 3 * max_hp
    a = int(numerator // denom)
    return max(1, a)


def shake_threshold(a: int) -> int:
    """
    Gen VI+ shake check threshold:

    b = floor(65536 / ((255 / a) ** 0.25))

    If a >= 255, treat as auto-catch before shake checks.
    """
    if a >= 255:
        return 65535  # always pass shakes
    ratio = 255.0 / max(1, float(a))
    root = ratio ** 0.25
    b = int(65536 / root)
    return max(0, min(65535, b))


def simulate_throw(
    max_hp: int,
    cur_hp: int,
    species_catch_rate: int,
    ball_bonus: float,
    status: Optional[str] = None,
    rng: Optional[random.Random] = None,
) -> Dict:
    """
    Simulate a single Poké Ball throw using modern capture mechanics.

    Args:
        max_hp: Target's maximum HP
        cur_hp: Target's current HP
        species_catch_rate: Species catch rate from pokedex data
        ball_bonus: Ball-specific multiplier
        status: Optional status string (sleep, paralyze, etc.)
        rng: Optional random.Random instance for determinism

    Returns:
        {
            "caught": bool,
            "shakes": int,  # 0..3 (if broke out), or 3 if caught on normal throw
            "a": int,
            "b": int,
        }
    """
    r = rng or random.Random()
    status_key = (status or "healthy").lower()
    status_bonus = StatusBonus.get(status_key, 1.0)

    a = modified_catch_rate(max_hp, cur_hp, species_catch_rate, ball_bonus, status_bonus)

    # Master Ball / guaranteed route
    if a >= 10**8:  # our sentinel from modified_catch_rate
        return {"caught": True, "shakes": 3, "a": a, "b": 65535}

    if a >= 255:
        # Auto catch before shakes in practice
        return {"caught": True, "shakes": 3, "a": a, "b": 65535}

    b = shake_threshold(a)

    shakes = 0
    for _ in range(4):
        rand = r.randint(0, 65535)
        if rand < b:
            shakes += 1
        else:
            break

    return {
        "caught": shakes >= 4,
        "shakes": min(shakes, 3),
        "a": a,
        "b": b,
    }


def guaranteed_capture() -> Dict:
    """Used for 'dazed' flow: guarantee capture regardless of HP or ball."""
    return {"caught": True, "shakes": 1, "a": 999999, "b": 65535}
