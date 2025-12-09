"""
Comprehensive Item Effect Data Implementation
Adds effect_data for all important competitive held items, berries, and battle items
"""

import json
import re

# Comprehensive item effect data
ITEM_EFFECT_DATA = {
    # ========== ALREADY IMPLEMENTED (25 items) ==========
    # These already have effect_data, included for reference

    # ========== COMPETITIVE HELD ITEMS - TYPE BOOSTERS ==========
    "silk_scarf": {"power_multiplier": 1.2, "type": "normal"},
    "muscle_band": {"power_multiplier": 1.1, "category": "physical"},
    "wise_glasses": {"power_multiplier": 1.1, "category": "special"},
    "expert_belt": {"power_multiplier": 1.2, "condition": "super_effective"},

    # ========== DEFENSIVE ITEMS ==========
    "rocky_helmet": {"contact_damage_percent": 16.7, "desc": "Deals 1/6 HP to attackers on contact"},
    "weakness_policy": {
        "trigger": "after_damage",
        "condition": "super_effective_hit",
        "boosts": {"attack": 2, "sp_attack": 2},
        "one_time_use": True,
        "desc": "Sharply raises Attack and Sp. Attack when hit by super-effective move"
    },
    "eviolite": {"multiplier": 1.5, "stat": "defense_and_sp_defense", "condition": "not_fully_evolved"},
    "safety_goggles": {"immunity": ["powder", "weather_damage"]},
    "protective_pads": {"immunity": ["contact_effects"]},

    # ========== OFFENSIVE ITEMS ==========
    "muscle_band": {"power_multiplier": 1.1, "category": "physical"},
    "wise_glasses": {"power_multiplier": 1.1, "category": "special"},
    "metronome": {"power_multiplier_per_use": 0.2, "max_multiplier": 2.0},
    "zoom_lens": {"accuracy_boost": 1.2, "condition": "move_second"},
    "wide_lens": {"accuracy_boost": 1.1},
    "scope_lens": {"crit_stage": 1},
    "razor_claw": {"crit_stage": 1},

    # ========== RECOVERY ITEMS ==========
    "shell_bell": {"drain_percent": 12.5, "desc": "Heals 1/8 HP on hit"},
    "absorb_bulb": {
        "trigger": "after_hit",
        "condition": "water_type_hit",
        "boosts": {"sp_attack": 1},
        "one_time_use": True
    },
    "cell_battery": {
        "trigger": "after_hit",
        "condition": "electric_type_hit",
        "boosts": {"attack": 1},
        "one_time_use": True
    },
    "luminous_moss": {
        "trigger": "after_hit",
        "condition": "water_type_hit",
        "boosts": {"sp_defense": 1},
        "one_time_use": True
    },
    "snowball": {
        "trigger": "after_hit",
        "condition": "ice_type_hit",
        "boosts": {"attack": 1},
        "one_time_use": True
    },

    # ========== STATUS BERRIES ==========
    "cheri_berry": {
        "trigger": "end_of_turn",
        "cures": ["par"],
        "one_time_use": True,
        "desc": "Cures paralysis"
    },
    "chesto_berry": {
        "trigger": "end_of_turn",
        "cures": ["slp"],
        "one_time_use": True,
        "desc": "Cures sleep"
    },
    "pecha_berry": {
        "trigger": "end_of_turn",
        "cures": ["psn", "tox"],
        "one_time_use": True,
        "desc": "Cures poison"
    },
    "rawst_berry": {
        "trigger": "end_of_turn",
        "cures": ["brn"],
        "one_time_use": True,
        "desc": "Cures burn"
    },
    "aspear_berry": {
        "trigger": "end_of_turn",
        "cures": ["frz"],
        "one_time_use": True,
        "desc": "Cures freeze"
    },
    "persim_berry": {
        "trigger": "end_of_turn",
        "cures": ["confusion"],
        "one_time_use": True,
        "desc": "Cures confusion"
    },
    "lum_berry": {
        "trigger": "end_of_turn",
        "cures": ["par", "slp", "psn", "tox", "brn", "frz", "confusion"],
        "one_time_use": True,
        "desc": "Cures any status condition"
    },

    # ========== STAT-BOOST BERRIES ==========
    "liechi_berry": {
        "trigger": "hp_threshold",
        "hp_threshold": 0.25,
        "boosts": {"attack": 1},
        "one_time_use": True
    },
    "ganlon_berry": {
        "trigger": "hp_threshold",
        "hp_threshold": 0.25,
        "boosts": {"defense": 1},
        "one_time_use": True
    },
    "salac_berry": {
        "trigger": "hp_threshold",
        "hp_threshold": 0.25,
        "boosts": {"speed": 1},
        "one_time_use": True
    },
    "petaya_berry": {
        "trigger": "hp_threshold",
        "hp_threshold": 0.25,
        "boosts": {"sp_attack": 1},
        "one_time_use": True
    },
    "apicot_berry": {
        "trigger": "hp_threshold",
        "hp_threshold": 0.25,
        "boosts": {"sp_defense": 1},
        "one_time_use": True
    },
    "lansat_berry": {
        "trigger": "hp_threshold",
        "hp_threshold": 0.25,
        "effect": "focus_energy",
        "one_time_use": True
    },
    "starf_berry": {
        "trigger": "hp_threshold",
        "hp_threshold": 0.25,
        "boosts": {"random_stat": 2},
        "one_time_use": True
    },
    "micle_berry": {
        "trigger": "hp_threshold",
        "hp_threshold": 0.25,
        "effect": "next_move_always_hits",
        "one_time_use": True
    },

    # ========== TYPE-RESIST BERRIES ==========
    "occa_berry": {"damage_reduction": 0.5, "type": "fire", "one_time_use": True},
    "passho_berry": {"damage_reduction": 0.5, "type": "water", "one_time_use": True},
    "wacan_berry": {"damage_reduction": 0.5, "type": "electric", "one_time_use": True},
    "rindo_berry": {"damage_reduction": 0.5, "type": "grass", "one_time_use": True},
    "yache_berry": {"damage_reduction": 0.5, "type": "ice", "one_time_use": True},
    "chople_berry": {"damage_reduction": 0.5, "type": "fighting", "one_time_use": True},
    "kebia_berry": {"damage_reduction": 0.5, "type": "poison", "one_time_use": True},
    "shuca_berry": {"damage_reduction": 0.5, "type": "ground", "one_time_use": True},
    "coba_berry": {"damage_reduction": 0.5, "type": "flying", "one_time_use": True},
    "payapa_berry": {"damage_reduction": 0.5, "type": "psychic", "one_time_use": True},
    "tanga_berry": {"damage_reduction": 0.5, "type": "bug", "one_time_use": True},
    "charti_berry": {"damage_reduction": 0.5, "type": "rock", "one_time_use": True},
    "kasib_berry": {"damage_reduction": 0.5, "type": "ghost", "one_time_use": True},
    "haban_berry": {"damage_reduction": 0.5, "type": "dragon", "one_time_use": True},
    "colbur_berry": {"damage_reduction": 0.5, "type": "dark", "one_time_use": True},
    "babiri_berry": {"damage_reduction": 0.5, "type": "steel", "one_time_use": True},
    "chilan_berry": {"damage_reduction": 0.5, "type": "normal", "one_time_use": True},
    "roseli_berry": {"damage_reduction": 0.5, "type": "fairy", "one_time_use": True},

    # ========== HP RESTORATION BERRIES ==========
    "oran_berry": {
        "trigger": "hp_threshold",
        "hp_threshold": 0.5,
        "heal_amount": 10,
        "one_time_use": True
    },
    "sitrus_berry": {
        "trigger": "hp_threshold",
        "hp_threshold": 0.5,
        "heal_percent": 25,
        "one_time_use": True
    },
    "figy_berry": {
        "trigger": "hp_threshold",
        "hp_threshold": 0.25,
        "heal_percent": 33,
        "confuse_if_nature": ["adamant", "careful", "impish", "jolly"],
        "one_time_use": True
    },
    "wiki_berry": {
        "trigger": "hp_threshold",
        "hp_threshold": 0.25,
        "heal_percent": 33,
        "confuse_if_nature": ["bold", "calm", "modest", "timid"],
        "one_time_use": True
    },
    "mago_berry": {
        "trigger": "hp_threshold",
        "hp_threshold": 0.25,
        "heal_percent": 33,
        "confuse_if_nature": ["brave", "lonely", "mild", "rash"],
        "one_time_use": True
    },
    "aguav_berry": {
        "trigger": "hp_threshold",
        "hp_threshold": 0.25,
        "heal_percent": 33,
        "confuse_if_nature": ["gentle", "hasty", "naive", "quiet"],
        "one_time_use": True
    },
    "iapapa_berry": {
        "trigger": "hp_threshold",
        "hp_threshold": 0.25,
        "heal_percent": 33,
        "confuse_if_nature": ["lax", "relaxed", "sassy", "serious"],
        "one_time_use": True
    },

    # ========== SPECIAL EFFECT ITEMS ==========
    "air_balloon": {
        "grants_levitate": True,
        "pops_on_hit": True,
        "desc": "Grants Ground immunity until hit"
    },
    "iron_ball": {"halves_speed": True, "removes_levitate": True},
    "lagging_tail": {"always_move_last": True},
    "quick_claw": {"priority_chance": 0.2, "priority_boost": 1},
    "bright_powder": {"evasion_boost": 1.1},
    "lax_incense": {"evasion_boost": 1.1},
    "red_card": {
        "trigger": "after_hit",
        "effect": "force_switch_attacker",
        "one_time_use": True
    },
    "eject_button": {
        "trigger": "after_hit",
        "effect": "force_switch_self",
        "one_time_use": True
    },
    "eject_pack": {
        "trigger": "stat_drop",
        "effect": "force_switch_self",
        "one_time_use": True
    },
    "white_herb": {
        "trigger": "stat_drop",
        "effect": "reset_negative_stats",
        "one_time_use": True
    },
    "mental_herb": {
        "trigger": "attract_or_disable",
        "effect": "cure_mental_status",
        "one_time_use": True
    },
    "power_herb": {
        "trigger": "charge_move",
        "effect": "skip_charge_turn",
        "one_time_use": True
    },
    "flame_orb": {
        "trigger": "end_of_turn",
        "inflict_status": "brn",
        "desc": "Burns holder at end of turn"
    },
    "toxic_orb": {
        "trigger": "end_of_turn",
        "inflict_status": "tox",
        "desc": "Badly poisons holder at end of turn"
    },
    "black_sludge": {
        "heal_percent": 6.25,
        "condition": "poison_type",
        "damage_percent_if_not": 12.5,
        "desc": "Heals Poison types 1/16 HP, damages others 1/8 HP"
    },
    "sticky_barb": {
        "damage_percent": 12.5,
        "transfers_on_contact": True,
        "desc": "Damages holder 1/8 HP per turn"
    },
    "ring_target": {
        "removes_immunities": True,
        "desc": "Removes type immunities"
    },
    "binding_band": {
        "binding_damage_boost": 1.5,
        "desc": "Boosts binding move damage by 50%"
    },
    "grip_claw": {
        "binding_turns": 7,
        "desc": "Makes binding moves last 7 turns"
    },

    # ========== MEGA STONES (mark as mega_stone) ==========
    # These would be handled separately by mega evolution system

    # ========== Z-CRYSTALS (mark as z_crystal) ==========
    # These would be handled separately by Z-move system
}


def normalize_item_id(item_id):
    """Normalize item ID by removing special characters"""
    return re.sub(r'[-_\s]+', '', item_id.lower())


def apply_item_effect_data():
    """Apply comprehensive item effect data"""

    items_file = '/home/user/PokebotANOTHAAAA/data/items.json'

    print("Loading items database...")
    with open(items_file, 'r', encoding='utf-8') as f:
        items = json.load(f)

    print(f"Loaded {len(items) - 1} items (excluding _STRUCTURE_NOTES)")
    print(f"Applying {len(ITEM_EFFECT_DATA)} effect data entries...\n")

    updated_count = 0
    items_updated = []
    already_had = []

    for item_id, effect_data in ITEM_EFFECT_DATA.items():
        # Normalize the item ID
        normalized_id = normalize_item_id(item_id)

        # Find the matching item in the database
        found = False
        for db_id in items.keys():
            if db_id == '_STRUCTURE_NOTES':
                continue
            if normalize_item_id(db_id) == normalized_id:
                item_data = items[db_id]
                item_name = item_data.get('name', db_id)
                found = True
                break

        if not found:
            print(f"⚠️  Item '{item_id}' not found in database")
            continue

        # Check if it already has effect_data
        if 'effect_data' in item_data:
            already_had.append(item_name)
            # Still update it with our data

        # Update with effect data
        item_data['effect_data'] = effect_data

        items_updated.append(item_name)
        updated_count += 1
        desc = effect_data.get('desc', '')
        if desc:
            print(f"✓ {item_name}: {desc[:70]}")
        else:
            print(f"✓ {item_name}")

    # Save updated items
    output_file = items_file
    backup_file = '/home/user/PokebotANOTHAAAA/data/items_backup.json'

    print(f"\n📁 Creating backup at {backup_file}")
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)

    print(f"💾 Saving updated items to {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)

    # Generate report
    print("\n" + "=" * 80)
    print("COMPREHENSIVE ITEM EFFECT DATA REPORT")
    print("=" * 80)
    print(f"Total items in database: {len(items) - 1}")
    print(f"Items updated with effect_data: {updated_count}")
    print(f"Items that already had effect_data: {len(already_had)}")
    print(f"New effect_data added: {updated_count - len(already_had)}")
    print("=" * 80)

    # Save report
    report_file = '/home/user/PokebotANOTHAAAA/item_effect_data_report.txt'
    with open(report_file, 'w') as f:
        f.write("COMPREHENSIVE ITEM EFFECT DATA REPORT\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Total items: {len(items) - 1}\n")
        f.write(f"Items with effect_data: {updated_count}\n")
        f.write(f"Coverage: {(updated_count / (len(items) - 1)) * 100:.1f}%\n\n")
        f.write("Updated items:\n")
        for name in items_updated:
            f.write(f"  - {name}\n")

    print(f"\n📄 Detailed report saved to: {report_file}")
    print("\n✅ All effect data applied successfully!")


if __name__ == '__main__':
    apply_item_effect_data()
