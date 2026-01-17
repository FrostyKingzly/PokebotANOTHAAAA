"""
Battle Engine V2 - Unified Core Battle System
Supports: Wild battles, Trainer battles (PvE), and PvP battles

This is a complete rewrite that handles ALL battle types with a single engine.
Includes abilities, switching, items, and AI opponent support.
"""

import re
import random
import json
import uuid
import math
import discord
from typing import Dict, List, Optional, Tuple, Any
from ruleset_handler import RulesetHandler
from dataclasses import dataclass, field
from enum import Enum

# Import enhanced systems
try:
    from enhanced_calculator import EnhancedDamageCalculator
    from status_conditions import StatusConditionManager
    from ability_handler import AbilityHandler
    ENHANCED_SYSTEMS_AVAILABLE = True
except ImportError:
    ENHANCED_SYSTEMS_AVAILABLE = False
    from status_conditions import StatusConditionManager
    print("⚠️ Enhanced systems not available. Using basic calculator.")


class BattleType(Enum):
    """Types of battles supported"""
    WILD = "wild"
    TRAINER = "trainer"  # PvE against NPC
    PVP = "pvp"  # Player vs Player


class BattleFormat(Enum):
    """Battle format types"""
    SINGLES = "singles"  # 1v1
    DOUBLES = "doubles"  # 2v2
    MULTI = "multi"  # 2v2 with partners
    RAID = "raid"  # Multi-trainer raid vs. a raid boss


@dataclass
class Battler:
    """Represents one side of a battle (trainer or opponent)"""
    battler_id: int  # Discord ID for trainers, negative for NPCs/wild
    battler_name: str
    party: List[Any]  # List of Pokemon objects
    active_positions: List[int]  # Which Pokemon are currently active (indices into party)
    is_ai: bool = False  # Whether this battler is controlled by AI
    can_switch: bool = True
    can_use_items: bool = True
    can_flee: bool = False
    is_eliminated: bool = False  # True when all Pokemon have fainted

    # For trainer battles
    trainer_class: Optional[str] = None  # "Youngster", "Ace Trainer", etc.
    prize_money: int = 0

    def get_active_pokemon(self) -> List[Any]:
        """Get currently active Pokemon"""
        return [self.party[i] for i in self.active_positions if i < len(self.party)]

    def has_usable_pokemon(self) -> bool:
        """Check if battler has any Pokemon that can still fight"""
        return any(p.current_hp > 0 for p in self.party)

    def has_usable_bench_pokemon(self, exclude_pokemon: Optional[Any] = None) -> bool:
        """Check if battler has any healthy, non-active Pokemon available to switch in."""
        for idx, pokemon in enumerate(self.party):
            if exclude_pokemon is not None and pokemon is exclude_pokemon:
                continue
            if idx in self.active_positions:
                continue
            if getattr(pokemon, "current_hp", 0) > 0:
                return True
        return False


@dataclass
class BattleState:
    """Complete state of an ongoing battle"""
    battle_id: str
    battle_type: BattleType
    battle_format: BattleFormat

    # Battlers (either 2 for normal, or 4 for multi battles)
    trainer: Battler  # The player who initiated
    opponent: Battler  # Wild Pokemon, NPC trainer, or other player

    # Multi battle partners (only used when battle_format == MULTI)
    trainer_partner: Optional[Battler] = None  # Partner of the initiating player
    opponent_partner: Optional[Battler] = None  # Partner of the opponent
    raid_allies: List[Battler] = field(default_factory=list)  # Additional player-controlled battlers in raids

    # Battle state
    turn_number: int = 1
    phase: str = 'START'  # START, WAITING_ACTIONS, RESOLVING, FORCED_SWITCH, END
    forced_switch_battler_id: Optional[int] = None  # Which battler must switch (DEPRECATED - use pending_switches)
    forced_switch_position: Optional[int] = None  # Which position (0 or 1 for doubles) to replace (DEPRECATED)
    pending_switches: Dict[int, Dict] = field(default_factory=dict)  # battler_id -> {position, switch_type}
    is_over: bool = False
    winner: Optional[str] = None  # 'trainer', 'opponent', 'draw'
    fled: bool = False
    
    # Field conditions
    weather: Optional[str] = None  # 'sandstorm', 'rain', 'sun', 'snow', 'hail'
    weather_turns: int = 0
    terrain: Optional[str] = None  # 'electric', 'grassy', 'psychic', 'misty'
    terrain_turns: int = 0

    # Overworld weather (persists indefinitely, restored when temporary weather ends)
    overworld_weather: Optional[str] = None  # Weather from the overworld at battle start

    # Rogue Pokemon permanent weather/terrain (returns when override expires)
    rogue_weather: Optional[str] = None
    rogue_terrain: Optional[str] = None
    
    # Field hazards
    trainer_hazards: Dict[str, int] = field(default_factory=dict)  # 'stealth_rock': 1, 'spikes': 3, etc.
    opponent_hazards: Dict[str, int] = field(default_factory=dict)
    
    # Screens and field effects
    trainer_screens: Dict[str, int] = field(default_factory=dict)  # 'reflect': 5, 'light_screen': 3
    opponent_screens: Dict[str, int] = field(default_factory=dict)

    # Trick Room
    trick_room_turns: int = 0
    
    # Turn actions (stored for simultaneous resolution)
    pending_actions: Dict[str, 'BattleAction'] = field(default_factory=dict)  # battler_id -> action
    
    # Battle log
    battle_log: List[str] = field(default_factory=list)
    turn_log: List[str] = field(default_factory=list)  # Current turn's events
    
    # NEW: queue AI replacement to happen AFTER end-of-turn
    pending_ai_switch_index: Optional[int] = None

    # EXP tracking: Record each opponent Pokemon that faints with the active trainer Pokemon index
    fainted_opponents: List[Dict[str, Any]] = field(default_factory=list)  # List of {pokemon, active_trainer_index, battler_id}

    # For wild battles only
    catch_attempted: bool = False
    wild_dazed: bool = False  # True when wild Pokémon has been reduced to a 'dazed' state instead of fainting

    # Ranked metadata
    is_ranked: bool = False
    ranked_context: Dict[str, Any] = field(default_factory=dict)
    mega_evolution_used: set[int] = field(default_factory=set)

    # RP Mode for PvP battles
    rp_mode_active: bool = False  # Whether RP mode is currently enabled
    rp_mode_go_ready: set[int] = field(default_factory=set)  # Battler IDs who have pressed "Go"
    rp_mode_execution_message_id: Optional[int] = None  # Message ID of the "awaiting execution" embed

    def get_all_battlers(self) -> List[Battler]:
        """Get all battlers in this battle (2 for singles/doubles, 4 for multi)"""
        battlers = [self.trainer, self.opponent]
        if self.battle_format == BattleFormat.MULTI:
            if self.trainer_partner:
                battlers.append(self.trainer_partner)
            if self.opponent_partner:
                battlers.append(self.opponent_partner)
        if self.battle_format == BattleFormat.RAID:
            battlers.extend(self.raid_allies)
        return battlers

    def get_team_battlers(self, battler_id: int) -> List[Battler]:
        """Get all battlers on the same team as the given battler_id"""
        if battler_id == self.trainer.battler_id or (self.trainer_partner and battler_id == self.trainer_partner.battler_id):
            team = [self.trainer]
            if self.trainer_partner:
                team.append(self.trainer_partner)
            if self.battle_format == BattleFormat.RAID:
                team.extend(self.raid_allies)
            return team

        for ally in self.raid_allies:
            if battler_id == ally.battler_id:
                team = [self.trainer]
                team.extend(self.raid_allies)
                if self.trainer_partner:
                    team.append(self.trainer_partner)
                return team

        team = [self.opponent]
        if self.opponent_partner:
            team.append(self.opponent_partner)
        return team

    def get_opposing_team_battlers(self, battler_id: int) -> List[Battler]:
        """Get all battlers on the opposing team (excluding eliminated battlers)"""
        if battler_id == self.trainer.battler_id or (self.trainer_partner and battler_id == self.trainer_partner.battler_id):
            team = [self.opponent]
            if self.opponent_partner:
                team.append(self.opponent_partner)
            # Filter out eliminated battlers
            return [b for b in team if not b.is_eliminated]

        for ally in self.raid_allies:
            if battler_id == ally.battler_id:
                team = [self.opponent]
                if self.opponent_partner:
                    team.append(self.opponent_partner)
                # Filter out eliminated battlers
                return [b for b in team if not b.is_eliminated]

        team = [self.trainer]
        if self.trainer_partner:
            team.append(self.trainer_partner)
        if self.battle_format == BattleFormat.RAID:
            team.extend(self.raid_allies)
        # Filter out eliminated battlers
        return [b for b in team if not b.is_eliminated]

    def is_team_defeated(self, battler_id: int) -> bool:
        """Check if a team has been completely defeated"""
        team = self.get_team_battlers(battler_id)
        return all(not b.has_usable_pokemon() for b in team)


class HeldItemManager:
    """Utility helper for held item effects."""

    def __init__(self, items_db, type_chart=None):
        self.items_db = items_db
        self.type_chart = type_chart

    def _is_consumed(self, pokemon, item_id: str) -> bool:
        consumed = getattr(pokemon, '_consumed_items', set())
        return item_id in consumed

    def _consume(self, pokemon, item_id: str):
        consumed = getattr(pokemon, '_consumed_items', set())
        consumed.add(item_id)
        pokemon._consumed_items = consumed

    def consume_item(self, pokemon, item_id: Optional[str] = None):
        """Public wrapper to mark an item as consumed for the given Pokémon."""
        if not item_id:
            item_id = getattr(pokemon, 'held_item', None)
        if not item_id:
            return
        self._consume(pokemon, item_id)

    def _get_item(self, pokemon):
        if not self.items_db:
            return None
        item_id = getattr(pokemon, 'held_item', None)
        if not item_id:
            return None
        if self._is_consumed(pokemon, item_id):
            return None
        return self.items_db.get_item(item_id)

    def _calculate_effectiveness(self, move_type: str, defender) -> float:
        if not move_type or not self.type_chart:
            return 1.0
        defending_types = []
        if hasattr(defender, 'species_data'):
            defending_types = defender.species_data.get('types', [])
        move_type = move_type.lower()
        if hasattr(self.type_chart, 'get_dual_effectiveness'):
            return self.type_chart.get_dual_effectiveness(move_type, defending_types)

        multiplier = 1.0
        for def_type in defending_types:
            multiplier *= self.type_chart.get_effectiveness(move_type, def_type)
        return multiplier

    def _apply_damage_reduction(self, defender, move_data, damage: int) -> tuple[int, Optional[str]]:
        item = self._get_item(defender)
        if not item:
            return damage, None

        effect = dict(item.get('effect_data') or {})
        reduction = effect.get('damage_reduction')
        move_type = (move_data.get('type') or '').lower()
        reduction_type = (effect.get('type') or '').lower()
        if not reduction or not move_type or move_type != reduction_type:
            return damage, None

        requires_super_effective = effect.get('requires_super_effective', True)
        if requires_super_effective:
            effectiveness = self._calculate_effectiveness(move_type, defender)
            if effectiveness <= 1.0:
                return damage, None

        reduced_damage = max(1, int(math.ceil(damage * reduction)))
        if effect.get('one_time_use'):
            self._consume(defender, item['id'])

        item_name = item.get('name', item['id'])
        return reduced_damage, f"{defender.species_name}'s {item_name} weakened the attack!"

    def _get_protect_status(self, pokemon) -> Optional[str]:
        """Return the active protect-like volatile status if present."""
        status_manager = getattr(pokemon, 'status_manager', None)
        if not status_manager:
            return None
        statuses = getattr(status_manager, 'volatile_statuses', {})
        for status_name in ('protect', 'kings_shield', 'detect'):
            if status_name in statuses:
                return status_name
        return None

    def _apply_kings_shield_attack_drop(self, attacker, move_data, messages: list[str]) -> None:
        """Apply King's Shield contact penalty if applicable."""
        flags = move_data.get('flags', {}) if isinstance(move_data, dict) else {}
        is_contact = isinstance(flags, dict) and flags.get('contact')
        if not is_contact or move_data.get('category') == 'status':
            return

        if not hasattr(attacker, 'stat_stages'):
            attacker.stat_stages = {
                'attack': 0, 'defense': 0, 'sp_attack': 0,
                'sp_defense': 0, 'speed': 0, 'evasion': 0, 'accuracy': 0
            }
        attacker.stat_stages['attack'] = max(-6, attacker.stat_stages['attack'] - 2)
        messages.append(f"{attacker.species_name}'s Attack harshly fell after hitting the shield!")

    def _maybe_cure_status(self, pokemon, effect: Dict[str, Any]) -> Optional[str]:
        cures = effect.get('cures')
        trigger = effect.get('trigger')
        if not cures or trigger not in (None, 'end_of_turn'):
            return None

        normalized = {str(s).lower() for s in cures}
        status_manager = getattr(pokemon, 'status_manager', None)
        cured_status = None

        if status_manager and getattr(status_manager, 'major_status', None):
            major = status_manager.major_status
            if major and major.status_type in normalized:
                cured_status = major.status_type
                status_manager.major_status = None

        if not cured_status and status_manager:
            to_remove = [name for name in status_manager.volatile_statuses if name in normalized]
            if to_remove:
                status_manager.remove_status(to_remove[0])
                cured_status = to_remove[0]

        if not cured_status:
            raw_status = getattr(pokemon, 'status_condition', None)
            if raw_status and str(raw_status).lower() in normalized:
                cured_status = raw_status
                pokemon.status_condition = None

        if not cured_status:
            return None

        readable = cured_status.upper()
        return f"{pokemon.species_name}'s {effect.get('item_name', 'item')} cured {readable}!"

    def _apply_healing(
        self, pokemon, effect: Dict[str, Any], item_name: Optional[str] = None
    ) -> tuple[int, Optional[str]]:
        heal_amount = 0
        if 'heal_amount' in effect:
            heal_amount = int(effect.get('heal_amount', 0))
        elif 'heal_percent' in effect:
            heal_amount = int(round(pokemon.max_hp * (effect.get('heal_percent', 0) / 100.0)))

        if heal_amount <= 0 or getattr(pokemon, 'current_hp', 0) <= 0:
            return 0, None

        old_hp = pokemon.current_hp
        pokemon.current_hp = min(pokemon.max_hp, pokemon.current_hp + heal_amount)
        healed = pokemon.current_hp - old_hp
        if healed <= 0:
            return 0, None

        name = item_name or effect.get('item_name', 'item')
        return healed, f"{pokemon.species_name} restored health with its {name}! (+{healed} HP)"

    # -------- Restrictions / tracking --------
    def check_move_restrictions(self, pokemon, move_data) -> Optional[str]:
        item = self._get_item(pokemon)
        if not item:
            return None
        effect = item.get('effect_data') or {}

        if effect.get('blocks_status_moves') and move_data.get('category') == 'status':
            return f"{pokemon.species_name} can't use status moves while holding {item.get('name', item['id'])}!"

        if effect.get('locks_move'):
            locked = getattr(pokemon, '_choice_locked_move', None)
            move_id = move_data.get('id') or move_data.get('move_id')
            if locked and move_id and move_id != locked:
                move_name = move_data.get('name', move_id).title()
                item_name = item.get('name', item['id'])
                return f"{pokemon.species_name} is locked into {move_name} because of its {item_name}!"
        return None

    def register_move_use(self, pokemon, move_data):
        item = self._get_item(pokemon)
        if not item:
            return
        effect = item.get('effect_data') or {}
        if effect.get('locks_move'):
            move_id = move_data.get('id') or move_data.get('move_id')
            pokemon._choice_locked_move = move_id

    def clear_choice_lock(self, pokemon):
        if hasattr(pokemon, '_choice_locked_move'):
            delattr(pokemon, '_choice_locked_move')

    # -------- Offensive modifiers --------
    def _power_multiplier(self, pokemon, move_data) -> float:
        item = self._get_item(pokemon)
        if not item:
            return 1.0
        effect = item.get('effect_data') or {}
        multiplier = 1.0
        move_type = (move_data.get('type') or '').lower()
        category = move_data.get('category')

        if effect.get('type'):
            if move_type == effect['type'].lower():
                multiplier *= effect.get('power_multiplier', 1.0)
        elif 'power_multiplier' in effect:
            multiplier *= effect.get('power_multiplier', 1.0)

        stat = effect.get('stat')
        stat_mult = effect.get('multiplier', 1.0)
        if stat == 'attack' and category == 'physical':
            multiplier *= stat_mult
        elif stat == 'sp_attack' and category == 'special':
            multiplier *= stat_mult

        return multiplier

    def _defense_multiplier(self, pokemon, move_data) -> float:
        item = self._get_item(pokemon)
        if not item:
            return 1.0
        effect = item.get('effect_data') or {}
        stat = effect.get('stat')
        if stat == 'sp_defense' and move_data.get('category') == 'special':
            return effect.get('multiplier', 1.0)
        return 1.0

    def modify_damage(self, attacker, defender, move_data, damage: int) -> Tuple[int, List[str]]:
        if damage <= 0:
            return damage, []

        messages: List[str] = []
        damage = int(round(damage * self._power_multiplier(attacker, move_data)))
        defense_mult = self._defense_multiplier(defender, move_data)
        if defense_mult > 1:
            damage = max(1, int(math.ceil(damage / defense_mult)))

        damage, reduction_msg = self._apply_damage_reduction(defender, move_data, damage)
        if reduction_msg:
            messages.append(reduction_msg)

        damage, survival_msg = self._try_focus_items(defender, damage)
        if survival_msg:
            messages.append(survival_msg)

        return damage, messages

    def _try_focus_items(self, defender, damage: int) -> Tuple[int, Optional[str]]:
        if damage < defender.current_hp or defender.current_hp <= 0:
            return damage, None
        item = self._get_item(defender)
        if not item:
            return damage, None
        effect = item.get('effect_data') or {}

        trigger = item.get('trigger')
        if trigger and trigger != 'before_damage':
            return damage, None

        prevents_ko = effect.get('prevents_ko') or effect.get('requires_full_hp') or ('activation_chance' in effect)
        if not prevents_ko:
            return damage, None

        if effect.get('requires_full_hp') and defender.current_hp < defender.max_hp:
            return damage, None

        activation = effect.get('activation_chance')
        if activation is not None and random.random() > activation:
            return damage, None

        if defender.current_hp <= 1:
            return damage, None

        damage = defender.current_hp - 1
        item_name = item.get('name', item['id'])
        message = f"{defender.species_name} hung on using its {item_name}!"
        if effect.get('one_time_use'):
            self._consume(defender, item['id'])
        return damage, message

    def apply_after_damage(self, attacker, move_data, dealt_damage: int) -> List[str]:
        item = self._get_item(attacker)
        if not item:
            return []

        # Choice items lock even on misses
        self.register_move_use(attacker, move_data)

        if dealt_damage <= 0:
            return []

        effect = item.get('effect_data') or {}
        messages: List[str] = []

        if effect.get('recoil_percent'):
            recoil = max(1, int(round(attacker.max_hp * (effect['recoil_percent'] / 100.0))))
            attacker.current_hp = max(0, attacker.current_hp - recoil)
            messages.append(f"{attacker.species_name} was hurt by its {item.get('name', item['id'])}! (-{recoil} HP)")

        return messages

    def process_reactive_effects(self, pokemon, move_data, damage_taken: int) -> List[str]:
        item = self._get_item(pokemon)
        if not item:
            return []

        effect = dict(item.get('effect_data') or {})
        effect['item_name'] = item.get('name', item['id'])
        messages: List[str] = []
        consumed = False

        trigger = effect.get('trigger')
        if trigger == 'hp_threshold':
            threshold = effect.get('hp_threshold')
            if threshold is not None:
                try:
                    threshold_value = float(threshold)
                except Exception:
                    threshold_value = None
                if (
                    threshold_value is not None
                    and getattr(pokemon, 'current_hp', 0) > 0
                    and pokemon.current_hp <= pokemon.max_hp * threshold_value
                ):
                    healed, heal_msg = self._apply_healing(pokemon, effect, effect['item_name'])
                    if heal_msg:
                        messages.append(heal_msg)
                        consumed = consumed or effect.get('one_time_use')

        if consumed and effect.get('one_time_use'):
            self._consume(pokemon, item['id'])

        return messages

    def process_end_of_turn(self, pokemon) -> List[str]:
        item = self._get_item(pokemon)
        if not item:
            return []
        effect = dict(item.get('effect_data') or {})
        effect['item_name'] = item.get('name', item['id'])

        messages: List[str] = []
        consumed = False

        cure_msg = self._maybe_cure_status(pokemon, effect)
        if cure_msg:
            messages.append(cure_msg)
            consumed = consumed or effect.get('one_time_use')

        healed, heal_msg = self._apply_healing(pokemon, effect, effect['item_name'])
        if heal_msg:
            messages.append(heal_msg)
            consumed = consumed or effect.get('one_time_use')

        if consumed and effect.get('one_time_use'):
            self._consume(pokemon, item['id'])

        return messages

    def get_speed_multiplier(self, pokemon) -> float:
        item = self._get_item(pokemon)
        if not item:
            return 1.0
        effect = item.get('effect_data') or {}
        if effect.get('stat') == 'speed':
            return effect.get('multiplier', 1.0)
        return 1.0

    def get_priority_effect(self, pokemon, move_data) -> Optional[Dict[str, Any]]:
        """Return priority modification info if the held item provides one."""

        item = self._get_item(pokemon)
        if not item:
            return None

        effect = dict(item.get('effect_data') or {})
        priority_boost = effect.get('priority_boost')
        if not priority_boost:
            return None

        # Trigger conditions
        trigger = effect.get('trigger')
        if trigger == 'hp_threshold':
            threshold = effect.get('hp_threshold')
            if threshold is None:
                return None
            try:
                threshold_value = float(threshold)
            except (TypeError, ValueError):
                return None
            if (
                getattr(pokemon, 'current_hp', 0) <= 0
                or getattr(pokemon, 'max_hp', 0) <= 0
                or pokemon.current_hp > pokemon.max_hp * threshold_value
            ):
                return None

        chance = effect.get('priority_chance')
        if chance is not None:
            try:
                chance_value = float(chance)
            except (TypeError, ValueError):
                chance_value = None
            if chance_value is None or random.random() > chance_value:
                return None

        message_template = effect.get('priority_message')
        message = None
        if message_template:
            message = message_template.format(pokemon=pokemon.species_name)

        return {
            'priority_boost': priority_boost,
            'message': message,
            'consume': effect.get('one_time_use', False),
            'item_id': item.get('id'),
        }

@dataclass
class BattleAction:
    """A single action taken by a battler"""
    action_type: str  # 'move', 'switch', 'item', 'flee'
    battler_id: int

    # For moves
    move_id: Optional[str] = None
    target_position: Optional[int] = None  # Which opponent slot to target
    target_battler_id: Optional[int] = None  # Explicit target battler selection (for raids/multi)
    mega_evolve: bool = False
    pokemon_position: int = 0  # Which of the battler's active Pokemon is acting (for doubles)
    revive_target_battler_id: Optional[int] = None  # For Revival Blessing targeting
    revive_target_party_index: Optional[int] = None  # Party index to revive (supports raids)

    # For switching
    switch_to_position: Optional[int] = None

    # For items
    item_id: Optional[str] = None
    item_target_position: Optional[int] = None  # Which party member gets the item

    # Priority for turn order
    priority: int = 0
    speed: int = 0
    priority_message: Optional[str] = None
    priority_item_id: Optional[str] = None
    priority_consumes_item: bool = False


class BattleEngine:
    """
    Core battle engine that handles all battle types
    """
    
    def __init__(self, moves_db, type_chart, species_db=None, items_db=None):
        """
        Initialize the battle engine
        
        Args:
            moves_db: MovesDatabase instance
            type_chart: Type effectiveness data
            species_db: Optional species database for wild Pokemon generation
        """
        self.moves_db = moves_db
        self.type_chart = type_chart
        self.species_db = species_db
        self.items_db = items_db
        self.held_item_manager = (
            HeldItemManager(items_db, type_chart) if items_db else None
        )
        
        # Initialize enhanced systems
        # Ruleset handler
        self.ruleset_handler = RulesetHandler()
        if ENHANCED_SYSTEMS_AVAILABLE:
            self.calculator = EnhancedDamageCalculator(moves_db, type_chart)
            self.ability_handler = AbilityHandler('data/abilities.json')
            print("✨ Enhanced battle systems loaded!")
        else:
            print("⚠️ Using basic battle calculator")
        
        # Active battles
        self.active_battles: Dict[str, BattleState] = {}
        self.player_manager = None

    @staticmethod
    def map_overworld_weather_to_battle(overworld_weather: Optional[str]) -> Optional[str]:
        """
        Maps overworld weather types to battle weather effects.

        Mapping:
        - Cloudy, Gentle Skies: No weather (None)
        - Heatwave, Sunshine: Harsh sunlight ('sun')
        - Rain, Thunderstorm: Rain ('rain')
        - Sandstorm: Sandstorm ('sandstorm')
        - Snowing, Blizzard: Snow ('snow')

        Args:
            overworld_weather: The weather type from the overworld

        Returns:
            Battle weather string or None if no weather effect
        """
        if not overworld_weather:
            return None

        weather_map = {
            # No effects
            'cloudy': None,
            'gentle_skies': None,
            # Sun
            'heatwave': 'sun',
            'sunshine': 'sun',
            # Rain
            'rain': 'rain',
            'thunder_storm': 'rain',
            # Sandstorm
            'sandstorm': 'sandstorm',
            # Snow
            'snowing': 'snow',
            'blizzard': 'snow',
        }

        return weather_map.get(overworld_weather.lower())

    # ========================
    # Battle Initialization
    # ========================
    
    def start_battle(
        self,
        trainer_id: int,
        trainer_name: str,
        trainer_party: List[Any],
        opponent_party: List[Any],
        battle_type: BattleType,
        battle_format: BattleFormat = BattleFormat.SINGLES,
        opponent_id: Optional[int] = None,
        opponent_name: Optional[str] = None,
        opponent_is_ai: bool = True,
        is_ranked: bool = False,
        ranked_context: Optional[Dict[str, Any]] = None,
        weather_manager: Optional[Any] = None,
        location_id: Optional[str] = None,
        wild_area_state: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        """Universal battle starter"""
        battle_id = str(uuid.uuid4())

        if not trainer_party:
            raise ValueError("Trainer must have at least one Pokémon to start a battle.")
        if not opponent_party:
            raise ValueError("Opponent must have at least one Pokémon to battle.")

        raid_participants = kwargs.get('raid_participants') or []
        raid_opponent_slots = int(kwargs.get("raid_opponent_slots") or 1) if battle_format == BattleFormat.RAID else None

        # In multi battles, each trainer sends out 1 Pokemon (2 total per team)
        # In doubles battles, each trainer sends out 2 Pokemon
        if battle_format == BattleFormat.MULTI:
            active_slot_count = 1
        elif battle_format == BattleFormat.DOUBLES:
            active_slot_count = 2
        elif battle_format == BattleFormat.RAID:
            # For raids, each participant brings one active Pokémon
            active_slot_count = 1
        else:
            active_slot_count = 1

        raid_allies: List[Battler] = []

        # Select first non-fainted Pokemon for trainer
        trainer_active_positions = []
        for i, mon in enumerate(trainer_party):
            if getattr(mon, 'current_hp', 0) > 0:
                trainer_active_positions.append(i)
                if len(trainer_active_positions) >= active_slot_count:
                    break
        if not trainer_active_positions:
            trainer_active_positions = [0]  # Fallback if all fainted

        # Select first non-fainted Pokemon for opponent
        opponent_active_positions = []
        for i, mon in enumerate(opponent_party):
            if getattr(mon, 'current_hp', 0) > 0:
                opponent_active_positions.append(i)
                opponent_slot_cap = raid_opponent_slots if raid_opponent_slots is not None else active_slot_count
                if len(opponent_active_positions) >= opponent_slot_cap:
                    break
        if not opponent_active_positions:
            opponent_active_positions = [0]  # Fallback if all fainted

        # Create trainer battler
        if battle_format == BattleFormat.RAID and raid_participants:
            raid_battlers: List[Battler] = []
            for participant in raid_participants:
                p_party = participant.get('party') or []
                p_name = participant.get('trainer_name') or trainer_name
                p_id = participant.get('user_id') or trainer_id
                p_active = []
                for idx, mon in enumerate(p_party):
                    if getattr(mon, 'current_hp', 0) > 0:
                        p_active.append(idx)
                        break
                if not p_active and p_party:
                    p_active = [0]

                raid_battlers.append(
                    Battler(
                        battler_id=p_id,
                        battler_name=p_name,
                        party=p_party,
                        active_positions=p_active or [0],
                        is_ai=False,
                        can_switch=True,
                        can_use_items=True,
                        can_flee=False,
                    )
                )

            if not raid_battlers:
                raise ValueError("No raid participants provided for raid battle.")

            trainer = raid_battlers[0]
            raid_allies = raid_battlers[1:]
        else:
            trainer = Battler(
                battler_id=trainer_id,
                battler_name=trainer_name,
                party=trainer_party,
                active_positions=trainer_active_positions,
                is_ai=False,
                can_switch=True,
                can_use_items=True,
                can_flee=(battle_type == BattleType.WILD)
            )
        
        # Create opponent battler
        if opponent_id is None:
            opponent_id = -1 if battle_type == BattleType.WILD else -random.randint(1000, 9999)
        
        opponent = Battler(
            battler_id=opponent_id,
            battler_name=opponent_name or ("Wild Pokémon" if battle_type == BattleType.WILD else "Opponent"),
            party=opponent_party,
            active_positions=opponent_active_positions,
            is_ai=opponent_is_ai,
            can_switch=(battle_type != BattleType.WILD),  # Wild Pokemon can't switch
            can_use_items=(battle_type == BattleType.TRAINER),
            can_flee=False,
            trainer_class=kwargs.get('trainer_class'),
            prize_money=kwargs.get('prize_money', 0)
        )
        
        # Create battle state
        battle = BattleState(
            battle_id=battle_id,
            battle_type=battle_type,
            battle_format=battle_format,
            trainer=trainer,
            opponent=opponent,
            raid_allies=raid_allies,
            is_ranked=is_ranked,
            ranked_context=ranked_context or {}
        )
        if raid_opponent_slots is not None:
            battle.raid_opponent_slots = raid_opponent_slots

        # Set overworld weather if weather manager and location are provided
        if weather_manager and location_id:
            try:
                overworld_weather = weather_manager.get_weather_for_context(
                    location_id=location_id,
                    wild_area_state=wild_area_state
                )
                battle_weather = self.map_overworld_weather_to_battle(overworld_weather)
                if battle_weather:
                    battle.weather = battle_weather
                    battle.overworld_weather = battle_weather
                    battle.weather_turns = 0  # Indefinite duration for overworld weather
                    battle.turn_log.append(f"The battle is affected by {battle_weather}!")
            except Exception as e:
                # Don't let weather errors crash battle initialization
                print(f"Warning: Failed to set overworld weather: {e}")

        for battler in battle.get_all_battlers():
            for mon in battler.get_active_pokemon():
                self._mark_first_turn_entry(mon)
        
        # Trigger entry abilities
        # Trigger entry abilities and capture messages
        try:
            battle.entry_messages = self._trigger_entry_abilities(battle)
        except Exception:
            battle.entry_messages = []

        # Default to Standard NatDex (nat)
        try:
            battle.ruleset = self.ruleset_handler.resolve_default_ruleset('nat')
        except Exception:
            battle.ruleset = 'standardnatdex'

        # Store battle
        self.active_battles[battle_id] = battle
        
        return battle_id

    def _get_action_pokemon(self, battler: Battler, action: BattleAction) -> Optional[Any]:
        if not battler:
            return None
        active_idx = getattr(action, 'pokemon_position', 0)
        if active_idx >= len(battler.active_positions):
            active_idx = 0
        party_index = battler.active_positions[active_idx] if battler.active_positions else 0
        if party_index >= len(battler.party):
            return None
        return battler.party[party_index]

    @staticmethod
    def _mark_first_turn_entry(pokemon: Any) -> None:
        if pokemon:
            setattr(pokemon, "_first_turn_active", True)

    @staticmethod
    def _clear_first_turn_flags(active_pokemon: List[Any]) -> None:
        for mon in active_pokemon:
            if getattr(mon, "_first_turn_active", False):
                mon._first_turn_active = False

    @staticmethod
    def _normalize_name(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", name.lower())

    def _trainer_has_mega(self, battler_id: int) -> bool:
        if not self.player_manager:
            return False
        trainer = self.player_manager.get_player(battler_id)
        if not trainer:
            return False
        if not getattr(trainer, "has_omni_ring", False):
            return False
        gimmicks = getattr(trainer, "omni_ring_gimmicks", []) or []
        return any(str(gimmick).lower() == "mega" for gimmick in gimmicks)

    @staticmethod
    def _extract_mega_target(item_data: Dict[str, Any]) -> Optional[str]:
        description = item_data.get("description") or ""
        match = re.search(r"Have ([^,]+?) hold it", description, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    @staticmethod
    def _build_mega_name(target_name: str, item_id: str) -> str:
        suffix = ""
        if item_id.endswith("_x"):
            suffix = " X"
        elif item_id.endswith("_y"):
            suffix = " Y"
        return f"Mega {target_name}{suffix}"

    def get_mega_evolution_name(
        self,
        battle: Optional[BattleState],
        battler_id: int,
        pokemon: Any,
    ) -> Optional[str]:
        if not pokemon or getattr(pokemon, "current_hp", 0) <= 0:
            return None
        if not self._trainer_has_mega(battler_id):
            return None
        if battle and battler_id in battle.mega_evolution_used:
            return None
        if getattr(pokemon, "is_mega_evolved", False):
            return None
        item_id = getattr(pokemon, "held_item", None)
        if not item_id or not self.items_db:
            return None
        item_data = self.items_db.get_item(item_id)
        if not item_data:
            return None
        target_name = self._extract_mega_target(item_data)
        if not target_name:
            return None
        if self._normalize_name(pokemon.species_name) != self._normalize_name(target_name):
            return None
        return self._build_mega_name(target_name, item_id)

    def _apply_mega_evolution(self, pokemon: Any, mega_name: str) -> None:
        if not pokemon or getattr(pokemon, "is_mega_evolved", False):
            return
        pokemon._base_species_name = getattr(pokemon, "_base_species_name", pokemon.species_name)
        pokemon._base_form = getattr(pokemon, "_base_form", getattr(pokemon, "form", None))
        pokemon.is_mega_evolved = True
        pokemon.mega_display_name = mega_name
        pokemon.species_name = mega_name

    def _revert_mega_evolutions(self, battle: BattleState) -> None:
        for battler in battle.get_all_battlers():
            for mon in getattr(battler, "party", []):
                if getattr(mon, "is_mega_evolved", False):
                    base_name = getattr(mon, "_base_species_name", None)
                    base_form = getattr(mon, "_base_form", getattr(mon, "form", None))
                    if base_name:
                        mon.species_name = base_name
                    mon.form = base_form
                    mon.is_mega_evolved = False
                    for attr in ("mega_display_name", "_base_species_name", "_base_form"):
                        if hasattr(mon, attr):
                            delattr(mon, attr)

    def _record_faint(self, battler: Optional[Battler], pokemon: Any):
        if not battler or battler.is_ai:
            return
        if not self.player_manager:
            return
        self.player_manager.record_faint(pokemon)

    def _record_opponent_faint_for_exp(
        self,
        battle: BattleState,
        fainted_pokemon: Any,
        fainted_battler: Battler,
        attacker_battler: Optional[Battler] = None
    ):
        """
        Record an opponent Pokemon faint for EXP calculation.
        This tracks which opponent Pokemon fainted and which player Pokemon was active.

        Args:
            battle: The battle state
            fainted_pokemon: The Pokemon that fainted
            fainted_battler: The battler who owns the fainted Pokemon
            attacker_battler: The battler whose Pokemon caused the faint (optional)
        """
        # Only track if the fainted battler is an opponent (AI or wild)
        # and not a player's Pokemon
        is_opponent_faint = fainted_battler.is_ai or fainted_battler == battle.opponent

        if not is_opponent_faint:
            return

        # Determine which player Pokemon was active
        # If attacker_battler is provided and is a player, use their active Pokemon
        if attacker_battler and not attacker_battler.is_ai:
            active_trainer_index = attacker_battler.active_positions[0] if attacker_battler.active_positions else 0
            trainer_battler_id = attacker_battler.battler_id
        else:
            # Otherwise, use the main trainer's active Pokemon
            active_trainer_index = battle.trainer.active_positions[0] if battle.trainer.active_positions else 0
            trainer_battler_id = battle.trainer.battler_id

        # Record the faint for EXP calculation
        battle.fainted_opponents.append({
            'pokemon': fainted_pokemon,
            'active_trainer_index': active_trainer_index,
            'trainer_battler_id': trainer_battler_id
        })

    def start_wild_battle(
        self,
        trainer_id: int,
        trainer_name: str,
        trainer_party: List[Any],
        wild_pokemon: Any,
        weather_manager: Optional[Any] = None,
        location_id: Optional[str] = None,
        wild_area_state: Optional[Dict[str, Any]] = None
    ) -> str:
        """Convenience method for wild battles"""
        return self.start_battle(
            trainer_id=trainer_id,
            trainer_name=trainer_name,
            trainer_party=trainer_party,
            opponent_party=[wild_pokemon],
            battle_type=BattleType.WILD,
            opponent_name=f"Wild {wild_pokemon.species_name}",
            weather_manager=weather_manager,
            location_id=location_id,
            wild_area_state=wild_area_state
        )
    
    def start_trainer_battle(
        self,
        trainer_id: int,
        trainer_name: str,
        trainer_party: List[Any],
        npc_party: List[Any],
        npc_name: str,
        npc_class: str,
        prize_money: int,
        battle_format: BattleFormat = BattleFormat.SINGLES,
        is_ranked: bool = False,
        ranked_context: Optional[Dict[str, Any]] = None,
        weather_manager: Optional[Any] = None,
        location_id: Optional[str] = None,
        wild_area_state: Optional[Dict[str, Any]] = None
    ) -> str:
        """Convenience method for NPC trainer battles"""
        return self.start_battle(
            trainer_id=trainer_id,
            trainer_name=trainer_name,
            trainer_party=trainer_party,
            opponent_party=npc_party,
            battle_type=BattleType.TRAINER,
            battle_format=battle_format,
            opponent_name=npc_name,
            trainer_class=npc_class,
            prize_money=prize_money,
            is_ranked=is_ranked,
            ranked_context=ranked_context,
            weather_manager=weather_manager,
            location_id=location_id,
            wild_area_state=wild_area_state
        )
    
    def start_pvp_battle(
        self,
        trainer1_id: int,
        trainer1_name: str,
        trainer1_party: List[Any],
        trainer2_id: int,
        trainer2_name: str,
        trainer2_party: List[Any],
        battle_format: BattleFormat = BattleFormat.SINGLES,
        is_ranked: bool = False,
        ranked_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Convenience method for PvP battles"""
        return self.start_battle(
            trainer_id=trainer1_id,
            trainer_name=trainer1_name,
            trainer_party=trainer1_party,
            opponent_party=trainer2_party,
            battle_type=BattleType.PVP,
            opponent_id=trainer2_id,
            opponent_name=trainer2_name,
            opponent_is_ai=False,
            battle_format=battle_format,
            is_ranked=is_ranked,
            ranked_context=ranked_context
        )

    def start_multi_battle(
        self,
        trainer1_id: int,
        trainer1_name: str,
        trainer1_party: List[Any],
        partner1_id: int,
        partner1_name: str,
        partner1_party: List[Any],
        partner1_is_ai: bool,
        trainer2_id: int,
        trainer2_name: str,
        trainer2_party: List[Any],
        partner2_id: int,
        partner2_name: str,
        partner2_party: List[Any],
        partner2_is_ai: bool,
        is_ranked: bool = False,
        ranked_context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        """
        Start a multi battle (2v2 with partners)

        Args:
            trainer1_id: ID of first trainer (team 1 leader)
            trainer1_name: Name of first trainer
            trainer1_party: Pokemon party for trainer 1
            partner1_id: ID of trainer 1's partner
            partner1_name: Name of trainer 1's partner
            partner1_party: Pokemon party for partner 1
            partner1_is_ai: Whether partner 1 is AI controlled
            trainer2_id: ID of second trainer (team 2 leader)
            trainer2_name: Name of second trainer
            trainer2_party: Pokemon party for trainer 2
            partner2_id: ID of trainer 2's partner
            partner2_name: Name of trainer 2's partner
            partner2_party: Pokemon party for partner 2
            partner2_is_ai: Whether partner 2 is AI controlled
            is_ranked: Whether this is a ranked battle
            ranked_context: Additional ranked battle metadata
        """
        battle_id = str(uuid.uuid4())

        if not all([trainer1_party, partner1_party, trainer2_party, partner2_party]):
            raise ValueError("All trainers must have at least one Pokémon.")

        # Each trainer in multi battle sends out 1 Pokemon
        active_slot_count = 1

        # Helper function to get starting positions
        def get_starting_positions(party):
            positions = []
            for i, mon in enumerate(party):
                if getattr(mon, 'current_hp', 0) > 0:
                    positions.append(i)
                    if len(positions) >= active_slot_count:
                        break
            return positions if positions else [0]

        # Create all four battlers
        trainer1 = Battler(
            battler_id=trainer1_id,
            battler_name=trainer1_name,
            party=trainer1_party,
            active_positions=get_starting_positions(trainer1_party),
            is_ai=False,
            can_switch=True,
            can_use_items=True,
            can_flee=False
        )

        partner1 = Battler(
            battler_id=partner1_id,
            battler_name=partner1_name,
            party=partner1_party,
            active_positions=get_starting_positions(partner1_party),
            is_ai=partner1_is_ai,
            can_switch=True,
            can_use_items=True,
            can_flee=False,
            trainer_class=kwargs.get('partner1_class'),
            prize_money=kwargs.get('partner1_prize', 0)
        )

        trainer2 = Battler(
            battler_id=trainer2_id,
            battler_name=trainer2_name,
            party=trainer2_party,
            active_positions=get_starting_positions(trainer2_party),
            is_ai=partner2_is_ai and kwargs.get('is_pve', False),  # In PvP both team leaders are human
            can_switch=True,
            can_use_items=True,
            can_flee=False
        )

        partner2 = Battler(
            battler_id=partner2_id,
            battler_name=partner2_name,
            party=partner2_party,
            active_positions=get_starting_positions(partner2_party),
            is_ai=partner2_is_ai,
            can_switch=True,
            can_use_items=True,
            can_flee=False,
            trainer_class=kwargs.get('partner2_class'),
            prize_money=kwargs.get('partner2_prize', 0)
        )

        # Determine battle type (PvP if all humans, otherwise TRAINER for PvE)
        battle_type = BattleType.PVP if not (partner1_is_ai or partner2_is_ai) else BattleType.TRAINER

        # Create battle state
        battle = BattleState(
            battle_id=battle_id,
            battle_type=battle_type,
            battle_format=BattleFormat.MULTI,
            trainer=trainer1,
            opponent=trainer2,
            trainer_partner=partner1,
            opponent_partner=partner2,
            is_ranked=is_ranked,
            ranked_context=ranked_context or {}
        )

        # Trigger entry abilities
        try:
            battle.entry_messages = self._trigger_entry_abilities(battle)
        except Exception:
            battle.entry_messages = []

        # Set ruleset
        try:
            battle.ruleset = self.ruleset_handler.resolve_default_ruleset('nat')
        except Exception:
            battle.ruleset = 'standardnatdex'

        # Store battle
        self.active_battles[battle_id] = battle

        return battle_id

    # ========================
    # Ability System
    # ========================
    
    def _trigger_entry_abilities(self, battle: BattleState) -> list[str]:
        """Trigger abilities when Pokemon enter the field"""
        if not ENHANCED_SYSTEMS_AVAILABLE:
            return []
        
        messages = []
        
        # Trigger for all active Pokemon
        for pokemon in battle.trainer.get_active_pokemon():
            ability_msgs = self.ability_handler.trigger_on_entry(pokemon, battle)
            messages.extend(ability_msgs)
            messages.extend(self._apply_entry_hazards(battle, battle.trainer, pokemon))

        for pokemon in battle.opponent.get_active_pokemon():
            ability_msgs = self.ability_handler.trigger_on_entry(pokemon, battle)
            messages.extend(ability_msgs)
            messages.extend(self._apply_entry_hazards(battle, battle.opponent, pokemon))

        return messages

    def _apply_start_of_turn_passives(self, battle: BattleState) -> list[str]:
        """Handle start-of-turn passive ability upkeep (e.g., Schooling)."""
        if not ENHANCED_SYSTEMS_AVAILABLE:
            return []

        messages: List[str] = []
        for battler in battle.get_all_battlers():
            if battler.is_eliminated:
                continue
            for mon in battler.get_active_pokemon():
                passive_msgs = self.ability_handler.update_form_passives(mon)
                messages.extend(passive_msgs)

        return messages

    def _maybe_queue_hp_switch(self, battle: BattleState, battler: Battler, pokemon: Any) -> Optional[str]:
        """Queue a forced switch for Emergency Exit / Wimp Out if HP is low enough."""
        if not ENHANCED_SYSTEMS_AVAILABLE or not self.ability_handler:
            return None

        ability_id = getattr(pokemon, 'ability', None)
        is_emergency_exit = self.ability_handler.ability_matches(pokemon, 'emergencyexit')
        is_wimp_out = self.ability_handler.ability_matches(pokemon, 'wimpout')
        if not (is_emergency_exit or is_wimp_out):
            return None

        ability = self.ability_handler.get_ability(ability_id) or {}
        threshold = ability.get('threshold', 0.5)

        max_hp = getattr(pokemon, 'max_hp', 0) or 0
        if max_hp <= 0:
            return None

        # Reset the flag if the Pokemon recovered above the threshold
        if getattr(pokemon, '_hp_switch_triggered', False) and pokemon.current_hp > max_hp * threshold:
            pokemon._hp_switch_triggered = False

        if getattr(pokemon, 'current_hp', 0) <= 0:
            return None
        if pokemon.current_hp > max_hp * threshold:
            return None
        if getattr(pokemon, '_hp_switch_triggered', False):
            return None

        # Must have a bench Pokemon to swap into
        has_replacement = any(
            idx not in battler.active_positions and getattr(p, 'current_hp', 0) > 0
            for idx, p in enumerate(battler.party)
        )
        if not has_replacement:
            return None

        # Find the active position for this Pokemon
        active_position = None
        for pos_idx, party_idx in enumerate(battler.active_positions):
            if party_idx < len(battler.party) and battler.party[party_idx] is pokemon:
                active_position = pos_idx
                break

        if active_position is None:
            return None

        pokemon._hp_switch_triggered = True

        if battler.battler_id not in battle.pending_switches:
            battle.pending_switches[battler.battler_id] = {
                'position': active_position,
                'switch_type': 'FORCED'
            }
        battle.phase = 'FORCED_SWITCH'
        if not battle.forced_switch_battler_id:
            battle.forced_switch_battler_id = battler.battler_id
            battle.forced_switch_position = active_position

        ability_name = ability.get('name', ability_id) or ability_id
        return f"{pokemon.species_name}'s {ability_name} activated!"


    # ========================
    # Action Registration
    # ========================
    
    def register_action(self, battle_id: str, battler_id: int, action: BattleAction) -> Dict:
        """
        Register an action for a battler
        
        Returns:
            Status dict with success/error
        """
        battle = self.active_battles.get(battle_id)
        if not battle:
            return {"error": "Battle not found"}

        if getattr(battle, "scripted_locked", False):
            return {"error": "The dream holds you in place."}
        
        # NEW CODE: Check if forced switch is required
        if battle.phase in ['FORCED_SWITCH', 'VOLT_SWITCH']:
            if battle.forced_switch_battler_id == battler_id:
                if action.action_type != 'switch':
                    return {"error": "You must switch to another Pokémon!"}

                # For VOLT_SWITCH, execute the switch and process end-of-turn immediately
                is_volt_switch = battle.phase == 'VOLT_SWITCH'

                # Execute the switch
                switch_result = self._execute_switch(battle, action, forced=True)

                # Clear forced switch state after valid switch action
                battle.phase = 'WAITING_ACTIONS'
                battle.forced_switch_battler_id = None

                # If this was a volt switch, process end-of-turn effects that were skipped
                if is_volt_switch:
                    eot_messages = self._process_end_of_turn(battle)
                    auto_switch_events = self.auto_switch_if_forced_ai(battle)

                    battle.turn_log.extend(eot_messages)

                    # Return the switch result with end-of-turn messages
                    return {
                        "success": True,
                        "volt_switch_complete": True,
                        "switch_messages": switch_result.get("messages", []),
                        "eot_messages": eot_messages,
                        "auto_switch_events": auto_switch_events,
                        "ready_to_resolve": False  # Turn is already resolved
                    }

                # For regular forced switches, just return success
                return {
                    "success": True,
                    "forced_switch_complete": True,
                    "switch_messages": switch_result.get("messages", []),
                    "ready_to_resolve": False
                }
            # If it's not the forced switch battler, don't allow actions yet
            elif battler_id != battle.forced_switch_battler_id:
                return {"error": "Waiting for opponent to switch..."}
        
        if battle.is_over:
            return {"error": "Battle is already over"}
        
        # Validate battler
        valid_battler_ids = [b.battler_id for b in battle.get_all_battlers()]

        if battler_id not in valid_battler_ids:
            return {"error": "Invalid battler ID"}

        battler = self._get_battler_by_id(battle, battler_id)
        if battler and not battler.is_ai and action.action_type == 'move':
            active_pokemon = self._get_action_pokemon(battler, action)
            friendship_value = getattr(active_pokemon, 'friendship', 20) if active_pokemon else 20
            obey_threshold = (
                getattr(self.player_manager, 'FRIENDSHIP_OBEY_THRESHOLD', 10)
                if self.player_manager
                else 10
            )
            if friendship_value <= obey_threshold:
                action.action_type = 'disobey'
                action.move_id = None

        # Store action with composite key for doubles/multi (battler_id_position)
        if battle.battle_format in [BattleFormat.DOUBLES, BattleFormat.MULTI, BattleFormat.RAID]:
            action_key = f"{battler_id}_{action.pokemon_position}"
        else:
            action_key = str(battler_id)
        battle.pending_actions[action_key] = action

        # Check if we have all actions needed
        # For doubles/multi, we need actions from all active Pokemon
        if battle.battle_format in [BattleFormat.DOUBLES, BattleFormat.MULTI, BattleFormat.RAID]:
            required_action_keys = []

            # Collect actions needed from all non-AI, non-eliminated battlers with usable Pokemon
            for battler in battle.get_all_battlers():
                if not battler.is_ai and not battler.is_eliminated and battler.has_usable_pokemon():
                    num_active = len(battler.get_active_pokemon())
                    for pos in range(num_active):
                        required_action_keys.append(f"{battler.battler_id}_{pos}")

            all_actions_ready = all(key in battle.pending_actions for key in required_action_keys)
            waiting_for = [key for key in required_action_keys if key not in battle.pending_actions]
        else:
            # Singles - simple battler_id check
            required_actions = []
            if not battle.trainer.is_ai and not battle.trainer.is_eliminated and battle.trainer.has_usable_pokemon():
                required_actions.append(str(battle.trainer.battler_id))
            if not battle.opponent.is_ai and not battle.opponent.is_eliminated and battle.opponent.has_usable_pokemon():
                required_actions.append(str(battle.opponent.battler_id))

            all_actions_ready = all(str(rid) in battle.pending_actions for rid in required_actions)
            waiting_for = [rid for rid in required_actions if str(rid) not in battle.pending_actions]

        # Check if RP mode is active for PvP battles
        if all_actions_ready and battle.rp_mode_active and battle.battle_type == BattleType.PVP:
            # In RP mode, don't resolve immediately - wait for both players to press "Go"
            return {
                "success": True,
                "waiting_for": waiting_for,
                "ready_to_resolve": False,
                "rp_mode_waiting": True  # Signal that we're waiting for RP mode execution
            }

        return {
            "success": True,
            "waiting_for": waiting_for,
            "ready_to_resolve": all_actions_ready
        }
    
    def generate_ai_action(self, battle_id: str, battler_id: int, pokemon_position: int = 0) -> BattleAction:
        """
        Generate an AI action for a specific Pokemon

        Args:
            battle_id: The battle ID
            battler_id: The battler's ID
            pokemon_position: Which active Pokemon (0 or 1 for doubles)

        Returns:
            BattleAction for the specified Pokemon
        """
        battle = self.active_battles.get(battle_id)
        if not battle:
            return None

        # Find the battler
        battler = self._get_battler_by_id(battle, battler_id)
        active_pokemon_list = battler.get_active_pokemon()

        if pokemon_position >= len(active_pokemon_list):
            return None

        active_pokemon = active_pokemon_list[pokemon_position]

        if getattr(active_pokemon, "scripted_ai", None) == "ambipom_raid":
            return self._generate_ambipom_ai_action(battle, battler_id, pokemon_position, active_pokemon)

        # Smarter AI: Categorize moves and choose strategically
        usable_moves = [m for m in active_pokemon.moves if m['pp'] > 0]
        if not usable_moves:
            # Struggle
            return BattleAction(
                action_type='move',
                battler_id=battler_id,
                move_id='struggle',
                target_position=0,
                pokemon_position=pokemon_position
            )

        # Check for ineffective and failed moves to avoid
        ineffective_moves = set()
        failed_moves = {}
        pokemon_key = f"{battler_id}_{id(active_pokemon)}"

        if hasattr(battle, 'ai_ineffective_moves'):
            ineffective_moves = battle.ai_ineffective_moves.get(pokemon_key, set())

        if hasattr(battle, 'ai_failed_moves'):
            failed_moves = battle.ai_failed_moves.get(pokemon_key, {})

        # Get opposing Pokemon for type effectiveness checking
        opposing_battlers = battle.get_opposing_team_battlers(battler_id)
        active_opponents = []
        for opp in opposing_battlers:
            for idx, mon in enumerate(opp.get_active_pokemon()):
                active_opponents.append((opp, idx, mon))

        # Categorize moves with type effectiveness consideration
        offensive_moves = []
        super_effective_moves = []
        support_moves = []
        setup_moves = []

        for move in usable_moves:
            # Skip moves that have been ineffective
            if move['move_id'] in ineffective_moves:
                continue

            # Skip moves that have failed multiple times (2+ times)
            if failed_moves.get(move['move_id'], 0) >= 2:
                continue

            move_data = self.moves_db.get_move(move['move_id'])
            if not move_data:
                continue

            category = move_data.get('category', 'status')
            target_type = move_data.get('target', 'single')

            if category in ['physical', 'special']:
                # Check type effectiveness against opponents
                move_type = move_data.get('type', 'normal')
                is_usable = False
                is_super_effective = False

                for _, _, opponent_mon in active_opponents:
                    if hasattr(opponent_mon, 'species_data') and 'types' in opponent_mon.species_data:
                        defender_types = opponent_mon.species_data['types']
                        effectiveness = self.calculator._get_type_effectiveness(move_type, defender_types)

                        # Don't use completely ineffective moves (0x damage like Normal on Ghost)
                        if effectiveness > 0:
                            is_usable = True

                        # Track if move is super effective against any opponent
                        if effectiveness >= 2.0:
                            is_super_effective = True
                    else:
                        # If we can't determine types, assume move is usable
                        is_usable = True

                # Only add offensive moves that can hit at least one opponent
                if is_usable:
                    offensive_moves.append(move)
                    if is_super_effective:
                        super_effective_moves.append(move)
            elif target_type in ['ally', 'all_allies'] or move['move_id'] in ['helping_hand', 'protect', 'detect', 'kings_shield']:
                support_moves.append(move)
            elif target_type in ['self', 'user_field']:
                setup_moves.append(move)
            else:
                # Other status moves (e.g., field effects)
                setup_moves.append(move)

        # Decision logic with type awareness
        # Prefer super-effective moves highly (60% weight)
        # Then other offensive moves (30% weight)
        # Then support/setup (10% weight)
        ally_active = battler.get_active_pokemon()
        has_allies = len(ally_active) > 1

        choice_pool = []

        # Heavily favor super-effective moves
        if super_effective_moves:
            choice_pool.extend(super_effective_moves * 6)  # 60% weight

        # Add other offensive moves
        if offensive_moves:
            choice_pool.extend(offensive_moves * 3)  # 30% weight

        # Support moves only with allies and early game
        if support_moves and has_allies and battle.turn_number <= 3:
            choice_pool.extend(support_moves)  # 10% weight

        # Setup on turn 1 only
        if setup_moves and battle.turn_number == 1:
            choice_pool.extend(setup_moves)

        # Fallback to any usable move (shouldn't happen often with type checking)
        if not choice_pool:
            choice_pool = usable_moves if usable_moves else [m for m in active_pokemon.moves if m['pp'] > 0]

        chosen_move = random.choice(choice_pool)

        # Determine target based on move's target type
        move_data = self.moves_db.get_move(chosen_move['move_id'])
        target_type = move_data.get('target', 'single') if move_data else 'single'

        # Select target based on move type
        target_battler_id = None
        if target_type in ['ally', 'all_allies']:
            # Target an ally (other Pokemon on same team)
            ally_active = battler.get_active_pokemon()
            if len(ally_active) > 1:
                # Pick the other Pokemon (not self)
                other_positions = [i for i in range(len(ally_active)) if i != pokemon_position]
                target_pos = random.choice(other_positions) if other_positions else pokemon_position
            else:
                target_pos = 0  # Only one Pokemon, target self
            target_battler_id = battler_id
        elif target_type in ['self', 'user_field', 'entire_field', 'enemy_field']:
            # Moves that don't need specific targeting
            target_pos = 0
            target_battler_id = battler_id
        else:
            # Target an opposing Pokemon (default for damaging moves)
            opposing_battlers = battle.get_opposing_team_battlers(battler_id)
            active_opponents = []
            for opp in opposing_battlers:
                for idx, mon in enumerate(opp.get_active_pokemon()):
                    active_opponents.append((opp, idx, mon))

            if active_opponents and target_type == 'single':
                # Pick random target for more varied battles
                target_battler, target_pos, _ = random.choice(active_opponents)
                target_battler_id = target_battler.battler_id
            elif active_opponents:
                # Spread moves don't need explicit targeting; just pick first for reference
                target_battler, target_pos, _ = active_opponents[0]
                target_battler_id = target_battler.battler_id
            else:
                target_pos = 0

        return BattleAction(
            action_type='move',
            battler_id=battler_id,
            move_id=chosen_move['move_id'],
            target_position=target_pos,
            target_battler_id=target_battler_id,
            pokemon_position=pokemon_position
        )

    def _generate_ambipom_ai_action(
        self,
        battle: BattleState,
        battler_id: int,
        pokemon_position: int,
        active_pokemon,
    ) -> BattleAction:
        preferred_attacks = ["double_hit", "dual_chop"]
        rally_move = "rally_cry"
        support_moves = ["tail_whip"]

        battler = self._get_battler_by_id(battle, battler_id)
        active_allies = battler.get_active_pokemon()
        aipom_count = sum(1 for mon in active_allies if getattr(mon, "species_name", "").lower() == "aipom")

        # Get valid targets from player positions
        opponent_battler = battle.trainer if battler == battle.opponent else battle.opponent
        active_opponents = opponent_battler.get_active_pokemon()
        valid_targets = [i for i, mon in enumerate(active_opponents) if mon and mon.current_hp > 0]

        # Smart targeting: Choose the opponent that will take the most damage
        target_position = 0
        if valid_targets and ENHANCED_SYSTEMS_AVAILABLE:
            max_damage = 0
            best_target = valid_targets[0]

            # Test damage against each valid target
            for target_idx in valid_targets:
                target_mon = active_opponents[target_idx]
                # Use double_hit as the test move since it's Ambipom's preferred move
                test_move_id = preferred_attacks[0] if preferred_attacks else "tackle"
                test_damage, _, _, _ = self.calculator.calculate_damage_with_effects(
                    active_pokemon, target_mon, test_move_id,
                    weather=battle.weather,
                    terrain=battle.terrain,
                    battle_state=battle
                )

                # Add some randomness (±20%) to avoid always targeting the same player
                test_damage = test_damage * random.uniform(0.8, 1.2)

                if test_damage > max_damage:
                    max_damage = test_damage
                    best_target = target_idx

            target_position = best_target
        elif valid_targets:
            # Fallback to random if enhanced systems not available
            target_position = random.choice(valid_targets)
        else:
            target_position = 0

        rally_move_data = next(
            (move for move in active_pokemon.moves if move["move_id"] == rally_move and move.get("pp", 0) > 0),
            None,
        )
        if rally_move_data:
            if aipom_count < 1:
                return BattleAction(
                    action_type='move',
                    battler_id=battler_id,
                    move_id=rally_move,
                    target_position=target_position,
                    pokemon_position=pokemon_position,
                )
            if aipom_count == 1 and random.random() < 0.5:
                return BattleAction(
                    action_type='move',
                    battler_id=battler_id,
                    move_id=rally_move,
                    target_position=target_position,
                    pokemon_position=pokemon_position,
                )

        attack_options = [
            move["move_id"] for move in active_pokemon.moves
            if move["move_id"] in preferred_attacks and move.get("pp", 0) > 0
        ]
        support_options = [
            move["move_id"] for move in active_pokemon.moves
            if move["move_id"] in support_moves and move.get("pp", 0) > 0
        ]
        other_options = [
            move["move_id"] for move in active_pokemon.moves
            if move["move_id"] != rally_move and move.get("pp", 0) > 0
        ]
        if support_options and random.random() < 0.25:
            chosen = random.choice(support_options)
            return BattleAction(
                action_type='move',
                battler_id=battler_id,
                move_id=chosen,
                target_position=target_position,
                pokemon_position=pokemon_position,
            )
        if attack_options:
            chosen = random.choice(attack_options)
            return BattleAction(
                action_type='move',
                battler_id=battler_id,
                move_id=chosen,
                target_position=target_position,
                pokemon_position=pokemon_position,
            )
        if other_options:
            chosen = random.choice(other_options)
            return BattleAction(
                action_type='move',
                battler_id=battler_id,
                move_id=chosen,
                target_position=target_position,
                pokemon_position=pokemon_position,
            )

        return BattleAction(
            action_type='move',
            battler_id=battler_id,
            move_id=active_pokemon.moves[0]["move_id"],
            target_position=target_position,
            pokemon_position=pokemon_position,
        )
    
    # ========================
    # Turn Processing
    # ========================
    
    async def process_turn(self, battle_id: str) -> Dict:
        """
        Process a complete turn with all registered actions
        
        Returns:
            Dict with turn results and narration
        """
        battle = self.active_battles.get(battle_id)
        if not battle:
            return {"error": "Battle not found"}
        
        # Generate AI actions if needed (one per active Pokemon for doubles)
        for battler in battle.get_all_battlers():
            if not getattr(battler, "is_ai", False):
                continue
            for pos in range(len(battler.get_active_pokemon())):
                action_key = f"{battler.battler_id}_{pos}"
                if action_key not in battle.pending_actions:
                    action = self.generate_ai_action(battle_id, battler.battler_id, pos)
                    if action:
                        battle.pending_actions[action_key] = action

        # Clear turn log
        battle.turn_log = []

        # Apply start-of-turn passive ability upkeep (e.g., Schooling)
        upkeep_messages = self._apply_start_of_turn_passives(battle)
        battle.turn_log.extend(upkeep_messages)

        turn_start_active = []
        for battler in battle.get_all_battlers():
            turn_start_active.extend(battler.get_active_pokemon())

        manual_switch_events: List[Dict[str, Any]] = []
        action_events: List[Dict[str, Any]] = []

        # Apply mega evolutions before turn order
        mega_actions = [action for action in battle.pending_actions.values() if getattr(action, "mega_evolve", False)]
        for action in mega_actions:
            if battle.is_over:
                break
            battler = self._get_battler_by_id(battle, action.battler_id)
            if not battler:
                continue
            acting_pokemon = self._get_action_pokemon(battler, action)
            mega_name = self.get_mega_evolution_name(battle, action.battler_id, acting_pokemon)
            if not mega_name:
                continue
            base_name = getattr(acting_pokemon, "nickname", None) or getattr(acting_pokemon, "species_name", "Pokémon")
            self._apply_mega_evolution(acting_pokemon, mega_name)
            battle.mega_evolution_used.add(action.battler_id)
            ring_messages = [f"{battler.battler_name} activates their Omni Ring!"]
            mega_messages = [f"{base_name} mega evolved!"]
            battle.turn_log.extend(ring_messages)
            battle.turn_log.extend(mega_messages)
            action_events.append(
                {
                    "type": "omni_ring",
                    "trainer": battler,
                    "messages": ring_messages,
                }
            )
            action_events.append(
                {
                    "type": "mega_evolve",
                    "actor": acting_pokemon,
                    "base_name": base_name,
                    "messages": mega_messages,
                }
            )

        # Sort actions by priority and speed
        actions = list(battle.pending_actions.values())
        actions = self._sort_actions(battle, actions)

        # Track which actions were registered vs executed to ensure all commands show up
        registered_actions = {}
        for action in actions:
            battler = self._get_battler_by_id(battle, action.battler_id)
            active_pokemon = battler.get_active_pokemon()
            if active_pokemon:
                pokemon_pos = getattr(action, 'pokemon_position', 0)
                if pokemon_pos < len(active_pokemon):
                    acting_pokemon = active_pokemon[pokemon_pos]
                    action_key = f"{action.battler_id}_{pokemon_pos}"
                    registered_actions[action_key] = {
                        'action': action,
                        'pokemon': acting_pokemon,
                        'executed': False
                    }

        # Execute actions in order
        for action in actions:
            # If the battle is over or the wild Pokémon has been dazed, stop resolving further actions
            if battle.is_over or getattr(battle, "wild_dazed", False):
                break

            # Skip actions from eliminated battlers
            battler = self._get_battler_by_id(battle, action.battler_id)
            if battler and battler.is_eliminated:
                continue

            # Skip actions for fainted Pokemon
            active_pokemon = battler.get_active_pokemon()
            acting_pokemon = None

            # In doubles, check the specific Pokemon's HP
            if battle.battle_format in [BattleFormat.DOUBLES, BattleFormat.RAID] and hasattr(action, 'pokemon_position'):
                pokemon_pos = action.pokemon_position
                if pokemon_pos < len(active_pokemon):
                    acting_pokemon = active_pokemon[pokemon_pos]
                    if acting_pokemon.current_hp <= 0:
                        # This specific Pokemon has fainted, skip its action
                        continue
                else:
                    # Invalid position, skip
                    continue
            else:
                # Singles: check if any Pokemon are conscious
                if not active_pokemon or all(p.current_hp <= 0 for p in active_pokemon):
                    # This side has no conscious active Pokémon right now
                    continue
                acting_pokemon = active_pokemon[0]

            # If a forced switch is pending for this battler, ignore non-switch actions
            # In doubles, only skip actions from the specific position that needs to switch
            if (
                battle.phase in ['FORCED_SWITCH', 'VOLT_SWITCH']
                and battle.forced_switch_battler_id == battler.battler_id
                and action.action_type != 'switch'
            ):
                # In doubles, check if this specific Pokemon needs to switch
                if battle.battle_format in [BattleFormat.DOUBLES, BattleFormat.RAID] and battle.forced_switch_position is not None:
                    if hasattr(action, 'pokemon_position') and action.pokemon_position == battle.forced_switch_position:
                        # This Pokemon needs to switch, skip its action
                        continue
                    # else: This is the other Pokemon on the team, let it act
                else:
                    # Singles: skip all non-switch actions when forced switch is pending
                    continue

            # Mark this action as executed for tracking
            action_key = f"{action.battler_id}_{getattr(action, 'pokemon_position', 0)}"
            if action_key in registered_actions:
                registered_actions[action_key]['executed'] = True

            result = await self._execute_action(battle, action)
            messages = result.get('messages', [])

            # CRITICAL: Ensure every executed action generates at least one message
            # If no messages were generated for a move action, add a fallback message
            if not messages and action.action_type == 'move':
                battler = self._get_battler_by_id(battle, action.battler_id)
                active_pokemon = battler.get_active_pokemon()
                pokemon_pos = getattr(action, 'pokemon_position', 0)
                if pokemon_pos < len(active_pokemon):
                    acting_pokemon = active_pokemon[pokemon_pos]
                    move_data = self.moves_db.get_move(action.move_id)
                    move_name = move_data.get('name', action.move_id) if move_data else action.move_id
                    messages = [f"{acting_pokemon.species_name} used {move_name}!"]

            if action.action_type == 'switch':
                switch_event = {
                    "messages": messages,
                    "pokemon": result.get("pokemon") or result.get("switched_in"),
                    "source": "manual",
                }
                manual_switch_events.append(switch_event)
            else:
                battle.turn_log.extend(messages)
                action_events.append({"type": action.action_type, "actor": acting_pokemon, "messages": messages})
                extra_events = result.get("action_events") or []
                if extra_events:
                    action_events.extend(extra_events)

            # NOTE: We no longer break the action loop for forced switches or volt switches
            # All remaining actions execute first, THEN players are prompted to switch
            # This ensures every Pokemon gets their turn even when switches are needed

        # Check for registered actions that were not executed and add explanatory messages
        # This helps debug issues where moves don't show up in turn embeds
        for action_key, action_info in registered_actions.items():
            if not action_info['executed'] and action_info['action'].action_type == 'move':
                pokemon = action_info['pokemon']
                # Only add message if the Pokemon is still conscious (if fainted, that's obvious)
                if getattr(pokemon, 'current_hp', 0) > 0:
                    # This action was skipped for some reason - could be due to forced switch, etc.
                    # We don't add a message here to avoid clutter, but this tracking helps identify issues
                    pass

        # End of turn effects (skip only if wild Pokémon is in the special 'dazed' state)
        # IMPORTANT: End-of-turn effects should ALWAYS happen before switches, even if switches are pending
        if getattr(battle, "wild_dazed", False):
            eot_messages = []
            auto_switch_events = []
        else:
            eot_messages = self._process_end_of_turn(battle)
            auto_switch_events = self.auto_switch_if_forced_ai(battle)

        battle.turn_log.extend(eot_messages)
        if eot_messages:
            # Check for Ambipom resonance boost messages and create a special event for them
            resonance_messages = [msg for msg in eot_messages if "draws strength from its ally" in msg]
            other_messages = [msg for msg in eot_messages if "draws strength from its ally" not in msg]

            if other_messages:
                action_events.append({"type": "end_of_turn", "messages": other_messages})

            if resonance_messages:
                # Find the Ambipom for the image
                ambipom = None
                for battler in battle.get_all_battlers():
                    if battler.is_eliminated:
                        continue
                    for mon in battler.get_active_pokemon():
                        if getattr(mon, "scripted_ai", None) == "ambipom_raid":
                            ambipom = mon
                            break
                    if ambipom:
                        break

                action_events.append({
                    "type": "ambipom_resonance",
                    "messages": resonance_messages,
                    "actor": ambipom,
                    "custom_title": "Alpha Ambipom and Aipom begin to resonate! Alpha Ambipom's power grows!",
                    "custom_color": discord.Color.purple()
                })

        switch_events = manual_switch_events + auto_switch_events
        
        # Check for battle end
        self._check_battle_end(battle)

        if getattr(battle, "scripted_sequence", None) == "nidoking_test" and battle.turn_number >= 5:
            battle.scripted_locked = True
        
        # Clear pending actions
        battle.pending_actions = {}
        
        # Increment turn
        self._clear_first_turn_flags(turn_start_active)
        battle.turn_number += 1
        
        return {
            "success": True,
            "turn_number": battle.turn_number - 1,
            "messages": battle.turn_log,
            "action_events": action_events,
            "switch_events": switch_events,
            "is_over": battle.is_over,
            "winner": battle.winner,
            "battle_over": battle.is_over
        }
    
    def _sort_actions(self, battle: BattleState, actions: List[BattleAction]) -> List[BattleAction]:
        """Sort actions by priority, then speed"""
        for action in actions:
            # Switching always goes first
            if action.action_type == 'switch':
                action.priority = 100
                action.speed = 999
                continue

            # Items are high priority
            if action.action_type == 'item':
                action.priority = 90
                action.speed = 999
                continue

            if action.action_type == 'move':
                move_data = self.moves_db.get_move(action.move_id)
                priority = move_data.get('priority', 0)

                battler = self._get_battler_by_id(battle, action.battler_id)
                active_pokemon = battler.get_active_pokemon()
                pokemon = active_pokemon[0] if active_pokemon else None
                speed = self._get_effective_speed(pokemon)

                # Check if this is Nidoking in the test path - make it go last
                if getattr(battle, "scripted_sequence", None) == "nidoking_test" and pokemon:
                    if getattr(pokemon, "species_name", "").lower() == "nidoking":
                        action.priority = -999
                        action.speed = -999
                        continue

                if self.held_item_manager and pokemon:
                    priority_effect = self.held_item_manager.get_priority_effect(pokemon, move_data)
                    if priority_effect:
                        priority += priority_effect.get('priority_boost', 0)
                        action.priority_message = priority_effect.get('message')
                        action.priority_consumes_item = priority_effect.get('consume', False)
                        action.priority_item_id = priority_effect.get('item_id')

                if battle.trick_room_turns > 0:
                    speed = -speed

                action.priority = priority
                action.speed = speed
                continue

            action.priority = 0
            action.speed = 0

        actions.sort(key=lambda a: (a.priority, a.speed), reverse=True)
        return actions

    def _get_effective_speed(self, pokemon) -> int:
        if pokemon is None:
            return 0
        speed = getattr(pokemon, 'speed', 0)
        if ENHANCED_SYSTEMS_AVAILABLE and hasattr(self, 'calculator'):
            try:
                speed = self.calculator.get_speed(pokemon)
            except Exception:
                pass
        if self.held_item_manager:
            speed = int(round(speed * self.held_item_manager.get_speed_multiplier(pokemon)))
        return speed
    
    async def _execute_action(self, battle: BattleState, action: BattleAction) -> Dict:
        """Execute a single action"""
        battler = self._get_battler_by_id(battle, action.battler_id)
        if action.action_type == 'disobey':
            pokemon = self._get_action_pokemon(battler, action)
            name = getattr(pokemon, 'species_name', 'The Pokémon')
            return {"messages": [f"{name} won't obey!"]}
        if action.action_type == 'move':
            result = await self._execute_move(battle, action)
        elif action.action_type == 'switch':
            result = self._execute_switch(battle, action)
        elif action.action_type == 'item':
            result = self._execute_item(battle, action)
        elif action.action_type == 'flee':
            result = self._execute_flee(battle, action)
        else:
            result = {"messages": []}

        return result
        
        return {"messages": []}
    
    def _determine_move_targets(self, battle: BattleState, action: BattleAction, move_data: Dict) -> List[Tuple[Any, Any]]:
        """
        Determine all targets for a move based on its target type.

        Returns:
            List of (defender_battler, defender_pokemon) tuples
        """
        attacker_battler = self._get_battler_by_id(battle, action.battler_id)
        # Determine ally/opponent pools dynamically to support raids/multi battles
        ally_team = battle.get_team_battlers(attacker_battler.battler_id)
        opposing_team = battle.get_opposing_team_battlers(attacker_battler.battler_id)

        target_type = move_data.get('target', 'single')
        targets = []

        if target_type == 'single':
            # Single target can be opponent or ally depending on target_battler_id
            target_battler = self._get_battler_by_id(battle, action.target_battler_id) if action.target_battler_id else None

            # If no explicit target battler provided, default to the primary opposing battler
            if not target_battler:
                target_battler = opposing_team[0] if opposing_team else battle.opponent

            # Redirect to Follow Me user on the target side
            follow_me_holder = None
            if target_battler in opposing_team:
                for opp_battler in opposing_team:
                    for mon in opp_battler.get_active_pokemon():
                        if hasattr(mon, 'status_manager') and mon.status_manager.has_status('follow_me'):
                            follow_me_holder = (opp_battler, mon)
                            break
                    if follow_me_holder:
                        break

            if follow_me_holder:
                targets.append(follow_me_holder)
            else:
                target_pos = action.target_position if action.target_position is not None else 0
                defender_active = target_battler.get_active_pokemon()
                if target_pos < len(defender_active):
                    targets.append((target_battler, defender_active[target_pos]))

        elif target_type in ['all_opponents', 'all_adjacent']:
            # Hit all opponent Pokemon
            for opp in opposing_team:
                for mon in opp.get_active_pokemon():
                    targets.append((opp, mon))

        elif target_type == 'all':
            # Hit all Pokemon on the field (opponents and allies)
            for opp in opposing_team:
                for mon in opp.get_active_pokemon():
                    targets.append((opp, mon))
            for ally in ally_team:
                for mon in ally.get_active_pokemon():
                    targets.append((ally, mon))

        elif target_type == 'all_allies':
            # Hit all ally Pokemon (including self)
            for ally in ally_team:
                for mon in ally.get_active_pokemon():
                    targets.append((ally, mon))

        elif target_type == 'ally':
            # Single ally target (for support moves like Helping Hand)
            target_pos = action.target_position if action.target_position is not None else 0
            target_battler = self._get_battler_by_id(battle, action.target_battler_id) if action.target_battler_id else attacker_battler
            ally_active = target_battler.get_active_pokemon()
            if target_pos < len(ally_active):
                targets.append((target_battler, ally_active[target_pos]))

        elif target_type in ['self', 'user_field']:
            # Target is the attacker itself (handled separately, return empty)
            pass

        elif target_type in ['entire_field', 'enemy_field']:
            # Field effects (handled separately, return empty)
            pass

        else:
            # Default to single target
            target_pos = action.target_position if action.target_position is not None else 0
            defender_active = defender_battler.get_active_pokemon()
            if target_pos < len(defender_active):
                targets.append((defender_battler, defender_active[target_pos]))

        return targets

    def _get_protect_status(self, pokemon) -> Optional[str]:
        """Return the active protect-like volatile status if present."""
        status_manager = getattr(pokemon, 'status_manager', None)
        if not status_manager:
            return None
        statuses = getattr(status_manager, 'volatile_statuses', {})
        for status_name in ('protect', 'kings_shield', 'detect'):
            if status_name in statuses:
                return status_name
        return None

    def _apply_kings_shield_attack_drop(self, attacker, move_data, messages: list[str]) -> None:
        """Apply King's Shield contact penalty if applicable."""
        flags = move_data.get('flags', {}) if isinstance(move_data, dict) else {}
        is_contact = isinstance(flags, dict) and flags.get('contact')
        if not is_contact or move_data.get('category') == 'status':
            return

        if not hasattr(attacker, 'stat_stages'):
            attacker.stat_stages = {
                'attack': 0, 'defense': 0, 'sp_attack': 0,
                'sp_defense': 0, 'speed': 0, 'evasion': 0, 'accuracy': 0
            }
        attacker.stat_stages['attack'] = max(-6, attacker.stat_stages['attack'] - 2)
        messages.append(f"{attacker.species_name}'s Attack harshly fell after hitting the shield!")

    async def _execute_spread_move(
        self,
        battle: BattleState,
        action: BattleAction,
        attacker,
        targets: List[Tuple[Any, Any]],
        move_data: Dict,
        attacker_battler=None,
    ) -> Dict:
        """Handle moves that hit multiple targets (spread moves)."""
        messages = []
        resonance_broken_events = []

        # Deduct PP once
        for move in attacker.moves:
            if move['move_id'] == action.move_id:
                move['pp'] = max(0, move['pp'] - 1)
                break

        # Filter out fainted targets before attacking
        valid_targets = [(b, p) for b, p in targets if p.current_hp > 0]

        # If no valid targets, move fails
        if not valid_targets:
            return {"messages": [f"{attacker.species_name} used {move_data['name']}, but there was no target!"]}

        # Build list of target names for the move message
        target_names = [defender.species_name for _, defender in valid_targets]
        if len(target_names) == 1:
            target_text = target_names[0]
        elif len(target_names) == 2:
            target_text = f"{target_names[0]} and {target_names[1]}"
        else:
            target_text = ", ".join(target_names[:-1]) + f", and {target_names[-1]}"

        messages.append(f"{attacker.species_name} used {move_data['name']} on {target_text}!")

        # In doubles/raids, spread moves have 0.75x power
        spread_modifier = 0.75 if battle.battle_format in [BattleFormat.DOUBLES, BattleFormat.RAID] and len(valid_targets) > 1 else 1.0

        # Hit each target
        for defender_battler, defender in valid_targets:
            # Check if defender is protected
            if ENHANCED_SYSTEMS_AVAILABLE and hasattr(defender, 'status_manager'):
                protect_status = self._get_protect_status(defender)
                if protect_status:
                    if move_data.get('category') in ['physical', 'special']:
                        if protect_status == 'kings_shield':
                            self._apply_kings_shield_attack_drop(attacker, move_data, messages)
                        messages.append(f"{defender.species_name} protected itself!")
                        continue

            # Calculate damage
            if ENHANCED_SYSTEMS_AVAILABLE:
                if self._is_status_immune(defender):
                    damage, is_crit, effectiveness, effect_msgs = self._calculate_damage_no_effects(
                        attacker, defender, move_data, battle
                    )
                else:
                    damage, is_crit, effectiveness, effect_msgs = self.calculator.calculate_damage_with_effects(
                        attacker, defender, action.move_id,
                        weather=battle.weather,
                        terrain=battle.terrain,
                        battle_state=battle
                    )
                damage = min(int(damage * spread_modifier), defender.current_hp)
            else:
                damage = int(10 * spread_modifier)
                is_crit = False
                effectiveness = 1.0
                effect_msgs = []

            if self._is_damage_immune(defender):
                damage = 0
                effect_msgs = []

            # Apply damage
            if damage > 0:
                defender.current_hp = max(0, defender.current_hp - damage)
                if move_data.get('category') in ['physical', 'special']:
                    defender.last_damage_taken = damage
                    defender.last_damage_category = move_data.get('category')
                    defender.last_damage_from = attacker
                if getattr(defender, 'bide_turns_remaining', 0):
                    defender.bide_damage = getattr(defender, 'bide_damage', 0) + damage
                if (
                    ENHANCED_SYSTEMS_AVAILABLE
                    and move_data.get('category') in ['physical', 'special']
                    and attacker_battler is not None
                    and attacker_battler != defender_battler
                ):
                    defender.rage_fist_hits_taken = getattr(defender, 'rage_fist_hits_taken', 0) + 1

            # Build damage message
            crit_text = " It's a critical hit!" if is_crit else ""
            effectiveness_text = ""
            if effectiveness > 1:
                effectiveness_text = " It's super effective!"
            elif effectiveness < 1 and effectiveness > 0:
                effectiveness_text = " It's not very effective..."

            if effectiveness == 0:
                messages.append(f"It doesn't affect {defender.species_name}...")
                continue

            # Only show damage message for damaging moves (physical/special)
            if move_data.get('category') in ['physical', 'special'] and damage > 0:
                messages.append(f"{defender.species_name} took {damage} damage!{crit_text}{effectiveness_text}")

            messages.extend(effect_msgs)

            # Check for HP-based form changes after the exchange
            if self.ability_handler:
                messages.extend(self.ability_handler.update_form_passives(defender))
                messages.extend(self.ability_handler.update_form_passives(attacker))

            # Check for faint
            if defender.current_hp <= 0:
                if battle.battle_type == BattleType.WILD and defender_battler == battle.opponent:
                    defender.current_hp = 1
                    battle.wild_dazed = True
                    battle.phase = 'DAZED'
                    messages.append(f"The wild {defender.species_name} is dazed!")
                else:
                    messages.append(f"{defender.species_name} fainted!")
                    self._record_faint(defender_battler, defender)
                    # Record opponent faint for EXP calculation
                    self._record_opponent_faint_for_exp(battle, defender, defender_battler, attacker_battler)

                    # Check for Aipom faint in Ambipom raid - trigger resonance broken
                    if getattr(defender, "species_name", "").lower() == "aipom":
                        # Find Ambipom in the same battler team
                        for mon in defender_battler.get_active_pokemon():
                            if getattr(mon, "scripted_ai", None) == "ambipom_raid" and mon.current_hp > 0:
                                # Lower Ambipom's stats by 1
                                self._ensure_stat_stages(mon)
                                for stat in ['attack', 'defense', 'sp_attack', 'sp_defense', 'speed']:
                                    mon.stat_stages[stat] = max(-6, mon.stat_stages.get(stat, 0) - 1)
                                boost_level = mon.stat_stages.get('attack', 0)
                                resonance_msg = f"Resonance broken! {mon.species_name}'s connection weakens!"
                                stat_msg = f"All stats fell! (Now {boost_level:+d})"
                                messages.append(f"{resonance_msg} {stat_msg}")

                                # Create special event for embed
                                resonance_broken_events.append({
                                    "type": "resonance_broken",
                                    "messages": [resonance_msg, stat_msg],
                                    "actor": mon,
                                    "custom_title": "Resonance Broken!",
                                    "custom_color": discord.Color.red()
                                })
                                break

                        # Aipom heals all ally pokemon by 20% HP
                        heal_messages = []
                        for ally_mon in attacker_battler.get_active_pokemon():
                            if ally_mon.current_hp > 0:
                                max_hp = ally_mon.max_hp
                                heal_amount = int(max_hp * 0.20)
                                old_hp = ally_mon.current_hp
                                ally_mon.current_hp = min(max_hp, ally_mon.current_hp + heal_amount)
                                actual_heal = ally_mon.current_hp - old_hp
                                if actual_heal > 0:
                                    heal_messages.append(f"{ally_mon.species_name} recovered {actual_heal} HP!")

                        if heal_messages:
                            # Create special event for healing embed
                            resonance_broken_events.append({
                                "type": "aipom_healing",
                                "messages": heal_messages,
                                "actor": defender,
                                "custom_title": "Aipom unleashes a strange energy, healing your pokemon!",
                                "custom_color": discord.Color.green()
                            })

                    # Determine which position the fainted Pokemon was in
                    fainted_position = None
                    for pos_idx, party_idx in enumerate(defender_battler.active_positions):
                        if defender_battler.party[party_idx] == defender:
                            fainted_position = pos_idx
                            break

                    # For player's Pokemon fainting (non-AI), they need to switch (if they have Pokemon left)
                    if not defender_battler.is_ai:
                        if defender_battler.has_usable_bench_pokemon(exclude_pokemon=defender):
                            # Add to pending switches
                            battle.pending_switches[defender_battler.battler_id] = {
                                'position': fainted_position,
                                'switch_type': 'FORCED'
                            }
                            battle.phase = 'FORCED_SWITCH'
                            # Maintain backwards compatibility with old fields
                            if not battle.forced_switch_battler_id:
                                battle.forced_switch_battler_id = defender_battler.battler_id
                                battle.forced_switch_position = fainted_position
                        else:
                            if fainted_position is not None and fainted_position < len(defender_battler.active_positions):
                                defender_battler.active_positions.pop(fainted_position)
                            self._check_battle_end(battle)

        result = {"messages": messages}
        if resonance_broken_events:
            result["action_events"] = resonance_broken_events
        return result

    def _should_skip_charge(self, move_data: Dict, battle: BattleState) -> bool:
        """Check if a charging move should skip its charge turn (e.g., Solar Beam in sun)."""
        move_id = (move_data.get('id') or '').lower()
        weather = getattr(battle, 'weather', None)

        if move_id in ['solar_beam', 'solar_blade'] and weather == 'sun':
            return True
        return False

    def _apply_charge_start_effects(self, attacker, move_data: Dict, messages: List[str]):
        """Apply first-turn effects for charging moves (e.g., Skull Bash defense boost)."""
        move_id = (move_data.get('id') or '').lower()

        if move_id == 'skull_bash':
            if not hasattr(attacker, 'stat_stages'):
                attacker.stat_stages = {'attack': 0, 'defense': 0, 'sp_attack': 0, 'sp_defense': 0, 'speed': 0,
                                         'evasion': 0, 'accuracy': 0}
            current = attacker.stat_stages.get('defense', 0)
            attacker.stat_stages['defense'] = min(6, current + 1)
            messages.append(f"{attacker.species_name} is bracing itself! Defense rose.")

    def _get_semi_invulnerable_state(self, move_id: str) -> Optional[str]:
        """Return the semi-invulnerable state applied by a charging move."""
        move_id = (move_id or '').lower()
        if move_id == 'dig':
            return 'underground'
        if move_id == 'fly':
            return 'air'
        return None

    def _move_hits_semi_invulnerable(self, move_id: str, state: str) -> bool:
        """Return True if a move can hit a target in a semi-invulnerable state."""
        move_id = (move_id or '').lower()
        if state == 'underground':
            return move_id in {'earthquake', 'magnitude', 'fissure'}
        if state == 'air':
            return move_id in {'gust', 'thunder', 'hurricane', 'twister', 'smack_down', 'thousand_arrows'}
        return False

    def _is_target_semi_invulnerable(self, target, move_data: Dict) -> bool:
        """Return True if the target should be untargetable by the move."""
        state = getattr(target, '_semi_invulnerable', None)
        if not state:
            return False
        return not self._move_hits_semi_invulnerable(move_data.get('id'), state)

    def _semi_invulnerable_message(self, target) -> str:
        state = getattr(target, '_semi_invulnerable', None)
        if state == 'underground':
            return f"{target.species_name} is hiding underground!"
        if state == 'air':
            return f"{target.species_name} is flying high!"
        return f"{target.species_name} can't be hit right now!"

    def _get_charge_message(self, attacker, move_data: Dict) -> Optional[str]:
        move_id = (move_data.get('id') or '').lower()
        if move_id == 'dig':
            return f"{attacker.species_name} began to dig underground!"
        if move_id == 'fly':
            return f"{attacker.species_name} flew up high!"
        return None

    def _roll_multihit_count(self, move_data: Dict) -> int:
        multihit = move_data.get('multihit')
        if isinstance(multihit, list) and len(multihit) == 2:
            return random.randint(multihit[0], multihit[1])
        if isinstance(multihit, int):
            return multihit
        return 1

    def _build_move_message(self, attacker, move_data: Dict, defender, target_type: str) -> str:
        if target_type in ['self', 'entire_field', 'user_field', 'enemy_field', 'all_allies']:
            return f"{attacker.species_name} used {move_data['name']}!"
        return f"{attacker.species_name} used {move_data['name']} on {defender.species_name}!"

    def _calculate_damage_without_accuracy(self, attacker, defender, move_data: Dict, battle: BattleState) -> Tuple[int, bool, float, List[str]]:
        if move_data.get('category') == 'status':
            effects = self.calculator.effect_handler.apply_move_effects(
                move_data, attacker, defender, 0, battle
            )
            return 0, False, 1.0, effects

        damage, is_crit, effectiveness = self.calculator._calculate_base_damage(
            attacker,
            defender,
            move_data,
            False,
            battle.weather,
            battle.terrain
        )

        if effectiveness == 0:
            return 0, is_crit, effectiveness, []

        damage_dealt = min(damage, defender.current_hp)
        effects = self.calculator.effect_handler.apply_move_effects(
            move_data, attacker, defender, damage_dealt, battle
        )
        return damage_dealt, is_crit, effectiveness, effects

    def _calculate_damage_no_effects(
        self,
        attacker,
        defender,
        move_data: Dict,
        battle: BattleState,
    ) -> Tuple[int, bool, float, List[str]]:
        if move_data.get('category') == 'status':
            return 0, False, 1.0, []
        if ENHANCED_SYSTEMS_AVAILABLE and hasattr(self.calculator, '_calculate_base_damage'):
            damage, is_crit, effectiveness = self.calculator._calculate_base_damage(
                attacker,
                defender,
                move_data,
                False,
                battle.weather,
                battle.terrain,
            )
            return damage, is_crit, effectiveness, []
        return 10, False, 1.0, []

    def _is_status_immune(self, defender) -> bool:
        return bool(getattr(defender, "scripted_immune_status", False))

    def _is_damage_immune(self, defender) -> bool:
        return bool(getattr(defender, "scripted_immune_damage", False))

    def _ensure_stat_stages(self, pokemon):
        if not hasattr(pokemon, 'stat_stages'):
            pokemon.stat_stages = {
                'attack': 0,
                'defense': 0,
                'sp_attack': 0,
                'sp_defense': 0,
                'speed': 0,
                'accuracy': 0,
                'evasion': 0,
            }

    def _apply_ambipom_rally_cry_resonance(self, battle: BattleState) -> List[str]:
        messages: List[str] = []

        for battler in battle.get_all_battlers():
            if battler.is_eliminated:
                continue
            active_allies = [mon for mon in battler.get_active_pokemon() if getattr(mon, "current_hp", 0) > 0]
            if not active_allies:
                continue
            aipom_alive = any(
                getattr(mon, "species_name", "").lower() == "aipom"
                for mon in active_allies
            )
            if not aipom_alive:
                continue
            for mon in active_allies:
                if getattr(mon, "scripted_ai", None) != "ambipom_raid":
                    continue
                self._ensure_stat_stages(mon)
                # Boost all stats by 1, up to +6
                for stat in ['attack', 'defense', 'sp_attack', 'sp_defense', 'speed']:
                    mon.stat_stages[stat] = min(6, mon.stat_stages.get(stat, 0) + 1)
                # Show cumulative boost level (all stats should be the same since they boost together)
                boost_level = mon.stat_stages.get('attack', 0)
                messages.append(f"{mon.species_name} draws strength from its ally! (All stats {boost_level:+d})")

        return messages

    def _execute_rally_cry(self, battle: BattleState, attacker, attacker_battler: Battler, move_data: Dict) -> Dict:
        messages = [f"{attacker.species_name} used {move_data['name']}!"]

        for move in attacker.moves:
            if move['move_id'] == move_data.get('id'):
                move['pp'] = max(0, move['pp'] - 1)
                break

        max_slots = getattr(battle, "raid_opponent_slots", 1)
        active_allies = attacker_battler.get_active_pokemon()
        aipom_active = sum(1 for mon in active_allies if getattr(mon, "species_name", "").lower() == "aipom")

        if len(active_allies) >= max_slots or aipom_active >= 2:
            return {"messages": messages}

        if not self.species_db:
            return {"messages": messages + ["But nothing answered the call."]}

        species_data = self.species_db.get_species("aipom")
        if not species_data:
            return {"messages": messages + ["But nothing answered the call."]}

        from models import Pokemon

        new_aipom = Pokemon(
            species_data=species_data,
            level=2,
            owner_discord_id=None
        )
        new_aipom._calculate_stats()
        new_aipom.current_hp = new_aipom.max_hp

        attacker_battler.party.append(new_aipom)
        attacker_battler.active_positions.append(len(attacker_battler.party) - 1)

        # Don't boost stats here - it will happen at end of turn via resonance
        action_events = [
            {
                "type": "custom",
                "title": "A wild Aipom answers the call!",
                "messages": ["Aipom joins Alpha Ambipom in battle!"],
                "actor": new_aipom,
            },
        ]

        return {"messages": messages, "action_events": action_events}

    def _execute_nidoking_wait(self, battle: BattleState, attacker) -> Dict:
        turn = battle.turn_number
        if turn <= 2:
            message = "Tyrant of Mist waits, and watches..."
        elif turn <= 4:
            message = "Tyrant of Mist takes a step forward."
        else:
            message = "Tyrant of Mist takes its last step. Tyrant of Mist is now upon you."
            # End the battle on turn 5 with a special ending
            battle.is_over = True
            battle.winner = "opponent"
            battle.nidoking_special_ending = True
        return {"messages": [message]}

    async def _execute_move(self, battle: BattleState, action: BattleAction) -> Dict:
        """Execute a move action - now supports spread moves hitting multiple targets"""
        # Get attacker and defender
        attacker_battler = self._get_battler_by_id(battle, action.battler_id)
        # Default defender is the first opposing battler; may change once targets are resolved
        opposing_team = battle.get_opposing_team_battlers(attacker_battler.battler_id)
        defender_battler = opposing_team[0] if opposing_team else battle.opponent

        # Get attacker Pokemon (the one using the move) - use pokemon_position from action
        active_pokemon_list = attacker_battler.get_active_pokemon()
        pokemon_pos = action.pokemon_position if action.pokemon_position < len(active_pokemon_list) else 0
        attacker = active_pokemon_list[pokemon_pos]

        messages: List[str] = []
        resonance_broken_events = []

        if action.priority_message:
            messages.append(action.priority_message)
            if action.priority_consumes_item and self.held_item_manager:
                self.held_item_manager.consume_item(attacker, action.priority_item_id)

        # Check if attacker can move (status conditions, flinch, etc.)
        if ENHANCED_SYSTEMS_AVAILABLE and hasattr(attacker, 'status_manager'):
            can_move, prevention_msg = attacker.status_manager.can_move(attacker)
            if not can_move:
                return {"messages": [prevention_msg]}
            if prevention_msg:
                messages.append(prevention_msg)

        # Get move data
        move_data = self.moves_db.get_move(action.move_id)
        if not move_data:
            return {"messages": [f"{attacker.species_name} tried to use an unknown move!"]}

        if move_data.get('id') == 'rally_cry':
            return self._execute_rally_cry(battle, attacker, attacker_battler, move_data)
        if move_data.get('id') == 'nidoking_wait':
            return self._execute_nidoking_wait(battle, attacker)

        # Handle form changes tied to move usage (e.g., Stance Change)
        if self.ability_handler:
            stance_msg = self.ability_handler.apply_stance_change(attacker, move_data)
            if stance_msg:
                messages.append(stance_msg)

        # Taunt prevents status-category moves
        if (
            ENHANCED_SYSTEMS_AVAILABLE
            and hasattr(attacker, 'status_manager')
            and attacker.status_manager.has_status('taunt')
            and move_data.get('category') == 'status'
        ):
            return {"messages": [f"{attacker.species_name} fell for the Taunt and can't use {move_data['name']}!"]}

        if move_data.get('id') == 'fake_out' and not getattr(attacker, "_first_turn_active", True):
            for move in attacker.moves:
                if move['move_id'] == action.move_id:
                    move['pp'] = max(0, move['pp'] - 1)
                    break
            if getattr(attacker_battler, 'is_ai', False):
                if not hasattr(battle, 'ai_failed_moves'):
                    battle.ai_failed_moves = {}
                pokemon_key = f"{attacker_battler.battler_id}_{id(attacker)}"
                if pokemon_key not in battle.ai_failed_moves:
                    battle.ai_failed_moves[pokemon_key] = {}
                fail_count = battle.ai_failed_moves[pokemon_key].get(action.move_id, 0)
                battle.ai_failed_moves[pokemon_key][action.move_id] = fail_count + 1
            return {"messages": [f"{attacker.species_name} used {move_data['name']}, but it failed!"]}

        # Two-turn charging moves
        skip_pp_deduct = False
        if getattr(attacker, '_charge_state', None) and attacker._charge_state.get('move_id') != action.move_id:
            attacker._charge_state = None
            attacker._semi_invulnerable = None

        if move_data.get('flags', {}).get('charge'):
            charge_state = getattr(attacker, '_charge_state', None)
            if charge_state and charge_state.get('move_id') == action.move_id:
                messages.append(f"{attacker.species_name} unleashed {move_data['name']}!")
                skip_pp_deduct = charge_state.get('pp_paid', False)
                attacker._charge_state = None
                attacker._semi_invulnerable = None
            elif not self._should_skip_charge(move_data, battle):
                # Deduct PP immediately since we're returning before normal processing
                for move in attacker.moves:
                    if move['move_id'] == action.move_id:
                        move['pp'] = max(0, move['pp'] - 1)
                        break
                charge_message = self._get_charge_message(attacker, move_data)
                messages.append(charge_message or f"{attacker.species_name} began charging {move_data['name']}!")
                self._apply_charge_start_effects(attacker, move_data, messages)
                attacker._charge_state = {'move_id': action.move_id, 'pp_paid': True}
                invulnerable_state = self._get_semi_invulnerable_state(move_data.get('id'))
                if invulnerable_state:
                    attacker._semi_invulnerable = invulnerable_state
                return {"messages": messages}
            else:
                messages.append(f"{attacker.species_name} used {move_data['name']} without charging!")

        # Special handling for Revival Blessing (target selection can include fainted allies)
        if move_data.get('id') == 'revival_blessing':
            if self.held_item_manager:
                restriction = self.held_item_manager.check_move_restrictions(attacker, move_data)
                if restriction:
                    return {"messages": [restriction]}

            # Deduct PP once
            for move in attacker.moves:
                if move['move_id'] == action.move_id:
                    move['pp'] = max(0, move['pp'] - 1)
                    break

            return self._execute_revival_blessing(battle, attacker_battler, attacker, action)

        # Determine all targets based on move target type
        target_type = move_data.get('target', 'single')
        targets = self._determine_move_targets(battle, action, move_data)

        if targets and target_type == 'single':
            _, target = targets[0]
            if self._is_target_semi_invulnerable(target, move_data):
                if not skip_pp_deduct:
                    for move in attacker.moves:
                        if move['move_id'] == action.move_id:
                            move['pp'] = max(0, move['pp'] - 1)
                            break
                messages.append(self._build_move_message(attacker, move_data, target, target_type))
                messages.append(self._semi_invulnerable_message(target))
                move_name = move_data.get('name', action.move_id)
                messages.append(f"{attacker.species_name} used {move_name}, but it missed!")
                return {"messages": messages}

        # Filter out fainted targets and redirect to valid targets if needed
        valid_targets = [(b, p) for b, p in targets if p.current_hp > 0]

        if valid_targets:
            filtered_targets = []
            for battler, target in valid_targets:
                if self._is_target_semi_invulnerable(target, move_data):
                    messages.append(self._semi_invulnerable_message(target))
                else:
                    filtered_targets.append((battler, target))
            valid_targets = filtered_targets

        # If original target(s) fainted, try to find a new target for single-target moves
        if not valid_targets and target_type == 'single':
            # Get opposing team to find alternative target
            opposing_team = battle.get_opposing_team_battlers(attacker_battler.battler_id)
            for opp_battler in opposing_team:
                for mon in opp_battler.get_active_pokemon():
                    if mon.current_hp > 0:
                        valid_targets = [(opp_battler, mon)]
                        messages.append(f"{attacker.species_name}'s target fainted! Attack redirected to {mon.species_name}!")
                        break
                if valid_targets:
                    break

        # If no valid targets exist, move fails
        if not valid_targets and target_type in ['single', 'all_opponents', 'all_adjacent', 'all']:
            # Deduct PP since the move was attempted
            for move in attacker.moves:
                if move['move_id'] == action.move_id:
                    move['pp'] = max(0, move['pp'] - 1)
                    break
            if targets:
                move_name = move_data.get('name', action.move_id)
                messages.append(f"{attacker.species_name} used {move_name}, but it missed!")
                return {"messages": messages}
            return {"messages": [f"{attacker.species_name} used {move_data['name']}, but there was no target!"]}

        # Use the filtered valid targets
        targets = valid_targets

        # Get the actual defender from targets (handles ally-targeting moves correctly)
        if targets:
            defender_battler_actual, defender = targets[0]
        else:
            # Fallback for self-targeting or field moves
            defender = attacker
            defender_battler_actual = attacker_battler
        defender_battler = defender_battler_actual

        if move_data.get('category') == 'status' and self._is_status_immune(defender):
            return {"messages": [f"It doesn't affect {defender.species_name}..."]}

        # If move hits multiple targets (spread move), handle differently
        if len(targets) > 1:
            return await self._execute_spread_move(
                battle,
                action,
                attacker,
                targets,
                move_data,
                attacker_battler=attacker_battler,
            )

        # Handle Protect/Detect/King's Shield successive use failure
        if action.move_id in ['protect', 'detect', 'kings_shield']:
            protect_count = getattr(attacker, '_protect_count', 0)
            if protect_count > 0:
                # Calculate success rate: (1/3)^protect_count
                success_rate = (1.0 / 3.0) ** protect_count
                if random.random() > success_rate:
                    # Protect failed
                    attacker._protect_count = 0  # Reset on failure
                    # Track failed moves for AI learning
                    if getattr(attacker_battler, 'is_ai', False):
                        if not hasattr(battle, 'ai_failed_moves'):
                            battle.ai_failed_moves = {}
                        pokemon_key = f"{attacker_battler.battler_id}_{id(attacker)}"
                        if pokemon_key not in battle.ai_failed_moves:
                            battle.ai_failed_moves[pokemon_key] = {}
                        fail_count = battle.ai_failed_moves[pokemon_key].get(action.move_id, 0)
                        battle.ai_failed_moves[pokemon_key][action.move_id] = fail_count + 1
                    return {"messages": [f"{attacker.species_name} used {move_data['name']}, but it failed!"]}
            # Increment protect count on successful use
            attacker._protect_count = protect_count + 1
        else:
            # Reset protect count when using any other move
            attacker._protect_count = 0

        if self.held_item_manager:
            restriction = self.held_item_manager.check_move_restrictions(attacker, move_data)
            if restriction:
                return {"messages": [restriction]}
        
        # Validate move by ruleset
        if hasattr(battle, 'ruleset') and self.ruleset_handler:
            ok, reason = self.ruleset_handler.is_move_allowed(action.move_id, battle.ruleset)
            if not ok:
                return {"messages": [f"{attacker.species_name} tried to use {move_data.get('name', action.move_id)} but it's banned by rules ({reason})."]}

        # Check if move is banned against raid bosses
        if getattr(defender, "is_raid_boss", False):
            from ruleset_handler import BANNED_RAID_MOVES
            move_id_normalized = (action.move_id or "").replace(" ", "").replace("-", "").lower()
            if move_id_normalized in BANNED_RAID_MOVES:
                return {"messages": [f"{attacker.species_name} tried to use {move_data.get('name', action.move_id)}, but it doesn't affect Rogue Pokemon!"]}

        # Deduct PP
        if not skip_pp_deduct:
            for move in attacker.moves:
                if move['move_id'] == action.move_id:
                    move['pp'] = max(0, move['pp'] - 1)
                    break

        # Check if defender is protected (Protect/Detect blocks damaging moves)
        if ENHANCED_SYSTEMS_AVAILABLE and hasattr(defender, 'status_manager'):
            protect_status = self._get_protect_status(defender)
            if protect_status:
                # Protect blocks all damaging moves and most status moves
                if move_data.get('category') in ['physical', 'special']:
                    if protect_status == 'kings_shield':
                        self._apply_kings_shield_attack_drop(attacker, move_data, messages)
                    move_msg = f"{attacker.species_name} used {move_data['name']}, but {defender.species_name} protected itself!"
                    return {"messages": [move_msg]}

        if move_data.get('multihit') and move_data.get('category') in ['physical', 'special']:
            hit_count = self._roll_multihit_count(move_data)
            target_type = move_data.get('target', 'single')
            messages.append(self._build_move_message(attacker, move_data, defender, target_type))

            if ENHANCED_SYSTEMS_AVAILABLE and hasattr(self.calculator, '_check_accuracy'):
                if not self.calculator._check_accuracy(move_data, attacker, defender, battle.weather):
                    move_name = move_data.get('name', action.move_id)
                    messages.append(f"{attacker.species_name} used {move_name}, but it missed!")
                    return {"messages": messages}

            actual_hits = 0
            for hit_index in range(1, hit_count + 1):
                if ENHANCED_SYSTEMS_AVAILABLE:
                    if hit_index == 1:
                        if self._is_status_immune(defender):
                            damage, is_crit, effectiveness, effect_msgs = self._calculate_damage_no_effects(
                                attacker, defender, move_data, battle
                            )
                        else:
                            damage, is_crit, effectiveness, effect_msgs = self._calculate_damage_without_accuracy(
                                attacker, defender, move_data, battle
                            )
                    else:
                        if self._is_status_immune(defender):
                            damage, is_crit, effectiveness, effect_msgs = self._calculate_damage_no_effects(
                                attacker, defender, move_data, battle
                            )
                        else:
                            damage, is_crit, effectiveness, effect_msgs = self._calculate_damage_without_accuracy(
                                attacker, defender, move_data, battle
                            )
                else:
                    damage = 10
                    is_crit = False
                    effectiveness = 1.0
                    effect_msgs = []

                if self._is_damage_immune(defender):
                    damage = 0
                    effect_msgs = []

                if effectiveness == 0:
                    messages.append(f"It doesn't affect {defender.species_name}...")
                    break

                if self.held_item_manager:
                    damage, held_msgs = self.held_item_manager.modify_damage(attacker, defender, move_data, damage)
                    effect_msgs.extend(held_msgs)

                damage = min(damage, defender.current_hp)

                if (
                    damage >= defender.current_hp
                    and hasattr(defender, 'status_manager')
                    and 'endure' in getattr(defender.status_manager, 'volatile_statuses', {})
                ):
                    if defender.current_hp > 1:
                        damage = defender.current_hp - 1
                        effect_msgs.append(f"{defender.species_name} endured the hit!")

                if damage > 0:
                    defender.current_hp = max(0, defender.current_hp - damage)
                    defender.last_damage_taken = damage
                    defender.last_damage_category = move_data.get('category')
                    defender.last_damage_from = attacker
                    if getattr(defender, 'bide_turns_remaining', 0):
                        defender.bide_damage = getattr(defender, 'bide_damage', 0) + damage

                if (
                    ENHANCED_SYSTEMS_AVAILABLE
                    and move_data.get('category') in ['physical', 'special']
                    and attacker_battler != defender_battler
                ):
                    defender.rage_fist_hits_taken = getattr(defender, 'rage_fist_hits_taken', 0) + 1

                if ENHANCED_SYSTEMS_AVAILABLE:
                    exit_msg = self._maybe_queue_hp_switch(battle, defender_battler, defender)
                    if exit_msg:
                        messages.append(exit_msg)

                crit_text = " It's a critical hit!" if is_crit else ""
                effectiveness_text = ""
                if effectiveness > 1:
                    effectiveness_text = " It's super effective!"
                elif effectiveness < 1 and effectiveness > 0:
                    effectiveness_text = " It's not very effective..."

                if damage > 0:
                    messages.append(
                        f"Hit {hit_index}: {defender.species_name} took {damage} damage!{crit_text}{effectiveness_text}"
                    )
                elif effectiveness > 0:
                    messages.append(
                        f"Hit {hit_index}: {defender.species_name} took 0 damage!{crit_text}{effectiveness_text}"
                    )
                messages.extend(effect_msgs)

                if self.held_item_manager:
                    post_msgs = self.held_item_manager.apply_after_damage(attacker, move_data, damage)
                    messages.extend(post_msgs)

                if self.held_item_manager:
                    reactive_msgs = self.held_item_manager.process_reactive_effects(
                        defender, move_data, damage
                    )
                    messages.extend(reactive_msgs)

                actual_hits += 1
                if defender.current_hp <= 0:
                    break

            if actual_hits:
                messages.append(f"It hit {actual_hits} time(s)!")

            if self.ability_handler:
                messages.extend(self.ability_handler.update_form_passives(defender))
                messages.extend(self.ability_handler.update_form_passives(attacker))

            if defender.current_hp <= 0:
                if battle.battle_type == BattleType.WILD and defender_battler == battle.opponent:
                    defender.current_hp = 1
                    battle.wild_dazed = True
                    battle.phase = 'DAZED'
                    messages.append(f"The wild {defender.species_name} is dazed!")
                else:
                    messages.append(f"{defender.species_name} fainted!")
                    self._record_faint(defender_battler, defender)
                    # Record opponent faint for EXP calculation
                    self._record_opponent_faint_for_exp(battle, defender, defender_battler, attacker_battler)

                    # Check for Aipom faint in Ambipom raid - trigger resonance broken
                    if getattr(defender, "species_name", "").lower() == "aipom":
                        # Find Ambipom in the same battler team
                        for mon in defender_battler.get_active_pokemon():
                            if getattr(mon, "scripted_ai", None) == "ambipom_raid" and mon.current_hp > 0:
                                # Lower Ambipom's stats by 1
                                self._ensure_stat_stages(mon)
                                for stat in ['attack', 'defense', 'sp_attack', 'sp_defense', 'speed']:
                                    mon.stat_stages[stat] = max(-6, mon.stat_stages.get(stat, 0) - 1)
                                boost_level = mon.stat_stages.get('attack', 0)
                                resonance_msg = f"Resonance broken! {mon.species_name}'s connection weakens!"
                                stat_msg = f"All stats fell! (Now {boost_level:+d})"
                                messages.append(f"{resonance_msg} {stat_msg}")

                                # Create special event for embed
                                resonance_broken_events.append({
                                    "type": "resonance_broken",
                                    "messages": [resonance_msg, stat_msg],
                                    "actor": mon,
                                    "custom_title": "Resonance Broken!",
                                    "custom_color": discord.Color.red()
                                })
                                break

                        # Aipom heals all ally pokemon by 20% HP
                        heal_messages = []
                        for ally_mon in attacker_battler.get_active_pokemon():
                            if ally_mon.current_hp > 0:
                                max_hp = ally_mon.max_hp
                                heal_amount = int(max_hp * 0.20)
                                old_hp = ally_mon.current_hp
                                ally_mon.current_hp = min(max_hp, ally_mon.current_hp + heal_amount)
                                actual_heal = ally_mon.current_hp - old_hp
                                if actual_heal > 0:
                                    heal_messages.append(f"{ally_mon.species_name} recovered {actual_heal} HP!")

                        if heal_messages:
                            # Create special event for healing embed
                            resonance_broken_events.append({
                                "type": "aipom_healing",
                                "messages": heal_messages,
                                "actor": defender,
                                "custom_title": "Aipom unleashes a strange energy, healing your pokemon!",
                                "custom_color": discord.Color.green()
                            })

            result = {"messages": messages}
            if resonance_broken_events:
                result["action_events"] = resonance_broken_events
            return result

        # Calculate damage and apply effects
        if ENHANCED_SYSTEMS_AVAILABLE:
            if self._is_status_immune(defender):
                damage, is_crit, effectiveness, effect_msgs = self._calculate_damage_no_effects(
                    attacker, defender, move_data, battle
                )
            else:
                damage, is_crit, effectiveness, effect_msgs = self.calculator.calculate_damage_with_effects(
                    attacker, defender, action.move_id,
                    weather=battle.weather,
                    terrain=battle.terrain,
                    battle_state=battle
                )
        else:
            # Basic damage calculation fallback
            damage = 10  # Simplified
            is_crit = False
            effectiveness = 1.0
            effect_msgs = []

        if self.held_item_manager:
            damage, held_msgs = self.held_item_manager.modify_damage(attacker, defender, move_data, damage)
            effect_msgs.extend(held_msgs)

        if self._is_damage_immune(defender):
            damage = 0
            effect_msgs = []

        damage = min(damage, defender.current_hp)

        # Endure check: if this hit would KO and defender is under ENDURE, leave at 1 HP
        if damage >= defender.current_hp and hasattr(defender, 'status_manager') and 'endure' in getattr(defender.status_manager, 'volatile_statuses', {}):
            if defender.current_hp > 1:
                damage = defender.current_hp - 1
                effect_msgs.append(f"{defender.species_name} endured the hit!")
        # Apply damage
        if damage > 0:
            defender.current_hp = max(0, defender.current_hp - damage)
            if move_data.get('category') in ['physical', 'special']:
                defender.last_damage_taken = damage
                defender.last_damage_category = move_data.get('category')
                defender.last_damage_from = attacker
            if getattr(defender, 'bide_turns_remaining', 0):
                defender.bide_damage = getattr(defender, 'bide_damage', 0) + damage
        if (
            ENHANCED_SYSTEMS_AVAILABLE
            and move_data.get('category') in ['physical', 'special']
            and attacker_battler != defender_battler
        ):
            defender.rage_fist_hits_taken = getattr(defender, 'rage_fist_hits_taken', 0) + 1

        if ENHANCED_SYSTEMS_AVAILABLE:
            exit_msg = self._maybe_queue_hp_switch(battle, defender_battler, defender)
            if exit_msg:
                messages.append(exit_msg)

        # Build message
        crit_text = " It's a critical hit!" if is_crit else ""
        effectiveness_text = ""
        if effectiveness > 1:
            effectiveness_text = " It's super effective!"
        elif effectiveness < 1 and effectiveness > 0:
            effectiveness_text = " It's not very effective..."
        elif effectiveness == 0:
            effectiveness_text = " It doesn't affect the target..."
        
        # Show who used the move and on whom (if single target)
        target_type = move_data.get('target', 'single')
        messages.append(self._build_move_message(attacker, move_data, defender, target_type))

        # Show damage as a separate message
        if damage > 0:
            damage_msg = f"{defender.species_name} took {damage} damage!{crit_text}{effectiveness_text}"
            messages.append(damage_msg)
        elif effectiveness == 0:
            messages.append(f"It doesn't affect {defender.species_name}...")
            # Track ineffective moves for AI learning
            if getattr(attacker_battler, 'is_ai', False):
                if not hasattr(battle, 'ai_ineffective_moves'):
                    battle.ai_ineffective_moves = {}
                pokemon_key = f"{attacker_battler.battler_id}_{id(attacker)}"
                if pokemon_key not in battle.ai_ineffective_moves:
                    battle.ai_ineffective_moves[pokemon_key] = set()
                battle.ai_ineffective_moves[pokemon_key].add(action.move_id)
        else:
            messages.append(f"{defender.species_name} took 0 damage!{crit_text}{effectiveness_text}")

        messages.extend(effect_msgs)

        if self.held_item_manager:
            post_msgs = self.held_item_manager.apply_after_damage(attacker, move_data, damage)
            messages.extend(post_msgs)

        if self.held_item_manager:
            reactive_msgs = self.held_item_manager.process_reactive_effects(
                defender, move_data, damage
            )
            messages.extend(reactive_msgs)

        # Handle moves that force the target to switch out without fainting
        if getattr(defender, '_force_switch', False) and defender.current_hp > 0:
            defender._force_switch = False

            defender_battler = next((b for b in battle.get_all_battlers() if defender in b.party), battle.opponent)
            if defender_battler.can_switch and defender_battler.has_usable_bench_pokemon():
                # Determine which active slot holds the target
                forced_position = None
                for pos_idx, party_idx in enumerate(defender_battler.active_positions):
                    if defender_battler.party[party_idx] == defender:
                        forced_position = pos_idx
                        break

                if forced_position is not None:
                    battle.pending_switches[defender_battler.battler_id] = {
                        'position': forced_position,
                        'switch_type': 'FORCED'
                    }
                    battle.phase = 'FORCED_SWITCH'
                    if not battle.forced_switch_battler_id:
                        battle.forced_switch_battler_id = defender_battler.battler_id
                        battle.forced_switch_position = forced_position
                    messages.append(f"{defender.species_name} was forced to switch out!")

        # Check for faint / dazed state
        if defender.current_hp <= 0:
            # Determine which battler owns the defender
            print(f"[DEBUG] Pokemon {defender.species_name} has fainted (HP: {defender.current_hp})")
            print(f"[DEBUG] Searching for owner among {len(battle.get_all_battlers())} battlers")
            defender_battler = None
            for b in battle.get_all_battlers():
                if defender in b.party:
                    defender_battler = b
                    print(f"[DEBUG] Found owner: {b.battler_name} (ID: {b.battler_id}, is_ai: {getattr(b, 'is_ai', False)})")
                    break
            if not defender_battler:
                print(f"[DEBUG] WARNING: Could not find owner for {defender.species_name}, defaulting to opponent")
                defender_battler = battle.opponent

            # Special handling for wild battles: wild Pokémon do not fully faint, they become "dazed"
            if battle.battle_type == BattleType.WILD and defender_battler == battle.opponent:
                # Set HP to 1 and mark dazed instead of true faint
                defender.current_hp = 1
                battle.wild_dazed = True
                battle.phase = 'DAZED'
                messages.append(f"The wild {defender.species_name} is dazed!")
            else:
                messages.append(f"{defender.species_name} fainted!")
                self._record_faint(defender_battler, defender)
                # Record opponent faint for EXP calculation
                self._record_opponent_faint_for_exp(battle, defender, defender_battler, attacker_battler)

                # Check for Aipom faint in Ambipom raid - trigger resonance broken
                if getattr(defender, "species_name", "").lower() == "aipom":
                    # Find Ambipom in the same battler team
                    for mon in defender_battler.get_active_pokemon():
                        if getattr(mon, "scripted_ai", None) == "ambipom_raid" and mon.current_hp > 0:
                            # Lower Ambipom's stats by 1
                            self._ensure_stat_stages(mon)
                            for stat in ['attack', 'defense', 'sp_attack', 'sp_defense', 'speed']:
                                mon.stat_stages[stat] = max(-6, mon.stat_stages.get(stat, 0) - 1)
                            boost_level = mon.stat_stages.get('attack', 0)
                            resonance_msg = f"Resonance broken! {mon.species_name}'s connection weakens!"
                            stat_msg = f"All stats fell! (Now {boost_level:+d})"
                            messages.append(f"{resonance_msg} {stat_msg}")

                            # Create special event for embed
                            resonance_broken_events.append({
                                "type": "resonance_broken",
                                "messages": [resonance_msg, stat_msg],
                                "actor": mon,
                                "custom_title": "Resonance Broken!",
                                "custom_color": discord.Color.red()
                            })
                            break

                    # Aipom heals all ally pokemon by 20% HP
                    heal_messages = []
                    for ally_mon in attacker_battler.get_active_pokemon():
                        if ally_mon.current_hp > 0:
                            max_hp = ally_mon.max_hp
                            heal_amount = int(max_hp * 0.20)
                            old_hp = ally_mon.current_hp
                            ally_mon.current_hp = min(max_hp, ally_mon.current_hp + heal_amount)
                            actual_heal = ally_mon.current_hp - old_hp
                            if actual_heal > 0:
                                heal_messages.append(f"{ally_mon.species_name} recovered {actual_heal} HP!")

                    if heal_messages:
                        # Create special event for healing embed
                        resonance_broken_events.append({
                            "type": "aipom_healing",
                            "messages": heal_messages,
                            "actor": defender,
                            "custom_title": "Aipom unleashes a strange energy, healing your pokemon!",
                            "custom_color": discord.Color.green()
                        })

                # Determine which position the fainted Pokemon was in
                fainted_position = None
                for pos_idx, party_idx in enumerate(defender_battler.active_positions):
                    if defender_battler.party[party_idx] == defender:
                        fainted_position = pos_idx
                        break

                # For player's Pokemon fainting (non‑AI), they need to switch (if they have Pokemon left)
                # In PVP, both trainer and opponent can be human players
                print(f"[DEBUG] Checking if battler {defender_battler.battler_id} ({defender_battler.battler_name}) is AI: {getattr(defender_battler, 'is_ai', 'ATTRIBUTE_MISSING')}")
                if not defender_battler.is_ai:
                    has_bench = defender_battler.has_usable_bench_pokemon(exclude_pokemon=defender)
                    print(f"[DEBUG] Battler has usable bench Pokemon: {has_bench}")
                    if has_bench:
                        # Add to pending switches
                        print(f"[DEBUG] Adding pending switch for battler {defender_battler.battler_id} ({defender_battler.battler_name}) at position {fainted_position}")
                        battle.pending_switches[defender_battler.battler_id] = {
                            'position': fainted_position,
                            'switch_type': 'FORCED'
                        }
                        battle.phase = 'FORCED_SWITCH'
                        print(f"[DEBUG] Set battle.phase to FORCED_SWITCH. Current pending_switches: {battle.pending_switches}")
                        # Maintain backwards compatibility with old fields
                        if not battle.forced_switch_battler_id:
                            battle.forced_switch_battler_id = defender_battler.battler_id
                            battle.forced_switch_position = fainted_position
                            print(f"[DEBUG] Set forced_switch_battler_id to {defender_battler.battler_id}")
                    else:
                        print(f"[DEBUG] Battler {defender_battler.battler_id} ({defender_battler.battler_name}) has no usable bench Pokemon")
                        if fainted_position is not None and fainted_position < len(defender_battler.active_positions):
                            defender_battler.active_positions.pop(fainted_position)
                        self._check_battle_end(battle)

                # For AI-controlled trainers (NPCs), auto-send the next Pokémon before continuing
                elif defender_battler.is_ai and battle.battle_type in (BattleType.TRAINER, BattleType.PVP):
                    print(f"[DEBUG] AI battler {defender_battler.battler_id} ({defender_battler.battler_name}) needs to switch")
                    if defender_battler.has_usable_bench_pokemon(exclude_pokemon=defender):
                        # Choose replacement index but DO NOT switch yet; queue it for after EOT
                        replacement_index = None
                        for idx, p in enumerate(defender_battler.party):
                            if p is defender:
                                continue
                            # Don't pick a Pokemon already on the field
                            if idx in defender_battler.active_positions:
                                continue
                            if getattr(p, 'current_hp', 0) > 0:
                                replacement_index = idx
                                break
                        if replacement_index is not None:
                            # Add to pending switches
                            battle.pending_switches[defender_battler.battler_id] = {
                                'position': fainted_position,
                                'switch_type': 'FORCED',
                                'ai_replacement_index': replacement_index
                            }
                            battle.phase = 'FORCED_SWITCH'
                            # Maintain backwards compatibility
                            if not battle.forced_switch_battler_id:
                                battle.forced_switch_battler_id = defender_battler.battler_id
                                battle.forced_switch_position = fainted_position
                            battle.pending_ai_switch_index = replacement_index
                    else:
                        if fainted_position is not None and fainted_position < len(defender_battler.active_positions):
                            defender_battler.active_positions.pop(fainted_position)
                        self._check_battle_end(battle)

        # Handle self-switch moves (Volt Switch, U-turn, etc.)
        if getattr(attacker, '_should_switch', False) and attacker.current_hp > 0:
            attacker._should_switch = False  # Clear the flag

            # Check if the attacker's battler can switch and has other Pokemon
            if attacker_battler.can_switch and attacker_battler.has_usable_bench_pokemon(exclude_pokemon=attacker):
                if attacker_battler.is_ai:
                    # AI auto-switches to first available Pokemon
                    replacement_index = None
                    for idx, p in enumerate(attacker_battler.party):
                        if p is attacker:
                            continue
                        if getattr(p, 'current_hp', 0) > 0:
                            replacement_index = idx
                            break
                    if replacement_index is not None:
                        switch_action = BattleAction(
                            action_type='switch',
                            battler_id=attacker_battler.battler_id,
                            switch_to_position=replacement_index
                        )
                        switch_result = self._execute_switch(battle, switch_action)
                        messages.extend(switch_result.get('messages', []))
                else:
                    # Player needs to choose which Pokemon to switch to
                    # Find the position of the attacker
                    attacker_position = None
                    for pos_idx, party_idx in enumerate(attacker_battler.active_positions):
                        if attacker_battler.party[party_idx] == attacker:
                            attacker_position = pos_idx
                            break

                    # Add to pending switches
                    battle.pending_switches[attacker_battler.battler_id] = {
                        'position': attacker_position,
                        'switch_type': 'VOLT'
                    }
                    # Set a flag that will be checked by the UI
                    battle.phase = 'VOLT_SWITCH'
                    # Maintain backwards compatibility
                    if not battle.forced_switch_battler_id:
                        battle.forced_switch_battler_id = attacker_battler.battler_id

        result = {"messages": messages}
        if resonance_broken_events:
            result["action_events"] = resonance_broken_events
        return result

    def _execute_revival_blessing(self, battle: BattleState, attacker_battler: Battler, attacker, action: BattleAction) -> Dict:
        """Execute Revival Blessing with explicit target selection."""

        messages: List[str] = [f"{attacker.species_name} used Revival Blessing!"]

        # Build candidate pool: all fainted allies on the attacker's team (includes other trainers in raids)
        team_battlers = battle.get_team_battlers(attacker_battler.battler_id)
        candidates = []
        for battler in team_battlers:
            for idx, mon in enumerate(battler.party):
                if mon is attacker:
                    continue
                if getattr(mon, 'current_hp', 0) <= 0:
                    candidates.append((battler, idx, mon))

        if not candidates:
            messages.append("But it failed! There was no one to revive.")
            return {"messages": messages}

        # Find the requested target
        target_battler_id = action.revive_target_battler_id
        target_party_index = action.revive_target_party_index
        target_entry = None
        for battler, idx, mon in candidates:
            if battler.battler_id == target_battler_id and idx == target_party_index:
                target_entry = (battler, idx, mon)
                break

        if not target_entry:
            target_entry = candidates[0]

        _, _, ally = target_entry
        ally.current_hp = max(1, ally.max_hp // 2)
        if hasattr(ally, 'status_manager'):
            ally.status_manager.major_status = None
            ally.status_manager.clear_volatile_statuses()

        messages.append(
            f"{attacker.species_name}'s Revival Blessing revived {ally.species_name}! ({ally.current_hp}/{ally.max_hp} HP)"
        )

        return {"messages": messages}

    
    
    def auto_switch_if_forced_ai(self, battle: BattleState) -> List[Dict[str, Any]]:
        """Perform any queued AI forced switch and return narration.

        This is used at end-of-turn (and can be re-used after manual switches).
        It no longer relies on `forced_switch_battler_id`, so it still works
        in doubles when both sides have a Pokémon faint in the same turn.
        """
        # If there is no pending AI choice, there's nothing to do
        idx = getattr(battle, "pending_ai_switch_index", None)
        if idx is None:
            return []

        # Determine which side is AI-controlled
        battler = battle.opponent if getattr(battle.opponent, "is_ai", False) else (
            battle.trainer if getattr(battle.trainer, "is_ai", False) else None
        )
        if battler is None:
            return []

        # Remember original forced-switch state so we can preserve player prompts
        original_phase = getattr(battle, "phase", None)
        original_forced_id = getattr(battle, "forced_switch_battler_id", None)
        original_forced_pos = getattr(battle, "forced_switch_position", None)

        # If the queued index is invalid or fainted, fall back to first healthy benched Pokémon
        if idx < 0 or idx >= len(battler.party) or getattr(battler.party[idx], "current_hp", 0) <= 0:
            idx = None
            for i, p in enumerate(battler.party):
                # Skip Pokémon that are already on the field
                if i in getattr(battler, "active_positions", []):
                    continue
                if getattr(p, "current_hp", 0) > 0:
                    idx = i
                    break
        if idx is None:
            # Clear stale pointer and bail
            battle.pending_ai_switch_index = None
            return []

        # Decide which active slot to replace (for doubles)
        switch_position = 0  # default for singles
        active = list(battler.get_active_pokemon() or [])
        if active:
            for pos, mon in enumerate(active):
                if getattr(mon, "current_hp", 0) <= 0:
                    switch_position = pos
                    break

        # Build a switch action targeted at that slot
        action = BattleAction(
            action_type="switch",
            battler_id=battler.battler_id,
            switch_to_position=idx,
        )
        # Hint to the switch executor which active position to replace
        setattr(action, "pokemon_position", switch_position)

        # Execute the switch directly; we don't want to disturb any player FORCED_SWITCH state
        result = self._execute_switch(battle, action, forced=False)

        # Clear the pending pointer now that the AI has moved
        battle.pending_ai_switch_index = None

        # Remove this AI battler from pending_switches if present
        if battler.battler_id in battle.pending_switches:
            del battle.pending_switches[battler.battler_id]

        # Check if any other battler needs to switch
        player_needs_switch = False

        # First check pending_switches for other players
        for other_battler_id, switch_info in battle.pending_switches.items():
            other_battler = self._get_battler_by_id(battle, other_battler_id)
            if other_battler and not getattr(other_battler, 'is_ai', False):
                player_needs_switch = True
                battle.phase = 'FORCED_SWITCH' if switch_info.get('switch_type') == 'FORCED' else 'VOLT_SWITCH'
                battle.forced_switch_battler_id = other_battler_id
                battle.forced_switch_position = switch_info.get('position')
                break

        # If no pending switches found, also check for any fainted Pokemon that weren't tracked
        if not player_needs_switch:
            if original_phase in ['FORCED_SWITCH', 'VOLT_SWITCH'] and original_forced_id == getattr(battler, "battler_id", None):
                # Determine the other battler (player)
                other_battler = battle.trainer if battler == battle.opponent else battle.opponent

                # Check if the other battler has any fainted active Pokemon
                if not getattr(other_battler, "is_ai", False):  # Only check for human player
                    active_pokemon = other_battler.get_active_pokemon()
                    for pos_idx, active_mon in enumerate(active_pokemon):
                        if getattr(active_mon, "current_hp", 0) <= 0:
                            if other_battler.has_usable_bench_pokemon(exclude_pokemon=active_mon):
                                # Player has a fainted Pokemon that needs switching
                                player_needs_switch = True
                                # Add to pending switches
                                battle.pending_switches[other_battler.battler_id] = {
                                    'position': pos_idx,
                                    'switch_type': 'FORCED'
                                }
                                # Set up forced switch for player
                                battle.phase = 'FORCED_SWITCH'
                                battle.forced_switch_battler_id = other_battler.battler_id
                                battle.forced_switch_position = pos_idx
                                break

        # Only reset to WAITING_ACTIONS if player doesn't need to switch
        if not player_needs_switch:
            battle.phase = 'WAITING_ACTIONS'
            battle.forced_switch_battler_id = None
            battle.forced_switch_position = None

        return [
            {
                "messages": result.get("messages", []),
                "pokemon": result.get("pokemon") or result.get("switched_in"),
                "source": "auto",
            }
        ] if result else []

    def _get_battler_by_id(self, battle: BattleState, battler_id: int) -> Battler:
        """Return the Battler object matching the given ID, searching allies in raids."""

        for battler in battle.get_all_battlers():
            if battler.battler_id == battler_id:
                return battler
        return battle.opponent

    def _apply_entry_hazards(self, battle: BattleState, battler: Battler, pokemon: Any) -> List[str]:
        """Apply field hazards to a newly-entered pokemon and return narration.
        Grounded check is simplified: Flying-type or Levitate ability -> not grounded.
        Implements: Stealth Rock, Spikes (1-3 layers), Toxic Spikes (1-2 layers), Sticky Web.
        """
        messages: List[str] = []

        # Which hazard map applies to this side? If this battler just entered, hazards were set by the opponent.
        hazards = battle.opponent_hazards if battler == battle.opponent else battle.trainer_hazards
        if not hazards:
            return messages

        # Helper: get types and simple grounded/ability
        types = [t.lower() for t in getattr(getattr(pokemon, 'species_data', {}), 'get', lambda *_: [])('types', [])] if False else [t.lower() for t in (getattr(pokemon, 'species_data', {}) or {}).get('types', [])]
        ability_name = getattr(pokemon, 'ability', None) or getattr(pokemon, 'ability_name', None)
        has_type = lambda t: t in types
        is_grounded = (not has_type('flying')) and (str(ability_name).lower() != 'levitate')

        # --- Stealth Rock ---
        if 'stealth_rock' in hazards and hasattr(pokemon, 'species_data'):
            chart = self.type_chart.chart if hasattr(self.type_chart, 'chart') else self.type_chart
            eff = 1.0
            if chart and 'rock' in chart:
                for t in types:
                    if t in chart['rock']:
                        eff *= chart['rock'][t]
            base = max(1, pokemon.max_hp // 8)
            dmg = max(1, int(base * eff)) if eff > 0 else 0
            if dmg > 0:
                pokemon.current_hp = max(0, pokemon.current_hp - dmg)
                messages.append(f"{pokemon.species_name} is hurt by Stealth Rock! (-{dmg} HP)")

        # --- Spikes (grounded only) ---
        if is_grounded and 'spikes' in hazards:
            layers = min(3, int(hazards.get('spikes', 1)))
            # 1 layer: 1/8, 2: 1/6, 3: 1/4
            if layers == 1:
                frac_num, frac_den = 1, 8
            elif layers == 2:
                frac_num, frac_den = 1, 6
            else:
                frac_num, frac_den = 1, 4
            dmg = max(1, (pokemon.max_hp * frac_num) // frac_den)
            pokemon.current_hp = max(0, pokemon.current_hp - dmg)
            messages.append(f"{pokemon.species_name} is hurt by Spikes! (-{dmg} HP)")

        # --- Toxic Spikes (grounded only) ---
        if 'toxic_spikes' in hazards and is_grounded:
            layers = min(2, int(hazards.get('toxic_spikes', 1)))
            # Poison-type absorbs the spikes (if grounded)
            if has_type('poison'):
                # Clear all layers from this side
                if battler == battle.opponent:
                    battle.opponent_hazards.pop('toxic_spikes', None)
                else:
                    battle.trainer_hazards.pop('toxic_spikes', None)
                messages.append(f"{pokemon.species_name} absorbed the Toxic Spikes!")
            else:
                # Steel-type and Poison-type can't be poisoned; Flying/Levitate handled by grounded
                if not has_type('steel'):
                    # Apply major status via status_manager if available
                    if hasattr(pokemon, 'status_manager'):
                        status = 'tox' if layers >= 2 else 'psn'
                        can_apply, _ = pokemon.status_manager.can_apply_status(status, None, pokemon)
                        if can_apply:
                            success, msg = pokemon.status_manager.apply_status(status)
                            if success and msg:
                                messages.append(f"{pokemon.species_name} {msg}")

        # --- Sticky Web (grounded only): lower Speed by 1 stage ---
        if 'sticky_web' in hazards and is_grounded:
            if not hasattr(pokemon, 'stat_stages'):
                pokemon.stat_stages = {
                    'attack': 0, 'defense': 0, 'sp_attack': 0,
                    'sp_defense': 0, 'speed': 0, 'evasion': 0, 'accuracy': 0
                }
            pokemon.stat_stages['speed'] = max(-6, pokemon.stat_stages['speed'] - 1)
            messages.append(f"{pokemon.species_name}'s Speed fell! (-1)")

        if ENHANCED_SYSTEMS_AVAILABLE:
            exit_msg = self._maybe_queue_hp_switch(battle, battler, pokemon)
            if exit_msg:
                messages.append(exit_msg)

        return messages
    def _execute_switch(self, battle: BattleState, action: BattleAction, forced: bool = False) -> Dict:
        """Execute a Pokemon switch"""
        battler = self._get_battler_by_id(battle, action.battler_id)

        # Determine which position to switch (for forced switches from fainting in doubles)
        switch_position = 0  # Default for singles
        if forced and battle.forced_switch_position is not None:
            switch_position = battle.forced_switch_position
        elif hasattr(action, 'pokemon_position') and action.pokemon_position is not None:
            switch_position = action.pokemon_position

        # Get old and new Pokemon
        old_active = battler.get_active_pokemon()
        old_pokemon = old_active[switch_position] if switch_position < len(old_active) else old_active[0]

        if not forced and hasattr(old_pokemon, 'status_manager'):
            trapping_statuses = {
                'partiallytrapped', 'bind', 'wrap', 'firespin', 'whirlpool', 'sandtomb', 'clamp', 'infestation'
            }
            if any(old_pokemon.status_manager.has_status(status) for status in trapping_statuses):
                return {"messages": [f"{old_pokemon.species_name} is trapped and can't be switched out!"]}

        new_pokemon = battler.party[action.switch_to_position]

        # Switch
        battler.active_positions[switch_position] = action.switch_to_position
        self._mark_first_turn_entry(new_pokemon)

        if self.held_item_manager:
            self.held_item_manager.clear_choice_lock(old_pokemon)

        # Trigger entry abilities
        messages = []
        if ENHANCED_SYSTEMS_AVAILABLE:
            ability_msgs = self.ability_handler.trigger_on_entry(new_pokemon, battle)
            messages.extend(ability_msgs)

        messages.extend(self._apply_entry_hazards(battle, battler, new_pokemon))

        # Baton Pass: transfer select effects and stat stages
        baton_pass_payload = getattr(old_pokemon, '_baton_pass_transfer', None)
        if baton_pass_payload:
            old_pokemon._baton_pass_transfer = None
            if baton_pass_payload.get('stat_stages') is not None:
                new_pokemon.stat_stages = baton_pass_payload['stat_stages']

            if baton_pass_payload.get('volatiles'):
                if not hasattr(new_pokemon, 'status_manager'):
                    new_pokemon.status_manager = StatusConditionManager()
                for status_name, condition_data in baton_pass_payload['volatiles'].items():
                    new_pokemon.status_manager.apply_status(
                        status_name,
                        duration=condition_data.get('duration'),
                        source=condition_data.get('source'),
                        metadata=condition_data.get('metadata')
                    )

        if forced:
            lead_messages = [f"{battler.battler_name} sent out {new_pokemon.species_name}!"]
        else:
            lead_messages = [
                f"{battler.battler_name} withdrew {old_pokemon.species_name}!",
                f"Go, {new_pokemon.species_name}!"
            ]

        return {
            "messages": lead_messages + messages,
            "pokemon": new_pokemon
        }

    def force_switch(self, battle_id: str, battler_id: int, switch_to_position: int) -> Dict:
        """Resolve a mandatory switch outside of normal turn order."""
        battle = self.active_battles.get(battle_id)
        if not battle:
            return {"error": "Battle not found"}

        # Check if this battler has a pending switch (new dict or old fields)
        has_pending_switch = (
            battler_id in battle.pending_switches or
            (battle.phase in ['FORCED_SWITCH', 'VOLT_SWITCH'] and battle.forced_switch_battler_id == battler_id)
        )
        if not has_pending_switch:
            return {"error": "No forced switch is pending"}

        battler = self._get_battler_by_id(battle, battler_id)
        if switch_to_position < 0 or switch_to_position >= len(battler.party):
            return {"error": "Invalid party slot"}
        target = battler.party[switch_to_position]
        if getattr(target, 'current_hp', 0) <= 0:
            return {"error": "That Pokémon can't battle"}

        action = BattleAction(action_type='switch', battler_id=battler_id, switch_to_position=switch_to_position)
        result = self._execute_switch(battle, action, forced=True)

        # Remove this battler from pending switches
        if battler_id in battle.pending_switches:
            del battle.pending_switches[battler_id]

        # Check if any other human battler still needs to switch
        # First check the pending_switches dict
        next_player_switch = None
        for other_battler_id, switch_info in battle.pending_switches.items():
            other_battler = self._get_battler_by_id(battle, other_battler_id)
            if other_battler and not getattr(other_battler, 'is_ai', False):
                next_player_switch = (other_battler_id, switch_info)
                break

        # If no pending switches, also scan for any fainted Pokemon that weren't tracked
        if not next_player_switch:
            for other_battler in battle.get_all_battlers():
                if other_battler.battler_id == battler_id:
                    continue
                if getattr(other_battler, 'is_ai', False):
                    continue

                # Skip eliminated battlers (those with no Pokemon left)
                if getattr(other_battler, 'is_eliminated', False):
                    continue

                active_pokemon = other_battler.get_active_pokemon()
                for pos_idx, active_mon in enumerate(active_pokemon):
                    if getattr(active_mon, 'current_hp', 0) <= 0:
                        # Add to pending switches
                        battle.pending_switches[other_battler.battler_id] = {
                            'position': pos_idx,
                            'switch_type': 'FORCED'
                        }
                        next_player_switch = (other_battler.battler_id, battle.pending_switches[other_battler.battler_id])
                        break
                if next_player_switch:
                    break

        # Set the next switch or reset to WAITING_ACTIONS
        if next_player_switch:
            battler_id_next, switch_info_next = next_player_switch
            battle.phase = 'FORCED_SWITCH' if switch_info_next.get('switch_type') == 'FORCED' else 'VOLT_SWITCH'
            battle.forced_switch_battler_id = battler_id_next
            battle.forced_switch_position = switch_info_next.get('position')
        else:
            battle.phase = 'WAITING_ACTIONS'
            battle.forced_switch_battler_id = None
            battle.forced_switch_position = None

        battle.pending_ai_switch_index = None
        battle.pending_actions.pop(str(battler_id), None)

        return result
    
    def _execute_item(self, battle: BattleState, action: BattleAction) -> Dict:
        """Execute an item use"""
        # TODO: Implement item system
        return {"messages": [f"Used {action.item_id}!"]}
    
    def _execute_flee(self, battle: BattleState, action: BattleAction) -> Dict:
        """Execute flee attempt"""
        if battle.battle_type != BattleType.WILD:
            return {"messages": ["Can't flee from a trainer battle!"]}
        
        # Simple flee chance for now
        if random.random() < 0.5:
            battle.is_over = True
            battle.fled = True
            battle.winner = None
            return {"messages": ["Got away safely!"]}
        else:
            return {"messages": ["Can't escape!"]}
    
    def _process_end_of_turn(self, battle: BattleState) -> List[str]:
        """Process end-of-turn effects"""
        messages = []
        
        if not ENHANCED_SYSTEMS_AVAILABLE:
            return []
        
        # Status damage - apply to ALL active Pokemon including raid allies (except eliminated battlers)
        all_active_pokemon = []

        # Get all active Pokemon from all non-eliminated battlers
        for battler in battle.get_all_battlers():
            if not battler.is_eliminated:
                all_active_pokemon.extend(battler.get_active_pokemon())

        # Apply status effects to all active Pokemon
        for pokemon in all_active_pokemon:
            if hasattr(pokemon, 'status_manager'):
                status_msgs = pokemon.status_manager.apply_end_of_turn_effects(pokemon)
                messages.extend(status_msgs)
            if self.held_item_manager:
                messages.extend(self.held_item_manager.process_end_of_turn(pokemon))

        messages.extend(self._apply_ambipom_rally_cry_resonance(battle))

        # Weather effects - apply to ALL active Pokemon including raid allies (except eliminated battlers)
        if battle.weather:
            all_active_pokemon = []

            # Get all active Pokemon from all non-eliminated battlers
            for battler in battle.get_all_battlers():
                if not battler.is_eliminated:
                    all_active_pokemon.extend(battler.get_active_pokemon())

            # Apply weather effects to all active Pokemon and track faints
            fainted_pokemon = []
            for pokemon in all_active_pokemon:
                weather_msg = self.ability_handler.apply_weather_damage(pokemon, battle.weather)
                if weather_msg:
                    messages.append(weather_msg)

                # Check if Pokemon fainted from weather damage
                if getattr(pokemon, 'current_hp', 0) <= 0:
                    fainted_pokemon.append(pokemon)

                heal_msg = self.ability_handler.apply_weather_healing(pokemon, battle.weather)
                if heal_msg:
                    messages.append(heal_msg)

            # Handle faints from weather damage
            for fainted_mon in fainted_pokemon:
                messages.append(f"{getattr(fainted_mon, 'species_name', 'The Pokémon')} fainted!")

                # Find which battler owns this Pokemon and set up forced switch
                for battler in battle.get_all_battlers():
                    if not battler.is_eliminated and fainted_mon in battler.party:
                        self._record_faint(battler, fainted_mon)
                        # Record opponent faint for EXP calculation (no specific attacker for weather damage)
                        self._record_opponent_faint_for_exp(battle, fainted_mon, battler, None)
                        # Find position of fainted Pokemon
                        fainted_position = None
                        for pos_idx, party_idx in enumerate(battler.active_positions):
                            if battler.party[party_idx] == fainted_mon:
                                fainted_position = pos_idx
                                break

                        if fainted_position is not None:
                            # For non-AI players, queue forced switch
                            if not battler.is_ai:
                                if battler.has_usable_bench_pokemon(exclude_pokemon=fainted_mon):
                                    battle.pending_switches[battler.battler_id] = {
                                        'position': fainted_position,
                                        'switch_type': 'FORCED'
                                    }
                                    battle.phase = 'FORCED_SWITCH'
                                    if not battle.forced_switch_battler_id:
                                        battle.forced_switch_battler_id = battler.battler_id
                                        battle.forced_switch_position = fainted_position
                                elif fainted_position is not None and fainted_position < len(battler.active_positions):
                                    battler.active_positions.pop(fainted_position)
                            # For AI, queue replacement
                            elif battler.is_ai and battle.battle_type in (BattleType.TRAINER, BattleType.PVP):
                                if battler.has_usable_bench_pokemon(exclude_pokemon=fainted_mon):
                                    replacement_index = None
                                    for idx, p in enumerate(battler.party):
                                        if p is fainted_mon or idx in battler.active_positions:
                                            continue
                                        if getattr(p, 'current_hp', 0) > 0:
                                            replacement_index = idx
                                            break
                                    if replacement_index is not None:
                                        battle.pending_switches[battler.battler_id] = {
                                            'position': fainted_position,
                                            'switch_type': 'FORCED',
                                            'ai_replacement_index': replacement_index
                                        }
                                        battle.phase = 'FORCED_SWITCH'
                                        if not battle.forced_switch_battler_id:
                                            battle.forced_switch_battler_id = battler.battler_id
                                            battle.forced_switch_position = fainted_position
                                elif fainted_position is not None and fainted_position < len(battler.active_positions):
                                    battler.active_positions.pop(fainted_position)
                        break

            # Check for battle end and mark eliminated battlers
            self._check_battle_end(battle)

            # Decrement weather (only if it has a turn count)
            if battle.weather_turns > 0:
                battle.weather_turns -= 1
                if battle.weather_turns <= 0:
                    # If rogue weather exists and current weather is not rogue weather, restore it
                    if battle.rogue_weather and battle.weather != battle.rogue_weather:
                        messages.append(f"The {battle.weather} subsided!")
                        battle.weather = battle.rogue_weather
                        battle.weather_turns = 999
                        messages.append(f"The {battle.rogue_weather} returned!")
                    # If overworld weather exists, restore it (or keep it active if it's the same)
                    elif battle.overworld_weather:
                        if battle.weather == battle.overworld_weather:
                            # Same weather type - just make it indefinite again
                            battle.weather_turns = 0
                        else:
                            # Different weather - restore overworld weather
                            messages.append(f"The {battle.weather} subsided!")
                            battle.weather = battle.overworld_weather
                            battle.weather_turns = 0  # Indefinite duration
                            messages.append(f"The {battle.overworld_weather} returned!")
                    else:
                        messages.append(f"The {battle.weather} subsided!")
                        battle.weather = None

        # Terrain effects
        if battle.terrain:
            battle.terrain_turns -= 1
            if battle.terrain_turns <= 0:
                # If rogue terrain exists and current terrain is not rogue terrain, restore it
                if battle.rogue_terrain and battle.terrain != battle.rogue_terrain:
                    messages.append(f"The {battle.terrain} terrain faded!")
                    battle.terrain = battle.rogue_terrain
                    battle.terrain_turns = 999
                    messages.append(f"The {battle.rogue_terrain} terrain returned!")
                else:
                    messages.append(f"The {battle.terrain} terrain faded!")
                    battle.terrain = None

        # Trick Room duration
        if getattr(battle, 'trick_room_turns', 0) > 0:
            battle.trick_room_turns -= 1
            if battle.trick_room_turns <= 0:
                messages.append("The dimensions returned to normal!")

        if ENHANCED_SYSTEMS_AVAILABLE:
            for battler in battle.get_all_battlers():
                if battler.is_eliminated:
                    continue
                for mon in battler.get_active_pokemon():
                    exit_msg = self._maybe_queue_hp_switch(battle, battler, mon)
                    if exit_msg:
                        messages.append(exit_msg)

                    schooling_msg = self.ability_handler.apply_schooling(mon)
                    if schooling_msg:
                        messages.append(schooling_msg)

        return messages
    
    def _check_battle_end(self, battle: BattleState):
        """Check if battle should end"""
        def team_has_usable(battler: Battler) -> bool:
            team = battle.get_team_battlers(battler.battler_id)
            return any(getattr(mon, 'current_hp', 0) > 0 for member in team for mon in getattr(member, 'party', []))

        trainer_has_pokemon = team_has_usable(battle.trainer)
        opponent_has_pokemon = team_has_usable(battle.opponent)

        # Mark battlers as eliminated when they have no usable Pokemon
        for battler in battle.get_all_battlers():
            has_usable = battler.has_usable_pokemon()
            # Debug: Show detailed party state
            party_hp = [(p.species_name if hasattr(p, 'species_name') else 'Unknown', getattr(p, 'current_hp', 0), getattr(p, 'max_hp', 0)) for p in battler.party]
            print(f"[DEBUG] _check_battle_end: Battler {battler.battler_id} ({battler.battler_name}), has_usable={has_usable}, party_hp={party_hp}")

            if not has_usable:
                if not battler.is_eliminated:
                    print(f"[DEBUG] Marking battler {battler.battler_id} ({battler.battler_name}) as eliminated")
                battler.is_eliminated = True
            elif battler.is_eliminated:
                # Safety check: Reset is_eliminated if battler has usable Pokemon
                # This prevents bugs where players are incorrectly stuck in eliminated state
                print(f"[DEBUG] SAFETY: Resetting is_eliminated for battler {battler.battler_id} ({battler.battler_name}) who has usable Pokemon")
                battler.is_eliminated = False

        if not trainer_has_pokemon and not opponent_has_pokemon:
            battle.is_over = True
            battle.winner = 'draw'
        elif not trainer_has_pokemon:
            battle.is_over = True
            battle.winner = 'opponent'
        elif not opponent_has_pokemon:
            battle.is_over = True
            battle.winner = 'trainer'
    
    # ========================
    # Battle Info Getters
    # ========================
    
    def get_battle(self, battle_id: str) -> Optional[BattleState]:
        """Get battle state"""
        return self.active_battles.get(battle_id)
    
    def end_battle(self, battle_id: str):
        """Clean up a finished battle"""
        battle = self.active_battles.pop(battle_id, None)
        if battle:
            self._revert_mega_evolutions(battle)


# ========================
# Command Parser
# ========================


# ========================
# Command Parser
# ========================

class CommandParser:
    """Parse natural language battle commands into BattleActions"""
    def __init__(self, moves_db):
        self.moves_db = moves_db

    def parse(self, command: str, active_pokemon: Any, battler_id: int) -> Optional[BattleAction]:
        """Parse a simple command into a BattleAction.

        Supports:
          - 'switch'/'swap'/'go' -> None (UI must pick target)
          - otherwise: tries to match a known move in user's move list
        """
        if not command:
            return None
        command = command.lower().strip()

        # Switch intent: handled by UI elsewhere
        if any(w in command for w in ('switch', 'swap', 'go ')):
            return None

        # Try to match one of the user's moves
        for mv in getattr(active_pokemon, 'moves', []):
            md = self.moves_db.get_move(mv.get('move_id'))
            if not md:
                continue
            move_name = (md.get('name') or md.get('id') or '').lower()
            move_id = md.get('id') or mv.get('move_id')
            if (move_name and move_name in command) or (move_id and move_id in command):
                return BattleAction(
                    action_type='move',
                    battler_id=battler_id,
                    move_id=move_id,
                    target_position=0
                )

        return None
