"""
Comprehensive Move Audit and Fix Script
Checks all 937 moves for correctness and fixes issues
"""

import json
import re
from typing import Dict, List, Tuple, Any

# Known move mechanics from Pokemon games
MOVE_FIXES = {
    # Status moves that inflict status conditions
    'thunder_wave': {'status': 'par'},
    'glare': {'status': 'par'},
    'stun_spore': {'status': 'par'},
    'will_o_wisp': {'status': 'brn'},
    'poison_powder': {'status': 'psn'},
    'poison_gas': {'status': 'psn'},
    'toxic': {'status': 'tox'},
    'sleep_powder': {'status': 'slp'},
    'spore': {'status': 'slp'},
    'hypnosis': {'status': 'slp'},
    'lovely_kiss': {'status': 'slp'},
    'sing': {'status': 'slp'},
    'grass_whistle': {'status': 'slp'},
    'dark_void': {'status': 'slp'},

    # Yawn - special case (applies sleep next turn)
    'yawn': {'volatileStatus': 'yawn'},

    # Moves that confuse
    'confuse_ray': {'volatileStatus': 'confusion'},
    'supersonic': {'volatileStatus': 'confusion'},
    'sweet_kiss': {'volatileStatus': 'confusion'},
    'swagger': {'volatileStatus': 'confusion', 'boosts': {'atk': 2}},
    'flatter': {'volatileStatus': 'confusion', 'boosts': {'spa': 1}},

    # Flinch moves
    'fake_out': {'volatileStatus': 'flinch'},
    'astonish': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},
    'bite': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},
    'bone_club': {'secondary': {'chance': 10, 'volatileStatus': 'flinch'}},
    'dark_pulse': {'secondary': {'chance': 20, 'volatileStatus': 'flinch'}},
    'extrasensory': {'secondary': {'chance': 10, 'volatileStatus': 'flinch'}},
    'headbutt': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},
    'hyper_fang': {'secondary': {'chance': 10, 'volatileStatus': 'flinch'}},
    'iron_head': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},
    'needle_arm': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},
    'rock_slide': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},
    'rolling_kick': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},
    'sky_attack': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},
    'steamroller': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},
    'stomp': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},
    'waterfall': {'secondary': {'chance': 20, 'volatileStatus': 'flinch'}},
    'zen_headbutt': {'secondary': {'chance': 20, 'volatileStatus': 'flinch'}},
    'zing_zap': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},

    # Trap moves (bind, wrap, etc.)
    'bind': {'volatileStatus': 'partiallytrapped'},
    'clamp': {'volatileStatus': 'partiallytrapped'},
    'fire_spin': {'volatileStatus': 'partiallytrapped'},
    'infestation': {'volatileStatus': 'partiallytrapped'},
    'magma_storm': {'volatileStatus': 'partiallytrapped'},
    'sand_tomb': {'volatileStatus': 'partiallytrapped'},
    'snap_trap': {'volatileStatus': 'partiallytrapped'},
    'thunder_cage': {'volatileStatus': 'partiallytrapped'},
    'whirlpool': {'volatileStatus': 'partiallytrapped'},
    'wrap': {'volatileStatus': 'partiallytrapped'},

    # Moves with self-destruct
    'explosion': {'selfdestruct': True},
    'self_destruct': {'selfdestruct': True},
    'misty_explosion': {'selfdestruct': True},

    # OHKO moves
    'fissure': {'ohko': True},
    'guillotine': {'ohko': True},
    'horn_drill': {'ohko': True},
    'sheer_cold': {'ohko': True},

    # Multi-hit moves
    'double_slap': {'multihit': [2, 5]},
    'fury_attack': {'multihit': [2, 5]},
    'fury_swipes': {'multihit': [2, 5]},
    'comet_punch': {'multihit': [2, 5]},
    'pin_missile': {'multihit': [2, 5]},
    'spike_cannon': {'multihit': [2, 5]},
    'barrage': {'multihit': [2, 5]},
    'bone_rush': {'multihit': [2, 5]},
    'icicle_spear': {'multihit': [2, 5]},
    'rock_blast': {'multihit': [2, 5]},
    'tail_slap': {'multihit': [2, 5]},
    'bullet_seed': {'multihit': [2, 5]},
    'scale_shot': {'multihit': [2, 5]},
    'surging_strikes': {'multihit': 3},
    'population_bomb': {'multihit': [1, 10]},

    'double_kick': {'multihit': 2},
    'bonemerang': {'multihit': 2},
    'double_hit': {'multihit': 2},
    'dual_chop': {'multihit': 2},
    'twineedle': {'multihit': 2},
    'gear_grind': {'multihit': 2},
    'double_iron_bash': {'multihit': 2},
    'dragon_darts': {'multihit': 2},

    'triple_kick': {'multihit': 3},
    'triple_axel': {'multihit': 3},
    'water_shuriken': {'multihit': [2, 5]},

    # Weather-setting moves
    'sunny_day': {'weather': 'sun'},
    'rain_dance': {'weather': 'rain'},
    'sandstorm': {'weather': 'sandstorm'},
    'hail': {'weather': 'hail'},
    'snowscape': {'weather': 'snow'},

    # Terrain-setting moves
    'electric_terrain': {'terrain': 'electricterrain'},
    'grassy_terrain': {'terrain': 'grassyterrain'},
    'misty_terrain': {'terrain': 'mistyterrain'},
    'psychic_terrain': {'terrain': 'psychicterrain'},

    # Force switch moves
    'roar': {'forceSwitch': True},
    'whirlwind': {'forceSwitch': True},
    'circle_throw': {'forceSwitch': True},
    'dragon_tail': {'forceSwitch': True},

    # Self-switch moves (U-turn, Volt Switch, etc.)
    'volt_switch': {'selfSwitch': True},
    'u_turn': {'selfSwitch': True},
    'flip_turn': {'selfSwitch': True},
    'baton_pass': {'selfSwitch': True},
    'parting_shot': {'selfSwitch': True},
    'teleport': {'selfSwitch': True},
    'chilly_reception': {'selfSwitch': True},
    'shed_tail': {'selfSwitch': True},

    # Priority moves
    'quick_attack': {'priority': 1},
    'aqua_jet': {'priority': 1},
    'mach_punch': {'priority': 1},
    'bullet_punch': {'priority': 1},
    'ice_shard': {'priority': 1},
    'shadow_sneak': {'priority': 1},
    'vacuum_wave': {'priority': 1},
    'water_shuriken': {'priority': 1},
    'accelerock': {'priority': 1},
    'aqua_step': {'priority': 1},

    'extreme_speed': {'priority': 2},
    'feint': {'priority': 2},

    'protect': {'priority': 4},
    'detect': {'priority': 4},
    'endure': {'priority': 4},
    'king_s_shield': {'priority': 4},
    'spiky_shield': {'priority': 4},
    'baneful_bunker': {'priority': 4},
    'obstruct': {'priority': 4},

    'fake_out': {'priority': 3},

    # Recoil moves
    'take_down': {'recoil': [1, 4]},  # 1/4 recoil
    'submission': {'recoil': [1, 4]},
    'double_edge': {'recoil': [33, 100]},  # 1/3 recoil
    'brave_bird': {'recoil': [33, 100]},
    'flare_blitz': {'recoil': [33, 100]},
    'volt_tackle': {'recoil': [33, 100]},
    'wild_charge': {'recoil': [1, 4]},
    'head_smash': {'recoil': [1, 2]},  # 1/2 recoil
    'wood_hammer': {'recoil': [33, 100]},
    'head_charge': {'recoil': [1, 4]},

    # Drain moves
    'absorb': {'drain': [1, 2]},
    'mega_drain': {'drain': [1, 2]},
    'giga_drain': {'drain': [1, 2]},
    'drain_punch': {'drain': [1, 2]},
    'draining_kiss': {'drain': [3, 4]},  # 75% drain
    'horn_leech': {'drain': [1, 2]},
    'leech_life': {'drain': [1, 2]},
    'parabolic_charge': {'drain': [1, 2]},
    'oblivion_wing': {'drain': [3, 4]},

    # Healing moves
    'recover': {'heal': [1, 2]},
    'soft_boiled': {'heal': [1, 2]},
    'milk_drink': {'heal': [1, 2]},
    'slack_off': {'heal': [1, 2]},
    'roost': {'heal': [1, 2]},
    'moonlight': {'heal': [1, 2]},
    'morning_sun': {'heal': [1, 2]},
    'synthesis': {'heal': [1, 2]},
    'rest': {'heal': [1, 1], 'status': 'slp'},  # Full heal + sleep
    'shore_up': {'heal': [1, 2]},

    # Two-turn moves
    'razor_wind': {'charge': True},
    'solar_beam': {'charge': True},
    'skull_bash': {'charge': True},
    'sky_attack': {'charge': True},
    'freeze_shock': {'charge': True},
    'ice_burn': {'charge': True},
    'geomancy': {'charge': True},
    'fly': {'charge': True},
    'bounce': {'charge': True},
    'dig': {'charge': True},
    'dive': {'charge': True},
    'phantom_force': {'charge': True},
    'shadow_force': {'charge': True},
    'sky_drop': {'charge': True},
}


class MoveAuditor:
    def __init__(self, moves_file: str):
        with open(moves_file, 'r', encoding='utf-8') as f:
            self.moves = json.load(f)

        self.issues = []
        self.fixes_applied = 0

    def audit_all_moves(self) -> Tuple[List[Dict], int]:
        """Audit all moves and return issues found"""
        print(f"Auditing {len(self.moves)} moves...")

        for move_id, move_data in self.moves.items():
            self._audit_move(move_id, move_data)

        return self.issues, len(self.moves)

    def _audit_move(self, move_id: str, move_data: Dict):
        """Audit a single move"""
        move_name = move_data.get('name', move_id)

        # Check for missing required fields
        required_fields = ['id', 'name', 'type', 'category', 'pp', 'priority', 'target']
        for field in required_fields:
            if field not in move_data:
                self.issues.append({
                    'move_id': move_id,
                    'move_name': move_name,
                    'severity': 'ERROR',
                    'issue': f'Missing required field: {field}'
                })

        # Check damaging moves have power
        if move_data.get('category') in ['physical', 'special']:
            if move_data.get('power') is None and not move_data.get('ohko'):
                # Some special moves like Foul Play calculate damage differently
                special_cases = ['foul_play', 'psyshock', 'psystrike', 'secret_sword']
                if move_id not in special_cases:
                    self.issues.append({
                        'move_id': move_id,
                        'move_name': move_name,
                        'severity': 'WARNING',
                        'issue': f'Damaging move missing power value'
                    })

        # Check if move should have effects based on known mechanics
        if move_id in MOVE_FIXES:
            expected = MOVE_FIXES[move_id]
            for key, value in expected.items():
                if key not in move_data or move_data[key] != value:
                    self.issues.append({
                        'move_id': move_id,
                        'move_name': move_name,
                        'severity': 'FIX',
                        'issue': f'Missing or incorrect {key}: expected {value}, got {move_data.get(key)}',
                        'fix': {key: value}
                    })

    def apply_fixes(self) -> int:
        """Apply all known fixes to moves"""
        print("\nApplying fixes...")
        fixes_count = 0

        for move_id, fixes in MOVE_FIXES.items():
            if move_id in self.moves:
                move_data = self.moves[move_id]
                for key, value in fixes.items():
                    # Only apply if missing or different
                    if key not in move_data or move_data[key] != value:
                        move_data[key] = value
                        fixes_count += 1
                        print(f"  Fixed {move_id}: Added/updated {key} = {value}")

        self.fixes_applied = fixes_count
        return fixes_count

    def save_moves(self, output_file: str):
        """Save fixed moves to file"""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.moves, f, indent=2, ensure_ascii=False)
        print(f"\nSaved fixed moves to {output_file}")

    def generate_report(self) -> str:
        """Generate a detailed report of all issues"""
        report = []
        report.append("=" * 80)
        report.append("MOVE AUDIT REPORT")
        report.append("=" * 80)
        report.append(f"\nTotal moves audited: {len(self.moves)}")
        report.append(f"Issues found: {len(self.issues)}")
        report.append(f"Fixes applied: {self.fixes_applied}")

        # Group issues by severity
        errors = [i for i in self.issues if i['severity'] == 'ERROR']
        warnings = [i for i in self.issues if i['severity'] == 'WARNING']
        fixes = [i for i in self.issues if i['severity'] == 'FIX']

        if errors:
            report.append(f"\n\nERRORS ({len(errors)}):")
            report.append("-" * 80)
            for issue in errors[:50]:  # Limit to first 50
                report.append(f"  {issue['move_name']} ({issue['move_id']}): {issue['issue']}")

        if warnings:
            report.append(f"\n\nWARNINGS ({len(warnings)}):")
            report.append("-" * 80)
            for issue in warnings[:50]:
                report.append(f"  {issue['move_name']} ({issue['move_id']}): {issue['issue']}")

        if fixes:
            report.append(f"\n\nFIXES NEEDED ({len(fixes)}):")
            report.append("-" * 80)
            for issue in fixes[:100]:
                report.append(f"  {issue['move_name']} ({issue['move_id']}): {issue['issue']}")

        report.append("\n" + "=" * 80)

        return "\n".join(report)


def main():
    moves_file = '/home/user/PokebotANOTHAAAA/data/moves.json'

    auditor = MoveAuditor(moves_file)

    # Run audit
    issues, total = auditor.audit_all_moves()

    # Apply fixes
    fixes_count = auditor.apply_fixes()

    # Generate report
    report = auditor.generate_report()
    print(report)

    # Save report to file
    with open('/home/user/PokebotANOTHAAAA/move_audit_report.txt', 'w') as f:
        f.write(report)

    # Save fixed moves
    auditor.save_moves('/home/user/PokebotANOTHAAAA/data/moves_fixed.json')

    print(f"\n✓ Audit complete!")
    print(f"✓ Report saved to: move_audit_report.txt")
    print(f"✓ Fixed moves saved to: data/moves_fixed.json")

    return auditor


if __name__ == '__main__':
    main()
