"""
Data Models - Classes for game entities
"""

import random
import json
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from exp_system import ExpSystem

from social_stats import (
    SOCIAL_STAT_DEFINITIONS,
    SOCIAL_STAT_ORDER,
    get_stat_cap,
    rank_to_points,
    calculate_max_stamina,
)


@dataclass
class PokemonMove:
    """Represents a single move on a Pokemon"""
    move_id: str
    pp: int
    max_pp: int


class Pokemon:
    """Represents an owned Pokemon instance"""
    
    def __init__(self, species_data: Dict, level: int = 5,
                 owner_discord_id: int = None, nature: str = None,
                 ability: str = None, moves: List[str] = None,
                 ivs: Dict[str, int] = None, is_shiny: bool = False,
                 form: str = None, gender: Optional[str] = None,
                 pokeball: Optional[str] = None):
        """
        Create a new Pokemon instance

        Args:
            species_data: Species info from SpeciesDatabase
            level: Starting level
            owner_discord_id: Trainer who owns this Pokemon
            nature: Nature name (random if None)
            ability: Ability ID (random valid ability if None)
            moves: List of move IDs (auto-generated if None)
            ivs: IV dict (random if None)
            is_shiny: Whether this Pokemon is shiny
            form: Regional form (e.g. 'alola', 'hisui', 'galar') or None for base form
            gender: 'male', 'female', or None to auto-generate based on species ratio
        """
        self.species_dex_number = species_data['dex_number']
        self.species_name = species_data['name']
        self.species_data = species_data
        self.growth_rate = species_data.get('growth_rate', 'medium_fast')
        self.level = level
        self.owner_discord_id = owner_discord_id
        self.nickname = None
        self.form = form if form is not None else species_data.get('form')
        
        # Generate gender based on species ratio (unless provided)
        self.gender = gender if gender is not None else self._generate_gender(
            species_data.get('gender_ratio', {})
        )
        
        # Nature
        from database import NaturesDatabase
        if nature is None:
            natures_db = NaturesDatabase('data/natures.json')
            nature = random.choice(list(natures_db.data.keys()))
        self.nature = nature
        
        # Ability
        abilities = species_data['abilities']
        if ability is None:
            # Random between primary and secondary (if exists)
            valid_abilities = [abilities['primary']]
            if abilities.get('secondary'):
                valid_abilities.append(abilities['secondary'])
            ability = random.choice(valid_abilities)
        self.ability = ability
        
        # IVs (0-31)
        if ivs is None:
            ivs = {
                'hp': random.randint(0, 31),
                'attack': random.randint(0, 31),
                'defense': random.randint(0, 31),
                'sp_attack': random.randint(0, 31),
                'sp_defense': random.randint(0, 31),
                'speed': random.randint(0, 31)
            }
        self.ivs = ivs
        
        # EVs (all 0 initially)
        self.evs = {
            'hp': 0,
            'attack': 0,
            'defense': 0,
            'sp_attack': 0,
            'sp_defense': 0,
            'speed': 0
        }
        
        # Calculate stats
        self.base_stats = species_data['base_stats']
        self._calculate_stats()
        
        # Moves
        if moves is None:
            moves = self._generate_starting_moves()
        self.moves = self._create_move_objects(moves)
        
        # Status
        self.current_hp = self.max_hp
        self.status_condition = None
        
        # Social
        self.friendship = 70
        self.bond_level = 0

        # Capture metadata
        self.pokeball = pokeball or 'poke_ball'
        
        # Battle state
        self.held_item = None
        self.is_shiny = is_shiny
        
        # Storage
        self.in_party = False
        self.party_position = None
        self.box_position = None

        # Special flags
        self.tera_type = None  # Could be set for Terastal
        self.is_partner = False

        # Raid attributes
        self.is_raid_boss = False
        self.raid_stat_multiplier = 1.0
        self.raid_hp_multiplier = 1.0
        self.raid_level_cap = None

        # Experience
        self.exp = ExpSystem.exp_to_level(level, self.growth_rate)
        self.stored_exp = 0
    
    def _generate_gender(self, gender_ratio: Dict) -> Optional[str]:
        """Generate gender based on species ratio"""
        male_percent = gender_ratio.get('male', 50)
        female_percent = gender_ratio.get('female', 50)
        
        # Genderless species
        if male_percent == 0 and female_percent == 0:
            return None
        
        # Generate
        roll = random.random() * 100
        if roll < male_percent:
            return 'male'
        else:
            return 'female'
    
    def _calculate_stats(self):
        """Calculate actual stats from base stats, IVs, EVs, nature"""
        from database import NaturesDatabase
        
        # Load nature modifiers
        natures_db = NaturesDatabase('data/natures.json')
        nature_data = natures_db.get_nature(self.nature)
        
        # HP calculation (different formula)
        self.max_hp = int(
            ((2 * self.base_stats['hp'] + self.ivs['hp'] + (self.evs['hp'] // 4))
             * self.level // 100) + self.level + 10
        )
        
        # Other stats
        for stat in ['attack', 'defense', 'sp_attack', 'sp_defense', 'speed']:
            base = self.base_stats[stat]
            iv = self.ivs[stat]
            ev = self.evs[stat]
            
            # Base calculation
            value = int(((2 * base + iv + (ev // 4)) * self.level // 100) + 5)
            
            # Apply nature modifier
            if nature_data:
                if nature_data.get('increased_stat') == stat:
                    value = int(value * 1.1)
                elif nature_data.get('decreased_stat') == stat:
                    value = int(value * 0.9)

            setattr(self, stat, value)

        # Apply raid multipliers (HP uses dedicated multiplier; other stats share raid_stat_multiplier)
        if getattr(self, "is_raid_boss", False):
            hp_multi = max(1.0, getattr(self, "raid_hp_multiplier", 1.0))
            stat_multi = max(1.0, getattr(self, "raid_stat_multiplier", 1.0))

            self.max_hp = int(self.max_hp * hp_multi)

            for stat in ['attack', 'defense', 'sp_attack', 'sp_defense']:
                boosted = int(getattr(self, stat, 0) * stat_multi)
                setattr(self, stat, boosted)
    
    def _generate_starting_moves(self) -> List[str]:
        """
        Generate starting moves based on level and species learnset
        Falls back to tackle/growl if learnsets not available
        """
        try:
            # Try to load learnset database
            import os
            from learnset_database import LearnsetDatabase
            
            learnset_path = 'data/learnsets.json'
            if os.path.exists(learnset_path):
                learnset_db = LearnsetDatabase(learnset_path)
                moves = learnset_db.get_starting_moves(
                    self.species_name,
                    level=self.level,
                    max_moves=4
                )
                
                # Make sure we got valid moves
                if moves and len(moves) > 0:
                    return moves
        except Exception as e:
            # If anything goes wrong, fall back to default
            print(f"Warning: Could not load learnsets for {self.species_name}: {e}")
        
        # Fallback to default moves
        return ['tackle', 'growl']
    
    def _create_move_objects(self, move_ids: List[str]) -> List[Dict]:
        """Convert move IDs to move objects with PP"""
        from database import MovesDatabase
        
        moves_db = MovesDatabase('data/moves.json')
        move_objects = []
        
        for move_id in move_ids:
            move_data = moves_db.get_move(move_id)
            if move_data:
                move_objects.append({
                    'move_id': move_id,
                    'pp': move_data['pp'],
                    'max_pp': move_data['pp']
                })
        
        return move_objects
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for database storage"""
        return {
            'owner_discord_id': self.owner_discord_id,
            'species_dex_number': self.species_dex_number,
            'form': self.form,
            'nickname': self.nickname,
            'level': self.level,
            'exp': self.exp,
            'gender': self.gender,
            'nature': self.nature,
            'ability': self.ability,
            'held_item': self.held_item,
            'current_hp': self.current_hp,
            'max_hp': self.max_hp,
            'status_condition': self.status_condition,
            'iv_hp': self.ivs['hp'],
            'iv_attack': self.ivs['attack'],
            'iv_defense': self.ivs['defense'],
            'iv_sp_attack': self.ivs['sp_attack'],
            'iv_sp_defense': self.ivs['sp_defense'],
            'iv_speed': self.ivs['speed'],
            'ev_hp': self.evs['hp'],
            'ev_attack': self.evs['attack'],
            'ev_defense': self.evs['defense'],
            'ev_sp_attack': self.evs['sp_attack'],
            'ev_sp_defense': self.evs['sp_defense'],
            'ev_speed': self.evs['speed'],
            'moves': self.moves,
            'pokeball': self.pokeball,
            'friendship': self.friendship,
            'bond_level': self.bond_level,
            'stored_exp': self.stored_exp,
            'in_party': 1 if self.in_party else 0,
            'party_position': self.party_position,
            'box_position': self.box_position,
            'is_shiny': 1 if self.is_shiny else 0,
            'can_mega_evolve': 0,  # Default to 0, can be set later
            'tera_type': self.tera_type,
            'is_partner': 1 if self.is_partner else 0
        }
    
    def get_display_name(self) -> str:
        """Get the display name (nickname or species name)"""
        return self.nickname if self.nickname else self.species_name
    
    def get_hp_percentage(self) -> float:
        """Get HP as a percentage"""
        if self.max_hp == 0:
            return 0
        return (self.current_hp / self.max_hp) * 100
    
    def is_fainted(self) -> bool:
        """Check if Pokemon is fainted"""
        return self.current_hp <= 0


class Trainer:
    """Represents a trainer profile"""
    
    def __init__(self, data: Dict):
        """Initialize from database row"""
        self.discord_user_id = data['discord_user_id']
        self.trainer_name = data['trainer_name']
        self.avatar_url = data.get('avatar_url')
        
        self.age = data.get('age')
        self.home_region = data.get('home_region')
        self.bio = data.get('bio')

        # Location
        self.current_location_id = data.get('current_location_id', 'lights_district_central_plaza')
        
        # Economy
        self.money = data.get('money', 5000)
        
        # Social Stats
        self.boon_stat = data.get('boon_stat')
        self.bane_stat = data.get('bane_stat')
        self.social_stats: Dict[str, Dict[str, int]] = {}

        legacy_rank_map = {
            'heart': data.get('instinct_rank'),
            'insight': data.get('knowledge_rank'),
            'charisma': data.get('charisma_rank'),
            'fortitude': data.get('vigor_rank'),
            'will': data.get('will_rank'),
        }

        for stat_key in SOCIAL_STAT_ORDER:
            cap = get_stat_cap(stat_key, self.boon_stat, self.bane_stat)
            rank = data.get(f'{stat_key}_rank')
            if rank is None:
                rank = legacy_rank_map.get(stat_key, 1)
            points = data.get(f'{stat_key}_points')
            if points is None:
                points = rank_to_points(rank or 0, cap)

            rank = rank or 0
            points = int(points)
            setattr(self, f'{stat_key}_rank', rank)
            setattr(self, f'{stat_key}_points', points)

            self.social_stats[stat_key] = {
                'rank': rank,
                'points': points,
                'cap': cap,
            }

        # Backwards-compatibility attribute aliases
        self.charisma_rank = self.social_stats['charisma']['rank']
        self.knowledge_rank = self.social_stats['insight']['rank']
        self.instinct_rank = self.social_stats['heart']['rank']
        self.vigor_rank = self.social_stats['fortitude']['rank']
        self.will_rank = self.social_stats['will']['rank']

        # Stamina
        self.stamina_max = data.get('stamina_max')
        if self.stamina_max is None:
            self.stamina_max = calculate_max_stamina(self.fortitude_rank)
        self.stamina_current = data.get('stamina_current', self.stamina_max)
        if self.stamina_current is None:
            self.stamina_current = self.stamina_max

        # Ranked Ladder
        self.rank_tier_name = data.get('rank_tier_name', 'Qualifier')
        self.rank_tier_number = data.get('rank_tier_number')
        self.ladder_points = data.get('ladder_points', 0)
        self.has_promotion_ticket = bool(data.get('has_promotion_ticket', 0))
        self.ticket_tier = data.get('ticket_tier')
        self.rank_pending_tier = data.get('rank_pending_tier')
        self.has_omni_ring = bool(data.get('has_omni_ring', 0))
        gimmicks_raw = data.get('omni_ring_gimmicks')
        if isinstance(gimmicks_raw, str):
            try:
                self.omni_ring_gimmicks = json.loads(gimmicks_raw) or []
            except json.JSONDecodeError:
                self.omni_ring_gimmicks = []
        elif isinstance(gimmicks_raw, list):
            self.omni_ring_gimmicks = gimmicks_raw
        else:
            self.omni_ring_gimmicks = []

        # Following Pokemon
        self.following_pokemon_id = data.get('following_pokemon_id')

        # Partner Pokemon
        self.partner_pokemon_id = data.get('partner_pokemon_id')

        # Battle Themes
        self.battle_theme_url = data.get('battle_theme_url')
        self.victory_theme_url = data.get('victory_theme_url')

    def get_social_stats_dict(self) -> Dict[str, Dict[str, int]]:
        """Return social stats with rank/point data keyed by display name."""

        stats: Dict[str, Dict[str, int]] = {}
        for stat_key in SOCIAL_STAT_ORDER:
            definition = SOCIAL_STAT_DEFINITIONS[stat_key]
            stat_state = self.social_stats.get(stat_key, {'rank': 0, 'points': 0, 'cap': self.get_stat_cap(stat_key)})
            stats[definition.display_name] = {
                'key': stat_key,
                'rank': stat_state['rank'],
                'points': stat_state['points'],
                'cap': stat_state['cap'],
                'description': definition.description,
            }
        return stats

    def get_stat_rank(self, stat_key: str) -> int:
        """Convenience accessor for a specific stat rank."""
        return getattr(self, f'{stat_key}_rank', 0)

    def get_stat_cap(self, stat_key: str) -> int:
        return get_stat_cap(stat_key, self.boon_stat, self.bane_stat)

    def get_stat_info(self, stat_key: str) -> Dict[str, int]:
        """Return rank/points/cap metadata for a given stat key."""
        return self.social_stats.get(stat_key, {
            'rank': 0,
            'points': 0,
            'cap': self.get_stat_cap(stat_key),
        })

    def get_stamina_display(self, segments: int = 10) -> str:
        """Return a text-based stamina bar."""
        if self.stamina_max <= 0:
            return "Stamina not set"

        current = max(0, min(self.stamina_current, self.stamina_max))
        filled_segments = int(round((current / self.stamina_max) * segments))
        filled_segments = max(0, min(segments, filled_segments))
        bar = '█' * filled_segments + '░' * (segments - filled_segments)
        return f"{bar} ({current}/{self.stamina_max})"
    

    def get_rank_display(self) -> str:
        """Get formatted rank string, normalizing legacy 'Rookie' to 'Qualifiers'."""
        base_name = self.rank_tier_name or "Qualifiers"
        # Normalize any legacy/default 'Rookie' label into the proper first rank
        if str(base_name).strip().lower() == "rookie":
            base_name = "Qualifiers"
        if str(base_name).strip().lower().startswith("qualifier"):
            return "Qualifier"

        if self.rank_tier_number:
            return f"{base_name} {self.rank_tier_number}"
        return base_name
