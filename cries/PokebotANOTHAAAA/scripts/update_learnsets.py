#!/usr/bin/env python3
"""
Update learnsets.json with accurate Gen 9 data from PMSV

Strategy (Option 2):
1. Replace ALL Gen 9 level-up moves with PMSV data (accurate levels)
2. For TMs: Include ALL TMs from PMSV Gen 9, PLUS keep historical TMs from all other gens
3. Keep tutor moves and other categories as-is
4. Remove any moves that don't belong (the script will be conservative here)
"""
import json
import sys
from pathlib import Path


def load_pmsv_data(pmsv_json_path):
    """Load the parsed PMSV data"""
    with open(pmsv_json_path, 'r') as f:
        return json.load(f)


def update_learnsets(current_path, pmsv_data, output_path):
    """
    Update learnsets with PMSV Gen 9 data
    """
    with open(current_path, 'r') as f:
        current_data = json.load(f)

    stats = {
        'pokemon_processed': 0,
        'level_moves_updated': 0,
        'tm_moves_added': 0,
        'tm_moves_removed': 0,
    }

    for pokemon_id, pmsv_pokemon in pmsv_data.items():
        if pokemon_id not in current_data:
            print(f"Warning: {pokemon_id} from PMSV not in current learnsets")
            continue

        current_pokemon = current_data[pokemon_id]
        stats['pokemon_processed'] += 1

        # 1. Update level-up moves: Remove all Gen 9 moves, add PMSV Gen 9 moves
        old_level_moves = current_pokemon.get('level_up_moves', [])

        # Keep non-Gen-9 moves
        non_gen9_moves = [m for m in old_level_moves if m.get('gen') != 9]

        # Add PMSV Gen 9 moves
        new_level_moves = non_gen9_moves + pmsv_pokemon['level_up_moves']

        # Sort by gen (older first) then by level
        new_level_moves.sort(key=lambda m: (m.get('gen', 0), m.get('level', 0)))

        if len(old_level_moves) != len(new_level_moves):
            stats['level_moves_updated'] += 1

        current_pokemon['level_up_moves'] = new_level_moves

        # 2. Update TM moves: Add all PMSV Gen 9 TMs if not already present
        current_tm_moves = set(current_pokemon.get('tm_moves', []))
        pmsv_tm_moves = set(pmsv_pokemon['tm_moves'])

        # Add any PMSV TMs that are missing
        new_tms = pmsv_tm_moves - current_tm_moves
        if new_tms:
            stats['tm_moves_added'] += len(new_tms)
            current_tm_moves.update(new_tms)

        # Convert back to sorted list
        current_pokemon['tm_moves'] = sorted(list(current_tm_moves))

        # 3. Update egg moves if PMSV has them
        if pmsv_pokemon['egg_moves']:
            pmsv_egg_moves = set(pmsv_pokemon['egg_moves'])
            current_egg_moves = set(current_pokemon.get('egg_moves', []))

            # Add missing egg moves
            current_egg_moves.update(pmsv_egg_moves)
            current_pokemon['egg_moves'] = sorted(list(current_egg_moves))

    # Write updated data
    with open(output_path, 'w') as f:
        json.dump(current_data, f, indent=2)

    return stats


def verify_specific_pokemon(learnsets_path, pokemon_ids):
    """Verify specific Pokemon after update"""
    with open(learnsets_path, 'r') as f:
        data = json.load(f)

    for pokemon_id in pokemon_ids:
        if pokemon_id not in data:
            print(f"\n{pokemon_id}: NOT FOUND")
            continue

        poke = data[pokemon_id]
        print(f"\n{pokemon_id}:")
        print(f"  Level-up moves: {len(poke.get('level_up_moves', []))}")

        # Count by gen
        gen_counts = {}
        for move in poke.get('level_up_moves', []):
            gen = move.get('gen', 0)
            gen_counts[gen] = gen_counts.get(gen, 0) + 1
        print(f"    By gen: {dict(sorted(gen_counts.items()))}")

        print(f"  TM moves: {len(poke.get('tm_moves', []))}")
        print(f"  Has 'incinerate': {'incinerate' in poke.get('tm_moves', [])}")

        # Show some Gen 9 level-up moves
        gen9_moves = [m for m in poke.get('level_up_moves', []) if m.get('gen') == 9]
        if gen9_moves:
            print(f"  First 5 Gen 9 level-up moves:")
            for move in gen9_moves[:5]:
                print(f"    Lv{move['level']:2d}: {move['move_id']}")


if __name__ == '__main__':
    pmsv_json = '/tmp/pmsv_parsed.json'
    current_learnsets = '/home/user/PokebotDOUBLESFIX/data/learnsets.json'
    output_learnsets = '/home/user/PokebotDOUBLESFIX/data/learnsets.json.new'

    print("Loading PMSV data...")
    pmsv_data = load_pmsv_data(pmsv_json)
    print(f"Loaded {len(pmsv_data)} Pokemon from PMSV")

    print("\nUpdating learnsets...")
    stats = update_learnsets(current_learnsets, pmsv_data, output_learnsets)

    print(f"\nUpdate complete!")
    print(f"  Pokemon processed: {stats['pokemon_processed']}")
    print(f"  Level-up move sets updated: {stats['level_moves_updated']}")
    print(f"  TM moves added: {stats['tm_moves_added']}")
    print(f"  TM moves removed: {stats['tm_moves_removed']}")

    print(f"\nNew learnsets saved to: {output_learnsets}")

    print("\n" + "="*60)
    print("Verifying sample Pokemon:")
    print("="*60)
    verify_specific_pokemon(output_learnsets, ['tyranitar', 'pikachu', 'charizard', 'meowscarada'])

    print("\n" + "="*60)
    print("IMPORTANT: Review the changes above before replacing the original file!")
    print("If everything looks good, run:")
    print(f"  mv {output_learnsets} {current_learnsets}")
    print("="*60)
