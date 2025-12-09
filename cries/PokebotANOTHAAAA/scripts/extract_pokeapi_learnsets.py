#!/usr/bin/env python3
"""Extract learnsets from the latest PokeAPI CSV export.

The script reads the CSV drop stored in ``pokeapi_csv_bot`` and merges the
learnset data for the highest available generation (preferring Gen 9, then
Gen 8, then 7, and so on) into ``data/learnsets.json``.

Usage:
    python scripts/extract_pokeapi_learnsets.py [--output data/learnsets.json]

The default behavior updates ``data/learnsets.json`` in place.
"""
from __future__ import annotations

import argparse
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


def select_generation(pokemon_moves_path: Path, vg_generations: Dict[int, int]) -> int:
    """Return the highest available generation present in pokemon_moves.csv."""

    counts: Dict[int, int] = defaultdict(int)
    with pokemon_moves_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            vg_id = int(row["version_group_id"])
            generation = vg_generations.get(vg_id)
            if generation is None:
                continue
            counts[generation] += 1

    for generation in range(9, 0, -1):
        if counts.get(generation):
            return generation

    raise ValueError("No generation data found in pokemon_moves.csv")


def extract_moves(
    csv_path: Path,
    pokemon_lookup: Dict[int, str],
    move_lookup: Dict[int, str],
    allowed_version_groups: Set[int],
):
    """Collect learnset data for the selected generation from pokemon_moves.csv."""
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

    return {
        "level_up_moves": level_moves,
        "egg_moves": egg_moves,
        "tutor_moves": tutor_moves,
        "tm_moves": tm_moves,
    }


def build_level_up_list(move_levels: Dict[str, int], generation: int):
    """Convert move->level mapping to the learnsets.json list format."""
    return [
        {"level": level, "move_id": move, "gen": generation}
        for move, level in sorted(move_levels.items(), key=lambda item: (item[1], item[0]))
    ]


def merge_learnsets(existing_path: Path, output_path: Path, extracted, generation: int) -> Dict[str, int]:
    with existing_path.open(encoding="utf-8") as f:
        learnsets = json.load(f)

    stats = {
        "pokemon_updated": 0,
        "missing_in_learnsets": 0,
        "level_sets_replaced": 0,
        "tm_moves_added": 0,
        "egg_moves_added": 0,
        "tutor_moves_added": 0,
    }

    for pokemon_key, move_levels in extracted["level_up_moves"].items():
        if pokemon_key not in learnsets:
            stats["missing_in_learnsets"] += 1
            continue

        entry = learnsets[pokemon_key]
        stats["pokemon_updated"] += 1

        existing_levels = entry.get("level_up_moves", [])
        non_selected = [move for move in existing_levels if move.get("gen") != generation]
        new_levels = non_selected + build_level_up_list(move_levels, generation)
        entry["level_up_moves"] = new_levels
        stats["level_sets_replaced"] += 1

        current_tm = set(entry.get("tm_moves", []))
        new_tm = extracted["tm_moves"].get(pokemon_key, set())
        stats["tm_moves_added"] += len(new_tm - current_tm)
        entry["tm_moves"] = sorted(current_tm | new_tm)

        current_egg = set(entry.get("egg_moves", []))
        new_egg = extracted["egg_moves"].get(pokemon_key, set())
        stats["egg_moves_added"] += len(new_egg - current_egg)
        entry["egg_moves"] = sorted(current_egg | new_egg)

        current_tutor = set(entry.get("tutor_moves", []))
        new_tutor = extracted["tutor_moves"].get(pokemon_key, set())
        stats["tutor_moves_added"] += len(new_tutor - current_tutor)
        entry["tutor_moves"] = sorted(current_tutor | new_tutor)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(learnsets, f, indent=2)

    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv-root",
        type=Path,
        default=Path("pokeapi_csv_bot"),
        help="Directory containing the PokeAPI CSV export",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/learnsets.json"),
        help="Where to write the merged learnsets file",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    pokemon_csv = args.csv_root / "pokemon.csv"
    moves_csv = args.csv_root / "moves.csv"
    version_groups_csv = args.csv_root / "version_groups.csv"
    pokemon_moves_csv = args.csv_root / "pokemon_moves.csv"

    pokemon_lookup = load_pokemon_names(pokemon_csv)
    move_lookup = load_move_names(moves_csv)

    vg_generations = load_version_group_generations(version_groups_csv)
    generation = select_generation(pokemon_moves_csv, vg_generations)
    allowed_version_groups = {vg for vg, gen in vg_generations.items() if gen == generation}

    extracted = extract_moves(
        pokemon_moves_csv,
        pokemon_lookup,
        move_lookup,
        allowed_version_groups,
    )

    stats = merge_learnsets(Path("data/learnsets.json"), args.output, extracted, generation)

    print(f"Generation {generation} learnset extraction complete:")
    print(f"  Pokemon updated: {stats['pokemon_updated']}")
    print(f"  Missing in learnsets: {stats['missing_in_learnsets']}")
    print(f"  Level-up sets replaced: {stats['level_sets_replaced']}")
    print(f"  TM moves added: {stats['tm_moves_added']}")
    print(f"  Egg moves added: {stats['egg_moves_added']}")
    print(f"  Tutor moves added: {stats['tutor_moves_added']}")


if __name__ == "__main__":
    main()
