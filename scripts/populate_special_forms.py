#!/usr/bin/env python3
"""
Populate learnsets for special forms (Gigantamax, Mega, etc.) by copying from their base forms.
"""

import json
import re
from pathlib import Path


def get_base_form(form_name: str) -> str:
    """Extract the base Pokemon name from a form name."""
    # Remove suffixes like 'gmax', 'mega', etc.
    base = re.sub(r'(gmax|mega)$', '', form_name)
    return base


def main():
    learnsets_path = Path("data/learnsets.json")

    with learnsets_path.open(encoding="utf-8") as f:
        learnsets = json.load(f)

    print("Populating special forms with base form learnsets...")

    updated_count = 0
    not_found_count = 0
    not_found_list = []

    for pokemon_key, data in learnsets.items():
        # Check if this Pokemon has empty learnsets
        if data.get('level_up_moves'):
            continue  # Already has moves

        # Try to find the base form
        base_form = get_base_form(pokemon_key)

        if base_form == pokemon_key:
            # No suffix found, can't determine base form
            not_found_list.append(pokemon_key)
            not_found_count += 1
            continue

        if base_form in learnsets:
            base_data = learnsets[base_form]

            # Copy learnsets from base form
            data['level_up_moves'] = base_data.get('level_up_moves', []).copy()
            data['tm_moves'] = base_data.get('tm_moves', []).copy()
            data['egg_moves'] = base_data.get('egg_moves', []).copy()
            data['tutor_moves'] = base_data.get('tutor_moves', []).copy()

            updated_count += 1
            print(f"  {pokemon_key} <- {base_form}")
        else:
            not_found_list.append(f"{pokemon_key} (base: {base_form})")
            not_found_count += 1

    # Write updated learnsets
    with learnsets_path.open("w", encoding="utf-8") as f:
        json.dump(learnsets, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Updated {updated_count} special forms")
    print(f"Could not find base form for {not_found_count} Pokemon")

    if not_found_list:
        print(f"\nPokemon without base forms:")
        for name in not_found_list:
            print(f"  {name}")

    # Final count
    empty_count = sum(1 for data in learnsets.values() if not data.get('level_up_moves'))
    print(f"\n{'='*60}")
    print(f"Final statistics:")
    print(f"  Total Pokemon: {len(learnsets)}")
    print(f"  Pokemon with moves: {len(learnsets) - empty_count}")
    print(f"  Pokemon still empty: {empty_count}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
