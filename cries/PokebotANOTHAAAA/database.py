"""
Database Module - Handles loading game data and player data storage
"""

import csv
import json
import sqlite3
import time
from pathlib import Path
from typing import Optional, Dict, List, Any
import uuid
import re
import unicodedata

from social_stats import (
    SOCIAL_STAT_ORDER,
    get_stat_cap,
    rank_to_points,
    calculate_max_stamina,
)


# ============================================================
# GAME DATA LOADERS (Read-only JSON data)
# ============================================================

class SpeciesDatabase:
    """Loads and queries Pokemon species data"""
    
    def __init__(self, json_path: str):
        with open(json_path, 'r', encoding='utf-8') as f:
            self.data = json.load(f)

        # Load regional variants and merge them into the main species map so lookups
        # (both by name and dex number) can return form-specific data.
        forms_path = Path(json_path).with_name('regional_forms.json')
        self._alias_map: Dict[str, Dict] = {}
        if forms_path.exists():
            self._load_regional_forms(forms_path)

    def get_species(self, identifier) -> Optional[Dict]:
        """Get species by dex number or name"""
        # Try as dex number first
        if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
            return self.data.get(str(identifier))

        # Try as name
        identifier_lower = str(identifier).lower()
        for species in self.data.values():
            if species['name'].lower() == identifier_lower:
                return species

        # Check alias map for regional forms and alternate spellings
        normalized_query = self._normalize_name(identifier_lower)
        if normalized_query in self._alias_map:
            return self._alias_map[normalized_query]

        # Fallback to normalized comparison (handles Showdown formatting)
        for species in self.data.values():
            if self._normalize_name(species['name']) == normalized_query:
                return species

        # Last resort: partial match for base species name (for Pokemon with forms)
        # e.g., "urshifu" will match "Urshifu Single Strike"
        for species in self.data.values():
            species_base = species['name'].lower().split()[0]  # Get first word
            if species_base == identifier_lower:
                return species

        return None

    def _normalize_name(self, name: str) -> str:
        """Normalize species names (removes punctuation, accents, spacing)"""
        normalized = unicodedata.normalize('NFKD', name)
        normalized = normalized.encode('ascii', 'ignore').decode('ascii')
        normalized = normalized.lower()
        normalized = normalized.replace('♀', 'f').replace('♂', 'm')
        normalized = normalized.replace('-', ' ').replace('_', ' ')
        normalized = re.sub(r'[^a-z0-9 ]+', ' ', normalized)
        normalized = re.sub(r'\s+', '', normalized)
        return normalized

    def _load_regional_forms(self, forms_path: Path) -> None:
        """Merge regional variants into the species list.

        Regional forms inherit data from their base species and override
        properties like types, abilities, and stats as needed. Each form
        registers multiple aliases so users can request "alolan vulpix",
        "vulpix-alola", or "vulpix (alola)" and receive the correct entry.
        """

        with open(forms_path, 'r', encoding='utf-8') as f:
            forms_data = json.load(f)

        for form_entry in forms_data:
            base_identifier = form_entry['base_species']
            base_species = self.data.get(str(base_identifier))
            if base_species is None:
                base_species = next(
                    (s for s in self.data.values() if s['name'].lower() == str(base_identifier).lower()),
                    None,
                )

            if base_species is None:
                continue

            form = form_entry['form']
            variant = json.loads(json.dumps(base_species))  # deep copy
            variant['form'] = form
            variant['name'] = form_entry.get('name', f"{base_species['name']}-{form}")
            variant['types'] = form_entry.get('types', base_species.get('types', []))
            variant['abilities'] = form_entry.get('abilities', base_species.get('abilities', {}))

            if 'base_stats' in form_entry:
                variant['base_stats'] = form_entry['base_stats']

            # Use a predictable key so variants don't overwrite the base species
            variant_id = form_entry.get('id', f"{base_species['dex_number']}-{form}")
            variant['dex_number'] = base_species['dex_number']
            self.data[str(variant_id)] = variant

            # Register aliases for flexible lookups
            base_name = base_species['name']
            aliases = set(form_entry.get('aliases', []))
            aliases.update(
                {
                    f"{base_name}-{form}",
                    f"{form} {base_name}",
                    f"{base_name} ({form})",
                }
            )

            for alias in aliases:
                self._alias_map[self._normalize_name(alias)] = variant
    
    def get_all_starters(self) -> List[Dict]:
        """Get all non-legendary Pokemon suitable as starters"""
        try:
            from config.starters import STARTER_MODE, ALLOWED_STARTERS, EXCLUDED_POKEMON
        except ImportError:
            # Fallback if config doesn't exist
            STARTER_MODE = "all_non_legendary"
            ALLOWED_STARTERS = []
            EXCLUDED_POKEMON = []
        
        starters = []
        
        if STARTER_MODE == "curated_list":
            # Use handpicked list from config
            for dex_num in ALLOWED_STARTERS:
                species = self.get_species(dex_num)
                if species and dex_num not in EXCLUDED_POKEMON:
                    starters.append(species)

        elif STARTER_MODE == "first_forms_only":
            # Only allow first evolution forms
            for species in self.data.values():
                # Exclude legendaries, mythicals, ultra beasts, paradox
                if any([
                    species.get('is_legendary', False),
                    species.get('is_mythical', False),
                    species.get('is_ultra_beast', False),
                    species.get('is_paradox', False),
                    species['dex_number'] in EXCLUDED_POKEMON
                ]):
                    continue
                
                # Check if first form (has no pre-evolution)
                # This is a simple check - you could enhance this with evolution data
                if self._is_first_form(species):
                    starters.append(species)
        
        elif STARTER_MODE == "all_species":
            # Literally every Pokemon that exists in the species database
            for species in self.data.values():
                if species['dex_number'] in EXCLUDED_POKEMON:
                    continue
                starters.append(species)

        else:  # "all_non_legendary" or default
            # Allow all non-legendary Pokemon
            for species in self.data.values():
                if not any([
                    species.get('is_legendary', False),
                    species.get('is_mythical', False),
                    species.get('is_ultra_beast', False),
                    species.get('is_paradox', False),
                    species['dex_number'] in EXCLUDED_POKEMON
                ]):
                    starters.append(species)
        
        return sorted(starters, key=lambda x: x['dex_number'])
    
    def _is_first_form(self, species: Dict) -> bool:
        """Check if this Pokemon is a first evolution form"""
        # Simple heuristic: check if dex number is lower than similar species
        # This isn't perfect but works for most cases
        # You could enhance this by adding evolution_chain data to the species JSON
        
        # For now, use a simple rule: if it's not a legendary/mythical and 
        # its base_experience is relatively low, it's probably a first form
        base_exp = species.get('base_experience', 0)
        
        # First forms usually have base_exp < 150
        # Middle forms 150-200, Final forms 200+
        return base_exp < 150
    
    def search_species(self, query: str, limit: int = 25) -> List[Dict]:
        """Search for species by name"""
        query_lower = query.lower()
        results = []
        
        for species in self.data.values():
            if query_lower in species['name'].lower():
                results.append(species)
                if len(results) >= limit:
                    break
        
        return results


class MovesDatabase:
    """Loads and queries move data"""
    
    def __init__(self, json_path: str):
        with open(json_path, 'r', encoding='utf-8') as f:
            self.data = json.load(f)

        # Build an alias map so we can resolve common formatting differences
        # (e.g., Showdown's "firefang" -> our stored "fire_fang").
        self._alias_map = {}
        for move_id in self.data.keys():
            collapsed = re.sub(r'[\s_-]+', '', move_id.lower())
            # Preserve the first occurrence for any collision; Showdown names
            # are unique enough that conflicts are unlikely in practice.
            self._alias_map.setdefault(collapsed, move_id)

    def get_move(self, move_id: str) -> Optional[Dict]:
        """Get move by ID"""
        normalized = move_id.lower().replace(' ', '_')
        move = self.data.get(normalized)
        if move:
            return move

        # Fallback: collapse spaces, hyphens, and underscores to find Showdown-style IDs
        collapsed = re.sub(r'[\s_-]+', '', move_id.lower())
        alias = self._alias_map.get(collapsed)
        if alias:
            return self.data.get(alias)

        return None
    
    def get_moves_by_type(self, move_type: str) -> List[Dict]:
        """Get all moves of a specific type"""
        return [move for move in self.data.values() if move['type'] == move_type.lower()]


class AbilitiesDatabase:
    """Loads and queries ability data"""
    
    def __init__(self, json_path: str):
        with open(json_path, 'r', encoding='utf-8') as f:
            self.data = json.load(f)
    
    def get_ability(self, ability_id: str) -> Optional[Dict]:
        """Get ability by ID"""
        return self.data.get(ability_id.lower().replace(' ', '_'))


class ItemsDatabase:
    """Loads and queries item data"""

    def __init__(self, json_path: str):
        with open(json_path, 'r', encoding='utf-8') as f:
            self.data = json.load(f)

        self._apply_bag_categories()
    
    def get_item(self, item_id: str) -> Optional[Dict]:
        """Get item by ID"""
        return self.data.get(item_id.lower().replace(' ', '_'))
    
    def get_items_by_category(self, category: str) -> List[Dict]:
        """Get all items in a category"""
        return [item for item in self.data.values() if item.get('category') == category]

    def _apply_bag_categories(self) -> None:
        """Use the bundled PokeAPI CSV dump to map items into bag categories.

        The bot's bag UI uses a simplified set of categories. We derive those from the
        authoritative PokeAPI item tables (including Gen 9) so new items are grouped
        correctly without hand-maintaining the JSON data.
        """

        csv_root = Path(__file__).resolve().parent / "pokeapi_csv_bot"
        items_csv = csv_root / "items.csv"
        categories_csv = csv_root / "item_categories.csv"
        pockets_csv = csv_root / "item_pockets.csv"

        if not (items_csv.exists() and categories_csv.exists() and pockets_csv.exists()):
            return

        categories = {}
        with open(categories_csv, newline='') as f:
            for row in csv.DictReader(f):
                categories[row['id']] = {
                    'identifier': row['identifier'],
                    'pocket_id': row['pocket_id'],
                }

        pockets = {}
        with open(pockets_csv, newline='') as f:
            for row in csv.DictReader(f):
                pockets[row['id']] = row['identifier']

        def derive_bag_category(cat_identifier: str, pocket_identifier: str, item_identifier: str) -> str:
            """Collapse PokeAPI categories into the bot's bag groupings."""

            pocket_map = {
                'medicine': 'medicine',
                'pokeballs': 'pokeball',
                'battle': 'battle_item',
                'berries': 'berries',
                'machines': 'tms',
                'key': 'key_item',
                'mail': 'other',
                'misc': 'other',
            }

            omni_categories = {'mega-stones', 'tera-shard', 'z-crystals', 'dynamax-crystals'}
            if cat_identifier in omni_categories or 'tera-' in item_identifier or 'mega-' in item_identifier:
                return 'omni'

            if cat_identifier == 'tm-materials':
                return 'tms'

            return pocket_map.get(pocket_identifier, 'other')

        # Explicit overrides for items whose Gen 9 bag placement differs from older games
        overrides = {
            'rare_candy': 'other',
        }

        bag_categories = {}
        with open(items_csv, newline='') as f:
            for row in csv.DictReader(f):
                cat_info = categories.get(row['category_id'])
                if not cat_info:
                    continue

                pocket_identifier = pockets.get(cat_info['pocket_id'], 'misc')
                bag_categories[row['identifier'].replace('-', '_')] = derive_bag_category(
                    cat_info['identifier'], pocket_identifier, row['identifier']
                )

        for item_id, item_data in self.data.items():
            if not isinstance(item_data, dict):
                continue

            bag_category = overrides.get(item_id, bag_categories.get(item_id))
            if bag_category:
                item_data['bag_category'] = bag_category
            else:
                item_data.setdefault('bag_category', item_data.get('category', 'other'))


class NaturesDatabase:
    """Loads and queries nature data"""
    
    def __init__(self, json_path: str):
        with open(json_path, 'r', encoding='utf-8') as f:
            self.data = json.load(f)
    
    def get_nature(self, nature_name: str) -> Optional[Dict]:
        """Get nature by name"""
        return self.data.get(nature_name.lower())
    
    def get_all_natures(self) -> List[Dict]:
        """Get all natures"""
        return list(self.data.values())


class TypeChart:
    """Loads type effectiveness chart"""
    
    def __init__(self, json_path: str):
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.chart = data['type_chart']
    
    def get_effectiveness(self, attacking_type: str, defending_type: str) -> float:
        """Get type effectiveness multiplier"""
        return self.chart.get(attacking_type.lower(), {}).get(defending_type.lower(), 1.0)
    
    def get_dual_effectiveness(self, attacking_type: str, defending_types: List[str]) -> float:
        """Calculate effectiveness against dual-type Pokemon"""
        multiplier = 1.0
        for def_type in defending_types:
            multiplier *= self.get_effectiveness(attacking_type, def_type)
        return multiplier


# ============================================================
# PLAYER DATA STORAGE (SQLite database)
# ============================================================

class PlayerDatabase:
    """Handles player data storage in SQLite"""
    
    def __init__(self, db_path: str = "data/players.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.init_database()
    
    def init_database(self):
        """Create tables if they don't exist"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Trainers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trainers (
                discord_user_id INTEGER PRIMARY KEY,
                trainer_name TEXT NOT NULL,
                avatar_url TEXT,
                pronouns TEXT,
                age TEXT,
                birthday TEXT,
                home_region TEXT,
                bio TEXT,
                current_location_id TEXT DEFAULT 'lights_district_moonwake_port',
                money INTEGER DEFAULT 5000,

                boon_stat TEXT,
                bane_stat TEXT,

                -- Social Stats
                heart_rank INTEGER DEFAULT 1,
                heart_points INTEGER DEFAULT 50,
                insight_rank INTEGER DEFAULT 1,
                insight_points INTEGER DEFAULT 50,
                charisma_rank INTEGER DEFAULT 1,
                charisma_points INTEGER DEFAULT 50,
                fortitude_rank INTEGER DEFAULT 1,
                fortitude_points INTEGER DEFAULT 50,
                will_rank INTEGER DEFAULT 1,
                will_points INTEGER DEFAULT 50,

                -- Stamina
                stamina_current INTEGER DEFAULT 9,
                stamina_max INTEGER DEFAULT 9,
                last_stamina_update INTEGER DEFAULT 0,

                -- Ranked Ladder
                rank_tier_name TEXT DEFAULT 'Qualifier',
                rank_tier_number INTEGER,
                ladder_points INTEGER DEFAULT 0,
                has_promotion_ticket INTEGER DEFAULT 0,
                ticket_tier INTEGER,
                rank_pending_tier INTEGER,
                has_omni_ring INTEGER DEFAULT 0,
                omni_ring_gimmicks TEXT,

                -- Following Pokemon
                following_pokemon_id TEXT,

                -- Forever Partner Pokemon
                partner_pokemon_id TEXT,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self._ensure_trainer_columns(cursor)

        # Pokemon instances table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_instances (
                pokemon_id TEXT PRIMARY KEY,
                owner_discord_id INTEGER NOT NULL,
                species_dex_number INTEGER NOT NULL,
                form TEXT,
                nickname TEXT,
                level INTEGER DEFAULT 5,
                exp INTEGER DEFAULT 0,

                -- Core Stats
                gender TEXT,
                nature TEXT NOT NULL,
                ability TEXT NOT NULL,
                held_item TEXT,
                pokeball TEXT DEFAULT 'poke_ball',

                -- Battle Stats
                current_hp INTEGER NOT NULL,
                max_hp INTEGER NOT NULL,
                status_condition TEXT,

                -- IVs
                iv_hp INTEGER DEFAULT 31,
                iv_attack INTEGER DEFAULT 31,
                iv_defense INTEGER DEFAULT 31,
                iv_sp_attack INTEGER DEFAULT 31,
                iv_sp_defense INTEGER DEFAULT 31,
                iv_speed INTEGER DEFAULT 31,

                -- EVs
                ev_hp INTEGER DEFAULT 0,
                ev_attack INTEGER DEFAULT 0,
                ev_defense INTEGER DEFAULT 0,
                ev_sp_attack INTEGER DEFAULT 0,
                ev_sp_defense INTEGER DEFAULT 0,
                ev_speed INTEGER DEFAULT 0,

                -- Moves (stored as JSON array)
                moves TEXT NOT NULL,

                -- Social
                friendship INTEGER DEFAULT 70,
                bond_level INTEGER DEFAULT 0,

                -- Storage
                in_party INTEGER DEFAULT 0,
                party_position INTEGER,
                box_position INTEGER,

                -- Flags
                is_shiny INTEGER DEFAULT 0,
                can_mega_evolve INTEGER DEFAULT 0,
                tera_type TEXT,

                -- Special Flags
                is_partner INTEGER DEFAULT 0,

                caught_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (owner_discord_id) REFERENCES trainers(discord_user_id)
            )
        """)

        self._ensure_pokemon_columns(cursor)
        
        # Inventory table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                discord_user_id INTEGER,
                item_id TEXT,
                quantity INTEGER DEFAULT 0,
                PRIMARY KEY (discord_user_id, item_id),
                FOREIGN KEY (discord_user_id) REFERENCES trainers(discord_user_id)
            )
        """)
        
        # Pokedex (encountered species)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pokedex (
                discord_user_id INTEGER,
                species_dex_number INTEGER,
                first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (discord_user_id, species_dex_number),
                FOREIGN KEY (discord_user_id) REFERENCES trainers(discord_user_id)
            )
        """)

        # Wild Areas system
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS wild_areas (
                area_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS wild_area_zones (
                zone_id TEXT PRIMARY KEY,
                area_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                has_pokemon_station INTEGER DEFAULT 0,
                zone_travel_cost INTEGER DEFAULT 5,
                encounters TEXT,
                npc_trainers TEXT,
                FOREIGN KEY (area_id) REFERENCES wild_areas(area_id)
            )
        """)

        # Party/Team system
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS parties (
                party_id TEXT PRIMARY KEY,
                party_name TEXT NOT NULL,
                leader_discord_id INTEGER NOT NULL,
                area_id TEXT NOT NULL,
                current_zone_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (leader_discord_id) REFERENCES trainers(discord_user_id),
                FOREIGN KEY (area_id) REFERENCES wild_areas(area_id),
                FOREIGN KEY (current_zone_id) REFERENCES wild_area_zones(zone_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS party_members (
                party_id TEXT,
                discord_user_id INTEGER,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (party_id, discord_user_id),
                FOREIGN KEY (party_id) REFERENCES parties(party_id),
                FOREIGN KEY (discord_user_id) REFERENCES trainers(discord_user_id)
            )
        """)

        # Trainer wild area state tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trainer_wild_area_states (
                discord_user_id INTEGER PRIMARY KEY,
                area_id TEXT NOT NULL,
                current_zone_id TEXT NOT NULL,
                entry_stamina INTEGER NOT NULL,
                current_stamina INTEGER NOT NULL,
                snapshot_money INTEGER NOT NULL,
                snapshot_inventory TEXT NOT NULL,
                snapshot_pokemon_exp TEXT NOT NULL,
                entered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (discord_user_id) REFERENCES trainers(discord_user_id),
                FOREIGN KEY (area_id) REFERENCES wild_areas(area_id),
                FOREIGN KEY (current_zone_id) REFERENCES wild_area_zones(zone_id)
            )
        """)

        # Static encounters
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS static_encounters (
                encounter_id TEXT PRIMARY KEY,
                zone_id TEXT NOT NULL,
                encounter_type TEXT NOT NULL,
                target_player_id INTEGER,
                pokemon_data TEXT,
                trainer_data TEXT,
                battle_format TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (zone_id) REFERENCES wild_area_zones(zone_id),
                FOREIGN KEY (target_player_id) REFERENCES trainers(discord_user_id)
            )
        """)
        
        conn.commit()
        conn.close()

    def _get_table_columns(self, cursor, table_name: str) -> set:
        cursor.execute(f"PRAGMA table_info({table_name})")
        return {row[1] for row in cursor.fetchall()}

    def _ensure_trainer_columns(self, cursor):
        """Add missing trainer columns when migrating older databases."""

        existing_columns = self._get_table_columns(cursor, 'trainers')
        legacy_columns = existing_columns.copy()

        def add_column(column: str, definition: str) -> bool:
            if column not in existing_columns:
                cursor.execute(f"ALTER TABLE trainers ADD COLUMN {column} {definition}")
                existing_columns.add(column)
                return True
            return False

        # Track boon/bane choices
        add_column('boon_stat', 'TEXT')
        add_column('bane_stat', 'TEXT')

        # Registration info columns
        add_column('pronouns', 'TEXT')
        add_column('age', 'TEXT')
        add_column('birthday', 'TEXT')
        add_column('home_region', 'TEXT')
        add_column('bio', 'TEXT')
        add_column('avatar_url', 'TEXT')

        # Ranks
        if add_column('heart_rank', 'INTEGER DEFAULT 1') and 'instinct_rank' in legacy_columns:
            cursor.execute("UPDATE trainers SET heart_rank = COALESCE(instinct_rank, 1)")
        if add_column('insight_rank', 'INTEGER DEFAULT 1') and 'knowledge_rank' in legacy_columns:
            cursor.execute("UPDATE trainers SET insight_rank = COALESCE(knowledge_rank, 1)")
        add_column('charisma_rank', 'INTEGER DEFAULT 1')
        if add_column('fortitude_rank', 'INTEGER DEFAULT 1') and 'vigor_rank' in legacy_columns:
            cursor.execute("UPDATE trainers SET fortitude_rank = COALESCE(vigor_rank, 1)")
        add_column('will_rank', 'INTEGER DEFAULT 1')
        add_column('ticket_tier', 'INTEGER')
        add_column('rank_pending_tier', 'INTEGER')

        # Points
        if add_column('heart_points', 'INTEGER DEFAULT 50'):
            cursor.execute("UPDATE trainers SET heart_points = heart_rank * 50")
        if add_column('insight_points', 'INTEGER DEFAULT 50'):
            cursor.execute("UPDATE trainers SET insight_points = insight_rank * 50")
        if add_column('charisma_points', 'INTEGER DEFAULT 50'):
            cursor.execute("UPDATE trainers SET charisma_points = charisma_rank * 50")
        if add_column('fortitude_points', 'INTEGER DEFAULT 50'):
            cursor.execute("UPDATE trainers SET fortitude_points = fortitude_rank * 50")
        if add_column('will_points', 'INTEGER DEFAULT 50'):
            cursor.execute("UPDATE trainers SET will_points = will_rank * 50")

        # Stamina
        stamina_max_added = add_column('stamina_max', 'INTEGER DEFAULT 0')
        stamina_current_added = add_column('stamina_current', 'INTEGER DEFAULT 0')
        last_stamina_update_added = add_column('last_stamina_update', 'INTEGER DEFAULT 0')

        if stamina_max_added or stamina_current_added:
            cursor.execute("SELECT discord_user_id, fortitude_rank FROM trainers")
            rows = cursor.fetchall()
            for row in rows:
                fortitude_rank = row['fortitude_rank'] if isinstance(row, sqlite3.Row) else row[1]
                if fortitude_rank is None:
                    fortitude_rank = 1
                stamina_max = calculate_max_stamina(fortitude_rank)
                cursor.execute(
                    "UPDATE trainers SET stamina_max = ?, stamina_current = ? WHERE discord_user_id = ?",
                    (stamina_max, stamina_max, row['discord_user_id'] if isinstance(row, sqlite3.Row) else row[0])
                )

        if last_stamina_update_added:
            cursor.execute("UPDATE trainers SET last_stamina_update = strftime('%s','now')")

        add_column('has_omni_ring', 'INTEGER DEFAULT 0')
        add_column('omni_ring_gimmicks', 'TEXT')
        add_column('partner_pokemon_id', 'TEXT')

        # Battle Themes
        add_column('battle_theme_url', 'TEXT')
        add_column('victory_theme_url', 'TEXT')

    def _ensure_pokemon_columns(self, cursor):
        """Add missing pokemon_instances columns when migrating older databases."""

        existing_columns = self._get_table_columns(cursor, 'pokemon_instances')

        def add_column(column: str, definition: str) -> bool:
            if column not in existing_columns:
                cursor.execute(f"ALTER TABLE pokemon_instances ADD COLUMN {column} {definition}")
                existing_columns.add(column)
                return True
            return False

        # Add form column for regional variants
        add_column('form', 'TEXT')

        # Track stored experience earned while at a level cap
        add_column('stored_exp', 'INTEGER DEFAULT 0')

        # Track the Poké Ball each Pokémon was caught in
        pokeball_added = add_column('pokeball', "TEXT DEFAULT 'poke_ball'")
        if pokeball_added:
            cursor.execute("UPDATE pokemon_instances SET pokeball = 'poke_ball' WHERE pokeball IS NULL")

        # Forever partner flag
        add_column('is_partner', 'INTEGER DEFAULT 0')

        # Cooldown tracking for per-opponent battles
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS battle_cooldowns (
                discord_user_id INTEGER NOT NULL,
                target_type TEXT NOT NULL,
                target_identifier TEXT NOT NULL,
                expires_at INTEGER,
                PRIMARY KEY (discord_user_id, target_type, target_identifier)
            )
            """
        )

    def get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    # ============================================================
    # TRAINER OPERATIONS
    # ============================================================

    def create_trainer(self, discord_user_id: int, trainer_name: str,
                      avatar_url: str = None, boon_stat: str = None,
                      bane_stat: str = None, pronouns: str = None, age: str = None,
                      birthday: str = None, home_region: str = None, bio: str = None) -> bool:
        """Create a new trainer profile"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            stats_payload: Dict[str, int] = {}
            for stat_key in SOCIAL_STAT_ORDER:
                cap = get_stat_cap(stat_key, boon_stat, bane_stat)
                base_rank = 1
                if stat_key == boon_stat:
                    base_rank = 2
                elif stat_key == bane_stat:
                    base_rank = 0

                # Default starting points: 50 per rank
                stats_payload[f"{stat_key}_rank"] = base_rank
                stats_payload[f"{stat_key}_points"] = base_rank * 50

            fortitude_rank = stats_payload['fortitude_rank']
            stamina_max = calculate_max_stamina(fortitude_rank)

            cursor.execute(
                """
                INSERT INTO trainers (
                    discord_user_id, trainer_name, avatar_url,
                    pronouns, age, birthday, home_region, bio, current_location_id,
                    boon_stat, bane_stat,
                    heart_rank, heart_points,
                    insight_rank, insight_points,
                    charisma_rank, charisma_points,
                    fortitude_rank, fortitude_points,
                    will_rank, will_points,
                    stamina_current, stamina_max, last_stamina_update
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    discord_user_id,
                    trainer_name,
                    avatar_url,
                    pronouns,
                    age,
                    birthday,
                    home_region,
                    bio,
                    "lights_district_moonwake_port",
                    boon_stat,
                    bane_stat,
                    stats_payload['heart_rank'],
                    stats_payload['heart_points'],
                    stats_payload['insight_rank'],
                    stats_payload['insight_points'],
                    stats_payload['charisma_rank'],
                    stats_payload['charisma_points'],
                    stats_payload['fortitude_rank'],
                    stats_payload['fortitude_points'],
                    stats_payload['will_rank'],
                    stats_payload['will_points'],
                    stamina_max,
                    stamina_max,
                    int(time.time()),
                ),
            )

            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # Trainer already exists
        finally:
            conn.close()

    def get_trainer(self, discord_user_id: int) -> Optional[Dict]:
        """Get trainer by Discord ID"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM trainers WHERE discord_user_id = ?", (discord_user_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def trainer_exists(self, discord_user_id: int) -> bool:
        """Check if trainer exists"""
        return self.get_trainer(discord_user_id) is not None

    def get_top_ranked_players(self, limit: int = 10) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT discord_user_id, trainer_name, rank_tier_number, rank_tier_name,
                   ladder_points, has_promotion_ticket, ticket_tier
            FROM trainers
            ORDER BY COALESCE(rank_tier_number, 1) DESC, ladder_points DESC
            LIMIT ?
            """,
            (limit,)
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def get_ticket_holders(self) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT discord_user_id, trainer_name, rank_tier_number, ladder_points,
                   ticket_tier
            FROM trainers
            WHERE has_promotion_ticket = 1
            ORDER BY COALESCE(ticket_tier, rank_tier_number) ASC, ladder_points DESC
            """
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def get_trainers_with_pending_promotions(self, max_tier: int) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT discord_user_id, trainer_name, rank_pending_tier
            FROM trainers
            WHERE rank_pending_tier IS NOT NULL AND rank_pending_tier <= ?
            """,
            (max_tier,)
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows
    
    def update_trainer(self, discord_user_id: int, **kwargs):
        """Update trainer fields"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Build UPDATE query dynamically
        fields = ', '.join([f"{key} = ?" for key in kwargs.keys()])
        values = list(kwargs.values()) + [discord_user_id]
        
        cursor.execute(f"""
            UPDATE trainers 
            SET {fields}, updated_at = CURRENT_TIMESTAMP
            WHERE discord_user_id = ?
        """, values)
        
        conn.commit()
        conn.close()

    def set_partner_pokemon(self, discord_user_id: int, pokemon_id: str):
        """Mark a Pokemon as the trainer's forever partner and clear other flags."""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE pokemon_instances SET is_partner = 0 WHERE owner_discord_id = ?",
            (discord_user_id,),
        )
        cursor.execute(
            "UPDATE pokemon_instances SET is_partner = 1 WHERE pokemon_id = ?",
            (pokemon_id,),
        )
        cursor.execute(
            """
            UPDATE trainers
            SET partner_pokemon_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE discord_user_id = ?
            """,
            (pokemon_id, discord_user_id),
        )

        conn.commit()
        conn.close()

    # ------------------------------------------------------------
    # Battle cooldown operations
    # ------------------------------------------------------------
    def set_battle_cooldown(
        self,
        discord_user_id: int,
        target_type: str,
        target_identifier: str,
        expires_at: Optional[int],
    ):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO battle_cooldowns (discord_user_id, target_type, target_identifier, expires_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(discord_user_id, target_type, target_identifier)
            DO UPDATE SET expires_at=excluded.expires_at
            """,
            (discord_user_id, target_type, target_identifier, expires_at),
        )
        conn.commit()
        conn.close()

    def get_battle_cooldown(self, discord_user_id: int, target_type: str, target_identifier: str) -> Optional[int]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT expires_at FROM battle_cooldowns
            WHERE discord_user_id = ? AND target_type = ? AND target_identifier = ?
            """,
            (discord_user_id, target_type, target_identifier),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        value = row[0] if not isinstance(row, sqlite3.Row) else row["expires_at"]
        return value

    def clear_expired_cooldowns(self, now_ts: Optional[int] = None):
        conn = self.get_connection()
        cursor = conn.cursor()
        if now_ts is None:
            now_ts = int(time.time())
        cursor.execute(
            "DELETE FROM battle_cooldowns WHERE expires_at IS NOT NULL AND expires_at >= 0 AND expires_at <= ?",
            (now_ts,),
        )
        conn.commit()
        conn.close()
    
    # ============================================================
    # POKEMON OPERATIONS
    # ============================================================
    
    def add_pokemon(self, pokemon_data: Dict) -> str:
        """Add a Pokemon to a trainer's collection"""
        conn = self.get_connection()
        cursor = conn.cursor()

        pokemon_id = pokemon_data.get('pokemon_id', str(uuid.uuid4()))

        # Keep the column ordering and the placeholder count in sync to avoid
        # "X values for Y columns" errors when inserting new Pokémon.
        column_value_pairs = [
            ('pokemon_id', pokemon_id),
            ('owner_discord_id', pokemon_data['owner_discord_id']),
            ('species_dex_number', pokemon_data['species_dex_number']),
            ('form', pokemon_data.get('form')),
            ('nickname', pokemon_data.get('nickname')),
            ('level', pokemon_data.get('level', 5)),
            ('exp', pokemon_data.get('exp', 0)),
            ('stored_exp', pokemon_data.get('stored_exp', 0)),
            ('gender', pokemon_data.get('gender')),
            ('nature', pokemon_data['nature']),
            ('ability', pokemon_data['ability']),
            ('held_item', pokemon_data.get('held_item')),
            ('pokeball', pokemon_data.get('pokeball', 'poke_ball')),
            ('current_hp', pokemon_data['current_hp']),
            ('max_hp', pokemon_data['max_hp']),
            ('status_condition', pokemon_data.get('status_condition')),
            ('iv_hp', pokemon_data.get('iv_hp', 31)),
            ('iv_attack', pokemon_data.get('iv_attack', 31)),
            ('iv_defense', pokemon_data.get('iv_defense', 31)),
            ('iv_sp_attack', pokemon_data.get('iv_sp_attack', 31)),
            ('iv_sp_defense', pokemon_data.get('iv_sp_defense', 31)),
            ('iv_speed', pokemon_data.get('iv_speed', 31)),
            ('ev_hp', pokemon_data.get('ev_hp', 0)),
            ('ev_attack', pokemon_data.get('ev_attack', 0)),
            ('ev_defense', pokemon_data.get('ev_defense', 0)),
            ('ev_sp_attack', pokemon_data.get('ev_sp_attack', 0)),
            ('ev_sp_defense', pokemon_data.get('ev_sp_defense', 0)),
            ('ev_speed', pokemon_data.get('ev_speed', 0)),
                ('moves', json.dumps(pokemon_data['moves'])),
                ('friendship', pokemon_data.get('friendship', 70)),
                ('bond_level', pokemon_data.get('bond_level', 0)),
                ('in_party', pokemon_data.get('in_party', 0)),
                ('party_position', pokemon_data.get('party_position')),
                ('box_position', pokemon_data.get('box_position')),
                ('is_shiny', pokemon_data.get('is_shiny', 0)),
                ('can_mega_evolve', pokemon_data.get('can_mega_evolve', 0)),
                ('tera_type', pokemon_data.get('tera_type')),
                ('is_partner', pokemon_data.get('is_partner', 0)),
            ]

        columns = ", ".join(name for name, _ in column_value_pairs)
        placeholders = ", ".join("?" for _ in column_value_pairs)
        values = tuple(value for _, value in column_value_pairs)

        cursor.execute(
            f"""
            INSERT INTO pokemon_instances ({columns})
            VALUES ({placeholders})
        """,
            values,
        )

        conn.commit()
        conn.close()

        return pokemon_id

    def get_pokemon(self, pokemon_id: str) -> Optional[Dict]:
        """Get a specific Pokemon by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM pokemon_instances WHERE pokemon_id = ?", (pokemon_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            pokemon = dict(row)
            pokemon['moves'] = json.loads(pokemon['moves'])
            pokemon['is_partner'] = bool(pokemon.get('is_partner'))
            return pokemon
        return None
    
    def get_trainer_party(self, discord_user_id: int) -> List[Dict]:
        """Get trainer's party Pokemon"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM pokemon_instances 
            WHERE owner_discord_id = ? AND in_party = 1
            ORDER BY party_position
        """, (discord_user_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        party = []
        for row in rows:
            pokemon = dict(row)
            pokemon['moves'] = json.loads(pokemon['moves'])
            pokemon['is_partner'] = bool(pokemon.get('is_partner'))
            party.append(pokemon)

        return party

    def get_players_in_location(self, location_id: str) -> List[Dict]:
        """Return all trainers currently registered at a specific location."""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM trainers WHERE current_location_id = ?",
            (location_id,)
        )

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_trainer_boxes(self, discord_user_id: int) -> List[Dict]:
        """Get trainer's boxed Pokemon"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM pokemon_instances 
            WHERE owner_discord_id = ? AND in_party = 0
            ORDER BY box_position
        """, (discord_user_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        boxes = []
        for row in rows:
            pokemon = dict(row)
            pokemon['moves'] = json.loads(pokemon['moves'])
            pokemon['is_partner'] = bool(pokemon.get('is_partner'))
            boxes.append(pokemon)

        return boxes

    def heal_party(self, discord_user_id: int) -> int:
        """Restore all party Pokémon HP and clear their major status conditions."""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE pokemon_instances
            SET current_hp = max_hp,
                status_condition = NULL
            WHERE owner_discord_id = ?
              AND in_party = 1
              AND (current_hp < max_hp OR status_condition IS NOT NULL)
            """,
            (discord_user_id,),
        )

        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected
    
    # ============================================================
    # POKEDEX OPERATIONS
    # ============================================================
    
    def add_pokedex_entry(self, discord_user_id: int, species_dex_number: int):
        """Record that a trainer has seen this species"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO pokedex (discord_user_id, species_dex_number)
                VALUES (?, ?)
            """, (discord_user_id, species_dex_number))
            conn.commit()
        except sqlite3.IntegrityError:
            pass  # Already seen
        finally:
            conn.close()
    
    def get_pokedex(self, discord_user_id: int) -> List[int]:
        """Get list of seen species dex numbers"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT species_dex_number FROM pokedex
            WHERE discord_user_id = ?
            ORDER BY species_dex_number
        """, (discord_user_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [row['species_dex_number'] for row in rows]
    
    # ============================================================
    # INVENTORY OPERATIONS
    # ============================================================
    
    def get_inventory(self, discord_user_id: int) -> List[Dict]:
        """Get trainer's inventory"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM inventory
            WHERE discord_user_id = ?
            ORDER BY item_id
        """, (discord_user_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def add_item(self, discord_user_id: int, item_id: str, quantity: int = 1):
        """Add item(s) to inventory (creates or updates)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Check if item already exists
        cursor.execute("""
            SELECT quantity FROM inventory
            WHERE discord_user_id = ? AND item_id = ?
        """, (discord_user_id, item_id))
        
        row = cursor.fetchone()
        
        if row:
            # Update existing
            new_quantity = row['quantity'] + quantity
            cursor.execute("""
                UPDATE inventory
                SET quantity = ?
                WHERE discord_user_id = ? AND item_id = ?
            """, (new_quantity, discord_user_id, item_id))
        else:
            # Insert new
            cursor.execute("""
                INSERT INTO inventory (discord_user_id, item_id, quantity)
                VALUES (?, ?, ?)
            """, (discord_user_id, item_id, quantity))
        
        conn.commit()
        conn.close()
    
    def remove_item(self, discord_user_id: int, item_id: str, quantity: int = 1) -> bool:
        """Remove item(s) from inventory. Returns True if successful."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Check current quantity
        cursor.execute("""
            SELECT quantity FROM inventory
            WHERE discord_user_id = ? AND item_id = ?
        """, (discord_user_id, item_id))
        
        row = cursor.fetchone()
        
        if not row or row['quantity'] < quantity:
            conn.close()
            return False  # Not enough items
        
        new_quantity = row['quantity'] - quantity
        
        if new_quantity <= 0:
            # Remove item entirely
            cursor.execute("""
                DELETE FROM inventory
                WHERE discord_user_id = ? AND item_id = ?
            """, (discord_user_id, item_id))
        else:
            # Update quantity
            cursor.execute("""
                UPDATE inventory
                SET quantity = ?
                WHERE discord_user_id = ? AND item_id = ?
            """, (new_quantity, discord_user_id, item_id))
        
        conn.commit()
        conn.close()
        return True
    
    def get_item_quantity(self, discord_user_id: int, item_id: str) -> int:
        """Get quantity of a specific item"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT quantity FROM inventory
            WHERE discord_user_id = ? AND item_id = ?
        """, (discord_user_id, item_id))
        
        row = cursor.fetchone()
        conn.close()
        
        return row['quantity'] if row else 0

    
    def update_pokemon(self, pokemon_id: str, updates: Dict) -> bool:
        """Update Pokemon fields"""
        if not updates:
            return False
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Build UPDATE query dynamically
        fields = ', '.join([f"{key} = ?" for key in updates.keys()])
        values = list(updates.values()) + [pokemon_id]
        
        cursor.execute(f"""
            UPDATE pokemon_instances 
            SET {fields}
            WHERE pokemon_id = ?
        """, values)
        
        conn.commit()
        conn.close()
        return True
    
    def delete_pokemon(self, pokemon_id: str) -> bool:
        """Delete a Pokemon permanently"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM pokemon_instances
            WHERE pokemon_id = ?
        """, (pokemon_id,))
        
        conn.commit()
        conn.close()
        return True

def delete_player(player_id: int | str) -> bool:
    """Delete a player character by numeric ID or discord_id. Returns True if a row was removed."""
    import sqlite3, os
    db_path = os.path.join(os.path.dirname(__file__), "data", "players.db")
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM players WHERE id = ?", (int(player_id),))
        except Exception:
            cur.execute("DELETE FROM players WHERE discord_id = ?", (str(player_id),))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()