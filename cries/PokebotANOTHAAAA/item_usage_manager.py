"""
Comprehensive Item Usage System
Handles Rare Candy, TMs/HMs, Evolution Items, and all other consumable items
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass


@dataclass
class ItemUseResult:
    """Result of using an item"""
    success: bool
    message: str
    pokemon_changed: bool = False
    evolution_triggered: bool = False
    move_learned: bool = False
    level_up_data: Optional[Dict] = None
    # Convenience fields for UI/commands (flattened from level_up_data or other logic)
    new_level: Optional[int] = None
    learned_move: Optional[str] = None
    evolved_into: Optional[str] = None


class ItemUsageManager:
    """Manages all item usage outside of battle"""

    def __init__(self, bot):
        self.bot = bot
        self.items_db = bot.items_db
        self.moves_db = bot.moves_db
        self.species_db = bot.species_db

        # Load evolution data
        self.evolution_data = self._load_evolution_data()
        self.exp_candy_values = {
            'exp_candy_xs': 100,
            'exp_candy_s': 800,
            'exp_candy_m': 3000,
            'exp_candy_l': 10000,
            'exp_candy_xl': 30000,
        }

    def _normalize_species_key(self, raw: Optional[str]) -> Optional[str]:
        """Normalize species identifiers for robust lookups.

        Evolution data keys use lowercase with hyphens. Player data can contain
        spaces, underscores, mixed casing, or trailing punctuation. This helper
        standardizes names so every lookup path (species name, dex number, held
        item checks) resolves to the same key.
        """
        if not raw:
            return None

        key = str(raw).strip().lower()
        key = key.replace('_', '-').replace(' ', '-')
        key = key.replace("'", "")
        key = key.replace('.', '')
        return key


    def _load_evolution_data(self) -> Dict:
        """Load evolution data from disk and ensure every species is covered."""
        data_dir = Path(__file__).resolve().parent / 'data'
        json_path = data_dir / 'evolution_data.json'

        loaded_data: Dict[str, Dict] = {}
        if json_path.exists():
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                loaded_data = {self._normalize_species_key(k): v for k, v in raw.items()}
            except Exception:
                # Fall back to the baked-in defaults if the JSON is malformed
                loaded_data = {}

        base_data = self._default_evolution_data()
        evolution_data: Dict[str, Dict] = {**base_data, **loaded_data}

        # Ensure every species in the local dex has an entry so lookups never fail.
        species_names = self._load_species_names()
        missing_species = []
        for name in species_names:
            if name not in evolution_data:
                evolution_data[name] = {'method': 'none'}
                missing_species.append(name)

        if missing_species:
            print(
                f"[EvolutionData] Added {len(missing_species)} placeholder entries. "
                "Run tools/generate_evolution_data.py to refresh with full evolution rules."
            )

        return evolution_data

    def _load_species_names(self) -> set:
        """Load all species names from the bundled dex for coverage checks."""
        species_path = Path(__file__).resolve().parent / 'data' / 'pokemon_species.json'
        names = set()
        try:
            with open(species_path, 'r', encoding='utf-8') as f:
                species_data = json.load(f)
            for entry in species_data.values():
                norm = self._normalize_species_key(entry.get('name'))
                if norm:
                    names.add(norm)
                for form in entry.get('forms', []):
                    form_name = self._normalize_species_key(form.get('name'))
                    if form_name:
                        names.add(form_name)
        except Exception:
            pass
        return names

    def _default_evolution_data(self) -> Dict:
        """Baked-in fallback evolution data for when no external dataset is present."""
        return {
            # Gen 1 - Level evolutions
            'bulbasaur': {'method': 'level', 'level': 16, 'into': 'ivysaur'},
            'ivysaur': {'method': 'level', 'level': 32, 'into': 'venusaur'},
            'charmander': {'method': 'level', 'level': 16, 'into': 'charmeleon'},
            'charmeleon': {'method': 'level', 'level': 36, 'into': 'charizard'},
            'squirtle': {'method': 'level', 'level': 16, 'into': 'wartortle'},
            'wartortle': {'method': 'level', 'level': 36, 'into': 'blastoise'},
            'caterpie': {'method': 'level', 'level': 7, 'into': 'metapod'},
            'metapod': {'method': 'level', 'level': 10, 'into': 'butterfree'},
            'weedle': {'method': 'level', 'level': 7, 'into': 'kakuna'},
            'kakuna': {'method': 'level', 'level': 10, 'into': 'beedrill'},
            'pidgey': {'method': 'level', 'level': 18, 'into': 'pidgeotto'},
            'pidgeotto': {'method': 'level', 'level': 36, 'into': 'pidgeot'},
            'rattata': {'method': 'level', 'level': 20, 'into': 'raticate'},
            'spearow': {'method': 'level', 'level': 20, 'into': 'fearow'},
            'ekans': {'method': 'level', 'level': 22, 'into': 'arbok'},
            'pikachu': {'method': 'stone', 'stone': 'thunder_stone', 'into': 'raichu'},
            'sandshrew': {'method': 'level', 'level': 22, 'into': 'sandslash'},
            'nidoran-f': {'method': 'level', 'level': 16, 'into': 'nidorina'},
            'nidorina': {'method': 'stone', 'stone': 'moon_stone', 'into': 'nidoqueen'},
            'nidoran-m': {'method': 'level', 'level': 16, 'into': 'nidorino'},
            'nidorino': {'method': 'stone', 'stone': 'moon_stone', 'into': 'nidoking'},
            'clefairy': {'method': 'stone', 'stone': 'moon_stone', 'into': 'clefable'},
            'vulpix': {'method': 'stone', 'stone': 'fire_stone', 'into': 'ninetales'},
            'jigglypuff': {'method': 'stone', 'stone': 'moon_stone', 'into': 'wigglytuff'},
            'zubat': {'method': 'level', 'level': 22, 'into': 'golbat'},
            'oddish': {'method': 'level', 'level': 21, 'into': 'gloom'},
            'gloom': {'method': 'stone', 'stone': 'leaf_stone', 'into': 'vileplume'},
            'paras': {'method': 'level', 'level': 24, 'into': 'parasect'},
            'venonat': {'method': 'level', 'level': 31, 'into': 'venomoth'},
            'diglett': {'method': 'level', 'level': 26, 'into': 'dugtrio'},
            'meowth': {'method': 'level', 'level': 28, 'into': 'persian'},
            'psyduck': {'method': 'level', 'level': 33, 'into': 'golduck'},
            'mankey': {'method': 'level', 'level': 28, 'into': 'primeape'},
            'growlithe': {'method': 'stone', 'stone': 'fire_stone', 'into': 'arcanine'},
            'poliwag': {'method': 'level', 'level': 25, 'into': 'poliwhirl'},
            'poliwhirl': {'method': 'stone', 'stone': 'water_stone', 'into': 'poliwrath'},
            'abra': {'method': 'level', 'level': 16, 'into': 'kadabra'},
            'kadabra': {'method': 'trade', 'into': 'alakazam'},
            'machop': {'method': 'level', 'level': 28, 'into': 'machoke'},
            'machoke': {'method': 'trade', 'into': 'machamp'},
            'bellsprout': {'method': 'level', 'level': 21, 'into': 'weepinbell'},
            'weepinbell': {'method': 'stone', 'stone': 'leaf_stone', 'into': 'victreebel'},
            'tentacool': {'method': 'level', 'level': 30, 'into': 'tentacruel'},
            'geodude': {'method': 'level', 'level': 25, 'into': 'graveler'},
            'graveler': {'method': 'trade', 'into': 'golem'},
            'ponyta': {'method': 'level', 'level': 40, 'into': 'rapidash'},
            'slowpoke': {'method': 'level', 'level': 37, 'into': 'slowbro'},
            'magnemite': {'method': 'level', 'level': 30, 'into': 'magneton'},
            'doduo': {'method': 'level', 'level': 31, 'into': 'dodrio'},
            'seel': {'method': 'level', 'level': 34, 'into': 'dewgong'},
            'grimer': {'method': 'level', 'level': 38, 'into': 'muk'},
            'shellder': {'method': 'stone', 'stone': 'water_stone', 'into': 'cloyster'},
            'gastly': {'method': 'level', 'level': 25, 'into': 'haunter'},
            'haunter': {'method': 'trade', 'into': 'gengar'},
            'onix': {'method': 'trade', 'item': 'metal_coat', 'into': 'steelix'},
            'drowzee': {'method': 'level', 'level': 26, 'into': 'hypno'},
            'krabby': {'method': 'level', 'level': 28, 'into': 'kingler'},
            'voltorb': {'method': 'level', 'level': 30, 'into': 'electrode'},
            'exeggcute': {'method': 'stone', 'stone': 'leaf_stone', 'into': 'exeggutor'},
            'cubone': {'method': 'level', 'level': 28, 'into': 'marowak'},
            'hitmon chan': {'method': 'none'},
            'hitmonchan': {'method': 'none'},
            'lickitung': {'method': 'level', 'level': 33, 'move': 'rollout', 'into': 'lickilicky'},
            'koffing': {'method': 'level', 'level': 35, 'into': 'weezing'},
            'rhyhorn': {'method': 'level', 'level': 42, 'into': 'rhydon'},
            'chansey': {'method': 'friendship', 'into': 'blissey'},
            'tangela': {'method': 'level', 'level': 33, 'move': 'ancient_power', 'into': 'tangrowth'},
            'kangaskhan': {'method': 'none'},
            'horsea': {'method': 'level', 'level': 32, 'into': 'seadra'},
            'goldeen': {'method': 'level', 'level': 33, 'into': 'seaking'},
            'staryu': {'method': 'stone', 'stone': 'water_stone', 'into': 'starmie'},
            'scyther': {'method': 'trade', 'item': 'metal_coat', 'into': 'scizor'},
            'electabuzz': {'method': 'trade', 'item': 'electirizer', 'into': 'electivire'},
            'magmar': {'method': 'trade', 'item': 'magmarizer', 'into': 'magmortar'},
            'pinsir': {'method': 'none'},
            'tauros': {'method': 'none'},
            'magikarp': {'method': 'level', 'level': 20, 'into': 'gyarados'},
            'lapras': {'method': 'none'},
            'ditto': {'method': 'none'},
            'eevee': {'method': 'multiple', 'evolutions': [
                {'method': 'stone', 'stone': 'water_stone', 'into': 'vaporeon'},
                {'method': 'stone', 'stone': 'thunder_stone', 'into': 'jolteon'},
                {'method': 'stone', 'stone': 'fire_stone', 'into': 'flareon'},
                {'method': 'friendship', 'time': 'day', 'into': 'espeon'},
                {'method': 'friendship', 'time': 'night', 'into': 'umbreon'},
                {'method': 'stone', 'stone': 'leaf_stone', 'into': 'leafeon'},
                {'method': 'stone', 'stone': 'ice_stone', 'into': 'glaceon'},
                {'method': 'friendship', 'move_type': 'fairy', 'into': 'sylveon'},
            ]},
            'porygon': {'method': 'trade', 'item': 'upgrade', 'into': 'porygon2'},
            'omanyte': {'method': 'level', 'level': 40, 'into': 'omastar'},
            'kabuto': {'method': 'level', 'level': 40, 'into': 'kabutops'},
            'aerodactyl': {'method': 'none'},
            'snorlax': {'method': 'none'},
            'articuno': {'method': 'none'},
            'zapdos': {'method': 'none'},
            'moltres': {'method': 'none'},
            'dratini': {'method': 'level', 'level': 30, 'into': 'dragonair'},
            'dragonair': {'method': 'level', 'level': 55, 'into': 'dragonite'},
            'mewtwo': {'method': 'none'},
            'mew': {'method': 'none'},

            # Gen 2 additions
            'chikorita': {'method': 'level', 'level': 16, 'into': 'bayleef'},
            'bayleef': {'method': 'level', 'level': 32, 'into': 'meganium'},
            'cyndaquil': {'method': 'level', 'level': 14, 'into': 'quilava'},
            'quilava': {'method': 'level', 'level': 36, 'into': 'typhlosion'},
            'totodile': {'method': 'level', 'level': 18, 'into': 'croconaw'},
            'croconaw': {'method': 'level', 'level': 30, 'into': 'feraligatr'},

            # Gen 9 pseudo-legendary line
            'frigibax': {'method': 'level', 'level': 35, 'into': 'arctibax'},
            'arctibax': {'method': 'level', 'level': 54, 'into': 'baxcalibur'},
            'baxcalibur': {'method': 'none'},
        }
    def can_evolve(self, pokemon: Dict) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Check if Pokemon can evolve
        Returns: (can_evolve, evolution_method, evolution_data)
        """
        # Resolve species name robustly. Prefer an explicit species_name field,
        # but fall back to looking up via species_dex_number if needed.
        species_name: Optional[str] = None
        raw_name = pokemon.get('species_name')
        if raw_name:
            species_name = self._normalize_species_key(raw_name)
        else:
            try:
                species_id = pokemon.get('species_dex_number')
                if species_id and self.bot.species_db:
                    species_data = self.bot.species_db.get_species(species_id)
                    if species_data:
                        species_name = self._normalize_species_key(species_data.get('name', ''))
            except Exception:
                species_name = None

        if not species_name:
            return False, None, None

        evolution = self.evolution_data.get(species_name)

        if not evolution or evolution.get('method') == 'none':
            return False, None, None

        method = evolution['method']

        if method == 'level':
            required_level = evolution.get('level', 100)
            if pokemon.get('level', 0) >= required_level:
                # Check if requires knowing a specific move
                required_move = evolution.get('move')
                if required_move:
                    knows_move = any(m.get('move_id') == required_move for m in pokemon.get('moves', []))
                    if not knows_move:
                        return False, 'level_with_move', evolution
                return True, 'level', evolution
            return False, 'stone', evolution  # Needs item to evolve

        elif method == 'trade':
            # Support trade evolutions when holding the required item (e.g., Metal Coat)
            required_item = evolution.get('item')
            if required_item and pokemon.get('held_item') == required_item:
                return True, 'trade', evolution
            return False, 'trade', evolution

        elif method == 'friendship':
            # Simplified: assume high friendship after certain level
            if pokemon.get('level', 0) >= 20:
                return True, 'friendship', evolution

        elif method == 'multiple':
            # Multiple options (e.g., Eevee). If a compatible item is already held,
            # surface the option so the evolution button can appear.
            held_item = pokemon.get('held_item')
            if held_item:
                for option in evolution.get('evolutions', []):
                    if option.get('method') == 'stone' and option.get('stone') == held_item:
                        return True, 'multiple', {**option, 'into': option.get('into')}
            return False, 'multiple', evolution  # Needs item choice

        return False, None, None

    def use_item(self, player_id: int, pokemon_id: str, item_id: str) -> ItemUseResult:
        """
        Use an item on a Pokemon

        Args:
            player_id: Player using the item
            pokemon_id: Pokemon to use item on
            item_id: Item to use

        Returns:
            ItemUseResult with success status and details
        """
        # Get item data
        item = self.items_db.get_item(item_id)
        if not item:
            return ItemUseResult(False, f"❌ Item '{item_id}' not found!")

        # Get Pokemon
        pokemon = self.bot.player_manager.get_pokemon(pokemon_id)
        if not pokemon:
            return ItemUseResult(False, "❌ Pokemon not found!")

        # Check item category and handle appropriately
        category = item.get('category', '').lower()

        if item_id in self.exp_candy_values:
            return self._use_exp_candy(player_id, pokemon, item_id, item)

        if item_id == 'rare_candy' or 'rare' in item_id and 'candy' in item_id:
            return self._use_rare_candy(player_id, pokemon, item)

        elif category == 'tms' or item_id.startswith('tm'):
            return self._use_tm(player_id, pokemon, item, item_id)

        elif 'stone' in item_id or category == 'evolution':
            return self._use_evolution_item(player_id, pokemon, item, item_id)

        elif category == 'medicine':
            return self._use_medicine(player_id, pokemon, item)

        else:
            return ItemUseResult(False, f"❌ Don't know how to use {item.get('name', item_id)}!")

    def _get_species_display_name(self, pokemon: Dict) -> str:
        """Resolve a readable species name for messages."""
        species_name = pokemon.get('species_name')
        if species_name:
            return species_name

        try:
            species_id = pokemon.get('species_dex_number')
            if species_id and self.bot.species_db:
                species_data = self.bot.species_db.get_species(species_id)
                if species_data:
                    return species_data.get('name', 'Pokemon')
        except Exception:
            return 'Pokemon'

        return 'Pokemon'

    def _use_rare_candy(self, player_id: int, pokemon: Dict, item: Dict) -> ItemUseResult:
        """Level up Pokemon with Rare Candy"""
        species_name = self._get_species_display_name(pokemon)

        if pokemon.get('level', 1) >= 100:
            return ItemUseResult(False, f"❌ {species_name} is already at max level (100)!")

        # Level up Pokemon
        old_level = pokemon.get('level', 1)
        levelup_result = self.bot.player_manager.level_up_pokemon(
            player_id,
            pokemon['pokemon_id'],
            set_level=old_level + 1
        )

        if not levelup_result:
            return ItemUseResult(False, "❌ Failed to level up Pokemon!")

        # Consume the item
        self.bot.player_manager.remove_item(player_id, item['id'], 1)

        # Check if can evolve now
        can_evolve, method, evo_data = self.can_evolve(pokemon)

        message = f"✨ {species_name} leveled up to **Level {old_level + 1}**!"
        if can_evolve and method == 'level':
            message += f"\n🌟 {species_name} is ready to evolve!"
        # Flatten some data for convenience
        new_level = None
        if isinstance(levelup_result, dict):
            new_level = levelup_result.get('new_level')
        return ItemUseResult(
            success=True,
            message=message,
            pokemon_changed=True,
            evolution_triggered=can_evolve and method == 'level',
            level_up_data=levelup_result,
            new_level=new_level,
        )

    def _use_exp_candy(self, player_id: int, pokemon: Dict, item_id: str, item: Dict) -> ItemUseResult:
        """Grant EXP based on the candy tier."""
        species_name = self._get_species_display_name(pokemon)
        exp_amount = self.exp_candy_values.get(item_id, 0)

        if exp_amount <= 0:
            return ItemUseResult(False, "❌ Invalid EXP candy configuration.")

        result = self.bot.player_manager.grant_experience(
            player_id,
            pokemon.get('pokemon_id'),
            exp_amount,
        )

        if not result:
            return ItemUseResult(False, "❌ Failed to apply EXP candy.")

        self.bot.player_manager.remove_item(player_id, item_id, 1)

        message = f"✨ {species_name} gained **{exp_amount} EXP** from {item.get('name', item_id)}!"
        if result['new_level'] > result['old_level']:
            message += f"\n⬆️ Level {result['old_level']} → {result['new_level']}!"

        return ItemUseResult(
            success=True,
            message=message,
            pokemon_changed=True,
            level_up_data=result.get('level_up_data'),
            new_level=result.get('new_level'),
        )

    def _use_tm(self, player_id: int, pokemon: Dict, item: Dict, item_id: str) -> ItemUseResult:
        """Teach a TM move to Pokemon"""
        # Extract TM number and get move
        tm_num = item_id.replace('tm', '').replace('_', '').replace('-', '').zfill(3)

        # TMs teach specific moves - need mapping
        # For now, extract from item description or use a mapping
        # This is a placeholder - you'd need actual TM -> Move mapping
        move_id = item.get('move_id')  # Assuming items have this

        if not move_id:
            # Try to parse from description
            desc = item.get('description', '').lower()
            # Extract move name from description if possible
            return ItemUseResult(False, f"❌ Couldn't determine which move {item.get('name')} teaches!")

        # Check if Pokemon can learn this move
        species = self.species_db.get_species(pokemon.get('species_dex_number'))
        if not species:
            return ItemUseResult(False, "❌ Pokemon species data not found!")

        # Check learnset
        learnset = self.bot.learnsets_db.get_learnset(species['name'].lower())
        if not learnset:
            return ItemUseResult(False, f"❌ No learnset data for {species['name']}!")

        # Check if move is in TM list
        tm_moves = learnset.get('tm_moves', [])
        if move_id not in tm_moves:
            return ItemUseResult(
                False,
                f"❌ {pokemon['species_name']} cannot learn {move_id.replace('_', ' ').title()}!"
            )

        # Check if already knows the move
        current_moves = pokemon.get('moves', [])
        if any(m.get('move_id') == move_id for m in current_moves):
            return ItemUseResult(False, f"❌ {pokemon['species_name']} already knows that move!")

        # Check if has room for new move
        if len(current_moves) >= 4:
            return ItemUseResult(
                False,
                f"❌ {pokemon['species_name']} already knows 4 moves! Forget a move first."
            )

        # Teach the move
        success = self.bot.player_manager.add_move_to_pokemon(
            player_id,
            pokemon['pokemon_id'],
            move_id
        )

        if not success:
            return ItemUseResult(False, "❌ Failed to teach move!")

        # Consume TM (modern TMs are reusable, but let's make them consumable)
        self.bot.player_manager.remove_item(player_id, item_id, 1)

        move_name = move_id.replace('_', ' ').title()

        # Determine a readable species name
        species_name = pokemon.get('species_name')
        if not species_name:
            try:
                species_id = pokemon.get('species_dex_number')
                if species_id and self.bot.species_db:
                    species_data = self.bot.species_db.get_species(species_id)
                    if species_data:
                        species_name = species_data.get('name', 'Pokemon')
            except Exception:
                species_name = None
        if not species_name:
            species_name = 'Pokemon'

        return ItemUseResult(
            success=True,
            message=f"✨ {species_name} learned **{move_name}**!",
            pokemon_changed=True,
            move_learned=True,
            learned_move=move_name,
        )

    def _use_evolution_item(self, player_id: int, pokemon: Dict, item: Dict, item_id: str) -> ItemUseResult:
        """Use an evolution stone or item"""
        raw_name = pokemon.get('species_name')
        lookup_key = (raw_name or '').lower()
        evolution = self.evolution_data.get(self._normalize_species_key(lookup_key))

        if not evolution:
            # Try to get a readable name for messaging
            species_name = raw_name
            if not species_name:
                try:
                    species_id = pokemon.get('species_dex_number')
                    if species_id and self.bot.species_db:
                        species_data = self.bot.species_db.get_species(species_id)
                        if species_data:
                            species_name = species_data.get('name', 'Pokemon')
                except Exception:
                    species_name = None
            if not species_name:
                species_name = 'Pokemon'
            return ItemUseResult(False, f"❌ {species_name} cannot evolve with this item!")

        # Check if this Pokemon evolves with this stone
        method = evolution.get('method')
        required_stone = evolution.get('stone', '').lower()

        if method == 'stone' and required_stone in item_id.lower():
            # Valid evolution!
            evolve_into = evolution.get('into')
            if not evolve_into:
                return ItemUseResult(False, "❌ Evolution data incomplete!")

            # Trigger evolution
            success = self._trigger_evolution(player_id, pokemon, evolve_into)
            if not success:
                return ItemUseResult(False, "❌ Evolution failed!")

            # Consume stone
            self.bot.player_manager.remove_item(player_id, item_id, 1)

            # Determine evolved species name (best-effort; evolution target is usually a species ID/key)
            evolved_into = evolve_into
            return ItemUseResult(
                success=True,
                message=f"✨ Your Pokemon is evolving!",
                pokemon_changed=True,
                evolution_triggered=True,
                evolved_into=evolved_into,
            )

        return ItemUseResult(
            False,
            f"❌ {pokemon['species_name']} cannot evolve with {item.get('name')}!"
        )

    def _use_medicine(self, player_id: int, pokemon: Dict, item: Dict) -> ItemUseResult:
        """Use healing/medicine items"""
        item_id = item['id'].lower()

        # Potion types
        if 'potion' in item_id:
            if pokemon['current_hp'] >= pokemon['max_hp']:
                return ItemUseResult(False, f"❌ {pokemon['species_name']} already has full HP!")

            heal_amount = 20  # Basic potion
            if 'super' in item_id:
                heal_amount = 50
            elif 'hyper' in item_id:
                heal_amount = 200
            elif 'max' in item_id:
                heal_amount = pokemon['max_hp']

            new_hp = min(pokemon['max_hp'], pokemon['current_hp'] + heal_amount)
            pokemon['current_hp'] = new_hp
            self.bot.player_manager.update_pokemon(player_id, pokemon)
            self.bot.player_manager.remove_item(player_id, item_id, 1)

            return ItemUseResult(
                success=True,
                message=f"✨ {pokemon['species_name']} restored {heal_amount} HP!",
                pokemon_changed=True
            )

        # Status healers
        elif 'antidote' in item_id or 'paralyze' in item_id or 'awakening' in item_id or 'burn_heal' in item_id or 'ice_heal' in item_id:
            if not pokemon.get('status'):
                return ItemUseResult(False, f"❌ {pokemon['species_name']} doesn't have a status condition!")

            pokemon['status'] = None
            self.bot.player_manager.update_pokemon(player_id, pokemon)
            self.bot.player_manager.remove_item(player_id, item_id, 1)

            return ItemUseResult(
                success=True,
                message=f"✨ {pokemon['species_name']}'s status was healed!",
                pokemon_changed=True
            )

        # Full Restore
        elif 'full_restore' in item_id:
            pokemon['current_hp'] = pokemon['max_hp']
            pokemon['status'] = None
            self.bot.player_manager.update_pokemon(player_id, pokemon)
            self.bot.player_manager.remove_item(player_id, item_id, 1)

            return ItemUseResult(
                success=True,
                message=f"✨ {pokemon['species_name']} was fully restored!",
                pokemon_changed=True
            )

        return ItemUseResult(False, f"❌ Don't know how to use {item.get('name')}!")

    def _trigger_evolution(self, player_id: int, pokemon: Dict, evolve_into: str) -> bool:
        """Evolve a Pokemon into a new species"""
        # Get new species data
        new_species = self.species_db.get_species(evolve_into)
        if not new_species:
            return False

        # Update Pokemon
        old_name = pokemon.get('species_name')
        pokemon['species_name'] = new_species['name']
        pokemon['species_dex_number'] = new_species['dex_number']

        # Recalculate stats for new species
        level = pokemon.get('level', 1)
        ivs = pokemon.get('ivs', {})
        evs = pokemon.get('evs', {})

        # Calculate new stats
        base_stats = new_species.get('base_stats', {})
        for stat in ['hp', 'attack', 'defense', 'sp_attack', 'sp_defense', 'speed']:
            base = base_stats.get(stat, 50)
            iv = ivs.get(stat, 15)
            ev = evs.get(stat, 0)

            if stat == 'hp':
                new_value = ((2 * base + iv + (ev // 4)) * level // 100) + level + 10
            else:
                new_value = ((2 * base + iv + (ev // 4)) * level // 100) + 5

            pokemon[stat] = new_value

        pokemon['max_hp'] = pokemon['hp']
        pokemon['current_hp'] = min(pokemon['current_hp'], pokemon['max_hp'])

        # Update in database
        return self.bot.player_manager.update_pokemon(player_id, pokemon)