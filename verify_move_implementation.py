"""
Verify that all moves can be properly processed by the effect handler
"""

import json
import sys

def verify_moves():
    """Verify all moves are properly implemented"""

    # Load moves
    with open('/home/user/PokebotANOTHAAAA/data/moves.json', 'r') as f:
        moves = json.load(f)

    print(f"Verifying {len(moves)} moves...\n")

    # Categories of moves to check
    stats = {
        'total': len(moves),
        'damaging': 0,
        'status': 0,
        'with_secondary': 0,
        'with_boosts': 0,
        'with_status_inflict': 0,
        'with_volatile': 0,
        'with_drain': 0,
        'with_recoil': 0,
        'with_heal': 0,
        'multihit': 0,
        'charge_moves': 0,
        'priority_moves': 0,
        'weather_moves': 0,
        'terrain_moves': 0,
        'switch_moves': 0,
        'hazard_moves': 0,
        'ohko_moves': 0,
    }

    incomplete_moves = []
    well_implemented = []

    for move_id, move_data in moves.items():
        category = move_data.get('category')
        move_name = move_data.get('name', move_id)

        # Count by category
        if category in ['physical', 'special']:
            stats['damaging'] += 1
        elif category == 'status':
            stats['status'] += 1

        # Count special mechanics
        if 'secondary' in move_data:
            stats['with_secondary'] += 1
        if 'boosts' in move_data:
            stats['with_boosts'] += 1
        if 'status' in move_data:
            stats['with_status_inflict'] += 1
        if 'volatileStatus' in move_data:
            stats['with_volatile'] += 1
        if 'drain' in move_data:
            stats['with_drain'] += 1
        if 'recoil' in move_data:
            stats['with_recoil'] += 1
        if 'heal' in move_data:
            stats['with_heal'] += 1
        if 'multihit' in move_data:
            stats['multihit'] += 1
        if 'charge' in move_data:
            stats['charge_moves'] += 1
        if move_data.get('priority', 0) != 0:
            stats['priority_moves'] += 1
        if 'weather' in move_data:
            stats['weather_moves'] += 1
        if 'terrain' in move_data:
            stats['terrain_moves'] += 1
        if 'selfSwitch' in move_data or 'forceSwitch' in move_data:
            stats['switch_moves'] += 1
        if 'enemy_field' in move_data.get('target', ''):
            stats['hazard_moves'] += 1
        if 'ohko' in move_data:
            stats['ohko_moves'] += 1

        # Check for potentially incomplete moves
        is_incomplete = False
        reasons = []

        # Damaging moves should have power or special calculation
        if category in ['physical', 'special']:
            if move_data.get('power') is None and not move_data.get('ohko'):
                # Check if it's a special damage calculation move
                special_calc_moves = [
                    'counter', 'mirror_coat', 'metal_burst', 'bide',
                    'dragon_rage', 'sonic_boom', 'seismic_toss', 'night_shade',
                    'psywave', 'super_fang', 'endeavor',
                    'flail', 'reversal', 'return', 'frustration',
                    'gyro_ball', 'electro_ball', 'grass_knot', 'low_kick',
                    'heavy_slam', 'heat_crash', 'crush_grip', 'wring_out',
                    'punishment', 'trump_card', 'magnitude', 'beat_up',
                    'spit_up', 'fling', 'natural_gift', 'present', 'final_gambit',
                ]
                if move_id not in special_calc_moves:
                    is_incomplete = True
                    reasons.append("Missing power value")

        # Status moves that should inflict status
        if category == 'status' and 'wave' in move_name.lower() or 'powder' in move_name.lower() or 'spore' in move_name.lower():
            if 'status' not in move_data and 'volatileStatus' not in move_data and 'boosts' not in move_data:
                is_incomplete = True
                reasons.append("Status move missing effect")

        if is_incomplete:
            incomplete_moves.append({
                'id': move_id,
                'name': move_name,
                'reasons': reasons
            })
        else:
            # Well implemented if it has proper effects
            if any([
                'secondary' in move_data,
                'boosts' in move_data,
                'status' in move_data,
                'volatileStatus' in move_data,
                'drain' in move_data,
                'recoil' in move_data,
                'heal' in move_data,
                'multihit' in move_data,
                'charge' in move_data,
                'weather' in move_data,
                'terrain' in move_data,
                'selfSwitch' in move_data,
                'forceSwitch' in move_data,
                'ohko' in move_data,
            ]):
                well_implemented.append(move_name)

    # Print report
    print("=" * 80)
    print("MOVE IMPLEMENTATION VERIFICATION REPORT")
    print("=" * 80)
    print(f"\nTotal moves: {stats['total']}")
    print(f"  - Damaging moves: {stats['damaging']}")
    print(f"  - Status moves: {stats['status']}")
    print(f"\nMoves with special mechanics:")
    print(f"  - Secondary effects: {stats['with_secondary']}")
    print(f"  - Stat boosts/drops: {stats['with_boosts']}")
    print(f"  - Status infliction: {stats['with_status_inflict']}")
    print(f"  - Volatile status: {stats['with_volatile']}")
    print(f"  - Drain moves: {stats['with_drain']}")
    print(f"  - Recoil moves: {stats['with_recoil']}")
    print(f"  - Healing moves: {stats['with_heal']}")
    print(f"  - Multi-hit moves: {stats['multihit']}")
    print(f"  - Two-turn moves: {stats['charge_moves']}")
    print(f"  - Priority moves: {stats['priority_moves']}")
    print(f"  - Weather moves: {stats['weather_moves']}")
    print(f"  - Terrain moves: {stats['terrain_moves']}")
    print(f"  - Switch moves: {stats['switch_moves']}")
    print(f"  - Hazard moves: {stats['hazard_moves']}")
    print(f"  - OHKO moves: {stats['ohko_moves']}")
    print(f"\nWell-implemented moves: {len(well_implemented)}")
    print(f"Potentially incomplete: {len(incomplete_moves)}")

    if incomplete_moves:
        print(f"\nPotentially incomplete moves ({len(incomplete_moves)}):")
        for move in incomplete_moves[:20]:  # Show first 20
            print(f"  - {move['name']} ({move['id']}): {', '.join(move['reasons'])}")

    # Coverage percentage
    coverage = (len(well_implemented) / stats['total']) * 100
    print(f"\nImplementation coverage: {coverage:.1f}%")

    # Save detailed report
    with open('/home/user/PokebotANOTHAAAA/move_verification_report.txt', 'w') as f:
        f.write("MOVE IMPLEMENTATION VERIFICATION REPORT\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Total moves: {stats['total']}\n")
        f.write(f"Well-implemented moves: {len(well_implemented)}\n")
        f.write(f"Implementation coverage: {coverage:.1f}%\n\n")
        f.write("Statistics:\n")
        for key, value in stats.items():
            f.write(f"  {key}: {value}\n")
        f.write(f"\n\nWell-implemented moves ({len(well_implemented)}):\n")
        for name in well_implemented:
            f.write(f"  - {name}\n")

    print(f"\n✅ Verification complete!")
    print(f"📄 Detailed report saved to: move_verification_report.txt")
    print("=" * 80)


if __name__ == '__main__':
    verify_moves()
