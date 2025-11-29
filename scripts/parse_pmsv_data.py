#!/usr/bin/env python3
"""
Parse PMSV game-extracted data and convert to learnsets format
"""
import json
import re
from collections import defaultdict


def normalize_pokemon_name(name):
    """Convert Pokemon name to standard ID format"""
    # Remove everything after parentheses or hashes
    base_name = re.sub(r'\s+[#B].*$', '', name).strip()

    # Convert to lowercase and remove non-alphanumeric characters
    pokemon_id = re.sub(r'[^a-z0-9]', '', base_name.lower())
    return pokemon_id


def normalize_move_name(move):
    """Convert move name to standard ID format"""
    # Convert to lowercase and remove non-alphanumeric characters
    move_id = re.sub(r'[^a-z0-9]', '', move.lower())
    return move_id


def parse_pmsv_file(filepath):
    """Parse the PMSV Pokemon Info EN.txt file"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Normalize line endings
    content = content.replace('\r\n', '\n').replace('\r', '\n')

    pokemon_data = {}

    # Split into lines and process
    lines = content.split('\n')

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Look for Pokemon entry lines (e.g., "001 - Bulbasaur ...")
        if re.match(r'^\d{3,4} - ', line):
            # Extract Pokemon info
            match = re.match(r'^(\d+) - (.+?)(?:\s+[#B]|$)', line)
            if not match:
                i += 1
                continue

            dex_num = match.group(1)
            pokemon_name = match.group(2).strip()
            pokemon_id = normalize_pokemon_name(pokemon_name)

            # Initialize data
            data = {
                'pokemon_id': pokemon_id,
                'dex_number': int(dex_num),
                'name': pokemon_name,
                'level_up_moves': [],
                'tm_moves': [],
                'egg_moves': []
            }

            # Skip the ====== line
            i += 1
            if i < len(lines) and '====' in lines[i]:
                i += 1

            # Parse the Pokemon's data
            current_section = None
            while i < len(lines):
                line = lines[i].strip()

                # Stop if we hit the next Pokemon or evolves line
                if not line or line.startswith('===') or re.match(r'^\d{3,4} - ', line):
                    break

                if line.startswith('Evolves'):
                    break
                elif 'Level Up Moves:' in line:
                    current_section = 'level_up'
                elif 'TM Learn:' in line:
                    current_section = 'tm'
                elif 'Egg Moves:' in line:
                    current_section = 'egg'
                elif line.startswith('- [') and current_section:
                    # Parse move
                    if current_section == 'level_up':
                        match = re.match(r'- \[(\d+)\] (.+)', line)
                        if match:
                            level = int(match.group(1))
                            move_name = match.group(2).strip()
                            move_id = normalize_move_name(move_name)
                            data['level_up_moves'].append({
                                'level': level,
                                'move_id': move_id,
                                'gen': 9
                            })
                    elif current_section == 'tm':
                        match = re.match(r'- \[TM\d+\] (.+)', line)
                        if match:
                            move_name = match.group(1).strip()
                            move_id = normalize_move_name(move_name)
                            data['tm_moves'].append(move_id)
                elif line.startswith('- ') and current_section == 'egg':
                    # Egg moves don't have brackets
                    move_name = line[2:].strip()
                    move_id = normalize_move_name(move_name)
                    data['egg_moves'].append(move_id)

                i += 1

            # Save this Pokemon's data
            pokemon_data[pokemon_id] = data
            continue

        i += 1

    return pokemon_data


def compare_learnsets(pmsv_data, current_learnsets_path):
    """Compare PMSV data with current learnsets and report differences"""
    with open(current_learnsets_path, 'r') as f:
        current_data = json.load(f)

    issues = []

    for pokemon_id, pmsv_pokemon in pmsv_data.items():
        if pokemon_id not in current_data:
            continue  # Skip missing Pokemon for now

        current_pokemon = current_data[pokemon_id]

        # Check Gen 9 level-up moves
        current_gen9_levelup = [m for m in current_pokemon.get('level_up_moves', [])
                                 if isinstance(m, dict) and m.get('gen') == 9]

        pmsv_levelup = pmsv_pokemon['level_up_moves']

        # Create sets for comparison
        current_moves_set = {(m['level'], m['move_id']) for m in current_gen9_levelup}
        pmsv_moves_set = {(m['level'], m['move_id']) for m in pmsv_levelup}

        missing = pmsv_moves_set - current_moves_set
        extra = current_moves_set - pmsv_moves_set

        if missing or extra:
            issues.append(f"{pokemon_id}: Missing {len(missing)} moves, Extra {len(extra)} moves")

        # Check TM moves - are all PMSV TMs present?
        current_tm_moves = set(current_pokemon.get('tm_moves', []))
        pmsv_tm_moves = set(pmsv_pokemon['tm_moves'])

        missing_tms = pmsv_tm_moves - current_tm_moves
        if missing_tms:
            issues.append(f"{pokemon_id}: Missing {len(missing_tms)} Gen 9 TMs")

    return issues


if __name__ == '__main__':
    print("Parsing PMSV data...")
    pmsv_data = parse_pmsv_file('/tmp/PMSV/Pokémon Info EN.txt')
    print(f"Parsed {len(pmsv_data)} Pokemon")

    # Check Tyranitar specifically
    if 'tyranitar' in pmsv_data:
        ttar = pmsv_data['tyranitar']
        print(f"\nTyranitar data:")
        print(f"  Level-up moves: {len(ttar['level_up_moves'])}")
        print(f"  First 5 level-up moves: {ttar['level_up_moves'][:5]}")
        print(f"  TM moves: {len(ttar['tm_moves'])}")
        print(f"  Has Incinerate: {'incinerate' in ttar['tm_moves']}")
        print(f"  Sample TMs: {ttar['tm_moves'][:10]}")

    # Save parsed data
    output_path = '/tmp/pmsv_parsed.json'
    with open(output_path, 'w') as f:
        json.dump(pmsv_data, f, indent=2)
    print(f"\nSaved parsed data to {output_path}")

    # Compare with current learnsets
    print("\nComparing with current learnsets...")
    issues = compare_learnsets(pmsv_data, '/home/user/PokebotDOUBLESFIX/data/learnsets.json')

    if issues:
        print(f"\nFound {len(issues)} Pokemon with issues (showing first 30):")
        for issue in issues[:30]:
            print(f"  - {issue}")
    else:
        print("\nNo issues found!")
