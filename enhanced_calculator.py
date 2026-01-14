"""
Enhanced Battle Damage Calculator
Integrates status conditions, move effects, stat stages, and more
Drop-in replacement/enhancement for anime_battle_engine.py
"""

import random
import json
from typing import Dict, List, Optional, Tuple, Any
from status_conditions import StatusConditionManager, StatusType, VolatileStatus
from effect_handler import EffectHandler, MoveDatabase


class EnhancedDamageCalculator:
    """
    Enhanced damage calculation with full move effects support
    """
    
    def __init__(self, moves_db, type_chart):
        self.moves_db = moves_db
        self.type_chart = type_chart
        self.effect_handler = EffectHandler(moves_db, type_chart)

    def _normalize_id(self, value: str) -> str:
        """Normalize identifiers for comparisons"""
        return (value or "").replace("-", "").replace(" ", "").lower()
    
    def calculate_damage_with_effects(
        self,
        attacker: Any,
        defender: Any,
        move_id: str,
        is_blocked: bool = False,
        weather: Optional[str] = None,
        terrain: Optional[str] = None,
        battle_state: Any = None
    ) -> Tuple[int, bool, float, List[str]]:
        """
        Calculate damage and apply all move effects
        
        Returns:
            (damage, is_critical, effectiveness, effect_messages)
        """
        # Initialize status managers if not present
        if not hasattr(attacker, 'status_manager'):
            attacker.status_manager = StatusConditionManager()
        if not hasattr(defender, 'status_manager'):
            defender.status_manager = StatusConditionManager()
        
        # Initialize stat stages if not present
        if not hasattr(attacker, 'stat_stages'):
            attacker.stat_stages = {
                'attack': 0, 'defense': 0, 'sp_attack': 0,
                'sp_defense': 0, 'speed': 0, 'evasion': 0, 'accuracy': 0
            }
        if not hasattr(defender, 'stat_stages'):
            defender.stat_stages = {
                'attack': 0, 'defense': 0, 'sp_attack': 0,
                'sp_defense': 0, 'speed': 0, 'evasion': 0, 'accuracy': 0
            }
        
        effect_messages = []
        
        # Check if attacker can move
        can_move, move_prevention_msg = attacker.status_manager.can_move(attacker)
        if not can_move:
            return 0, False, 1.0, [move_prevention_msg]
        
        # Get move data
        move_data = self.moves_db.get_move(move_id)
        if not move_data:
            return 0, False, 1.0, [f"Move {move_id} not found!"]

        move_id_normalized = (move_data.get('id') or '').lower()

        if move_id_normalized == 'bide':
            return self._resolve_bide(attacker, defender, move_data)


        # Special-case: Fling requires a held item
        if move_id_normalized == 'fling':
            held = getattr(attacker, 'held_item', None) or getattr(attacker, 'item', None)
            if not held:
                return 0, False, 1.0, ["But it failed! (No item to fling)"]
            # Check accuracy
        if not self._check_accuracy(move_data, attacker, defender, weather):
            return 0, False, 1.0, ["The attack missed!"]

        if move_id_normalized == 'present':
            outcome = random.random()
            if outcome >= 0.8:
                heal_amount = max(1, int(defender.max_hp * 0.25))
                defender.current_hp = min(defender.max_hp, defender.current_hp + heal_amount)
                return 0, False, 1.0, [f"{defender.species_name} regained {heal_amount} HP from Present!"]
            move_data = dict(move_data)
            if outcome < 0.4:
                move_data['power'] = 40
            elif outcome < 0.7:
                move_data['power'] = 80
            else:
                move_data['power'] = 120
        
        # Status moves don't deal damage but have effects
        if move_data['category'] == 'status':
            effects = self.effect_handler.apply_move_effects(
                move_data, attacker, defender, 0, battle_state
            )
            return 0, False, 1.0, effects
        
        # Calculate base damage
        damage, is_critical, effectiveness = self._calculate_base_damage(
            attacker, defender, move_data, is_blocked, weather, terrain
        )

        # If the move had no effect (immunity), skip secondary effects entirely
        if effectiveness == 0:
            return 0, is_critical, effectiveness, []

        # Clamp damage to the target's remaining HP so recoil/drain scale off actual damage dealt
        damage_dealt = min(damage, defender.current_hp)

        # Apply move effects (drain, recoil, status, stat changes, etc.)
        effects = self.effect_handler.apply_move_effects(
            move_data, attacker, defender, damage_dealt, battle_state
        )
        effect_messages.extend(effects)

        return damage_dealt, is_critical, effectiveness, effect_messages
    
    def _calculate_base_damage(
        self,
        attacker: Any,
        defender: Any,
        move_data: Dict,
        is_blocked: bool,
        weather: Optional[str],
        terrain: Optional[str]
        ) -> Tuple[int, bool, float]:
        """Calculate base damage with all modifiers"""

        # Get stats with stage modifications
        if move_data['category'] == 'physical':
            attack = attacker.attack
            defense = defender.defense
            # Apply stat stages
            attack = self.effect_handler.apply_stat_stages(attacker, attack, 'attack')
            defense = self.effect_handler.apply_stat_stages(defender, defense, 'defense')
            # Apply burn status (halves physical attack) unless ability prevents it
            if hasattr(attacker, "status_manager"):
                attack = attacker.status_manager.modify_attack_stat(
                    attack,
                    is_physical=True,
                    pokemon=attacker
                )
        else:  # special
            attack = attacker.sp_attack
            defense = defender.sp_defense
            attack = self.effect_handler.apply_stat_stages(attacker, attack, 'sp_attack')
            defense = self.effect_handler.apply_stat_stages(defender, defense, 'sp_defense')
        
        # Base damage formula (Gen 3+)
        level = attacker.level
        move_id = (move_data.get('id') or '').lower()
        power = move_data.get('power')

        # Rage Fist: power scales with number of times the user was hit
        if move_id == 'rage_fist':
            hits_taken = getattr(attacker, 'rage_fist_hits_taken', 0)
            power = min(350, 50 + 50 * hits_taken)

        if move_id in {'counter', 'mirror_coat', 'metal_burst'}:
            last_damage = getattr(attacker, 'last_damage_taken', 0)
            last_category = getattr(attacker, 'last_damage_category', None)
            last_from = getattr(attacker, 'last_damage_from', None)
            category_ok = (
                (move_id == 'counter' and last_category == 'physical')
                or (move_id == 'mirror_coat' and last_category == 'special')
                or (move_id == 'metal_burst' and last_category in {'physical', 'special'})
            )
            if last_damage > 0 and last_from == defender and category_ok:
                multiplier = 2.0 if move_id in {'counter', 'mirror_coat'} else 1.5
                attacker.last_damage_taken = 0
                attacker.last_damage_category = None
                attacker.last_damage_from = None
                return max(1, int(round(last_damage * multiplier))), False, 1.0
            return 0, False, 1.0

        # Special fixed-damage and fractional HP moves (e.g., Super Fang)
        if move_id in {'super_fang', 'natures_madness', 'ruination'}:
            # Respect full immunities (e.g., Ghost vs Normal) but ignore resistances
            effectiveness = self._get_type_effectiveness(move_data['type'], defender.species_data['types'])
            if effectiveness == 0:
                return 0, False, 0
            damage = max(1, defender.current_hp // 2)
            return damage, False, 1.0

        # Level-based damage moves (Night Shade, Seismic Toss, etc.)
        if move_id in {'night_shade', 'seismic_toss', 'psywave', 'sonic_boom', 'dragon_rage'}:
            # Check for type immunity
            effectiveness = self._get_type_effectiveness(move_data['type'], defender.species_data['types'])
            if effectiveness == 0:
                return 0, False, 0

            # Calculate fixed damage based on move type
            if move_id in {'night_shade', 'seismic_toss'}:
                # Damage = user's level
                damage = level
            elif move_id == 'psywave':
                # Damage = random(0.5x to 1.5x level)
                damage = int(level * random.uniform(0.5, 1.5))
            elif move_id == 'sonic_boom':
                # Always deals 20 damage
                damage = 20
            elif move_id == 'dragon_rage':
                # Always deals 40 damage
                damage = 40

            return max(1, damage), False, 1.0

        if move_id == 'endeavor':
            effectiveness = self._get_type_effectiveness(move_data['type'], defender.species_data['types'])
            if effectiveness == 0:
                return 0, False, 0
            damage = max(0, defender.current_hp - attacker.current_hp)
            return damage, False, 1.0

        if move_id == 'final_gambit':
            effectiveness = self._get_type_effectiveness(move_data['type'], defender.species_data['types'])
            if effectiveness == 0:
                return 0, False, 0
            return max(1, attacker.current_hp), False, 1.0

        power = self._calculate_variable_power(attacker, defender, move_data, power)

        # Safety check: Status moves or moves with no power
        if power is None:
            return 0, False, 1.0
        if power == 0:
            return 0, False, 1.0
        
        # Critical hit check
        crit_stage = move_data.get('crit_rate', 1)
        # Account for Focus Energy volatile status
        if attacker.status_manager.has_status(VolatileStatus.FOCUS_ENERGY.value):
            crit_stage += 2
        
        crit_chance = [1/24, 1/8, 1/2, 1/1][min(crit_stage - 1, 3)]
        is_critical = random.random() < crit_chance
        
        if is_critical:
            # Crits ignore negative attack stages and positive defense stages
            if hasattr(attacker, 'stat_stages'):
                if attacker.stat_stages.get('attack' if move_data['category'] == 'physical' else 'sp_attack', 0) < 0:
                    attack = attacker.attack if move_data['category'] == 'physical' else attacker.sp_attack
            if hasattr(defender, 'stat_stages'):
                if defender.stat_stages.get('defense' if move_data['category'] == 'physical' else 'sp_defense', 0) > 0:
                    defense = defender.defense if move_data['category'] == 'physical' else defender.sp_defense
            
            damage = ((2 * level / 5 + 2) * power * attack / defense / 50 + 2) * 1.5
        else:
            damage = (2 * level / 5 + 2) * power * attack / defense / 50 + 2
        
        # STAB (Same Type Attack Bonus)
        move_type = move_data['type']
        attacker_types = attacker.species_data['types']
        if move_type in attacker_types:
            damage *= 1.5

        # Guts ability: 1.5x physical damage when afflicted by a major status
        ability_id = getattr(attacker, 'ability', '')
        has_status = getattr(attacker.status_manager, 'major_status', None) is not None
        if move_data['category'] == 'physical' and has_status and self._normalize_id(ability_id) == 'guts':
            damage *= 1.5

        # Type effectiveness
        effectiveness = self._get_type_effectiveness(move_type, defender.species_data['types'])
        damage *= effectiveness
        
        # Weather modifications
        if weather:
            if weather == 'rain':
                if move_type == 'water':
                    damage *= 1.5
                elif move_type == 'fire':
                    damage *= 0.5
            elif weather == 'sun':
                if move_type == 'fire':
                    damage *= 1.5
                elif move_type == 'water':
                    damage *= 0.5
        
        # Random factor (0.85 to 1.0)
        damage *= random.uniform(0.85, 1.0)
        
        # Block reduces damage by 50%
        if is_blocked:
            damage *= 0.5
        
        # Convert to int, but respect type immunity (effectiveness == 0)
        if effectiveness == 0:
            damage = 0
        else:
            damage = max(1, int(damage))
        
        return damage, is_critical, effectiveness

    def _calculate_variable_power(
        self,
        attacker: Any,
        defender: Any,
        move_data: Dict,
        base_power: Optional[int]
    ) -> Optional[int]:
        move_id = (move_data.get('id') or '').lower()

        if move_id in {'low_kick', 'grass_knot'}:
            weight = defender.species_data.get('weight', 0)
            weight_kg = weight / 10 if weight else 0
            if weight_kg < 10:
                return 20
            if weight_kg < 25:
                return 40
            if weight_kg < 50:
                return 60
            if weight_kg < 100:
                return 80
            if weight_kg < 200:
                return 100
            return 120

        if move_id in {'heavy_slam', 'heat_crash'}:
            attacker_weight = attacker.species_data.get('weight', 0)
            defender_weight = defender.species_data.get('weight', 1) or 1
            ratio = attacker_weight / defender_weight
            if ratio >= 5:
                return 120
            if ratio >= 4:
                return 100
            if ratio >= 3:
                return 80
            if ratio >= 2:
                return 60
            return 40

        if move_id == 'gyro_ball':
            attacker_speed = max(1, self.get_speed(attacker))
            defender_speed = max(1, self.get_speed(defender))
            return min(150, int(25 * defender_speed / attacker_speed))

        if move_id == 'electro_ball':
            attacker_speed = max(1, self.get_speed(attacker))
            defender_speed = max(1, self.get_speed(defender))
            ratio = defender_speed / attacker_speed
            if ratio >= 4:
                return 150
            if ratio >= 3:
                return 120
            if ratio >= 2:
                return 80
            if ratio >= 1:
                return 60
            return 40

        if move_id in {'flail', 'reversal'}:
            if attacker.max_hp <= 0:
                return 20
            hp_ratio = attacker.current_hp / attacker.max_hp
            if hp_ratio <= 0.0417:
                return 200
            if hp_ratio <= 0.1042:
                return 150
            if hp_ratio <= 0.2083:
                return 100
            if hp_ratio <= 0.3542:
                return 80
            if hp_ratio <= 0.6875:
                return 40
            return 20

        if move_id in {'return', 'frustration'}:
            friendship = getattr(attacker, 'friendship', 20)
            if move_id == 'return':
                return min(102, int(friendship * 2 / 5))
            return min(102, int((255 - friendship) * 2 / 5))

        if move_id == 'magnitude':
            roll = random.random()
            if roll < 0.04:
                return 10
            if roll < 0.09:
                return 30
            if roll < 0.19:
                return 50
            if roll < 0.39:
                return 70
            if roll < 0.69:
                return 90
            if roll < 0.89:
                return 110
            return 150

        if move_id == 'present':
            if base_power is not None:
                return base_power
            roll = random.random()
            if roll < 0.4:
                return 40
            if roll < 0.7:
                return 80
            if roll < 0.8:
                return 120
            return 0

        if move_id == 'trump_card':
            pp_remaining = None
            for move in getattr(attacker, 'moves', []) or []:
                if move.get('move_id') == move_id:
                    pp_remaining = move.get('pp')
                    break
            if pp_remaining is None:
                pp_remaining = move_data.get('pp', 0)
            if pp_remaining <= 0:
                return 200
            if pp_remaining == 1:
                return 80
            if pp_remaining == 2:
                return 60
            if pp_remaining == 3:
                return 50
            return 40

        if move_id in {'wring_out', 'crush_grip'}:
            if defender.max_hp <= 0:
                return 1
            return max(1, int(120 * defender.current_hp / defender.max_hp))

        if move_id == 'punishment':
            boosts = getattr(defender, 'stat_stages', {}) or {}
            total_boosts = sum(max(0, stage) for stage in boosts.values())
            return min(200, 60 + 20 * total_boosts)

        if move_id == 'spit_up':
            stockpile = getattr(attacker, 'stockpile_count', 0)
            if stockpile <= 0:
                return 0
            return 100 * min(3, stockpile)

        if move_id.endswith('__physical') or move_id.endswith('__special'):
            base_power = self._get_z_move_base_power(attacker, base_power)
            if base_power is not None:
                return self._calculate_z_move_power(base_power)

        if move_id == 'beat_up':
            return base_power or 10

        if move_id == 'fling':
            return base_power or 30

        if move_id == 'natural_gift':
            return base_power or 60

        return base_power

    def _get_z_move_base_power(self, attacker: Any, fallback: Optional[int]) -> Optional[int]:
        base_move_id = getattr(attacker, 'z_move_base_id', None) or getattr(attacker, 'z_move_base_move_id', None)
        if base_move_id:
            base_move = self.moves_db.get_move(str(base_move_id))
            if base_move and base_move.get('power') is not None:
                return base_move['power']
        base_power = getattr(attacker, 'z_move_base_power', None)
        if base_power is not None:
            return base_power
        return fallback

    def _calculate_z_move_power(self, base_power: int) -> int:
        if base_power <= 55:
            return 100
        if base_power <= 65:
            return 120
        if base_power <= 75:
            return 140
        if base_power <= 85:
            return 160
        if base_power <= 95:
            return 175
        if base_power <= 100:
            return 180
        if base_power <= 110:
            return 185
        if base_power <= 125:
            return 190
        if base_power <= 130:
            return 195
        return 200
    
    def _check_accuracy(self, move_data: Dict, attacker: Any, defender: Any, weather: Optional[str] = None) -> bool:
        """Check if move hits based on accuracy"""
        move_id = move_data.get('id', '')
        base_accuracy = move_data.get('accuracy')

        # Weather-dependent accuracy overrides
        if weather == 'rain':
            # Hurricane and Thunder never miss in rain
            if move_id in ['hurricane', 'thunder']:
                return True
        elif weather == 'sun':
            # Thunder has reduced accuracy in sun
            if move_id == 'thunder':
                base_accuracy = 50

        # accuracy = true means always hits
        if base_accuracy is True or base_accuracy == 'true':
            return True

        # Get accuracy as int
        try:
            accuracy = int(base_accuracy)
        except (ValueError, TypeError):
            accuracy = 100

        # Apply accuracy/evasion stat stages
        accuracy_stage = attacker.stat_stages.get('accuracy', 0)
        evasion_stage = defender.stat_stages.get('evasion', 0)

        # Combined stage
        stage = accuracy_stage - evasion_stage
        stage = max(-6, min(6, stage))

        # Stage multipliers
        if stage >= 0:
            multiplier = (3 + stage) / 3
        else:
            multiplier = 3 / (3 - stage)

        final_accuracy = accuracy * multiplier

        return random.random() * 100 < final_accuracy

    def _resolve_bide(
        self,
        attacker: Any,
        defender: Any,
        move_data: Dict
    ) -> Tuple[int, bool, float, List[str]]:
        turns_remaining = getattr(attacker, 'bide_turns_remaining', None)

        if turns_remaining is None:
            attacker.bide_turns_remaining = 2
            attacker.bide_damage = 0
            return 0, False, 1.0, [f"{attacker.species_name} is biding its time!"]

        if turns_remaining > 1:
            attacker.bide_turns_remaining = turns_remaining - 1
            return 0, False, 1.0, [f"{attacker.species_name} is biding its time!"]

        attacker.bide_turns_remaining = None
        stored_damage = max(0, int(getattr(attacker, 'bide_damage', 0)))
        attacker.bide_damage = 0

        if stored_damage <= 0:
            return 0, False, 1.0, ["But it failed!"]

        move_type = move_data.get('type', 'normal')
        effectiveness = self._get_type_effectiveness(move_type, defender.species_data['types'])
        if effectiveness == 0:
            return 0, False, 0, [f"It doesn't affect {defender.species_name}..."]

        damage = max(1, int(stored_damage * 2))
        return damage, False, effectiveness, []
    
    def _get_type_effectiveness(self, attack_type: str, defender_types: List[str]) -> float:
        """Calculate type effectiveness multiplier"""
        multiplier = 1.0
        
        # Handle both TypeChart objects and raw dictionaries
        if hasattr(self.type_chart, 'get_dual_effectiveness'):
            # It's a TypeChart object
            return self.type_chart.get_dual_effectiveness(attack_type, defender_types)
        elif hasattr(self.type_chart, 'chart'):
            # It's a TypeChart object with a chart attribute
            chart = self.type_chart.chart
        else:
            # It's a raw dictionary
            chart = self.type_chart
        
        # Calculate effectiveness manually
        for def_type in defender_types:
            if attack_type in chart and def_type in chart[attack_type]:
                multiplier *= chart[attack_type][def_type]
        
        return multiplier
    
    def apply_end_of_turn(self, pokemon: Any) -> List[str]:
        """
        Apply end-of-turn effects (status damage, etc.)
        """
        if not hasattr(pokemon, 'status_manager'):
            return []
        
        return pokemon.status_manager.apply_end_of_turn_effects(pokemon)
    
    def get_speed(self, pokemon: Any) -> int:
        """Get effective speed with all modifications"""
        speed = pokemon.speed
        
        # Apply stat stages
        if hasattr(pokemon, 'stat_stages'):
            speed = self.effect_handler.apply_stat_stages(pokemon, speed, 'speed')
        
        # Apply status effects (paralysis halves speed)
        if hasattr(pokemon, 'status_manager'):
            speed = pokemon.status_manager.modify_speed(speed)
        
        return speed


def integrate_with_battle_engine(battle_engine):
    """
    Helper to integrate enhanced calculator into existing battle engine
    
    Usage:
        from enhanced_calculator import integrate_with_battle_engine
        
        # In your battle engine initialization:
        integrate_with_battle_engine(self)
    """
    enhanced_calc = EnhancedDamageCalculator(
        battle_engine.moves_db,
        battle_engine.type_chart
    )
    
    # Replace calculate_damage method
    battle_engine.calculate_damage_enhanced = enhanced_calc.calculate_damage_with_effects
    battle_engine.apply_end_of_turn = enhanced_calc.apply_end_of_turn
    battle_engine.get_speed = enhanced_calc.get_speed
    
    return enhanced_calc


# Example usage
if __name__ == '__main__':
    print("Enhanced Battle Calculator")
    print("=" * 50)
    print()
    print("This module provides:")
    print("  ✓ Full status condition system (burn, paralyze, etc.)")
    print("  ✓ Move effect handling (drain, recoil, stat changes)")
    print("  ✓ Stat stage modifications (-6 to +6)")
    print("  ✓ Accuracy/evasion calculations")
    print("  ✓ Weather/terrain effects")
    print("  ✓ Type effectiveness")
    print()
    print("Integration:")
    print("  from enhanced_calculator import integrate_with_battle_engine")
    print("  integrate_with_battle_engine(your_battle_engine)")
