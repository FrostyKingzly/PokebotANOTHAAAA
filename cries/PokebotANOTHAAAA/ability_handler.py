
"""
Ability Handler System
Triggers and executes Pokémon abilities (entry, weather/terrain hooks).
"""

from typing import Dict, List, Optional, Any
import json
from pathlib import Path
import re
import os
import random


class AbilityHandler:
    """Handles ability triggers and effects"""
    def __init__(self, abilities_file: str = 'data/abilities.json', overrides_file: str = 'data/ability_overrides.json'):
        self.abilities_data: Dict[str, Dict] = {}
        self._load_abilities(abilities_file)
        self._merge_overrides(overrides_file)

    # ----------------------
    # Loading
    # ----------------------
    def _load_abilities(self, abilities_file: str):
        candidates = [
            abilities_file,
            str(Path(__file__).parent / abilities_file),
            str(Path(__file__).parent / 'data' / Path(abilities_file).name),
            str((Path(__file__).parent / '..' / abilities_file).resolve()),
        ]
        data = {}
        for cand in candidates:
            try:
                with open(cand, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                    # normalize keys
                    for k, v in raw.items():
                        self.abilities_data[self._normalize(k)] = v
                return
            except Exception:
                continue
        # If nothing loaded, keep empty but defined dict
        print(f"Warning: {abilities_file} not found. Abilities will not work.")
        self.abilities_data = {}

    def _merge_overrides(self, overrides_file: str):
        candidates = [
            overrides_file,
            str(Path(__file__).parent / overrides_file),
            str(Path(__file__).parent / 'data' / Path(overrides_file).name),
        ]
        for cand in candidates:
            if os.path.exists(cand):
                try:
                    with open(cand, 'r', encoding='utf-8') as f:
                        ov = json.load(f)
                    for k, v in ov.items():
                        self.abilities_data[self._normalize(k)] = v
                    return
                except Exception:
                    continue

    # ----------------------
    # Utilities
    # ----------------------
    def _normalize(self, s: str) -> str:
        return re.sub(r'[-_\s]+', '', (s or '').strip().lower())

    def get_ability(self, ability_id: Optional[str]) -> Optional[Dict]:
        if not ability_id:
            return None
        key = self._normalize(ability_id)
        # direct normalized key
        if key in self.abilities_data:
            return self.abilities_data[key]
        # try scan for equal normalized keys
        for k, v in self.abilities_data.items():
            if self._normalize(k) == key:
                return v
        return None

    # ----------------------
    # Entry trigger
    # ----------------------
    def trigger_on_entry(self, pokemon: Any, battle_state: Any) -> List[str]:
        """Trigger abilities when a Pokemon enters the field (weather/terrain setters, Intimidate, etc.)"""
        msgs: List[str] = []
        # try multiple attribute names
        ability_id = getattr(pokemon, 'ability', None) or getattr(pokemon, 'current_ability', None) or getattr(pokemon, 'ability_id', None)
        if not ability_id and hasattr(pokemon, 'to_dict'):
            ability_id = pokemon.to_dict().get('ability')
        ability = self.get_ability(ability_id)
        if not ability:
            return msgs

        events = ability.get('events') or ability.get('triggers') or []
        if isinstance(events, str):
            events = [events]

        # Weather/Terrain setters on "Start"
        if 'Start' in [e if isinstance(e, str) else e.get('event') for e in events]:
            effect = ability.get('effect')
            if effect == 'weather':
                weather = ability.get('weather')
                if weather and getattr(battle_state, 'weather', None) != weather:
                    is_raid_boss = getattr(pokemon, "is_raid_boss", False)

                    # If rogue Pokemon sets weather, save as permanent
                    if is_raid_boss:
                        battle_state.rogue_weather = weather
                        battle_state.weather = weather
                        battle_state.weather_turns = 999  # Effectively permanent
                    else:
                        # Non-rogue Pokemon setting weather (override)
                        battle_state.weather = weather

                        # Default 5 turns, extended to 8 with weather-extending items
                        weather_turns = int(ability.get('duration', 5))

                        if hasattr(pokemon, 'held_item'):
                            item_id = pokemon.held_item

                            # Weather-extending items
                            weather_extenders = {
                                'heatrock': 'sun',
                                'damprock': 'rain',
                                'smoothrock': 'sandstorm',
                                'icyrock': ['hail', 'snow']
                            }

                            # Normalize item_id for comparison (remove spaces, hyphens, underscores, lowercase)
                            if item_id:
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

                        battle_state.weather_turns = weather_turns

                    # Use proper in-game messages for each weather ability
                    ability_name = ability.get('name', ability_id)
                    pokemon_name = getattr(pokemon, 'species_name', 'The Pokémon')

                    # Match official Pokemon game messages
                    weather_messages = {
                        'sun': f"{pokemon_name}'s {ability_name} intensified the sun's rays!",
                        'rain': f"{pokemon_name}'s {ability_name} made it rain!",
                        'sandstorm': f"{pokemon_name}'s {ability_name} whipped up a sandstorm!",
                        'hail': f"{pokemon_name}'s {ability_name} made it hail!",
                        'snow': f"{pokemon_name}'s {ability_name} made it snow!"
                    }

                    msgs.append(weather_messages.get(weather, f"{pokemon_name}'s {ability_name} changed the weather!"))
            elif effect == 'terrain':
                terrain = ability.get('terrain')
                if terrain and getattr(battle_state, 'terrain', None) != terrain:
                    is_raid_boss = getattr(pokemon, "is_raid_boss", False)

                    # If rogue Pokemon sets terrain, save as permanent
                    if is_raid_boss:
                        battle_state.rogue_terrain = terrain
                        battle_state.terrain = terrain
                        battle_state.terrain_turns = 999  # Effectively permanent
                    else:
                        # Non-rogue Pokemon setting terrain (override)
                        battle_state.terrain = terrain
                        battle_state.terrain_turns = int(ability.get('duration', 5))

                    msgs.append(f"The battlefield became {terrain} terrain due to {ability.get('name', ability_id)}!")

        # Example: Intimidate
        if ability_id and self._normalize(ability_id) == 'intimidate':
            # Lower opposing active Pokémon Attack by 1 (if your battle state exposes them)
            try:
                opponent = battle_state.opponent if pokemon in battle_state.trainer.party else battle_state.trainer
                for mon in opponent.get_active_pokemon():
                    if hasattr(mon, 'modify_stat_stage'):
                        mon.modify_stat_stage('attack', -1)
                        msgs.append(f"{getattr(mon, 'species_name','The foe')} was intimidated! Attack fell!")
            except Exception:
                pass

        return msgs

    # ----------------------
    # Weather residual helpers
    # ----------------------
    def _pokemon_types(self, pokemon: Any) -> List[str]:
        """Get Pokemon's types from various possible attributes"""
        # Try direct types attribute
        t = getattr(pokemon, 'types', None)
        if isinstance(t, list):
            return [str(x).lower() for x in t]
        
        # Try species_data (most common for Pokemon objects)
        if hasattr(pokemon, 'species_data') and isinstance(pokemon.species_data, dict):
            types = pokemon.species_data.get('types', [])
            if isinstance(types, list):
                return [str(x).lower() for x in types]
        
        # Try to_dict method
        if hasattr(pokemon, 'to_dict'):
            d = pokemon.to_dict()
            if 'types' in d and isinstance(d['types'], list):
                return [str(x).lower() for x in d['types']]
        
        return []

    def apply_weather_damage(self, pokemon: Any, weather: Optional[str]) -> Optional[str]:
        if not weather:
            return None
        w = (weather or '').lower()
        
        # Get Pokemon types for immunity checks
        types = self._pokemon_types(pokemon)
        
        # Sandstorm chip: non Rock/Ground/Steel take 1/16
        if w == 'sandstorm':
            if not any(t in ('rock', 'ground', 'steel') for t in types):
                if getattr(pokemon, 'current_hp', 0) > 0:
                    dmg = max(1, getattr(pokemon, 'max_hp', 1) // 16)
                    pokemon.current_hp = max(0, pokemon.current_hp - dmg)
                    return f"{getattr(pokemon, 'species_name', 'The Pokémon')} is buffeted by the sandstorm! (-{dmg} HP)"
        
        # Hail chip: non Ice types take 1/16
        elif w == 'hail':
            if 'ice' not in types:
                if getattr(pokemon, 'current_hp', 0) > 0:
                    dmg = max(1, getattr(pokemon, 'max_hp', 1) // 16)
                    pokemon.current_hp = max(0, pokemon.current_hp - dmg)
                    return f"{getattr(pokemon, 'species_name', 'The Pokémon')} is buffeted by the hail! (-{dmg} HP)"
        
        # Snow is like Hail but without damage in newer gens
        # For now we'll keep it simple
        
        return None

    def apply_weather_healing(self, pokemon: Any, weather: Optional[str]) -> Optional[str]:
        # Minimal safe default: no auto-heal to avoid incorrect double-ticking.
        return None


if __name__ == '__main__':
    print("Ability Handler System loaded.")
