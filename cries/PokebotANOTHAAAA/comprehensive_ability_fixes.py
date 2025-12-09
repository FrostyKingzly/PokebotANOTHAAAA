"""
Comprehensive Ability Implementation
Adds proper implementations for all major Pokemon abilities
"""

import json

# Comprehensive ability implementations
# Format: ability_id: {implementation data}

ABILITY_IMPLEMENTATIONS = {
    # ========== WEATHER SETTERS ==========
    "drought": {
        "events": ["Start"],
        "effect": "weather",
        "weather": "sun",
        "duration": 5,
        "desc": "On switch-in, the weather becomes sunny for 5 turns."
    },
    "drizzle": {
        "events": ["Start"],
        "effect": "weather",
        "weather": "rain",
        "duration": 5,
        "desc": "On switch-in, the weather becomes rainy for 5 turns."
    },
    "sand_stream": {
        "events": ["Start"],
        "effect": "weather",
        "weather": "sandstorm",
        "duration": 5,
        "desc": "On switch-in, the weather becomes sandstorm for 5 turns."
    },
    "snow_warning": {
        "events": ["Start"],
        "effect": "weather",
        "weather": "snow",
        "duration": 5,
        "desc": "On switch-in, the weather becomes snow for 5 turns."
    },

    # ========== TERRAIN SETTERS ==========
    "electric_surge": {
        "events": ["Start"],
        "effect": "terrain",
        "terrain": "electric",
        "duration": 5,
        "desc": "On switch-in, the terrain becomes Electric Terrain for 5 turns."
    },
    "grassy_surge": {
        "events": ["Start"],
        "effect": "terrain",
        "terrain": "grassy",
        "duration": 5,
        "desc": "On switch-in, the terrain becomes Grassy Terrain for 5 turns."
    },
    "psychic_surge": {
        "events": ["Start"],
        "effect": "terrain",
        "terrain": "psychic",
        "duration": 5,
        "desc": "On switch-in, the terrain becomes Psychic Terrain for 5 turns."
    },
    "misty_surge": {
        "events": ["Start"],
        "effect": "terrain",
        "terrain": "misty",
        "duration": 5,
        "desc": "On switch-in, the terrain becomes Misty Terrain for 5 turns."
    },

    # ========== STAT MODIFICATION ABILITIES ==========
    "intimidate": {
        "events": ["Start"],
        "effect": "stat_mod",
        "target": "opponents",
        "boosts": {"atk": -1},
        "desc": "On switch-in, lowers the opponent's Attack by 1 stage."
    },
    "download": {
        "events": ["Start"],
        "effect": "stat_mod",
        "target": "self",
        "conditional": "compare_defense",
        "boosts": {"atk": 1, "spa": 1},  # Chooses based on opponent's defenses
        "desc": "On switch-in, raises Attack or Sp. Attack by 1 stage based on opponent's lower defense."
    },
    "defiant": {
        "events": ["StatDown"],
        "effect": "stat_mod",
        "target": "self",
        "boosts": {"atk": 2},
        "desc": "When a stat is lowered by an opponent, raises Attack by 2 stages."
    },
    "competitive": {
        "events": ["StatDown"],
        "effect": "stat_mod",
        "target": "self",
        "boosts": {"spa": 2},
        "desc": "When a stat is lowered by an opponent, raises Sp. Attack by 2 stages."
    },

    # ========== TYPE DAMAGE BOOST ABILITIES ==========
    "blaze": {
        "effect": "type_boost",
        "type": "fire",
        "multiplier": 1.5,
        "condition": "hp_below_third",
        "desc": "When HP is below 1/3, Fire-type moves have 1.5x power."
    },
    "overgrow": {
        "effect": "type_boost",
        "type": "grass",
        "multiplier": 1.5,
        "condition": "hp_below_third",
        "desc": "When HP is below 1/3, Grass-type moves have 1.5x power."
    },
    "torrent": {
        "effect": "type_boost",
        "type": "water",
        "multiplier": 1.5,
        "condition": "hp_below_third",
        "desc": "When HP is below 1/3, Water-type moves have 1.5x power."
    },
    "swarm": {
        "effect": "type_boost",
        "type": "bug",
        "multiplier": 1.5,
        "condition": "hp_below_third",
        "desc": "When HP is below 1/3, Bug-type moves have 1.5x power."
    },

    # ========== IMMUNITY ABILITIES ==========
    "levitate": {
        "effect": "immunity",
        "immune_to": ["ground"],
        "desc": "Grants immunity to Ground-type moves."
    },
    "water_absorb": {
        "effect": "immunity",
        "immune_to": ["water"],
        "heal_on_hit": 0.25,
        "desc": "Grants immunity to Water-type moves. Heals 25% HP when hit by Water moves."
    },
    "volt_absorb": {
        "effect": "immunity",
        "immune_to": ["electric"],
        "heal_on_hit": 0.25,
        "desc": "Grants immunity to Electric-type moves. Heals 25% HP when hit by Electric moves."
    },
    "flash_fire": {
        "effect": "immunity",
        "immune_to": ["fire"],
        "boost_on_hit": {"spa": 1.5},
        "desc": "Grants immunity to Fire-type moves. When hit by Fire moves, boosts Fire-type move power by 50%."
    },
    "sap_sipper": {
        "effect": "immunity",
        "immune_to": ["grass"],
        "boost_on_hit": {"atk": 1},
        "desc": "Grants immunity to Grass-type moves. When hit by Grass moves, raises Attack by 1 stage."
    },
    "lightning_rod": {
        "effect": "immunity",
        "immune_to": ["electric"],
        "boost_on_hit": {"spa": 1},
        "redirect": "electric",
        "desc": "Draws Electric-type moves to this Pokemon and grants immunity. Raises Sp. Attack by 1 stage when hit."
    },
    "storm_drain": {
        "effect": "immunity",
        "immune_to": ["water"],
        "boost_on_hit": {"spa": 1},
        "redirect": "water",
        "desc": "Draws Water-type moves to this Pokemon and grants immunity. Raises Sp. Attack by 1 stage when hit."
    },
    "motor_drive": {
        "effect": "immunity",
        "immune_to": ["electric"],
        "boost_on_hit": {"spe": 1},
        "desc": "Grants immunity to Electric-type moves. When hit by Electric moves, raises Speed by 1 stage."
    },
    "wonder_guard": {
        "effect": "immunity",
        "immune_to": "not_super_effective",
        "desc": "Only super-effective moves can hit this Pokemon."
    },

    # ========== STATUS IMMUNITY ==========
    "limber": {
        "effect": "status_immunity",
        "immune_status": ["par"],
        "desc": "Cannot be paralyzed."
    },
    "water_veil": {
        "effect": "status_immunity",
        "immune_status": ["brn"],
        "desc": "Cannot be burned."
    },
    "insomnia": {
        "effect": "status_immunity",
        "immune_status": ["slp"],
        "desc": "Cannot be put to sleep."
    },
    "vital_spirit": {
        "effect": "status_immunity",
        "immune_status": ["slp"],
        "desc": "Cannot be put to sleep."
    },
    "immunity": {
        "effect": "status_immunity",
        "immune_status": ["psn", "tox"],
        "desc": "Cannot be poisoned."
    },
    "magma_armor": {
        "effect": "status_immunity",
        "immune_status": ["frz"],
        "desc": "Cannot be frozen."
    },
    "own_tempo": {
        "effect": "status_immunity",
        "immune_status": ["confusion"],
        "desc": "Cannot be confused."
    },
    "oblivious": {
        "effect": "status_immunity",
        "immune_status": ["infatuation", "taunt"],
        "desc": "Cannot be infatuated or taunted."
    },

    # ========== STAT PREVENTION ==========
    "clear_body": {
        "effect": "prevent_stat_loss",
        "desc": "Prevents other Pokemon from lowering this Pokemon's stats."
    },
    "white_smoke": {
        "effect": "prevent_stat_loss",
        "desc": "Prevents other Pokemon from lowering this Pokemon's stats."
    },
    "hyper_cutter": {
        "effect": "prevent_stat_loss",
        "stats": ["atk"],
        "desc": "Prevents other Pokemon from lowering this Pokemon's Attack stat."
    },
    "keen_eye": {
        "effect": "prevent_stat_loss",
        "stats": ["accuracy"],
        "desc": "Prevents other Pokemon from lowering this Pokemon's accuracy."
    },

    # ========== WEATHER ABILITIES ==========
    "swift_swim": {
        "effect": "weather_boost",
        "weather": "rain",
        "stat": "spe",
        "multiplier": 2.0,
        "desc": "Doubles Speed in rain."
    },
    "chlorophyll": {
        "effect": "weather_boost",
        "weather": "sun",
        "stat": "spe",
        "multiplier": 2.0,
        "desc": "Doubles Speed in harsh sunlight."
    },
    "sand_rush": {
        "effect": "weather_boost",
        "weather": "sandstorm",
        "stat": "spe",
        "multiplier": 2.0,
        "desc": "Doubles Speed in sandstorm."
    },
    "slush_rush": {
        "effect": "weather_boost",
        "weather": "snow",
        "stat": "spe",
        "multiplier": 2.0,
        "desc": "Doubles Speed in snow."
    },
    "solar_power": {
        "effect": "weather_boost",
        "weather": "sun",
        "stat": "spa",
        "multiplier": 1.5,
        "damage": 0.125,
        "desc": "In harsh sunlight, Sp. Attack is 1.5x but takes 1/8 HP damage per turn."
    },
    "rain_dish": {
        "effect": "weather_heal",
        "weather": "rain",
        "heal": 0.0625,
        "desc": "Heals 1/16 HP each turn in rain."
    },
    "ice_body": {
        "effect": "weather_heal",
        "weather": "snow",
        "heal": 0.0625,
        "desc": "Heals 1/16 HP each turn in snow."
    },
    "dry_skin": {
        "effect": "weather_heal",
        "weather": "rain",
        "heal": 0.125,
        "damage_weather": {"sun": 0.125},
        "desc": "Heals 1/8 HP in rain, loses 1/8 HP in sun."
    },
    "sand_force": {
        "effect": "weather_boost",
        "weather": "sandstorm",
        "types": ["rock", "ground", "steel"],
        "multiplier": 1.3,
        "desc": "In sandstorm, Rock/Ground/Steel moves have 1.3x power and immune to sandstorm damage."
    },

    # ========== CONTACT ABILITIES ==========
    "static": {
        "effect": "contact",
        "status": "par",
        "chance": 30,
        "desc": "30% chance to paralyze attackers that make contact."
    },
    "flame_body": {
        "effect": "contact",
        "status": "brn",
        "chance": 30,
        "desc": "30% chance to burn attackers that make contact."
    },
    "poison_point": {
        "effect": "contact",
        "status": "psn",
        "chance": 30,
        "desc": "30% chance to poison attackers that make contact."
    },
    "effect_spore": {
        "effect": "contact",
        "status": ["psn", "par", "slp"],
        "chance": 30,
        "desc": "30% chance to poison, paralyze, or sleep attackers that make contact."
    },
    "rough_skin": {
        "effect": "contact",
        "damage": 0.125,
        "desc": "Attackers that make contact lose 1/8 of their max HP."
    },
    "iron_barbs": {
        "effect": "contact",
        "damage": 0.125,
        "desc": "Attackers that make contact lose 1/8 of their max HP."
    },

    # ========== ACCURACY ABILITIES ==========
    "compound_eyes": {
        "effect": "accuracy_boost",
        "multiplier": 1.3,
        "desc": "Increases move accuracy by 30%."
    },
    "hustle": {
        "effect": "stat_mod",
        "stat": "atk",
        "multiplier": 1.5,
        "accuracy_penalty": 0.8,
        "desc": "Increases Attack by 50% but lowers accuracy of physical moves to 80%."
    },
    "no_guard": {
        "effect": "accuracy_override",
        "accuracy": "always",
        "desc": "All moves used by or against this Pokemon always hit."
    },

    # ========== PRIORITY ABILITIES ==========
    "prankster": {
        "effect": "priority_boost",
        "category": "status",
        "priority": 1,
        "desc": "Status moves have +1 priority."
    },
    "gale_wings": {
        "effect": "priority_boost",
        "type": "flying",
        "priority": 1,
        "condition": "full_hp",
        "desc": "At full HP, Flying-type moves have +1 priority."
    },

    # ========== HEALING ABILITIES ==========
    "regenerator": {
        "events": ["SwitchOut"],
        "effect": "heal",
        "heal": 0.33,
        "desc": "Heals 1/3 HP when switching out."
    },

    # ========== DAMAGE MODIFICATION ==========
    "thick_fat": {
        "effect": "damage_reduction",
        "types": ["fire", "ice"],
        "multiplier": 0.5,
        "desc": "Halves damage from Fire and Ice-type moves."
    },
    "filter": {
        "effect": "damage_reduction",
        "condition": "super_effective",
        "multiplier": 0.75,
        "desc": "Reduces damage from super-effective moves by 25%."
    },
    "solid_rock": {
        "effect": "damage_reduction",
        "condition": "super_effective",
        "multiplier": 0.75,
        "desc": "Reduces damage from super-effective moves by 25%."
    },
    "multiscale": {
        "effect": "damage_reduction",
        "condition": "full_hp",
        "multiplier": 0.5,
        "desc": "Reduces damage by 50% when at full HP."
    },
    "marvel_scale": {
        "effect": "stat_boost",
        "stat": "def",
        "multiplier": 1.5,
        "condition": "has_status",
        "desc": "Defense is 1.5x when Pokemon has a major status condition."
    },
    "guts": {
        "effect": "stat_boost",
        "stat": "atk",
        "multiplier": 1.5,
        "condition": "has_status",
        "desc": "Attack is 1.5x when Pokemon has a major status condition."
    },

    # ========== ITEM ABILITIES ==========
    "unburden": {
        "effect": "stat_boost",
        "stat": "spe",
        "multiplier": 2.0,
        "condition": "consumed_item",
        "desc": "Speed doubles after consuming a held item."
    },
    "sticky_hold": {
        "effect": "item_protection",
        "desc": "Prevents the Pokemon's item from being removed by other Pokemon."
    },
    "magician": {
        "effect": "item_steal",
        "desc": "Steals the target's held item when hitting with an attack."
    },

    # ========== CRITICAL HIT ABILITIES ==========
    "super_luck": {
        "effect": "crit_boost",
        "stages": 1,
        "desc": "Increases critical hit ratio by 1 stage."
    },
    "sniper": {
        "effect": "crit_power",
        "multiplier": 2.25,
        "desc": "Critical hits deal 2.25x damage instead of 1.5x."
    },
    "battle_armor": {
        "effect": "crit_immunity",
        "desc": "Protects the Pokemon from critical hits."
    },
    "shell_armor": {
        "effect": "crit_immunity",
        "desc": "Protects the Pokemon from critical hits."
    },

    # ========== SPECIAL MECHANICS ==========
    "disguise": {
        "effect": "block_first_hit",
        "damage": 0.125,
        "desc": "Blocks the first damaging move, taking 1/8 max HP as damage instead."
    },
    "sturdy": {
        "effect": "survive_ohko",
        "desc": "Cannot be KO'd in one hit from full HP. Immune to OHKO moves."
    },
    "magic_bounce": {
        "effect": "reflect_status",
        "desc": "Reflects status moves and entry hazards back at the user."
    },
    "adaptability": {
        "effect": "stab_boost",
        "multiplier": 2.0,
        "desc": "STAB bonus is 2x instead of 1.5x."
    },
    "technician": {
        "effect": "power_boost",
        "condition": "power_60_or_less",
        "multiplier": 1.5,
        "desc": "Moves with 60 power or less have 1.5x power."
    },
    "skill_link": {
        "effect": "multihit_max",
        "desc": "Multi-hit moves always hit the maximum number of times."
    },
    "sheer_force": {
        "effect": "remove_secondary",
        "power_boost": 1.3,
        "desc": "Removes secondary effects from moves but increases their power by 30%."
    },
    "serene_grace": {
        "effect": "secondary_boost",
        "multiplier": 2.0,
        "desc": "Doubles the chance of moves' secondary effects occurring."
    },

    # ========== TRANSFORMATION ==========
    "trace": {
        "events": ["Start"],
        "effect": "copy_ability",
        "desc": "Copies the ability of an opponent."
    },
    "imposter": {
        "events": ["Start"],
        "effect": "transform",
        "desc": "Transforms into the opponent Pokemon on switch-in."
    },

    # ========== TERRAIN BOOST ABILITIES ==========
    "surge_surfer": {
        "effect": "terrain_boost",
        "terrain": "electric",
        "stat": "spe",
        "multiplier": 2.0,
        "desc": "Doubles Speed on Electric Terrain."
    },
    "grass_pelt": {
        "effect": "terrain_boost",
        "terrain": "grassy",
        "stat": "def",
        "multiplier": 1.5,
        "desc": "Defense is 1.5x on Grassy Terrain."
    },
}


def normalize_ability_id(ability_id):
    """Normalize ability ID by removing underscores and spaces"""
    import re
    return re.sub(r'[-_\s]+', '', ability_id.lower())


def apply_ability_implementations():
    """Apply comprehensive ability implementations"""

    abilities_file = '/home/user/PokebotANOTHAAAA/data/abilities.json'

    print("Loading abilities database...")
    with open(abilities_file, 'r', encoding='utf-8') as f:
        abilities = json.load(f)

    print(f"Loaded {len(abilities)} abilities")
    print(f"Applying {len(ABILITY_IMPLEMENTATIONS)} implementations...\n")

    updated_count = 0
    abilities_updated = []

    for ability_id, implementation in ABILITY_IMPLEMENTATIONS.items():
        # Normalize the ability ID
        normalized_id = normalize_ability_id(ability_id)

        # Find the matching ability in the database
        found = False
        for db_id in abilities.keys():
            if normalize_ability_id(db_id) == normalized_id:
                ability_data = abilities[db_id]
                ability_name = ability_data.get('name', db_id)
                found = True
                break

        if not found:
            print(f"⚠️  Ability '{ability_id}' not found in database")
            continue

        # Update with implementation
        for key, value in implementation.items():
            ability_data[key] = value

        abilities_updated.append(ability_name)
        updated_count += 1
        print(f"✓ {ability_name}: {implementation.get('desc', 'Updated')[:80]}")

    # Save updated abilities
    output_file = abilities_file
    backup_file = '/home/user/PokebotANOTHAAAA/data/abilities_backup.json'

    print(f"\n📁 Creating backup at {backup_file}")
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(abilities, f, indent=2, ensure_ascii=False)

    print(f"💾 Saving updated abilities to {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(abilities, f, indent=2, ensure_ascii=False)

    # Generate report
    print("\n" + "=" * 80)
    print("COMPREHENSIVE ABILITY IMPLEMENTATION REPORT")
    print("=" * 80)
    print(f"Total abilities in database: {len(abilities)}")
    print(f"Abilities implemented: {updated_count}")
    print(f"Implementation coverage: {(updated_count / len(abilities)) * 100:.1f}%")
    print("=" * 80)

    # Save report
    report_file = '/home/user/PokebotANOTHAAAA/ability_implementation_report.txt'
    with open(report_file, 'w') as f:
        f.write("COMPREHENSIVE ABILITY IMPLEMENTATION REPORT\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Total abilities: {len(abilities)}\n")
        f.write(f"Abilities implemented: {updated_count}\n")
        f.write(f"Coverage: {(updated_count / len(abilities)) * 100:.1f}%\n\n")
        f.write("Implemented abilities:\n")
        for name in abilities_updated:
            f.write(f"  - {name}\n")

    print(f"\n📄 Detailed report saved to: {report_file}")
    print("\n✅ All implementations applied successfully!")


if __name__ == '__main__':
    apply_ability_implementations()
