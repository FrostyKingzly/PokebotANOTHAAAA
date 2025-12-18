
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
import copy
from status_conditions import StatusType


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
    # Ability helpers
    # ----------------------
    def ability_matches(self, pokemon: Any, ability_id: str) -> bool:
        """Return True if the Pokemon's ability matches the given ID (normalized)."""
        ability = getattr(pokemon, 'ability', None) or getattr(pokemon, 'current_ability', None)
        return self._normalize(ability) == self._normalize(ability_id)

    def reset_battle_state(self, pokemon: Any):
        """Reset per-battle flags when a Pokemon enters the field."""
        # Reset HP-trigger switch abilities so they can activate again on re-entry
        if self.ability_matches(pokemon, 'emergencyexit') or self.ability_matches(pokemon, 'wimpout'):
            setattr(pokemon, '_hp_switch_triggered', False)

        # Ensure Schooling state starts fresh each time the Pokemon hits the field
        if self.ability_matches(pokemon, 'schooling'):
            if not hasattr(pokemon, '_schooling_state'):
                pokemon._schooling_state = None
            if not hasattr(pokemon, '_schooling_base_name'):
                pokemon._schooling_base_name = getattr(pokemon, 'species_name', 'Wishiwashi')

        # Reset Shields Down state tracking so Minior can re-evaluate after switching
        if self.ability_matches(pokemon, 'shieldsdown'):
            pokemon._shields_down_state = None
            if not hasattr(pokemon, '_shields_down_base_name'):
                pokemon._shields_down_base_name = getattr(pokemon, 'species_name', 'Minior')

        # Reset Stance Change back to Shield Form on entry
        if self.ability_matches(pokemon, 'stancechange'):
            pokemon._stance_state = None
            if not hasattr(pokemon, '_stance_base_name'):
                pokemon._stance_base_name = getattr(pokemon, 'species_name', 'Aegislash')

    def apply_schooling(self, pokemon: Any) -> Optional[str]:
        """Apply Schooling form changes for Wishiwashi based on HP and level."""
        if not self.ability_matches(pokemon, 'schooling'):
            return None

        # Schooling only works on Wishiwashi at level 20+
        if getattr(pokemon, 'species_dex_number', None) != 746:
            return None

        ability = self.get_ability('schooling') or {}
        min_level = ability.get('min_level', 20)
        if getattr(pokemon, 'level', 0) < min_level:
            return None

        max_hp = getattr(pokemon, 'max_hp', 0) or 0
        if max_hp <= 0:
            return None

        threshold = ability.get('threshold', 0.25)
        hp_ratio = getattr(pokemon, 'current_hp', 0) / max_hp if max_hp else 0
        target_form = 'school' if pokemon.current_hp > 0 and hp_ratio >= threshold else 'solo'

        # Cache solo stats/name for reversion
        forms = ability.get('forms', {})
        solo_form = forms.get('solo', {})
        school_form = forms.get('school', {})

        if not hasattr(pokemon, '_schooling_solo_stats'):
            base_stats = solo_form.get('base_stats') or getattr(pokemon, 'base_stats', {})
            pokemon._schooling_solo_stats = copy.deepcopy(base_stats)
        if not hasattr(pokemon, '_schooling_base_name'):
            pokemon._schooling_base_name = solo_form.get('name') or getattr(pokemon, 'species_name', 'Wishiwashi')

        # Avoid duplicate work if already in the correct form
        current_state = getattr(pokemon, '_schooling_state', None) or 'solo'
        if current_state == target_form:
            return None

        new_form_data = school_form if target_form == 'school' else solo_form
        new_stats = new_form_data.get('base_stats') or (
            pokemon._schooling_solo_stats if target_form == 'solo' else None
        )

        if not new_stats:
            return None

        prev_hp = getattr(pokemon, 'current_hp', 0)
        prev_max_hp = max_hp
        prev_ratio = (prev_hp / prev_max_hp) if prev_max_hp else 0
        old_name = getattr(pokemon, 'species_name', 'Wishiwashi')

        # Recalculate stats with the new base statline
        pokemon.base_stats = copy.deepcopy(new_stats)
        if hasattr(pokemon, '_calculate_stats'):
            pokemon._calculate_stats()

        # Preserve current HP proportionally (minimum 1 HP if previously conscious)
        if prev_hp > 0 and getattr(pokemon, 'max_hp', 0) > 0:
            preserved_hp = int(round(pokemon.max_hp * prev_ratio))
            pokemon.current_hp = min(pokemon.max_hp, max(1, preserved_hp))
        else:
            pokemon.current_hp = max(0, min(getattr(pokemon, 'max_hp', 0), prev_hp))

        pokemon.form = new_form_data.get('form') if new_form_data.get('form') is not None else None
        pokemon.species_name = new_form_data.get('name') or (
            'Wishiwashi School' if target_form == 'school' else pokemon._schooling_base_name
        )
        pokemon._schooling_state = target_form

        if target_form == 'school':
            return f"{pokemon.species_name} formed a school!"
        return f"{pokemon._schooling_base_name}'s Schooling broke apart!"

    def apply_shields_down(self, pokemon: Any) -> Optional[str]:
        """Handle Minior's Shields Down form changes and immunities."""
        if not self.ability_matches(pokemon, 'shieldsdown'):
            return None

        if getattr(pokemon, 'species_dex_number', None) != 774:
            return None

        ability = self.get_ability('shieldsdown') or {}
        max_hp = getattr(pokemon, 'max_hp', 0) or 0
        if max_hp <= 0:
            return None

        threshold = ability.get('threshold', 0.5)
        hp_ratio = getattr(pokemon, 'current_hp', 0) / max_hp if max_hp else 0
        target_form = 'meteor' if pokemon.current_hp > 0 and hp_ratio >= threshold else 'core'

        forms = ability.get('forms', {})
        meteor_form = forms.get('meteor', {})
        core_form = forms.get('core', {})

        if not hasattr(pokemon, '_shields_down_state'):
            pokemon._shields_down_state = None
        if not hasattr(pokemon, '_shields_down_base_name'):
            pokemon._shields_down_base_name = getattr(pokemon, 'species_name', 'Minior')

        if pokemon._shields_down_state == target_form:
            return None

        new_form_data = meteor_form if target_form == 'meteor' else core_form
        new_stats = new_form_data.get('base_stats')
        if not new_stats:
            return None

        prev_hp = getattr(pokemon, 'current_hp', 0)
        prev_ratio = (prev_hp / max_hp) if max_hp else 0

        pokemon.base_stats = copy.deepcopy(new_stats)
        if hasattr(pokemon, '_calculate_stats'):
            pokemon._calculate_stats()

        if prev_hp > 0 and getattr(pokemon, 'max_hp', 0) > 0:
            preserved_hp = int(round(pokemon.max_hp * prev_ratio))
            pokemon.current_hp = min(pokemon.max_hp, max(1, preserved_hp))
        else:
            pokemon.current_hp = max(0, min(getattr(pokemon, 'max_hp', 0), prev_hp))

        pokemon.form = new_form_data.get('form')
        pokemon.species_name = new_form_data.get('name') or pokemon._shields_down_base_name
        pokemon._shields_down_state = target_form

        # Manage major status immunities in Meteor Form
        status_manager = getattr(pokemon, 'status_manager', None)
        if status_manager and hasattr(status_manager, 'immunities'):
            all_major_statuses = {s.value for s in StatusType}
            if target_form == 'meteor':
                status_manager.immunities.update(all_major_statuses)
            else:
                status_manager.immunities.difference_update(all_major_statuses)

        if target_form == 'meteor':
            return f"{pokemon.species_name}'s Shields Down formed a sturdy shell!"
        return f"{pokemon._shields_down_base_name} emerged from its shell!"

    def apply_stance_change(self, pokemon: Any, move_data: Optional[Dict] = None, force_form: Optional[str] = None) -> Optional[str]:
        """Toggle Aegislash between Shield and Blade formes based on move usage."""
        if not self.ability_matches(pokemon, 'stancechange'):
            return None

        if getattr(pokemon, 'species_dex_number', None) != 681:
            return None

        ability = self.get_ability('stancechange') or {}
        forms = ability.get('forms', {})
        shield_form = forms.get('shield', {})
        blade_form = forms.get('blade', {})

        if not hasattr(pokemon, '_stance_state'):
            pokemon._stance_state = None
        if not hasattr(pokemon, '_stance_base_name'):
            pokemon._stance_base_name = getattr(pokemon, 'species_name', 'Aegislash')

        target_form = force_form
        if not target_form and move_data:
            move_id = move_data.get('id')
            category = move_data.get('category')
            if move_id == 'kings_shield':
                target_form = 'shield'
            elif category in ['physical', 'special']:
                target_form = 'blade'

        # Default to Shield form if no state is set
        if not target_form and pokemon._stance_state is None:
            target_form = 'shield'

        if not target_form or pokemon._stance_state == target_form:
            return None

        new_form_data = shield_form if target_form == 'shield' else blade_form
        new_stats = new_form_data.get('base_stats')
        if not new_stats:
            return None

        prev_hp = getattr(pokemon, 'current_hp', 0)
        prev_max_hp = getattr(pokemon, 'max_hp', 0) or 0
        prev_ratio = (prev_hp / prev_max_hp) if prev_max_hp else 0

        pokemon.base_stats = copy.deepcopy(new_stats)
        if hasattr(pokemon, '_calculate_stats'):
            pokemon._calculate_stats()

        if prev_hp > 0 and getattr(pokemon, 'max_hp', 0) > 0:
            preserved_hp = int(round(pokemon.max_hp * prev_ratio))
            pokemon.current_hp = min(pokemon.max_hp, max(1, preserved_hp))
        else:
            pokemon.current_hp = max(0, min(getattr(pokemon, 'max_hp', 0), prev_hp))

        pokemon.form = new_form_data.get('form')
        pokemon.species_name = new_form_data.get('name') or pokemon._stance_base_name
        pokemon._stance_state = target_form

        if target_form == 'blade':
            return f"{pokemon.species_name} shifted into Blade Forme!"
        return f"{pokemon._stance_base_name} took on its Shield Forme!"

    def update_form_passives(self, pokemon: Any) -> List[str]:
        """Apply any passive form changes that depend on HP/ability."""
        msgs: List[str] = []
        schooling_msg = self.apply_schooling(pokemon)
        if schooling_msg:
            msgs.append(schooling_msg)
        shields_msg = self.apply_shields_down(pokemon)
        if shields_msg:
            msgs.append(shields_msg)
        return msgs

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

        # Reset per-entry flags and apply any passive form changes (e.g., Schooling)
        self.reset_battle_state(pokemon)

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

        # Passive form changes (e.g., Schooling/Shields Down) may need to run on entry as well
        msgs.extend(self.update_form_passives(pokemon))

        # Ensure Aegislash starts in Shield Forme when switching in
        stance_msg = self.apply_stance_change(pokemon, force_form='shield')
        if stance_msg:
            msgs.append(stance_msg)

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
