#!/usr/bin/env python3
"""
Clean up learnsets by removing moves that are incorrectly attributed

This script:
1. Updates Gen 9 level-up moves with accurate PMSV data
2. Adds missing Gen 9 TMs from PMSV
3. Removes moves that don't exist in Gen 9 and are incorrectly attributed
   (like Incinerate on 172 Pokemon that can't learn it)
"""
import json


def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def clean_learnsets(current_path, pmsv_path, output_path):
    current_data = load_json(current_path)
    pmsv_data = load_json(pmsv_path)

    # Build set of Pokemon that can learn specific moves in Gen 9
    gen9_move_learners = {}
    for poke_id, data in pmsv_data.items():
        # Get all moves this Pokemon can learn
        all_moves = set(data['tm_moves'])
        all_moves.update([m['move_id'] for m in data['level_up_moves']])
        all_moves.update(data['egg_moves'])

        for move in all_moves:
            if move not in gen9_move_learners:
                gen9_move_learners[move] = set()
            gen9_move_learners[move].add(poke_id)

    stats = {
        'pokemon_processed': 0,
        'level_moves_updated': 0,
        'tms_added': 0,
        'tms_removed': 0,
        'moves_cleaned': {}
    }

    # List of moves known to be incorrectly widespread (from Showdown errors)
    # We'll remove these from Pokemon that can't learn them in Gen 9
    suspicious_moves = ['incinerate']  # Add more as we find them

    for pokemon_id, current_pokemon in current_data.items():
        stats['pokemon_processed'] += 1

        # 1. Update level-up moves if we have PMSV data
        if pokemon_id in pmsv_data:
            pmsv_pokemon = pmsv_data[pokemon_id]

            # Remove all Gen 9 level-up moves
            old_level_moves = current_pokemon.get('level_up_moves', [])
            non_gen9_moves = [m for m in old_level_moves if m.get('gen') != 9]

            # Add PMSV Gen 9 moves
            new_level_moves = non_gen9_moves + pmsv_pokemon['level_up_moves']
            new_level_moves.sort(key=lambda m: (m.get('gen', 0), m.get('level', 0)))

            if len(old_level_moves) != len(new_level_moves):
                stats['level_moves_updated'] += 1

            current_pokemon['level_up_moves'] = new_level_moves

            # 2. Add missing Gen 9 TMs
            current_tm_moves = set(current_pokemon.get('tm_moves', []))
            pmsv_tm_moves = set(pmsv_pokemon['tm_moves'])

            new_tms = pmsv_tm_moves - current_tm_moves
            stats['tms_added'] += len(new_tms)
            current_tm_moves.update(new_tms)

            # 3. Remove suspicious moves if Pokemon can't learn them in Gen 9
            for sus_move in suspicious_moves:
                if sus_move in current_tm_moves:
                    # Check if Pokemon can actually learn this move in Gen 9
                    if pokemon_id not in gen9_move_learners.get(sus_move, set()):
                        current_tm_moves.remove(sus_move)
                        stats['tms_removed'] += 1

                        if sus_move not in stats['moves_cleaned']:
                            stats['moves_cleaned'][sus_move] = []
                        stats['moves_cleaned'][sus_move].append(pokemon_id)

            current_pokemon['tm_moves'] = sorted(list(current_tm_moves))

            # 4. Update egg moves
            if pmsv_pokemon['egg_moves']:
                pmsv_egg_moves = set(pmsv_pokemon['egg_moves'])
                current_egg_moves = set(current_pokemon.get('egg_moves', []))
                current_egg_moves.update(pmsv_egg_moves)
                current_pokemon['egg_moves'] = sorted(list(current_egg_moves))

    # Save cleaned data
    save_json(output_path, current_data)

    return stats


if __name__ == '__main__':
    current = '/home/user/PokebotDOUBLESFIX/data/learnsets.json'
    pmsv = '/tmp/pmsv_parsed.json'
    output = '/home/user/PokebotDOUBLESFIX/data/learnsets.json.cleaned'

    print("Cleaning learnsets...")
    print("=" * 70)

    stats = clean_learnsets(current, pmsv, output)

    print(f"\nCleaning complete!")
    print(f"  Pokemon processed: {stats['pokemon_processed']}")
    print(f"  Level-up move sets updated: {stats['level_moves_updated']}")
    print(f"  TMs added: {stats['tms_added']}")
    print(f"  TMs removed: {stats['tms_removed']}")

    print(f"\nMoves cleaned:")
    for move, pokemon_list in stats['moves_cleaned'].items():
        print(f"  {move}: removed from {len(pokemon_list)} Pokemon")
        if len(pokemon_list) <= 10:
            print(f"    Pokemon: {', '.join(sorted(pokemon_list))}")
        else:
            print(f"    First 10: {', '.join(sorted(pokemon_list)[:10])}")

    print(f"\nCleaned learnsets saved to: {output}")

    # Verify specific Pokemon
    print("\n" + "=" * 70)
    print("Verifying Tyranitar:")
    print("=" * 70)

    cleaned = load_json(output)
    ttar = cleaned.get('tyranitar', {})

    print(f"Level-up moves: {len(ttar.get('level_up_moves', []))}")

    gen_counts = {}
    for move in ttar.get('level_up_moves', []):
        gen = move.get('gen', 0)
        gen_counts[gen] = gen_counts.get(gen, 0) + 1
    print(f"  By generation: {dict(sorted(gen_counts.items()))}")

    print(f"TM moves: {len(ttar.get('tm_moves', []))}")
    print(f"Has 'incinerate': {'incinerate' in ttar.get('tm_moves', [])}")

    gen9_levelup = [m for m in ttar.get('level_up_moves', []) if m.get('gen') == 9]
    print(f"\nFirst 10 Gen 9 level-up moves:")
    for move in gen9_levelup[:10]:
        print(f"  Lv{move['level']:2d}: {move['move_id']}")

    print("\n" + "=" * 70)
    print("✓ Ready to replace original file:")
    print(f"  mv {output} {current}")
    print("=" * 70)
