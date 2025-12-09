"""
Move Effect Handler System
Parses and executes move effects from Pokemon Showdown data
Handles stat changes, status infliction, healing, recoil, drain, hazards, and more
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import random
import json
from status_conditions import StatusType, VolatileStatus, StatusConditionManager


@dataclass
class MoveEffect:
    """Represents a move's effect"""
    effect_type: str  # 'status', 'stat_boost', 'heal', 'recoil', 'drain', 'hazard', etc.
    chance: int = 100  # Percentage chance (100 = always)
    target: str = 'normal'  # 'self', 'normal' (opponent), 'both', 'enemy_field'
    power: Optional[int] = None
    params: Dict = None  # Additional parameters
    
    def __post_init__(self):
        if self.params is None:
            self.params = {}


# Hazard secondary messages (what happens after the move is used)
HAZARD_MESSAGES = {
    'stealth_rock': "Pointed stones float in the air around the opposing team!",
    'spikes': "Spikes were scattered on the ground around the opposing team!",
    'toxic_spikes': "Poison spikes were scattered on the ground around the opposing team!",
    'sticky_web': "A sticky web spreads out on the ground around the opposing team!",
}


class EffectHandler:
    """
    Handles parsing and execution of move effects
    Converts Showdown's effect data into executable Python code
    """
    
    # Stat name mapping (Showdown -> our system)
    STAT_MAP = {
        'atk': 'attack',
        'def': 'defense',
        'spa': 'sp_attack',
        'spd': 'sp_defense',
        'spe': 'speed',
        'evasion': 'evasion',
        'accuracy': 'accuracy'
    }
    
    def __init__(self, moves_db, type_chart):
        self.moves_db = moves_db
        self.type_chart = type_chart
    
    def parse_move_effects(self, move_data: Dict) -> List[MoveEffect]:
        """
        Parse a move's effects from Showdown data
        Returns list of MoveEffect objects
        """
        effects = []
        
        # Hazard moves (Stealth Rock, Spikes, etc.)
        move_target = move_data.get('target', '')
        move_id = move_data.get('id', '')
        if 'field' in move_target and move_id in ['stealth_rock', 'spikes', 'toxic_spikes', 'sticky_web']:
            effects.append(MoveEffect(
                effect_type='hazard',
                chance=100,
                target='enemy_field',
                params={'hazard_type': move_id}
            ))
        
        # Drain moves (Absorb, Giga Drain, etc.)
        if 'drain' in move_data:
            drain_data = move_data['drain']
            if isinstance(drain_data, list) and len(drain_data) == 2:
                percentage = (drain_data[0] / drain_data[1]) * 100
                effects.append(MoveEffect(
                    effect_type='drain',
                    chance=100,
                    target='self',
                    params={'percentage': percentage}
                ))
        
        # Recoil moves (Take Down, Brave Bird, etc.)
        if 'recoil' in move_data:
            recoil_data = move_data['recoil']
            if isinstance(recoil_data, list) and len(recoil_data) == 2:
                percentage = (recoil_data[0] / recoil_data[1]) * 100
                effects.append(MoveEffect(
                    effect_type='recoil',
                    chance=100,
                    target='self',
                    params={'percentage': percentage}
                ))
        
        # Self-destruct moves (Explosion, Self-Destruct)
        if move_data.get('selfdestruct'):
            effects.append(MoveEffect(
                effect_type='selfdestruct',
                chance=100,
                target='self'
            ))
        

        # Protect-like moves (block attacks this turn)
        if move_id in ['protect', 'detect']:
            effects.append(MoveEffect(
                effect_type='inflict_volatile',
                chance=100,
                target='self',
                params={'status': 'protect'}
            ))

        # Endure (survive this turn at 1 HP)
        if move_id == 'endure':
            effects.append(MoveEffect(
                effect_type='inflict_volatile',
                chance=100,
                target='self',
                params={'status': 'endure'}
            ))
        # Stat boosts - check target field to determine who receives the stat change
        if 'boosts' in move_data:
            boosts = move_data['boosts']
            
            # Determine target based on move's target field
            move_target = move_data.get('target', 'single')
            if move_target in ['self', 'allies', 'all_allies']:
                effect_target = 'self'
            else:
                # Most moves (like Growl, Leer) target the opponent
                effect_target = 'normal'
            
            effects.append(MoveEffect(
                effect_type='stat_boost',
                chance=100,
                target=effect_target,
                params={'boosts': boosts}
            ))
        
        # Top-level status (Thunder Wave, Will-O-Wisp, etc.)
        if 'status' in move_data:
            effects.append(MoveEffect(
                effect_type='inflict_status',
                chance=100,
                target='normal',
                params={'status': move_data['status']}
            ))
        
        # Top-level volatile status
        if 'volatileStatus' in move_data:
            effects.append(MoveEffect(
                effect_type='inflict_volatile',
                chance=100,
                target='normal',
                params={'status': move_data['volatileStatus']}
            ))
        
        # Secondary effects (status, stat changes on opponent, etc.)
        if 'secondary' in move_data and move_data['secondary']:
            secondary = move_data['secondary']
            chance = secondary.get('chance', 100)
            
            # Status condition
            if 'status' in secondary:
                effects.append(MoveEffect(
                    effect_type='inflict_status',
                    chance=chance,
                    target='normal',
                    params={'status': secondary['status']}
                ))
            
            # Volatile status
            if 'volatileStatus' in secondary:
                effects.append(MoveEffect(
                    effect_type='inflict_volatile',
                    chance=chance,
                    target='normal',
                    params={'status': secondary['volatileStatus']}
                ))
            
            # Stat boosts/drops on opponent
            if 'boosts' in secondary:
                effects.append(MoveEffect(
                    effect_type='stat_boost',
                    chance=chance,
                    target='normal',
                    params={'boosts': secondary['boosts']}
                ))
            
            # Self stat boosts (from secondary)
            if 'self' in secondary and 'boosts' in secondary['self']:
                effects.append(MoveEffect(
                    effect_type='stat_boost',
                    chance=chance,
                    target='self',
                    params={'boosts': secondary['self']['boosts']}
                ))
        
        # Multi-hit moves
        if 'multihit' in move_data:
            multihit = move_data['multihit']
            if isinstance(multihit, list):
                effects.append(MoveEffect(
                    effect_type='multihit',
                    chance=100,
                    params={'min': multihit[0], 'max': multihit[1]}
                ))
            elif isinstance(multihit, int):
                effects.append(MoveEffect(
                    effect_type='multihit',
                    chance=100,
                    params={'hits': multihit}
                ))
        
        # Weather setting moves
        if 'weather' in move_data:
            effects.append(MoveEffect(
                effect_type='weather',
                chance=100,
                params={'weather': move_data['weather']}
            ))
        
        # Terrain setting moves
        if 'terrain' in move_data:
            effects.append(MoveEffect(
                effect_type='terrain',
                chance=100,
                params={'terrain': move_data['terrain']}
            ))
        
        # Healing moves
        if 'heal' in move_data:
            heal_data = move_data['heal']
            if isinstance(heal_data, list) and len(heal_data) == 2:
                percentage = (heal_data[0] / heal_data[1]) * 100
                effects.append(MoveEffect(
                    effect_type='heal',
                    chance=100,
                    target='self',
                    params={'percentage': percentage}
                ))
        
        # Ohko moves
        if move_data.get('ohko'):
            effects.append(MoveEffect(
                effect_type='ohko',
                chance=100,
                params={'type': move_data.get('ohko', True)}
            ))
        
        # Moves that force switching
        if move_data.get('forceSwitch'):
            effects.append(MoveEffect(
                effect_type='force_switch',
                chance=100,
                target='normal'
            ))

        # Moves that make user switch (U-turn, Volt Switch, etc.)
        # These moves are detected by their move_id since the JSON doesn't have selfSwitch field
        switch_moves = ['volt_switch', 'u_turn', 'flip_turn', 'baton_pass', 'parting_shot', 'teleport']
        if move_data.get('selfSwitch') or move_id in switch_moves:
            effects.append(MoveEffect(
                effect_type='self_switch',
                chance=100,
                target='self'
            ))

        # Trick Room (reverse move order for 5 turns)
        if move_id == 'trick_room':
            effects.append(MoveEffect(
                effect_type='trick_room',
                chance=100,
                target='field',
                params={'duration': 5}
            ))

        # Follow Me (single-turn redirection)
        if move_id == 'follow_me':
            effects.append(MoveEffect(
                effect_type='inflict_volatile',
                chance=100,
                target='self',
                params={'status': 'follow_me', 'duration': 1}
            ))

        # Taunt (prevents status moves)
        if move_id == 'taunt':
            effects.append(MoveEffect(
                effect_type='inflict_volatile',
                chance=100,
                target='normal',
                params={'status': 'taunt'}
            ))

        return effects
    
    def apply_move_effects(
        self,
        move_data: Dict,
        attacker: Any,
        defender: Any,
        damage_dealt: int,
        battle_state: Any = None
    ) -> List[str]:
        """
        Apply all effects of a move after it hits
        Returns list of messages describing effects
        """
        if move_data.get('id') == 'revival_blessing':
            revival_msg = self._apply_revival_blessing(attacker, battle_state)
            return [revival_msg] if revival_msg else ["But it failed! There was no one to revive."]

        messages = []
        effects = self.parse_move_effects(move_data)
        
        for effect in effects:
            # Check if effect activates (based on chance)
            if random.random() * 100 > effect.chance:
                continue
            
            # Get target Pokemon
            if effect.target == 'self':
                target = attacker
            elif effect.target == 'normal':
                target = defender
            elif effect.target == 'enemy_field':
                target = defender  # For hazards, we still use defender to determine which side
            else:
                target = defender  # Default to defender
            
            # Apply effect based on type
            if effect.effect_type == 'hazard':
                result = self._apply_hazard(effect, battle_state)
                if result:
                    messages.append(result)
            
            elif effect.effect_type == 'drain':
                result = self._apply_drain(effect, attacker, damage_dealt)
                if result:
                    messages.append(result)
            
            elif effect.effect_type == 'recoil':
                result = self._apply_recoil(effect, attacker, damage_dealt)
                if result:
                    messages.append(result)
            
            elif effect.effect_type == 'heal':
                result = self._apply_heal(effect, target)
                if result:
                    messages.append(result)
            
            elif effect.effect_type == 'stat_boost':
                result = self._apply_stat_boost(effect, target)
                if result:
                    messages.extend(result)
            
            elif effect.effect_type == 'inflict_status':
                result = self._apply_status(effect, target)
                if result:
                    messages.append(result)
            
            elif effect.effect_type == 'inflict_volatile':
                result = self._apply_volatile(effect, target)
                if result:
                    messages.append(result)
            
            elif effect.effect_type == 'selfdestruct':
                attacker.current_hp = 0
                messages.append(f"{attacker.species_name} fainted from the blast!")

            elif effect.effect_type == 'self_switch':
                # Mark that the attacker should switch after this move
                # The battle engine will handle the actual switching
                attacker._should_switch = True
                messages.append(f"{attacker.species_name} will switch out!")

            elif effect.effect_type == 'weather':
                result = self._apply_weather(effect, battle_state, attacker)
                if result:
                    messages.append(result)

            elif effect.effect_type == 'terrain':
                result = self._apply_terrain(effect, battle_state)
                if result:
                    messages.append(result)

            elif effect.effect_type == 'trick_room':
                result = self._apply_trick_room(effect, battle_state)
                if result:
                    messages.append(result)

        return messages

    def _apply_revival_blessing(self, attacker: Any, battle_state: Any) -> Optional[str]:
        """Revive a fainted party member at half HP."""
        if not battle_state:
            return None

        target_battler = None
        for battler in battle_state.get_all_battlers():
            if attacker in getattr(battler, 'party', []):
                target_battler = battler
                break

        if not target_battler:
            return None

        fainted_allies = [mon for mon in target_battler.party if getattr(mon, 'current_hp', 0) <= 0]
        if not fainted_allies:
            return None

        ally = fainted_allies[0]
        ally.current_hp = max(1, ally.max_hp // 2)
        if hasattr(ally, 'status_manager'):
            ally.status_manager.major_status = None
            ally.status_manager.clear_volatile_statuses()

        return f"{attacker.species_name}'s Revival Blessing revived {ally.species_name}! ({ally.current_hp}/{ally.max_hp} HP)"
    
    def _apply_hazard(self, effect: MoveEffect, battle_state: Any) -> Optional[str]:
        """Apply hazard to the field"""
        hazard_type = effect.params.get('hazard_type')
        
        if not battle_state:
            # If no battle_state provided, just return the message
            return HAZARD_MESSAGES.get(hazard_type, "A hazard was set!")
        
        # Apply hazard to opponent's side
        if not hasattr(battle_state, 'opponent_hazards'):
            battle_state.opponent_hazards = {}
        
        # For spikes and toxic spikes, they can stack up to 3 layers
        if hazard_type in ['spikes', 'toxic_spikes']:
            current_layers = battle_state.opponent_hazards.get(hazard_type, 0)
            if current_layers < 3:
                battle_state.opponent_hazards[hazard_type] = current_layers + 1
                return HAZARD_MESSAGES.get(hazard_type, "A hazard was set!")
            else:
                return "But it failed! (Maximum layers already set)"
        else:
            # Stealth Rock and Sticky Web can only be set once
            if hazard_type not in battle_state.opponent_hazards:
                battle_state.opponent_hazards[hazard_type] = 1
                return HAZARD_MESSAGES.get(hazard_type, "A hazard was set!")
            else:
                return "But it failed! (Hazard already set)"
    
    def _apply_drain(self, effect: MoveEffect, attacker: Any, damage: int) -> Optional[str]:
        """Apply drain effect (heal based on damage dealt)"""
        percentage = effect.params.get('percentage', 50)
        heal_amount = max(1, int(damage * percentage / 100))
        heal_amount = min(heal_amount, attacker.max_hp - attacker.current_hp)
        
        if heal_amount > 0:
            attacker.current_hp += heal_amount
            return f"{attacker.species_name} drained {heal_amount} HP!"
        return None
    
    def _apply_recoil(self, effect: MoveEffect, attacker: Any, damage: int) -> Optional[str]:
        """Apply recoil damage"""
        # Only apply recoil if the move actually hit and dealt damage
        if damage <= 0:
            return None

        percentage = effect.params.get('percentage', 25)
        recoil_damage = max(1, int(damage * percentage / 100))

        attacker.current_hp = max(0, attacker.current_hp - recoil_damage)
        return f"{attacker.species_name} took {recoil_damage} recoil damage!"
    
    def _apply_heal(self, effect: MoveEffect, target: Any) -> Optional[str]:
        """Apply healing effect"""
        percentage = effect.params.get('percentage', 50)
        heal_amount = max(1, int(target.max_hp * percentage / 100))
        heal_amount = min(heal_amount, target.max_hp - target.current_hp)
        
        if heal_amount > 0:
            target.current_hp += heal_amount
            return f"{target.species_name} restored {heal_amount} HP!"
        return None
    
    def _apply_stat_boost(self, effect: MoveEffect, target: Any) -> List[str]:
        """Apply stat changes"""
        messages = []
        boosts = effect.params.get('boosts', {})
        
        # Initialize stat stages if not present
        if not hasattr(target, 'stat_stages'):
            target.stat_stages = {
                'attack': 0,
                'defense': 0,
                'sp_attack': 0,
                'sp_defense': 0,
                'speed': 0,
                'evasion': 0,
                'accuracy': 0
            }
        
        for stat_short, change in boosts.items():
            stat_name = self.STAT_MAP.get(stat_short, stat_short)
            
            if stat_name not in target.stat_stages:
                continue
            
            old_stage = target.stat_stages[stat_name]
            new_stage = max(-6, min(6, old_stage + change))
            actual_change = new_stage - old_stage
            
            if actual_change == 0:
                if new_stage >= 6:
                    messages.append(f"{target.species_name}'s {stat_name.replace('_', ' ').title()} won't go higher!")
                else:
                    messages.append(f"{target.species_name}'s {stat_name.replace('_', ' ').title()} won't go lower!")
            else:
                target.stat_stages[stat_name] = new_stage
                
                if actual_change > 0:
                    if actual_change == 1:
                        msg = f"{target.species_name}'s {stat_name.replace('_', ' ').title()} rose! ({new_stage:+d})"
                    elif actual_change == 2:
                        msg = f"{target.species_name}'s {stat_name.replace('_', ' ').title()} rose sharply! ({new_stage:+d})"
                    else:
                        msg = f"{target.species_name}'s {stat_name.replace('_', ' ').title()} rose drastically! ({new_stage:+d})"
                else:
                    if actual_change == -1:
                        msg = f"{target.species_name}'s {stat_name.replace('_', ' ').title()} fell! ({new_stage:+d})"
                    elif actual_change == -2:
                        msg = f"{target.species_name}'s {stat_name.replace('_', ' ').title()} harshly fell! ({new_stage:+d})"
                    else:
                        msg = f"{target.species_name}'s {stat_name.replace('_', ' ').title()} severely fell! ({new_stage:+d})"
                
                messages.append(msg)
        
        return messages
    
    def _apply_status(self, effect: MoveEffect, target: Any) -> Optional[str]:
        """Apply major status condition"""
        status = effect.params.get('status')
        
        if not hasattr(target, 'status_manager'):
            target.status_manager = StatusConditionManager()
        
        # Check type immunities
        pokemon_types = target.species_data.get('types', [])
        can_apply, reason = target.status_manager.can_apply_status(status, pokemon_types, target)
        
        if not can_apply:
            return f"{target.species_name} is not affected! ({reason})"
        
        success, message = target.status_manager.apply_status(status)
        if success:
            return f"{target.species_name} {message}"
        
        return None
    
    def _apply_volatile(self, effect: MoveEffect, target: Any) -> Optional[str]:
        """Apply volatile status condition"""
        status = effect.params.get('status')

        if not hasattr(target, 'status_manager'):
            target.status_manager = StatusConditionManager()

        # Set duration for certain volatile statuses
        duration = None
        if status in ['confusion']:
            duration = random.randint(1, 4)  # 1-4 turns
        elif status in ['bind', 'wrap', 'firespin', 'whirlpool', 'sandtomb', 'clamp', 'infestation', 'partiallytrapped']:
            duration = random.randint(4, 5)  # 4-5 turns
        elif status in ['flinch', 'protect', 'detect', 'endure']:
            duration = 1  # These only last until end of turn
        elif status == 'taunt':
            duration = 3  # Gen 9 duration
        elif status in ['lightscreen', 'reflect']:
            duration = 5  # Light Screen and Reflect last 5 turns (8 with Light Clay)
        elif status == 'auroraveil':
            duration = 5  # Aurora Veil lasts 5 turns (8 with Light Clay)
        elif status in ['tailwind', 'safeguard', 'mist', 'luckychant']:
            duration = 5  # Team-wide effects last 5 turns
        elif status == 'yawn':
            duration = 2  # Yawn causes sleep after 1 turn (2 turn duration)

        # Allow explicit duration overrides from move data
        duration = effect.params.get('duration', duration)

        success, message = target.status_manager.apply_status(status, duration=duration)
        if success:
            return f"{target.species_name} {message}"

        return None

    def _apply_weather(self, effect: MoveEffect, battle_state: Any, attacker: Any = None) -> Optional[str]:
        """Apply weather to the field"""
        weather = effect.params.get('weather')

        if not battle_state:
            return None

        weather_messages = {
            'sun': "The sunlight turned harsh!",
            'rain': "It started to rain!",
            'sandstorm': "A sandstorm kicked up!",
            'hail': "It started to hail!",
            'snow': "It started to snow!"
        }

        is_raid_boss = getattr(attacker, "is_raid_boss", False) if attacker else False

        # If rogue Pokemon sets weather, save as permanent
        if is_raid_boss:
            battle_state.rogue_weather = weather
            battle_state.weather = weather
            battle_state.weather_turns = 999  # Effectively permanent
        else:
            # Non-rogue Pokemon setting weather
            # Default 5 turns, extended to 8 with weather-extending items
            weather_turns = 5

            if attacker and hasattr(attacker, 'held_item'):
                item_id = attacker.held_item

                # Weather-extending items
                weather_extenders = {
                    'heatrock': 'sun',
                    'damprock': 'rain',
                    'smoothrock': 'sandstorm',
                    'icyrock': ['hail', 'snow']
                }

                # Normalize item_id for comparison (remove spaces, hyphens, underscores, lowercase)
                if item_id:
                    import re
                    normalized_item = re.sub(r'[-_\s]+', '', (item_id or '').strip().lower())
                    for item, weather_types in weather_extenders.items():
                        if normalized_item == item:
                            if isinstance(weather_types, list):
                                if weather in weather_types:
                                    weather_turns = 8
                                    break
                            elif weather == weather_types:
                                weather_turns = 8
                                break

            battle_state.weather = weather
            battle_state.weather_turns = weather_turns
        return weather_messages.get(weather, f"The weather changed to {weather}!")

    def _apply_terrain(self, effect: MoveEffect, battle_state: Any) -> Optional[str]:
        """Apply terrain to the field"""
        terrain = effect.params.get('terrain')

        if not battle_state:
            return None

        terrain_messages = {
            'electricterrain': "An electric current ran across the battlefield!",
            'grassyterrain': "Grass grew to cover the battlefield!",
            'mistyterrain': "Mist swirled around the battlefield!",
            'psychicterrain': "The battlefield got weird!"
        }

        battle_state.terrain = terrain
        battle_state.terrain_turns = 5  # Default 5 turns
        return terrain_messages.get(terrain, f"The terrain changed to {terrain}!")

    def _apply_trick_room(self, effect: MoveEffect, battle_state: Any) -> Optional[str]:
        """Apply Trick Room to the field"""
        if not battle_state:
            return None

        if getattr(battle_state, 'trick_room_turns', 0) > 0:
            return "But it failed! The dimensions are already twisted."

        battle_state.trick_room_turns = effect.params.get('duration', 5)
        return "The dimensions twisted! Slower Pokémon will move first."
    
    def get_stat_multiplier(self, stage: int) -> float:
        """Get the stat multiplier for a given stage (-6 to +6)"""
        if stage >= 0:
            return (2 + stage) / 2
        else:
            return 2 / (2 - stage)
    
    def apply_stat_stages(self, pokemon: Any, base_stat: int, stat_name: str) -> int:
        """Apply stat stage modifications to a base stat"""
        if not hasattr(pokemon, 'stat_stages'):
            return base_stat
        
        stage = pokemon.stat_stages.get(stat_name, 0)
        if stage == 0:
            return base_stat
        
        multiplier = self.get_stat_multiplier(stage)
        return int(base_stat * multiplier)


class MoveDatabase:
    """
    Enhanced move database that includes effect parsing
    """
    
    def __init__(self, moves_file: str):
        with open(moves_file, 'r', encoding='utf-8') as f:
            self.moves = json.load(f)
    
    def get_move(self, move_id: str) -> Optional[Dict]:
        """Get move data by ID"""
        move_id = move_id.lower().replace(' ', '_')
        return self.moves.get(move_id)
    
    def find_move_by_name(self, name: str) -> Optional[Dict]:
        """Find move by name (case insensitive)"""
        name_lower = name.lower().replace(' ', '')
        
        for move_id, move_data in self.moves.items():
            move_name = move_data['name'].lower().replace(' ', '')
            if move_name == name_lower:
                return move_data
        
        return None
    
    def get_moves_by_type(self, move_type: str) -> List[Dict]:
        """Get all moves of a specific type"""
        return [
            move for move in self.moves.values()
            if move.get('type', '').lower() == move_type.lower()
        ]
    
    def get_moves_by_category(self, category: str) -> List[Dict]:
        """Get all moves of a specific category (physical/special/status)"""
        return [
            move for move in self.moves.values()
            if move.get('category', '').lower() == category.lower()
        ]
