#!/usr/bin/env python3
"""Debug script to trace flinch clearing issue"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from status_conditions import StatusConditionManager


class MockPokemon:
    def __init__(self, name):
        self.species_name = name
        self.status_manager = StatusConditionManager()
        self.max_hp = 100
        self.current_hp = 100


def debug_flinch_clearing():
    pokemon = MockPokemon("Pikachu")

    # Apply flinch
    print("1. Applying flinch with duration=1...")
    success, msg = pokemon.status_manager.apply_status('flinch', duration=1)
    print(f"   Applied: {success}")

    # Check the actual status object
    if 'flinch' in pokemon.status_manager.volatile_statuses:
        flinch_status = pokemon.status_manager.volatile_statuses['flinch']
        print(f"   Flinch status object: {flinch_status}")
        print(f"   Duration: {flinch_status.duration}")
        print(f"   Status type: {flinch_status.status_type}")

    # Manually test tick_turn
    print("\n2. Manually calling tick_turn() on flinch...")
    if 'flinch' in pokemon.status_manager.volatile_statuses:
        flinch_status = pokemon.status_manager.volatile_statuses['flinch']
        should_remove = flinch_status.tick_turn()
        print(f"   tick_turn() returned: {should_remove}")
        print(f"   Duration after tick: {flinch_status.duration}")

    # Check if it's in the exclusion list
    print("\n3. Checking if flinch is in the exclusion list...")
    from status_conditions import VolatileStatus
    exclusion_list = [
        VolatileStatus.CONFUSION.value,
        VolatileStatus.LEECH_SEED.value,
        VolatileStatus.BIND.value,
        VolatileStatus.WRAP.value,
        VolatileStatus.FIRE_SPIN.value,
        VolatileStatus.WHIRLPOOL.value,
        VolatileStatus.SAND_TOMB.value,
        VolatileStatus.CLAMP.value,
        VolatileStatus.INFESTATION.value
    ]
    print(f"   Flinch value: '{VolatileStatus.FLINCH.value}'")
    print(f"   In exclusion list: {VolatileStatus.FLINCH.value in exclusion_list}")
    print(f"   Exclusion list: {exclusion_list}")

    # Now test the full apply_end_of_turn_effects
    print("\n4. Calling apply_end_of_turn_effects()...")
    print(f"   Volatiles before: {list(pokemon.status_manager.volatile_statuses.keys())}")

    messages = pokemon.status_manager.apply_end_of_turn_effects(pokemon)
    print(f"   Messages: {messages}")
    print(f"   Volatiles after: {list(pokemon.status_manager.volatile_statuses.keys())}")

    # Check if flinch was removed
    if 'flinch' in pokemon.status_manager.volatile_statuses:
        flinch_status = pokemon.status_manager.volatile_statuses['flinch']
        print(f"   ❌ Flinch still exists! Duration: {flinch_status.duration}")
    else:
        print(f"   ✅ Flinch was removed!")


if __name__ == '__main__':
    import os
    os.chdir(Path(__file__).parent.parent)
    debug_flinch_clearing()
