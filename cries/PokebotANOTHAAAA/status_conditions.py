"""
Status Condition System
Handles all major and volatile status conditions in Pokemon battles
Based on Pokemon Showdown's condition system
"""

from enum import Enum
from typing import Dict, Optional, Any, Callable
import csv
from dataclasses import dataclass, field
import random


class StatusType(Enum):
    """Major status conditions (persist between turns and switching)"""
    BURN = "brn"
    FREEZE = "frz"
    PARALYSIS = "par"
    POISON = "psn"
    BADLY_POISON = "tox"
    SLEEP = "slp"
    

class VolatileStatus(Enum):
    """Volatile status (removed on switch)"""
    CONFUSION = "confusion"
    CURSE = "curse"
    EMBARGO = "embargo"
    ENCORE = "encore"
    FLINCH = "flinch"
    HEAL_BLOCK = "healblock"
    LEECH_SEED = "leechseed"
    NIGHTMARE = "nightmare"
    PERISH_SONG = "perish"
    TAUNT = "taunt"
    TORMENT = "torment"
    SUBSTITUTE = "substitute"
    # Move-specific volatiles
    PROTECT = "protect"
    DETECT = "detect"
    ENDURE = "endure"
    # Stat stages
    FOCUS_ENERGY = "focusenergy"  # Increased crit rate
    FOLLOW_ME = "follow_me"
    # Trapping moves (generic status for all binding moves)
    PARTIALLY_TRAPPED = "partiallytrapped"
    BIND = "bind"
    WRAP = "wrap"
    FIRE_SPIN = "firespin"
    WHIRLPOOL = "whirlpool"
    SAND_TOMB = "sandtomb"
    CLAMP = "clamp"
    INFESTATION = "infestation"
    # Field effects (team-wide)
    LIGHT_SCREEN = "lightscreen"
    REFLECT = "reflect"
    AURORA_VEIL = "auroraveil"
    SAFEGUARD = "safeguard"
    MIST = "mist"
    LUCKY_CHANT = "luckychant"
    TAILWIND = "tailwind"
    # Special statuses
    YAWN = "yawn"  # Sleep next turn
    RAPID_SPIN = "rapidspin"  # Used to clear hazards
    SALT_CURE = "saltcure"
    SPARKLING_ARIA = "sparklingaria"
    SYRUP_BOMB = "syrupbomb"
    

@dataclass
class StatusCondition:
    """Represents an active status condition on a Pokemon"""
    status_type: str  # StatusType or VolatileStatus value
    duration: Optional[int] = None  # Turns remaining (None = indefinite)
    counter: int = 0  # Generic counter for various uses
    source: Optional[Any] = None  # The Pokemon/move that caused this
    metadata: Dict = field(default_factory=dict)  # Additional data
    
    def tick_turn(self) -> bool:
        """
        Advance the condition by one turn
        Returns True if the condition should be removed
        """
        if self.duration is not None:
            self.duration -= 1
            return self.duration <= 0
        return False


class StatusConditionManager:
    """
    Manages status conditions for a Pokemon
    Handles application, removal, and effects of status conditions
    """
    
    def __init__(self):
        self.major_status: Optional[StatusCondition] = None
        self.volatile_statuses: Dict[str, StatusCondition] = {}

        # Status immunity tracking
        self.immunities = set()  # Set of status types this Pokemon is immune to
        self.freeze_flavor_text = self._load_freeze_flavor_text()

    def _load_freeze_flavor_text(self) -> str:
        """Grab a short Gen 9-friendly freeze blurb from pokeapi CSVs."""
        try:
            with open('pokeapi_csv_bot/move_meta_ailment_names.csv', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)  # skip header
                for row in reader:
                    # move_meta_ailment_id, local_language_id, name
                    if len(row) >= 3 and row[0] == '3' and row[1] == '9':
                        return f"{row[2]} wore off as the ice melted away."
        except Exception:
            pass
        return "The ice melted away."
    
    def has_status(self, status_type: str) -> bool:
        """Check if Pokemon has a specific status"""
        if self.major_status and self.major_status.status_type == status_type:
            return True
        return status_type in self.volatile_statuses
    
    def has_any_major_status(self) -> bool:
        """Check if Pokemon has any major status"""
        return self.major_status is not None
    
    def can_apply_status(self, status_type: str, pokemon_types: list = None, pokemon: Any = None) -> tuple[bool, Optional[str]]:
        """
        Check if a status can be applied
        Returns (can_apply, failure_reason)
        """
        # Raid boss immunities
        if pokemon and getattr(pokemon, "is_raid_boss", False):
            if status_type == StatusType.SLEEP.value:
                return False, "Rogue Pokemon cannot be put to sleep!"

        # Check immunities
        if status_type in self.immunities:
            return False, f"Immune to {status_type}"

        # Type-based immunities
        if pokemon_types:
            if status_type == StatusType.BURN.value:
                if 'fire' in pokemon_types:
                    return False, "Fire types can't be burned"
                if 'water' in pokemon_types:
                    return False, "Water types can't be burned"
            if status_type == StatusType.FREEZE.value and 'ice' in pokemon_types:
                return False, "Ice types can't be frozen"
            if status_type == StatusType.PARALYSIS.value and 'electric' in pokemon_types:
                return False, "Electric types can't be paralyzed"
            if status_type in [StatusType.POISON.value, StatusType.BADLY_POISON.value]:
                if 'poison' in pokemon_types or 'steel' in pokemon_types:
                    return False, f"{pokemon_types[0].title()} types can't be poisoned"
        
        # Can only have one major status at a time
        if status_type in [s.value for s in StatusType]:
            if self.major_status:
                return False, f"Already has {self.major_status.status_type}"
        
        # Some volatile statuses don't stack
        if status_type in self.volatile_statuses:
            return False, f"Already has {status_type}"
        
        return True, None
    
    def apply_status(self, status_type: str, duration: Optional[int] = None, 
                    source: Any = None, metadata: Dict = None) -> tuple[bool, Optional[str]]:
        """
        Apply a status condition
        Returns (success, message)
        """
        condition = StatusCondition(
            status_type=status_type,
            duration=duration,
            source=source,
            metadata=metadata or {}
        )
        
        # Major status
        if status_type in [s.value for s in StatusType]:
            if self.major_status:
                return False, f"Already has {self.major_status.status_type}"
            
            # Sleep has random duration 1-3 turns
            if status_type == StatusType.SLEEP.value and duration is None:
                condition.duration = random.randint(1, 3)
            
            self.major_status = condition
            return True, self._get_status_application_message(status_type)
        
        # Volatile status
        if status_type in [s.value for s in VolatileStatus]:
            if status_type in self.volatile_statuses:
                return False, f"Already has {status_type}"
            self.volatile_statuses[status_type] = condition
            return True, self._get_status_application_message(status_type)
        
        return False, f"Unknown status type: {status_type}"
    
    def remove_status(self, status_type: str) -> bool:
        """Remove a specific status condition"""
        if self.major_status and self.major_status.status_type == status_type:
            self.major_status = None
            return True
        
        if status_type in self.volatile_statuses:
            del self.volatile_statuses[status_type]
            return True
        
        return False
    
    def clear_volatile_statuses(self):
        """Clear all volatile statuses (used when switching out)"""
        self.volatile_statuses.clear()
    
    def apply_end_of_turn_effects(self, pokemon: Any) -> list[str]:
        """
        Apply end-of-turn status effects
        Returns list of messages describing what happened
        """
        messages = []
        # If the Pokémon has already fainted, skip any end-of-turn damage
        if getattr(pokemon, "current_hp", 0) <= 0:
            return messages

        # Major status effects
        if self.major_status:
            status = self.major_status.status_type
            is_raid_boss = getattr(pokemon, "is_raid_boss", False)

            if status == StatusType.BURN.value:
                damage = max(1, pokemon.max_hp // 16)
                # Raid bosses take 1/5 (20%) burn damage
                if is_raid_boss:
                    damage = max(1, damage // 5)
                pokemon.current_hp = max(0, pokemon.current_hp - damage)
                messages.append(f"{pokemon.species_name} was hurt by its burn! (-{damage} HP)")

            elif status == StatusType.POISON.value:
                damage = max(1, pokemon.max_hp // 8)
                # Raid bosses take 1/5 (20%) poison damage
                if is_raid_boss:
                    damage = max(1, damage // 5)
                pokemon.current_hp = max(0, pokemon.current_hp - damage)
                messages.append(f"{pokemon.species_name} was hurt by poison! (-{damage} HP)")

            elif status == StatusType.BADLY_POISON.value:
                # Raid bosses have counter increase at half rate (0.5 per turn)
                if is_raid_boss:
                    self.major_status.counter += 0.5
                else:
                    self.major_status.counter += 1
                damage = max(1, int(pokemon.max_hp * self.major_status.counter // 16))
                # Raid bosses also take 1/5 (20%) badly poison damage
                if is_raid_boss:
                    damage = max(1, damage // 5)
                pokemon.current_hp = max(0, pokemon.current_hp - damage)
                messages.append(f"{pokemon.species_name} was badly poisoned! (-{damage} HP)")

            elif status == StatusType.SLEEP.value:
                if self.major_status.tick_turn():
                    self.major_status = None
                    messages.append(f"{pokemon.species_name} woke up!")

        # Volatile status effects
        volatiles_to_remove = []
        for status_name, status in list(self.volatile_statuses.items()):

            if status_name == VolatileStatus.CONFUSION.value:
                if status.tick_turn():
                    volatiles_to_remove.append(status_name)
                    messages.append(f"{pokemon.species_name} snapped out of confusion!")

            elif status_name == VolatileStatus.LEECH_SEED.value:
                if status.source and hasattr(status.source, 'current_hp'):
                    damage = max(1, pokemon.max_hp // 8)
                    pokemon.current_hp = max(0, pokemon.current_hp - damage)
                    heal = min(damage, status.source.max_hp - status.source.current_hp)
                    status.source.current_hp = min(status.source.max_hp, status.source.current_hp + heal)
                    messages.append(f"{pokemon.species_name} was hurt by Leech Seed! (-{damage} HP)")
                    messages.append(f"{status.source.species_name} absorbed HP! (+{heal} HP)")

            # Remove trapping move volatiles after turn
            elif status_name in [VolatileStatus.BIND.value, VolatileStatus.WRAP.value,
                                VolatileStatus.FIRE_SPIN.value, VolatileStatus.WHIRLPOOL.value,
                                VolatileStatus.SAND_TOMB.value, VolatileStatus.CLAMP.value,
                                VolatileStatus.INFESTATION.value]:
                damage = max(1, pokemon.max_hp // 8)
                pokemon.current_hp = max(0, pokemon.current_hp - damage)
                status_display = status_name.replace("_", " ").title()
                messages.append(f"{pokemon.species_name} is hurt by {status_display}! (-{damage} HP)")

                if status.tick_turn():
                    volatiles_to_remove.append(status_name)
                    status_display = status_name.replace("_", " ").title()
                    messages.append(f"{pokemon.species_name} was freed from {status_display}!")

            # Generic duration handler for other volatile statuses (e.g., Follow Me)
            elif status.duration is not None:
                if status.tick_turn():
                    volatiles_to_remove.append(status_name)


        # Generic duration tick for any other temporaries (e.g., endure, protect)
        for name, status in list(self.volatile_statuses.items()):
            if name in volatiles_to_remove:
                continue
            if name not in [VolatileStatus.CONFUSION.value, VolatileStatus.LEECH_SEED.value,
                            VolatileStatus.BIND.value, VolatileStatus.WRAP.value,
                            VolatileStatus.FIRE_SPIN.value, VolatileStatus.WHIRLPOOL.value,
                            VolatileStatus.SAND_TOMB.value, VolatileStatus.CLAMP.value,
                            VolatileStatus.INFESTATION.value]:
                if status.tick_turn():
                    del self.volatile_statuses[name]

        # Remove expired volatiles
        for status_name in volatiles_to_remove:
            del self.volatile_statuses[status_name]

        return messages
    def can_move(self, pokemon: Any) -> tuple[bool, Optional[str]]:
        """
        Check if Pokemon can move this turn
        Returns (can_move, reason_if_cant)
        """
        # Check flinch first (flinch prevents moving this turn)
        # Raid bosses cannot flinch
        if VolatileStatus.FLINCH.value in self.volatile_statuses:
            if not getattr(pokemon, "is_raid_boss", False):
                return False, f"{pokemon.species_name} flinched!"

        # Check major status
        if self.major_status:
            status = self.major_status.status_type

            if status == StatusType.FREEZE.value:
                # 20% chance to thaw
                if random.random() < 0.2:
                    self.major_status = None
                    return True, f"{pokemon.species_name} thawed out! {self.freeze_flavor_text}"
                return False, f"{pokemon.species_name} is frozen solid!"

            elif status == StatusType.SLEEP.value:
                return False, f"{pokemon.species_name} is fast asleep!"

            elif status == StatusType.PARALYSIS.value:
                # Raid bosses cannot be fully paralyzed (only slowed)
                if not getattr(pokemon, "is_raid_boss", False):
                    # 25% chance to be fully paralyzed
                    if random.random() < 0.25:
                        return False, f"{pokemon.species_name} is paralyzed and can't move!"

        # Check confusion
        if VolatileStatus.CONFUSION.value in self.volatile_statuses:
            if random.random() < 0.33:  # 1/3 chance to hurt self
                damage = max(1, pokemon.attack * 40 // pokemon.defense // 50 + 2)
                pokemon.current_hp = max(0, pokemon.current_hp - damage)
                return False, f"{pokemon.species_name} hurt itself in confusion! (-{damage} HP)"

        return True, None
    
    def modify_speed(self, speed: int) -> int:
        """Apply speed modifications from status"""
        if self.major_status and self.major_status.status_type == StatusType.PARALYSIS.value:
            return speed // 2
        return speed
    
    def modify_attack_stat(self, attack: int, is_physical: bool, pokemon: Any = None) -> int:
        """Apply attack stat modifications from status"""
        if self.major_status and self.major_status.status_type == StatusType.BURN.value and is_physical:
            ability_id = getattr(pokemon, 'ability', '') if pokemon else ''
            if str(ability_id).lower() != 'guts':
                return attack // 2
        return attack
    
    def _get_status_application_message(self, status_type: str) -> str:
        """Get the message when a status is applied"""
        messages = {
            StatusType.BURN.value: "was burned!",
            StatusType.FREEZE.value: "was frozen solid!",
            StatusType.PARALYSIS.value: "was paralyzed!",
            StatusType.POISON.value: "was poisoned!",
            StatusType.BADLY_POISON.value: "was badly poisoned!",
            StatusType.SLEEP.value: "fell asleep!",
            VolatileStatus.CONFUSION.value: "became confused!",
            VolatileStatus.LEECH_SEED.value: "was seeded!",
            VolatileStatus.FLINCH.value: "flinched!",
            VolatileStatus.PROTECT.value: "protected itself!",
            VolatileStatus.DETECT.value: "protected itself!",
            VolatileStatus.ENDURE.value: "is preparing to endure!",
            VolatileStatus.FOLLOW_ME.value: "became the center of attention!",
        }
        return messages.get(status_type, f"was affected by {status_type}!")
    
    def to_dict(self) -> Dict:
        """Serialize status conditions for storage"""
        return {
            'major_status': {
                'type': self.major_status.status_type,
                'duration': self.major_status.duration,
                'counter': self.major_status.counter,
                'metadata': self.major_status.metadata
            } if self.major_status else None,
            'volatile_statuses': {
                name: {
                    'duration': status.duration,
                    'counter': status.counter,
                    'metadata': status.metadata
                }
                for name, status in self.volatile_statuses.items()
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'StatusConditionManager':
        """Deserialize status conditions from storage"""
        manager = cls()
        
        if data.get('major_status'):
            ms = data['major_status']
            manager.major_status = StatusCondition(
                status_type=ms['type'],
                duration=ms.get('duration'),
                counter=ms.get('counter', 0),
                metadata=ms.get('metadata', {})
            )
        
        for name, vs_data in data.get('volatile_statuses', {}).items():
            manager.volatile_statuses[name] = StatusCondition(
                status_type=name,
                duration=vs_data.get('duration'),
                counter=vs_data.get('counter', 0),
                metadata=vs_data.get('metadata', {})
            )
        
        return manager
