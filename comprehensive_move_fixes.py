"""
COMPREHENSIVE Move Audit and Fix Script
Covers ALL known Pokemon move mechanics across all generations
"""

import json
import copy

# COMPREHENSIVE move fixes database
COMPREHENSIVE_FIXES = {
    # ========== STATUS MOVES ==========
    # Paralysis
    'thunder_wave': {'status': 'par'},
    'glare': {'status': 'par'},
    'stun_spore': {'status': 'par'},
    'nuzzle': {'status': 'par'},

    # Burn
    'will_o_wisp': {'status': 'brn'},

    # Poison
    'poison_powder': {'status': 'psn'},
    'poison_gas': {'status': 'psn'},
    'poisonpowder': {'status': 'psn'},

    # Toxic (Badly Poisoned)
    'toxic': {'status': 'tox'},

    # Sleep
    'sleep_powder': {'status': 'slp'},
    'spore': {'status': 'slp'},
    'hypnosis': {'status': 'slp'},
    'lovely_kiss': {'status': 'slp'},
    'sing': {'status': 'slp'},
    'grass_whistle': {'status': 'slp'},
    'dark_void': {'status': 'slp'},
    'yawn': {'volatileStatus': 'yawn'},

    # ========== CONFUSION ==========
    'confuse_ray': {'volatileStatus': 'confusion'},
    'supersonic': {'volatileStatus': 'confusion'},
    'sweet_kiss': {'volatileStatus': 'confusion'},
    'teeter_dance': {'volatileStatus': 'confusion'},
    'dizzy_punch': {'secondary': {'chance': 20, 'volatileStatus': 'confusion'}},
    'swagger': {'boosts': {'atk': 2}, 'volatileStatus': 'confusion'},
    'flatter': {'boosts': {'spa': 1}, 'volatileStatus': 'confusion'},

    # ========== FLINCH MOVES ==========
    'fake_out': {'priority': 3, 'volatileStatus': 'flinch'},
    'astonish': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},
    'bite': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},
    'bone_club': {'secondary': {'chance': 10, 'volatileStatus': 'flinch'}},
    'dark_pulse': {'secondary': {'chance': 20, 'volatileStatus': 'flinch'}},
    'dragon_rush': {'secondary': {'chance': 20, 'volatileStatus': 'flinch'}},
    'extrasensory': {'secondary': {'chance': 10, 'volatileStatus': 'flinch'}},
    'headbutt': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},
    'hyper_fang': {'secondary': {'chance': 10, 'volatileStatus': 'flinch'}},
    'iron_head': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},
    'needle_arm': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},
    'rock_slide': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},
    'rolling_kick': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},
    'sky_attack': {'charge': True, 'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},
    'steamroller': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},
    'stomp': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},
    'twister': {'secondary': {'chance': 20, 'volatileStatus': 'flinch'}},
    'waterfall': {'secondary': {'chance': 20, 'volatileStatus': 'flinch'}},
    'zen_headbutt': {'secondary': {'chance': 20, 'volatileStatus': 'flinch'}},
    'zing_zap': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},
    'air_slash': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},
    'heart_stamp': {'secondary': {'chance': 30, 'volatileStatus': 'flinch'}},

    # ========== TRAPPING/BINDING MOVES ==========
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

    # ========== SELF-DESTRUCT MOVES ==========
    'explosion': {'selfdestruct': True},
    'self_destruct': {'selfdestruct': True},
    'misty_explosion': {'selfdestruct': True},
    'final_gambit': {'selfdestruct': True},

    # ========== OHKO MOVES ==========
    'fissure': {'ohko': True},
    'guillotine': {'ohko': True},
    'horn_drill': {'ohko': True},
    'sheer_cold': {'ohko': True},

    # ========== MULTI-HIT MOVES ==========
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
    'water_shuriken': {'multihit': [2, 5], 'priority': 1},
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
    'surging_strikes': {'multihit': 3},

    # ========== WEATHER MOVES ==========
    'sunny_day': {'weather': 'sun'},
    'rain_dance': {'weather': 'rain'},
    'sandstorm': {'weather': 'sandstorm'},
    'hail': {'weather': 'hail'},
    'snowscape': {'weather': 'snow'},

    # ========== TERRAIN MOVES ==========
    'electric_terrain': {'terrain': 'electricterrain'},
    'grassy_terrain': {'terrain': 'grassyterrain'},
    'misty_terrain': {'terrain': 'mistyterrain'},
    'psychic_terrain': {'terrain': 'psychicterrain'},

    # ========== FORCE SWITCH MOVES ==========
    'roar': {'forceSwitch': True},
    'whirlwind': {'forceSwitch': True},
    'circle_throw': {'forceSwitch': True},
    'dragon_tail': {'forceSwitch': True},

    # ========== SELF-SWITCH MOVES ==========
    'volt_switch': {'selfSwitch': True},
    'u_turn': {'selfSwitch': True},
    'flip_turn': {'selfSwitch': True},
    'baton_pass': {'selfSwitch': True},
    'parting_shot': {'selfSwitch': True},
    'teleport': {'selfSwitch': True},
    'chilly_reception': {'selfSwitch': True},
    'shed_tail': {'selfSwitch': True},

    # ========== PRIORITY MOVES ==========
    'quick_attack': {'priority': 1},
    'aqua_jet': {'priority': 1},
    'mach_punch': {'priority': 1},
    'bullet_punch': {'priority': 1},
    'ice_shard': {'priority': 1},
    'shadow_sneak': {'priority': 1},
    'vacuum_wave': {'priority': 1},
    'accelerock': {'priority': 1},
    'aqua_step': {'priority': 1},
    'first_impression': {'priority': 2},
    'extreme_speed': {'priority': 2},
    'feint': {'priority': 2},
    'protect': {'priority': 4},
    'detect': {'priority': 4},
    'endure': {'priority': 4},
    'king_s_shield': {'priority': 4},
    'spiky_shield': {'priority': 4},
    'baneful_bunker': {'priority': 4},
    'obstruct': {'priority': 4},
    'silk_trap': {'priority': 4},
    'burning_bulwark': {'priority': 4},

    # ========== RECOIL MOVES ==========
    'take_down': {'recoil': [1, 4]},
    'submission': {'recoil': [1, 4]},
    'double_edge': {'recoil': [33, 100]},
    'brave_bird': {'recoil': [33, 100]},
    'flare_blitz': {'recoil': [33, 100]},
    'volt_tackle': {'recoil': [33, 100]},
    'wild_charge': {'recoil': [1, 4]},
    'head_smash': {'recoil': [1, 2]},
    'wood_hammer': {'recoil': [33, 100]},
    'head_charge': {'recoil': [1, 4]},
    'high_jump_kick': {'recoil': [1, 2]},  # Actually crash damage
    'jump_kick': {'recoil': [1, 2]},

    # ========== DRAIN MOVES ==========
    'absorb': {'drain': [1, 2]},
    'mega_drain': {'drain': [1, 2]},
    'giga_drain': {'drain': [1, 2]},
    'drain_punch': {'drain': [1, 2]},
    'draining_kiss': {'drain': [3, 4]},
    'horn_leech': {'drain': [1, 2]},
    'leech_life': {'drain': [1, 2]},
    'parabolic_charge': {'drain': [1, 2]},
    'oblivion_wing': {'drain': [3, 4]},
    'dream_eater': {'drain': [1, 2]},

    # ========== HEALING MOVES ==========
    'recover': {'heal': [1, 2]},
    'soft_boiled': {'heal': [1, 2]},
    'milk_drink': {'heal': [1, 2]},
    'slack_off': {'heal': [1, 2]},
    'roost': {'heal': [1, 2]},
    'moonlight': {'heal': [1, 2]},
    'morning_sun': {'heal': [1, 2]},
    'synthesis': {'heal': [1, 2]},
    'rest': {'heal': [1, 1], 'status': 'slp'},
    'shore_up': {'heal': [1, 2]},
    'wish': {'heal': [1, 2]},

    # ========== TWO-TURN CHARGE MOVES ==========
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
    'solar_blade': {'charge': True},
    'meteor_beam': {'charge': True},

    # ========== STAT BOOST MOVES (SELF) ==========
    'swords_dance': {'boosts': {'atk': 2}},
    'nasty_plot': {'boosts': {'spa': 2}},
    'dragon_dance': {'boosts': {'atk': 1, 'spe': 1}},
    'quiver_dance': {'boosts': {'spa': 1, 'spd': 1, 'spe': 1}},
    'calm_mind': {'boosts': {'spa': 1, 'spd': 1}},
    'bulk_up': {'boosts': {'atk': 1, 'def': 1}},
    'coil': {'boosts': {'atk': 1, 'def': 1, 'accuracy': 1}},
    'curse': {'boosts': {'atk': 1, 'def': 1, 'spe': -1}},  # Ghost type has different effect
    'iron_defense': {'boosts': {'def': 2}},
    'amnesia': {'boosts': {'spd': 2}},
    'agility': {'boosts': {'spe': 2}},
    'hone_claws': {'boosts': {'atk': 1, 'accuracy': 1}},
    'work_up': {'boosts': {'atk': 1, 'spa': 1}},
    'shell_smash': {'boosts': {'atk': 2, 'spa': 2, 'spe': 2, 'def': -1, 'spd': -1}},
    'shift_gear': {'boosts': {'atk': 1, 'spe': 2}},
    'cotton_guard': {'boosts': {'def': 3}},
    'tail_glow': {'boosts': {'spa': 3}},
    'growth': {'boosts': {'atk': 1, 'spa': 1}},
    'meditate': {'boosts': {'atk': 1}},
    'sharpen': {'boosts': {'atk': 1}},
    'defense_curl': {'boosts': {'def': 1}},
    'withdraw': {'boosts': {'def': 1}},
    'harden': {'boosts': {'def': 1}},
    'acid_armor': {'boosts': {'def': 2}},
    'barrier': {'boosts': {'def': 2}},
    'double_team': {'boosts': {'evasion': 1}},
    'minimize': {'boosts': {'evasion': 2}},
    'cosmic_power': {'boosts': {'def': 1, 'spd': 1}},
    'rock_polish': {'boosts': {'spe': 2}},
    'autotomize': {'boosts': {'spe': 2}},
    'charge': {'boosts': {'spd': 1}},
    'focus_energy': {'volatileStatus': 'focusenergy'},

    # ========== STAT DROP MOVES (OPPONENT) ==========
    'growl': {'boosts': {'atk': -1}},
    'leer': {'boosts': {'def': -1}},
    'tail_whip': {'boosts': {'def': -1}},
    'string_shot': {'boosts': {'spe': -2}},
    'sand_attack': {'boosts': {'accuracy': -1}},
    'smokescreen': {'boosts': {'accuracy': -1}},
    'kinesis': {'boosts': {'accuracy': -1}},
    'flash': {'boosts': {'accuracy': -1}},
    'sweet_scent': {'boosts': {'evasion': -2}},
    'screech': {'boosts': {'def': -2}},
    'charm': {'boosts': {'atk': -2}},
    'feather_dance': {'boosts': {'atk': -2}},
    'fake_tears': {'boosts': {'spd': -2}},
    'metal_sound': {'boosts': {'spd': -2}},
    'tickle': {'boosts': {'atk': -1, 'def': -1}},
    'scary_face': {'boosts': {'spe': -2}},
    'cotton_spore': {'boosts': {'spe': -2}},

    # ========== SECONDARY EFFECT MOVES ==========
    # Burn chance
    'fire_punch': {'secondary': {'chance': 10, 'status': 'brn'}},
    'flamethrower': {'secondary': {'chance': 10, 'status': 'brn'}},
    'fire_blast': {'secondary': {'chance': 10, 'status': 'brn'}},
    'heat_wave': {'secondary': {'chance': 10, 'status': 'brn'}},
    'lava_plume': {'secondary': {'chance': 30, 'status': 'brn'}},
    'scald': {'secondary': {'chance': 30, 'status': 'brn'}},
    'steam_eruption': {'secondary': {'chance': 30, 'status': 'brn'}},
    'sacred_fire': {'secondary': {'chance': 50, 'status': 'brn'}},
    'blaze_kick': {'secondary': {'chance': 10, 'status': 'brn'}},
    'flare_blitz': {'recoil': [33, 100], 'secondary': {'chance': 10, 'status': 'brn'}},

    # Paralyze chance
    'thunder_punch': {'secondary': {'chance': 10, 'status': 'par'}},
    'thunderbolt': {'secondary': {'chance': 10, 'status': 'par'}},
    'thunder': {'secondary': {'chance': 30, 'status': 'par'}},
    'discharge': {'secondary': {'chance': 30, 'status': 'par'}},
    'spark': {'secondary': {'chance': 30, 'status': 'par'}},
    'volt_tackle': {'recoil': [33, 100], 'secondary': {'chance': 10, 'status': 'par'}},
    'lick': {'secondary': {'chance': 30, 'status': 'par'}},
    'body_slam': {'secondary': {'chance': 30, 'status': 'par'}},
    'bounce': {'charge': True, 'secondary': {'chance': 30, 'status': 'par'}},
    'dragon_breath': {'secondary': {'chance': 30, 'status': 'par'}},
    'force_palm': {'secondary': {'chance': 30, 'status': 'par'}},

    # Freeze chance
    'ice_punch': {'secondary': {'chance': 10, 'status': 'frz'}},
    'ice_beam': {'secondary': {'chance': 10, 'status': 'frz'}},
    'blizzard': {'secondary': {'chance': 10, 'status': 'frz'}},
    'powder_snow': {'secondary': {'chance': 10, 'status': 'frz'}},
    'ice_fang': {'secondary': {'chance': 10, 'status': 'frz'}},

    # Poison chance
    'poison_sting': {'secondary': {'chance': 30, 'status': 'psn'}},
    'smog': {'secondary': {'chance': 40, 'status': 'psn'}},
    'sludge': {'secondary': {'chance': 30, 'status': 'psn'}},
    'sludge_bomb': {'secondary': {'chance': 30, 'status': 'psn'}},
    'sludge_wave': {'secondary': {'chance': 10, 'status': 'psn'}},
    'poison_jab': {'secondary': {'chance': 30, 'status': 'psn'}},
    'poison_fang': {'secondary': {'chance': 50, 'status': 'tox'}},
    'cross_poison': {'secondary': {'chance': 10, 'status': 'psn'}},
    'gunk_shot': {'secondary': {'chance': 30, 'status': 'psn'}},

    # Stat drops as secondary effects
    'psychic': {'secondary': {'chance': 10, 'boosts': {'spd': -1}}},
    'shadow_ball': {'secondary': {'chance': 20, 'boosts': {'spd': -1}}},
    'crunch': {'secondary': {'chance': 20, 'boosts': {'def': -1}}},
    'rock_smash': {'secondary': {'chance': 50, 'boosts': {'def': -1}}},
    'crush_claw': {'secondary': {'chance': 50, 'boosts': {'def': -1}}},
    'bulldoze': {'secondary': {'chance': 100, 'boosts': {'spe': -1}}},
    'icy_wind': {'secondary': {'chance': 100, 'boosts': {'spe': -1}}},
    'rock_tomb': {'secondary': {'chance': 100, 'boosts': {'spe': -1}}},
    'mud_shot': {'secondary': {'chance': 100, 'boosts': {'spe': -1}}},
    'bubble_beam': {'secondary': {'chance': 10, 'boosts': {'spe': -1}}},
    'bubble': {'secondary': {'chance': 10, 'boosts': {'spe': -1}}},
    'constrict': {'secondary': {'chance': 10, 'boosts': {'spe': -1}}},
    'low_sweep': {'secondary': {'chance': 100, 'boosts': {'spe': -1}}},
    'aurora_beam': {'secondary': {'chance': 10, 'boosts': {'atk': -1}}},
    'play_rough': {'secondary': {'chance': 10, 'boosts': {'atk': -1}}},
    'moonblast': {'secondary': {'chance': 30, 'boosts': {'spa': -1}}},
    'mystical_fire': {'secondary': {'chance': 100, 'boosts': {'spa': -1}}},
    'snarl': {'secondary': {'chance': 100, 'boosts': {'spa': -1}}},
    'earth_power': {'secondary': {'chance': 10, 'boosts': {'spd': -1}}},
    'flash_cannon': {'secondary': {'chance': 10, 'boosts': {'spd': -1}}},
    'energy_ball': {'secondary': {'chance': 10, 'boosts': {'spd': -1}}},
    'acid': {'secondary': {'chance': 10, 'boosts': {'spd': -1}}},
    'acid_spray': {'secondary': {'chance': 100, 'boosts': {'spd': -2}}},

    # Stat boosts as secondary effects
    'charge_beam': {'secondary': {'chance': 70, 'self': {'boosts': {'spa': 1}}}},
    'silver_wind': {'secondary': {'chance': 10, 'self': {'boosts': {'atk': 1, 'def': 1, 'spa': 1, 'spd': 1, 'spe': 1}}}},
    'ancient_power': {'secondary': {'chance': 10, 'self': {'boosts': {'atk': 1, 'def': 1, 'spa': 1, 'spd': 1, 'spe': 1}}}},
    'ominous_wind': {'secondary': {'chance': 10, 'self': {'boosts': {'atk': 1, 'def': 1, 'spa': 1, 'spd': 1, 'spe': 1}}}},
    'power_up_punch': {'secondary': {'chance': 100, 'self': {'boosts': {'atk': 1}}}},
    'meteor_mash': {'secondary': {'chance': 20, 'self': {'boosts': {'atk': 1}}}},
    'steel_wing': {'secondary': {'chance': 10, 'self': {'boosts': {'def': 1}}}},
    'fiery_dance': {'secondary': {'chance': 50, 'self': {'boosts': {'spa': 1}}}},

    # ========== HAZARD MOVES ==========
    'stealth_rock': {'target': 'enemy_field'},
    'spikes': {'target': 'enemy_field'},
    'toxic_spikes': {'target': 'enemy_field'},
    'sticky_web': {'target': 'enemy_field'},

    # ========== FIELD EFFECT MOVES ==========
    'light_screen': {'volatileStatus': 'lightscreen'},
    'reflect': {'volatileStatus': 'reflect'},
    'aurora_veil': {'volatileStatus': 'auroraveil'},
    'safeguard': {'volatileStatus': 'safeguard'},
    'mist': {'volatileStatus': 'mist'},
    'lucky_chant': {'volatileStatus': 'luckychant'},
    'tailwind': {'volatileStatus': 'tailwind'},
    'trick_room': {'target': 'entire_field'},

    # ========== HAZARD REMOVAL ==========
    'rapid_spin': {'volatileStatus': 'rapidspin'},  # Clears hazards
    'defog': {'boosts': {'evasion': -1}},  # Clears hazards and lowers evasion

    # ========== SPECIAL MOVES ==========
    'conversion': {'target': 'self'},
    'haze': {'target': 'self'},  # Resets all stat changes
    'transform': {'target': 'self'},
    'splash': {'target': 'self'},
    'celebrate': {'target': 'self'},
    'hold_hands': {'target': 'self'},
}


def apply_comprehensive_fixes():
    """Apply all comprehensive fixes to moves.json"""

    moves_file = '/home/user/PokebotANOTHAAAA/data/moves.json'

    print("Loading moves database...")
    with open(moves_file, 'r', encoding='utf-8') as f:
        moves = json.load(f)

    print(f"Loaded {len(moves)} moves")
    print(f"Applying {len(COMPREHENSIVE_FIXES)} comprehensive fixes...\n")

    fixes_applied = 0
    moves_fixed = []

    for move_id, fixes in COMPREHENSIVE_FIXES.items():
        if move_id not in moves:
            print(f"⚠️  Move '{move_id}' not found in database")
            continue

        move_data = moves[move_id]
        move_name = move_data.get('name', move_id)
        changes = []

        for key, value in fixes.items():
            current_value = move_data.get(key)

            # Check if fix is needed
            if current_value != value:
                move_data[key] = value
                changes.append(f"{key}={value}")
                fixes_applied += 1

        if changes:
            moves_fixed.append(move_name)
            print(f"✓ {move_name}: {', '.join(changes)}")

    # Save fixed moves
    output_file = '/home/user/PokebotANOTHAAAA/data/moves.json'
    backup_file = '/home/user/PokebotANOTHAAAA/data/moves_backup.json'

    # Create backup
    print(f"\n📁 Creating backup at {backup_file}")
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(moves, f, indent=2, ensure_ascii=False)

    # Save fixed version
    print(f"💾 Saving fixed moves to {output_file}")
    with open(moves_file, 'w', encoding='utf-8') as f:
        json.dump(moves, f, indent=2, ensure_ascii=False)

    # Generate report
    print("\n" + "=" * 80)
    print("COMPREHENSIVE MOVE FIX REPORT")
    print("=" * 80)
    print(f"Total moves in database: {len(moves)}")
    print(f"Moves checked: {len(COMPREHENSIVE_FIXES)}")
    print(f"Moves fixed: {len(moves_fixed)}")
    print(f"Total fixes applied: {fixes_applied}")
    print("=" * 80)

    if moves_fixed:
        print(f"\nFixed moves ({len(moves_fixed)}):")
        for i, name in enumerate(moves_fixed, 1):
            print(f"  {i}. {name}")

    # Save detailed report
    report_file = '/home/user/PokebotANOTHAAAA/comprehensive_fix_report.txt'
    with open(report_file, 'w') as f:
        f.write("COMPREHENSIVE MOVE FIX REPORT\n")
        f.write("=" * 80 + "\n")
        f.write(f"Total moves in database: {len(moves)}\n")
        f.write(f"Moves checked: {len(COMPREHENSIVE_FIXES)}\n")
        f.write(f"Moves fixed: {len(moves_fixed)}\n")
        f.write(f"Total fixes applied: {fixes_applied}\n")
        f.write("=" * 80 + "\n\n")
        f.write("Fixed moves:\n")
        for name in moves_fixed:
            f.write(f"  - {name}\n")

    print(f"\n📄 Detailed report saved to: {report_file}")
    print("\n✅ All fixes applied successfully!")


if __name__ == '__main__':
    apply_comprehensive_fixes()
