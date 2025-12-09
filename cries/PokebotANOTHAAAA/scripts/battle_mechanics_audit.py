#!/usr/bin/env python3
"""
Battle Mechanics Audit Script
Tests and verifies all move and ability mechanics are working correctly
"""

import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_moves_data():
    """Load moves database"""
    with open('data/moves.json', 'r') as f:
        return json.load(f)


def load_abilities_data():
    """Load abilities database"""
    with open('data/abilities.json', 'r') as f:
        return json.load(f)


def audit_move_categories():
    """Categorize moves by their special mechanics"""
    moves = load_moves_data()

    categories = {
        'flinch': [],
        'status_inflict': [],
        'stat_changes': [],
        'multi_hit': [],
        'recoil': [],
        'drain': [],
        'priority': [],
        'ohko': [],
        'fixed_damage': [],
        'weather': [],
        'terrain': [],
        'hazards': [],
        'healing': [],
        'protect': [],
        'switching': [],
        'charging': [],
        'trapping': [],
        'confusion': [],
        'no_effect_mechanics': []  # Moves with special effects not yet categorized
    }

    for move_id, move_data in moves.items():
        name = move_data.get('name', move_id)

        # Check for flinch
        if 'secondary' in move_data and move_data['secondary']:
            sec = move_data['secondary']
            if isinstance(sec, dict) and 'volatileStatus' in sec and sec['volatileStatus'] == 'flinch':
                categories['flinch'].append((move_id, name, sec.get('chance', 100)))

        # Check for status infliction
        if 'status' in move_data:
            categories['status_inflict'].append((move_id, name, move_data['status']))
        if 'secondary' in move_data and isinstance(move_data['secondary'], dict):
            if 'status' in move_data['secondary']:
                categories['status_inflict'].append((move_id, name, move_data['secondary']['status']))

        # Check for stat changes
        if 'boosts' in move_data or ('secondary' in move_data and isinstance(move_data['secondary'], dict) and 'boosts' in move_data['secondary']):
            categories['stat_changes'].append((move_id, name))

        # Check for multi-hit
        if 'multihit' in move_data:
            categories['multi_hit'].append((move_id, name, move_data['multihit']))

        # Check for recoil
        if 'recoil' in move_data:
            categories['recoil'].append((move_id, name, move_data['recoil']))

        # Check for drain
        if 'drain' in move_data:
            categories['drain'].append((move_id, name, move_data['drain']))

        # Check for priority
        if move_data.get('priority', 0) != 0:
            categories['priority'].append((move_id, name, move_data['priority']))

        # Check for OHKO
        if move_data.get('ohko'):
            categories['ohko'].append((move_id, name))

        # Check for weather
        if 'weather' in move_data:
            categories['weather'].append((move_id, name, move_data['weather']))

        # Check for terrain
        if 'terrain' in move_data:
            categories['terrain'].append((move_id, name, move_data['terrain']))

        # Check for hazards (Stealth Rock, Spikes, etc.)
        if move_id in ['stealthrock', 'spikes', 'toxicspikes', 'stickyweb']:
            categories['hazards'].append((move_id, name))

        # Check for healing
        if 'heal' in move_data:
            categories['healing'].append((move_id, name, move_data['heal']))

        # Check for protect-like moves
        if move_id in ['protect', 'detect', 'endure', 'banefulbunker', 'kingsshield', 'spikyshield']:
            categories['protect'].append((move_id, name))

        # Check for switching moves
        if move_id in ['uturn', 'voltswitch', 'batonpass', 'partingshot', 'flipturn']:
            categories['switching'].append((move_id, name))

        # Check for charging moves
        if 'charge' in move_data or move_id in ['razorwind', 'fly', 'dig', 'bounce', 'dive', 'shadowforce', 'skydrop', 'solarbeam', 'skullbash', 'skyattack', 'freezeshock', 'iceburn']:
            categories['charging'].append((move_id, name))

        # Check for trapping
        if 'volatileStatus' in move_data:
            if move_data['volatileStatus'] in ['bind', 'wrap', 'firespin', 'whirlpool', 'sandtomb', 'clamp', 'infestation']:
                categories['trapping'].append((move_id, name))

        # Check for confusion
        if 'volatileStatus' in move_data and move_data['volatileStatus'] == 'confusion':
            categories['confusion'].append((move_id, name))
        if 'secondary' in move_data and isinstance(move_data['secondary'], dict):
            if 'volatileStatus' in move_data['secondary'] and move_data['secondary']['volatileStatus'] == 'confusion':
                categories['confusion'].append((move_id, name))

    return categories


def analyze_flinch_implementation():
    """Specific analysis of flinch mechanics"""
    print("\n" + "="*70)
    print("FLINCH MECHANICS ANALYSIS")
    print("="*70)

    moves = load_moves_data()
    flinch_moves = []

    for move_id, move_data in moves.items():
        if 'secondary' in move_data and move_data['secondary']:
            sec = move_data['secondary']
            if isinstance(sec, dict) and 'volatileStatus' in sec and sec['volatileStatus'] == 'flinch':
                flinch_moves.append({
                    'id': move_id,
                    'name': move_data['name'],
                    'chance': sec.get('chance', 100),
                    'priority': move_data.get('priority', 0),
                    'power': move_data.get('power', 0)
                })

    print(f"\nFound {len(flinch_moves)} moves that can cause flinching:")
    print("\nMoves with 100% flinch:")
    for move in sorted(flinch_moves, key=lambda x: x['name']):
        if move['chance'] == 100:
            print(f"  {move['name']:20s} - Priority: {move['priority']:+2d}, Power: {move['power']}")

    print("\nMoves with < 100% flinch:")
    for move in sorted(flinch_moves, key=lambda x: -x['chance']):
        if move['chance'] < 100:
            print(f"  {move['name']:20s} - {move['chance']:3d}% chance, Priority: {move['priority']:+2d}, Power: {move['power']}")

    print("\n📋 Flinch Requirements (Pokemon Rules):")
    print("  1. Flinch-causing move must hit successfully")
    print("  2. Move must go FIRST (higher priority or higher speed)")
    print("  3. Flinch prevents target from moving THIS TURN only")
    print("  4. Flinch is cleared at end of turn")
    print("  5. Flinch doesn't work if target has already moved")

    return flinch_moves


def analyze_status_moves():
    """Analyze status condition moves"""
    print("\n" + "="*70)
    print("STATUS CONDITION MOVES")
    print("="*70)

    moves = load_moves_data()
    status_moves = {
        'burn': [],
        'freeze': [],
        'paralysis': [],
        'poison': [],
        'sleep': [],
        'badly_poison': []
    }

    for move_id, move_data in moves.items():
        # Direct status
        if 'status' in move_data:
            status = move_data['status']
            if status in ['brn', 'burn']:
                status_moves['burn'].append((move_id, move_data['name'], 100))
            elif status in ['frz', 'freeze']:
                status_moves['freeze'].append((move_id, move_data['name'], 100))
            elif status in ['par', 'paralysis']:
                status_moves['paralysis'].append((move_id, move_data['name'], 100))
            elif status in ['psn', 'poison']:
                status_moves['poison'].append((move_id, move_data['name'], 100))
            elif status in ['slp', 'sleep']:
                status_moves['sleep'].append((move_id, move_data['name'], 100))
            elif status in ['tox', 'badly_poison', 'badlypoison']:
                status_moves['badly_poison'].append((move_id, move_data['name'], 100))

        # Secondary status
        if 'secondary' in move_data and isinstance(move_data['secondary'], dict):
            sec = move_data['secondary']
            if 'status' in sec:
                status = sec['status']
                chance = sec.get('chance', 100)
                if status in ['brn', 'burn']:
                    status_moves['burn'].append((move_id, move_data['name'], chance))
                elif status in ['frz', 'freeze']:
                    status_moves['freeze'].append((move_id, move_data['name'], chance))
                elif status in ['par', 'paralysis']:
                    status_moves['paralysis'].append((move_id, move_data['name'], chance))
                elif status in ['psn', 'poison']:
                    status_moves['poison'].append((move_id, move_data['name'], chance))
                elif status in ['slp', 'sleep']:
                    status_moves['sleep'].append((move_id, move_data['name'], chance))
                elif status in ['tox', 'badly_poison']:
                    status_moves['badly_poison'].append((move_id, move_data['name'], chance))

    for status_type, moves_list in status_moves.items():
        if moves_list:
            print(f"\n{status_type.upper()} ({len(moves_list)} moves):")
            for move_id, name, chance in sorted(moves_list, key=lambda x: -x[2])[:10]:
                print(f"  {name:20s} - {chance}% chance")

    return status_moves


def check_move_implementation_coverage():
    """Check which move effects are implemented in effect_handler.py"""
    print("\n" + "="*70)
    print("MOVE EFFECT IMPLEMENTATION CHECK")
    print("="*70)

    # Read effect_handler.py to see what's implemented
    try:
        with open('effect_handler.py', 'r') as f:
            effect_handler_content = f.read()
    except FileNotFoundError:
        print("❌ effect_handler.py not found")
        return

    implemented_effects = []
    if 'inflict_status' in effect_handler_content:
        implemented_effects.append('✅ Status infliction (burn, freeze, paralysis, etc.)')
    if 'inflict_volatile' in effect_handler_content:
        implemented_effects.append('✅ Volatile status (flinch, confusion, etc.)')
    if 'stat_boost' in effect_handler_content:
        implemented_effects.append('✅ Stat changes (boosts/drops)')
    if 'drain' in effect_handler_content:
        implemented_effects.append('✅ HP drain (Giga Drain, Absorb, etc.)')
    if 'recoil' in effect_handler_content:
        implemented_effects.append('✅ Recoil damage (Take Down, Double-Edge, etc.)')
    if 'heal' in effect_handler_content:
        implemented_effects.append('✅ Healing moves (Recover, Roost, etc.)')
    if 'hazard' in effect_handler_content:
        implemented_effects.append('✅ Entry hazards (Stealth Rock, Spikes, etc.)')
    if 'weather' in effect_handler_content:
        implemented_effects.append('✅ Weather (Sunny Day, Rain Dance, etc.)')
    if 'terrain' in effect_handler_content:
        implemented_effects.append('✅ Terrain (Electric Terrain, Grassy Terrain, etc.)')

    print("\nImplemented Move Effects:")
    for effect in implemented_effects:
        print(f"  {effect}")

    # Check for potential missing effects
    moves = load_moves_data()
    special_mechanics = set()

    for move_id, move_data in moves.items():
        if 'flags' in move_data and isinstance(move_data['flags'], dict):
            if move_data['flags'].get('charge'):
                special_mechanics.add('charge')
            if move_data['flags'].get('recharge'):
                special_mechanics.add('recharge')
        if 'self_switch' in move_data or move_id in ['uturn', 'voltswitch', 'batonpass']:
            special_mechanics.add('self_switch')
        if 'ohko' in move_data:
            special_mechanics.add('ohko')
        if 'critRatio' in move_data and move_data['critRatio'] > 1:
            special_mechanics.add('high_crit_ratio')

    print("\nSpecial Mechanics Found in Move Data:")
    for mechanic in sorted(special_mechanics):
        implemented = mechanic in effect_handler_content or mechanic.replace('_', '') in effect_handler_content
        status = "✅" if implemented else "❓"
        print(f"  {status} {mechanic}")


def main():
    print("="*70)
    print("POKEMON BATTLE MECHANICS AUDIT")
    print("="*70)

    # Change to script's parent directory
    import os
    os.chdir(Path(__file__).parent.parent)

    # Run analyses
    analyze_flinch_implementation()
    analyze_status_moves()
    check_move_implementation_coverage()

    categories = audit_move_categories()

    print("\n" + "="*70)
    print("MOVE CATEGORY SUMMARY")
    print("="*70)
    for category, moves in sorted(categories.items()):
        if moves:
            print(f"  {category:25s}: {len(moves):4d} moves")

    print("\n" + "="*70)
    print("RECOMMENDATIONS")
    print("="*70)
    print("1. Test flinch mechanics with speed-based scenarios")
    print("2. Verify all status conditions apply correctly")
    print("3. Check stat changes are persisting correctly")
    print("4. Test multi-hit moves count properly")
    print("5. Verify recoil/drain calculations")
    print("6. Test priority move ordering")
    print("7. Check weather/terrain effects")
    print("8. Verify entry hazards work in battle")
    print("\n")


if __name__ == '__main__':
    main()
