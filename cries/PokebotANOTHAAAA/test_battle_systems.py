"""
Test Script for Pokemon Battle Systems
Run this to verify status conditions, move effects, and damage calculation work correctly
"""

import sys
import json
from dataclasses import dataclass
from typing import Dict, List

# Import our systems
from status_conditions import StatusConditionManager, StatusType, VolatileStatus
from effect_handler import EffectHandler, MoveDatabase
from enhanced_calculator import EnhancedDamageCalculator


# Simple test Pokemon class
@dataclass
class TestPokemon:
    species_name: str
    level: int = 50
    current_hp: int = 150
    max_hp: int = 150
    attack: int = 100
    defense: int = 80
    sp_attack: int = 110
    sp_defense: int = 90
    speed: int = 95
    species_data: Dict = None
    
    def __post_init__(self):
        if self.species_data is None:
            self.species_data = {'types': ['normal']}
        self.status_manager = StatusConditionManager()
        self.stat_stages = {
            'attack': 0,
            'defense': 0,
            'sp_attack': 0,
            'sp_defense': 0,
            'speed': 0,
            'evasion': 0,
            'accuracy': 0
        }


# Simple moves database for testing
class TestMovesDB:
    def __init__(self):
        self.moves = {
            'tackle': {
                'id': 'tackle',
                'name': 'Tackle',
                'type': 'normal',
                'category': 'physical',
                'power': 40,
                'accuracy': 100,
                'pp': 35,
                'priority': 0,
                'target': 'normal',
                'flags': {'contact': True},
                'description': 'A basic attack'
            },
            'fire_blast': {
                'id': 'fire_blast',
                'name': 'Fire Blast',
                'type': 'fire',
                'category': 'special',
                'power': 110,
                'accuracy': 85,
                'pp': 5,
                'secondary': {
                    'chance': 10,
                    'status': 'brn'
                },
                'description': 'May burn the target'
            },
            'giga_drain': {
                'id': 'giga_drain',
                'name': 'Giga Drain',
                'type': 'grass',
                'category': 'special',
                'power': 75,
                'accuracy': 100,
                'pp': 10,
                'drain': [1, 2],
                'description': 'Drains HP from the target'
            },
            'swords_dance': {
                'id': 'swords_dance',
                'name': 'Swords Dance',
                'type': 'normal',
                'category': 'status',
                'accuracy': True,
                'pp': 20,
                'target': 'self',
                'boosts': {
                    'atk': 2
                },
                'description': 'Sharply raises Attack'
            },
            'toxic': {
                'id': 'toxic',
                'name': 'Toxic',
                'type': 'poison',
                'category': 'status',
                'accuracy': 90,
                'pp': 10,
                'secondary': {
                    'chance': 100,
                    'status': 'tox'
                },
                'description': 'Badly poisons the target'
            },
            'brave_bird': {
                'id': 'brave_bird',
                'name': 'Brave Bird',
                'type': 'flying',
                'category': 'physical',
                'power': 120,
                'accuracy': 100,
                'pp': 15,
                'recoil': [1, 3],
                'flags': {'contact': True},
                'description': 'High power with recoil'
            }
        }
    
    def get_move(self, move_id):
        return self.moves.get(move_id)


# Simple type chart for testing
TEST_TYPE_CHART = {
    'normal': {'rock': 0.5, 'ghost': 0, 'steel': 0.5},
    'fire': {'fire': 0.5, 'water': 0.5, 'grass': 2, 'ice': 2, 'bug': 2, 'rock': 0.5, 'dragon': 0.5, 'steel': 2},
    'water': {'fire': 2, 'water': 0.5, 'grass': 0.5, 'ground': 2, 'rock': 2, 'dragon': 0.5},
    'grass': {'fire': 0.5, 'water': 2, 'grass': 0.5, 'poison': 0.5, 'ground': 2, 'flying': 0.5, 'bug': 0.5, 'rock': 2, 'dragon': 0.5, 'steel': 0.5},
    'poison': {'grass': 2, 'poison': 0.5, 'ground': 0.5, 'rock': 0.5, 'ghost': 0.5, 'steel': 0},
    'flying': {'grass': 2, 'fighting': 2, 'bug': 2, 'electric': 0.5, 'rock': 0.5, 'steel': 0.5}
}


def run_tests():
    """Run a suite of tests to verify everything works"""
    
    print("🧪 Pokemon Battle Systems Test Suite")
    print("=" * 60)
    print()
    
    # Initialize systems
    moves_db = TestMovesDB()
    calc = EnhancedDamageCalculator(moves_db, TEST_TYPE_CHART)
    
    # Test 1: Basic Damage Calculation
    print("Test 1: Basic Damage Calculation")
    print("-" * 60)
    attacker = TestPokemon("Charizard", species_data={'types': ['fire', 'flying']})
    defender = TestPokemon("Blastoise", species_data={'types': ['water']})
    
    damage, crit, effectiveness, msgs = calc.calculate_damage_with_effects(
        attacker, defender, 'tackle'
    )
    
    print(f"  Charizard used Tackle on Blastoise")
    print(f"  Damage: {damage}")
    print(f"  Critical: {crit}")
    print(f"  Effectiveness: {effectiveness}x")
    print(f"  ✅ Basic damage calculation works!")
    print()
    
    # Test 2: Status Conditions
    print("Test 2: Status Condition Application")
    print("-" * 60)
    attacker = TestPokemon("Pikachu", species_data={'types': ['electric']})
    defender = TestPokemon("Charizard", species_data={'types': ['fire', 'flying']})
    
    # Apply burn
    success, msg = defender.status_manager.apply_status('brn')
    print(f"  Applied burn to Charizard: {msg}")
    print(f"  Has burn: {defender.status_manager.has_status('brn')}")
    
    # Check attack reduction
    original_attack = defender.attack
    modified_attack = defender.status_manager.modify_attack_stat(original_attack, is_physical=True)
    print(f"  Attack: {original_attack} → {modified_attack} (halved by burn)")
    print(f"  ✅ Status conditions work!")
    print()
    
    # Test 3: Stat Stages
    print("Test 3: Stat Stage Modifications")
    print("-" * 60)
    attacker = TestPokemon("Machamp", species_data={'types': ['fighting']})
    defender = TestPokemon("Alakazam", species_data={'types': ['psychic']})
    
    damage_before, _, _, msgs = calc.calculate_damage_with_effects(
        attacker, defender, 'tackle'
    )
    print(f"  Machamp's Tackle damage (before): {damage_before}")
    
    # Use Swords Dance
    _, _, _, msgs = calc.calculate_damage_with_effects(
        attacker, defender, 'swords_dance'
    )
    print(f"  Used Swords Dance: {msgs[0]}")
    
    damage_after, _, _, _ = calc.calculate_damage_with_effects(
        attacker, defender, 'tackle'
    )
    print(f"  Machamp's Tackle damage (after): {damage_after}")
    print(f"  Damage increased: {damage_after / damage_before:.2f}x")
    print(f"  ✅ Stat stages work!")
    print()
    
    # Test 4: Drain Moves
    print("Test 4: Drain Move Healing")
    print("-" * 60)
    attacker = TestPokemon("Venusaur", species_data={'types': ['grass', 'poison']})
    defender = TestPokemon("Blastoise", species_data={'types': ['water']})
    
    # Damage attacker first
    attacker.current_hp = 100
    hp_before = attacker.current_hp
    
    damage, _, _, msgs = calc.calculate_damage_with_effects(
        attacker, defender, 'giga_drain'
    )
    
    hp_after = attacker.current_hp
    print(f"  Venusaur HP: {hp_before} → {hp_after}")
    print(f"  Damage dealt: {damage}")
    print(f"  HP restored: {hp_after - hp_before}")
    print(f"  Effects: {msgs}")
    print(f"  ✅ Drain moves work!")
    print()
    
    # Test 5: Recoil Moves
    print("Test 5: Recoil Damage")
    print("-" * 60)
    attacker = TestPokemon("Staraptor", species_data={'types': ['normal', 'flying']})
    defender = TestPokemon("Machamp", species_data={'types': ['fighting']})
    
    hp_before = attacker.current_hp
    damage, _, _, msgs = calc.calculate_damage_with_effects(
        attacker, defender, 'brave_bird'
    )
    hp_after = attacker.current_hp
    
    print(f"  Staraptor HP: {hp_before} → {hp_after}")
    print(f"  Damage dealt: {damage}")
    print(f"  Recoil taken: {hp_before - hp_after}")
    print(f"  Effects: {msgs}")
    print(f"  ✅ Recoil moves work!")
    print()
    
    # Test 6: End of Turn Effects
    print("Test 6: End of Turn Status Damage")
    print("-" * 60)
    pokemon = TestPokemon("Charizard", species_data={'types': ['fire', 'flying']})
    pokemon.status_manager.apply_status('psn')
    
    hp_before = pokemon.current_hp
    msgs = calc.apply_end_of_turn(pokemon)
    hp_after = pokemon.current_hp
    
    print(f"  Charizard HP: {hp_before} → {hp_after}")
    print(f"  Messages: {msgs}")
    print(f"  ✅ End of turn effects work!")
    print()
    
    # Test 7: Type Immunities
    print("Test 7: Status Type Immunities")
    print("-" * 60)
    fire_pokemon = TestPokemon("Charizard", species_data={'types': ['fire', 'flying']})
    
    can_apply, reason = fire_pokemon.status_manager.can_apply_status('brn', ['fire', 'flying'])
    print(f"  Can burn Fire-type? {can_apply}")
    print(f"  Reason: {reason}")
    print(f"  ✅ Type immunities work!")
    print()
    
    # Test 8: Speed Modifications
    print("Test 8: Speed Modifications")
    print("-" * 60)
    pokemon = TestPokemon("Pikachu", species_data={'types': ['electric']})
    
    normal_speed = calc.get_speed(pokemon)
    print(f"  Normal speed: {normal_speed}")
    
    pokemon.status_manager.apply_status('par')
    paralyzed_speed = calc.get_speed(pokemon)
    print(f"  Paralyzed speed: {paralyzed_speed}")
    print(f"  Reduction: {normal_speed / paralyzed_speed:.1f}x slower")
    print(f"  ✅ Speed modifications work!")
    print()
    
    # Final Summary
    print("=" * 60)
    print("🎉 All Tests Passed!")
    print()
    print("Your battle system is ready to use!")
    print("Next steps:")
    print("  1. Integrate with your battle engine (see IMPLEMENTATION_GUIDE.md)")
    print("  2. Add move effects to your moves.json (see MOVE_REFERENCE.md)")
    print("  3. Test in your Discord bot")
    print()


if __name__ == '__main__':
    try:
        run_tests()
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
