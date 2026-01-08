#!/usr/bin/env python3
"""
Populate learnsets for all Pokemon by extracting data from multiple generations.
Pokemon in Gen 9 get Gen 9 data, Pokemon not in Gen 9 get Gen 8 data, and so on.
"""

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, Set

MOVE_METHOD_LEVEL = 1
MOVE_METHOD_EGG = 2
MOVE_METHOD_TUTOR = 3
MOVE_METHOD_MACHINE = 4


def normalize_identifier(identifier: str) -> str:
    """Normalize PokeAPI identifiers to the keys used in learnsets.json."""
    return "".join(ch for ch in identifier.lower() if ch.isalnum())


def load_pokemon_names(csv_path: Path) -> Dict[int, str]:
    """Map pokemon.id -> normalized identifier."""
    mapping: Dict[int, str] = {}
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mapping[int(row["id"])] = normalize_identifier(row["identifier"])
    return mapping


def load_move_names(csv_path: Path) -> Dict[int, str]:
    """Map move.id -> normalized identifier."""
    mapping: Dict[int, str] = {}
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mapping[int(row["id"])] = normalize_identifier(row["identifier"])
    return mapping


def load_version_group_generations(csv_path: Path) -> Dict[int, int]:
    """Map version_group.id -> generation_id."""
    mapping: Dict[int, int] = {}
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mapping[int(row["id"])] = int(row["generation_id"])
    return mapping


def extract_moves_for_generation(
    csv_path: Path,
    pokemon_lookup: Dict[int, str],
    move_lookup: Dict[int, str],
    allowed_version_groups: Set[int],
    generation: int,
):
    """Collect learnset data for a specific generation from pokemon_moves.csv."""
    level_moves: Dict[str, Dict[str, int]] = defaultdict(dict)
    egg_moves: Dict[str, Set[str]] = defaultdict(set)
    tutor_moves: Dict[str, Set[str]] = defaultdict(set)
    tm_moves: Dict[str, Set[str]] = defaultdict(set)

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            version_group = int(row["version_group_id"])
            if version_group not in allowed_version_groups:
                continue

            method = int(row["pokemon_move_method_id"])
            pokemon_id = int(row["pokemon_id"])
            move_id = int(row["move_id"])

            pokemon_key = pokemon_lookup.get(pokemon_id)
            move_key = move_lookup.get(move_id)
            if not pokemon_key or not move_key:
                continue

            if method == MOVE_METHOD_LEVEL:
                level_str = row.get("level") or "0"
                level_val = int(level_str)
                current = level_moves[pokemon_key].get(move_key)
                if current is None or level_val < current:
                    level_moves[pokemon_key][move_key] = level_val
            elif method == MOVE_METHOD_EGG:
                egg_moves[pokemon_key].add(move_key)
            elif method == MOVE_METHOD_TUTOR:
                tutor_moves[pokemon_key].add(move_key)
            elif method == MOVE_METHOD_MACHINE:
                tm_moves[pokemon_key].add(move_key)

    # Convert to the format we need
    result = {}
    for pokemon_key in level_moves.keys():
        result[pokemon_key] = {
            "level_up_moves": [
                {"level": level, "move_id": move, "gen": generation}
                for move, level in sorted(level_moves[pokemon_key].items(), key=lambda x: (x[1], x[0]))
            ],
            "tm_moves": sorted(list(tm_moves.get(pokemon_key, set()))),
            "egg_moves": sorted(list(egg_moves.get(pokemon_key, set()))),
            "tutor_moves": sorted(list(tutor_moves.get(pokemon_key, set()))),
        }

    return result


def main():
    csv_root = Path("pokeapi_csv_bot")

    pokemon_csv = csv_root / "pokemon.csv"
    moves_csv = csv_root / "moves.csv"
    version_groups_csv = csv_root / "version_groups.csv"
    pokemon_moves_csv = csv_root / "pokemon_moves.csv"

    print("Loading CSV data...")
    pokemon_lookup = load_pokemon_names(pokemon_csv)
    move_lookup = load_move_names(moves_csv)
    vg_generations = load_version_group_generations(version_groups_csv)

    # Load existing learnsets
    learnsets_path = Path("data/learnsets.json")
    with learnsets_path.open(encoding="utf-8") as f:
        learnsets = json.load(f)

    print(f"Loaded {len(learnsets)} Pokemon from existing learnsets.json")

    # Extract data for each generation from 9 down to 1
    for generation in range(9, 0, -1):
        print(f"\nProcessing Generation {generation}...")

        allowed_version_groups = {vg for vg, gen in vg_generations.items() if gen == generation}

        gen_data = extract_moves_for_generation(
            pokemon_moves_csv,
            pokemon_lookup,
            move_lookup,
            allowed_version_groups,
            generation,
        )

        updated_count = 0
        new_count = 0

        for pokemon_key, data in gen_data.items():
            if pokemon_key not in learnsets:
                # Pokemon not in our learnsets yet
                continue

            # Only update if this Pokemon doesn't already have moves from a higher generation
            existing_entry = learnsets[pokemon_key]
            has_level_moves = bool(existing_entry.get("level_up_moves"))

            # Check if this Pokemon already has level-up moves from this gen or higher
            has_higher_gen = False
            for move in existing_entry.get("level_up_moves", []):
                if move.get("gen", 0) >= generation:
                    has_higher_gen = True
                    break

            if not has_level_moves:
                # No moves yet, populate with this generation's data
                learnsets[pokemon_key]["level_up_moves"] = data["level_up_moves"]
                learnsets[pokemon_key]["tm_moves"] = data["tm_moves"]
                learnsets[pokemon_key]["egg_moves"] = data["egg_moves"]
                learnsets[pokemon_key]["tutor_moves"] = data["tutor_moves"]
                new_count += 1
            elif has_higher_gen:
                # Already has data from this gen or higher, just merge TM/egg/tutor moves
                current_tm = set(existing_entry.get("tm_moves", []))
                new_tm = set(data["tm_moves"])
                existing_entry["tm_moves"] = sorted(list(current_tm | new_tm))

                current_egg = set(existing_entry.get("egg_moves", []))
                new_egg = set(data["egg_moves"])
                existing_entry["egg_moves"] = sorted(list(current_egg | new_egg))

                current_tutor = set(existing_entry.get("tutor_moves", []))
                new_tutor = set(data["tutor_moves"])
                existing_entry["tutor_moves"] = sorted(list(current_tutor | new_tutor))
                updated_count += 1

        print(f"  New Pokemon populated: {new_count}")
        print(f"  Pokemon updated (TM/egg/tutor): {updated_count}")

    # Count empty Pokemon
    empty_count = 0
    for pokemon_key, data in learnsets.items():
        if not data.get("level_up_moves"):
            empty_count += 1

    print(f"\n{'='*60}")
    print(f"Final statistics:")
    print(f"  Total Pokemon: {len(learnsets)}")
    print(f"  Pokemon with moves: {len(learnsets) - empty_count}")
    print(f"  Pokemon still empty: {empty_count}")
    print(f"{'='*60}")

    # Write updated learnsets
    output_path = Path("data/learnsets.json")
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(learnsets, f, indent=2)

    print(f"\nLearnsets updated successfully!")

    # Show some examples
    print("\nSample Pokemon check:")
    for name in ["pikachu", "caterpie", "pidgey", "charizard"]:
        if name in learnsets:
            level_moves = len(learnsets[name].get("level_up_moves", []))
            tm_moves = len(learnsets[name].get("tm_moves", []))
            print(f"  {name}: {level_moves} level-up moves, {tm_moves} TM moves")


if __name__ == "__main__":
    main()
