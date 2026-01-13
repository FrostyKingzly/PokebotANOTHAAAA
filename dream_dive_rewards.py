"""
Dream Dive reward helpers.

Handles EXP rewards and temporary level restoration for Dream Dive runs.
"""

from __future__ import annotations

import json
from typing import Dict, List

from exp_system import ExpSystem
from dream_rogue_manager import DreamRogueManager
from ui.buttons import _ensure_pokemon_instance


def calculate_dream_dive_exp(intensity: int, dreamlites: int) -> int:
    """Calculate EXP reward for a Dream Dive based on intensity and Dreamlites."""
    base = max(1, int(intensity) * 10)
    dreamlite_bonus = max(0, int(dreamlites * 0.5))
    return max(1, base + dreamlite_bonus)


def apply_dream_dive_exp(bot, user_id: int, exp_amount: int) -> List[Dict[str, object]]:
    """Apply EXP to a user's party and return summary entries."""
    party_data = bot.player_manager.get_party(user_id)
    party = [_ensure_pokemon_instance(bot, poke_data) for poke_data in party_data]
    party = [p for p in party if p is not None]
    if not party:
        return []

    trainer = bot.player_manager.get_player(user_id)
    level_cap = bot.player_manager.get_level_cap_for_trainer(trainer) if trainer else None
    results: List[Dict[str, object]] = []

    for pokemon in party:
        pokemon_id = getattr(pokemon, "pokemon_id", None)
        if not pokemon_id:
            continue

        level_up_result = ExpSystem.apply_exp_and_check_levelup(
            pokemon,
            exp_amount,
            bot.species_db,
            getattr(bot, "moves_db", None),
            level_cap=level_cap,
        )

        updates = {
            "exp": pokemon.exp,
            "level": pokemon.level,
            "current_hp": getattr(pokemon, "current_hp", pokemon.max_hp),
            "max_hp": getattr(pokemon, "max_hp", pokemon.max_hp),
            "moves": json.dumps(pokemon.moves),
            "stored_exp": getattr(pokemon, "stored_exp", 0),
        }
        bot.player_manager.db.update_pokemon(pokemon_id, updates)

        results.append(
            {
                "pokemon_name": pokemon.species_name,
                "exp_gained": exp_amount,
                "new_level": pokemon.level,
                "leveled_up": level_up_result is not None,
            }
        )

    return results


def restore_dream_dive_party_levels(bot, run_id: str, user_id: int) -> None:
    """Restore party levels/EXP to their pre-dive snapshot."""
    manager = DreamRogueManager()
    snapshots = manager.get_party_snapshots(run_id, user_id)
    if not snapshots:
        return

    snapshot_map = {snap["pokemon_id"]: snap for snap in snapshots}
    party_data = bot.player_manager.get_party(user_id)

    for poke_data in party_data:
        pokemon_id = poke_data.get("pokemon_id")
        if not pokemon_id or pokemon_id not in snapshot_map:
            continue

        pokemon = _ensure_pokemon_instance(bot, poke_data)
        if not pokemon:
            continue

        snapshot = snapshot_map[pokemon_id]
        old_max_hp = getattr(pokemon, "max_hp", 1) or 1
        current_hp = getattr(pokemon, "current_hp", old_max_hp)

        pokemon.level = int(snapshot.get("original_level", pokemon.level))
        pokemon.exp = int(snapshot.get("original_exp", pokemon.exp))
        pokemon.stored_exp = int(snapshot.get("original_stored_exp", 0))
        pokemon._calculate_stats()

        ratio = current_hp / max(1, old_max_hp)
        pokemon.current_hp = min(pokemon.max_hp, max(1, int(round(pokemon.max_hp * ratio))))

        updates = {
            "level": pokemon.level,
            "exp": pokemon.exp,
            "stored_exp": getattr(pokemon, "stored_exp", 0),
            "max_hp": pokemon.max_hp,
            "current_hp": pokemon.current_hp,
        }
        bot.player_manager.db.update_pokemon(pokemon_id, updates)

    manager.clear_party_snapshots(run_id, discord_user_id=user_id)
