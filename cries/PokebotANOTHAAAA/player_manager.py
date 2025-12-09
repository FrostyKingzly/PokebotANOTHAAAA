"""
Player Manager - Handles trainer profile operations
"""

import json
import math
import re
import time
from pathlib import Path
from typing import Optional, Dict, List
from database import PlayerDatabase, SpeciesDatabase, MovesDatabase
from exp_system import ExpSystem
from models import Trainer, Pokemon
from social_stats import calculate_max_stamina


class PlayerManager:
    """Manages player/trainer data"""

    STAMINA_FULL_RECOVERY_SECONDS = 7 * 24 * 60 * 60  # One week for full recovery

    LEVEL_CAP_BY_TIER = {
        1: 20,   # Qualifier
        2: 30,   # Challenger 1
        3: 40,   # Challenger 2
        4: 50,   # Great 1
        5: 60,   # Great 2
        6: 70,   # Ultra 1
        7: 80,   # Ultra 2
        8: 100,  # Master
    }

    def __init__(self, db_path: str = "data/players.db", species_db=None, items_db=None):
        self.db = PlayerDatabase(db_path)
        self.species_db = species_db
        self.items_db = items_db
        self.inventory_cache_path = Path("config/player_inventory.json")
        self._inventory_cache = self._load_inventory_cache()

    # ------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------
    def _load_inventory_cache(self) -> Dict[str, Dict[str, int]]:
        if self.inventory_cache_path.exists():
            try:
                with open(self.inventory_cache_path, "r", encoding="utf-8") as cache_file:
                    data = json.load(cache_file)
                    if isinstance(data, dict):
                        return data
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_inventory_cache(self):
        self.inventory_cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.inventory_cache_path, "w", encoding="utf-8") as cache_file:
            json.dump(self._inventory_cache, cache_file, indent=2)

    def _set_cached_quantity(self, discord_user_id: int, item_id: str, quantity: int):
        user_key = str(discord_user_id)
        if quantity <= 0:
            if user_key in self._inventory_cache and item_id in self._inventory_cache[user_key]:
                self._inventory_cache[user_key].pop(item_id, None)
                if not self._inventory_cache[user_key]:
                    self._inventory_cache.pop(user_key, None)
        else:
            self._inventory_cache.setdefault(user_key, {})[item_id] = quantity
        self._save_inventory_cache()

    def _bump_cached_quantity(self, discord_user_id: int, item_id: str, delta: int):
        user_key = str(discord_user_id)
        current = self._inventory_cache.get(user_key, {}).get(item_id, 0)
        self._set_cached_quantity(discord_user_id, item_id, current + delta)

    def _rows_to_inventory(self, rows: List[Dict]) -> List[Dict]:
        inventory = []
        for row in rows:
            if row.get("quantity", 0) > 0:
                inventory.append(row)
                self._set_cached_quantity(row["discord_user_id"], row["item_id"], row["quantity"])
        return inventory

    def _apply_passive_stamina(self, trainer_data: Dict) -> Dict:
        if not trainer_data:
            return trainer_data

        data = dict(trainer_data)
        discord_user_id = data.get("discord_user_id")
        now = int(time.time())

        stamina_max = calculate_max_stamina(data.get("fortitude_rank", 0) or 0)
        current_max = int(data.get("stamina_max") or stamina_max)
        current = int(data.get("stamina_current") or stamina_max)

        update_fields: Dict[str, int] = {}

        # Keep stamina_max in sync with Fortitude changes
        if current_max != stamina_max:
            update_fields["stamina_max"] = stamina_max
            current = min(current, stamina_max)
        else:
            stamina_max = current_max

        last_update_raw = data.get("last_stamina_update")
        if last_update_raw is None:
            last_update = now
            update_fields["last_stamina_update"] = last_update
        else:
            try:
                last_update = int(last_update_raw)
            except (TypeError, ValueError):
                last_update = now
                update_fields["last_stamina_update"] = last_update

        elapsed = max(0, now - last_update)
        if stamina_max > 0 and elapsed > 0 and current < stamina_max:
            regen_amount = int(
                math.floor((stamina_max * elapsed) / self.STAMINA_FULL_RECOVERY_SECONDS)
            )
            if regen_amount > 0:
                current = min(stamina_max, current + regen_amount)
                last_update = now
                update_fields["stamina_current"] = current
                update_fields["last_stamina_update"] = last_update

        if current > stamina_max:
            current = stamina_max
            update_fields["stamina_current"] = current

        data["stamina_max"] = stamina_max
        data["stamina_current"] = current
        data["last_stamina_update"] = update_fields.get("last_stamina_update", last_update)

        if update_fields and discord_user_id is not None:
            self.db.update_trainer(discord_user_id, **update_fields)
        return data
    
    # ============================================================
    # TRAINER OPERATIONS
    # ============================================================
    
    def get_player(self, discord_user_id: int) -> Optional[Trainer]:
        """Get a trainer profile"""
        data = self.db.get_trainer(discord_user_id)
        if data:
            refreshed = self._apply_passive_stamina(data)
            return Trainer(refreshed)
        return None

    def get_partner_pokemon(self, discord_user_id: int) -> Optional[Dict]:
        """Return the trainer's designated partner Pokemon, if any."""
        trainer = self.get_player(discord_user_id)
        if not trainer or not getattr(trainer, 'partner_pokemon_id', None):
            return None
        return self.get_pokemon(trainer.partner_pokemon_id)

    def set_partner_pokemon(self, discord_user_id: int, pokemon_id: str) -> tuple[bool, str]:
        """Lock in a forever partner for the trainer.

        Returns a tuple of (success, message).
        """

        trainer = self.get_player(discord_user_id)
        if not trainer:
            return False, "[X] You need a trainer profile first."

        current_partner_id = getattr(trainer, 'partner_pokemon_id', None)
        if current_partner_id and current_partner_id != pokemon_id:
            return False, "[X] You've already chosen a partner Pokemon."

        pokemon = self.get_pokemon(pokemon_id)
        if not pokemon or pokemon.get('owner_discord_id') != discord_user_id:
            return False, "[X] That Pokemon doesn't belong to you."

        if pokemon.get('is_partner'):
            # Already set as partner, just ensure trainer record is synced
            self.db.set_partner_pokemon(discord_user_id, pokemon_id)
            return True, "✅ This Pokemon is already your partner."

        self.db.set_partner_pokemon(discord_user_id, pokemon_id)
        return True, "✅ Partner set!"
    
    def player_exists(self, discord_user_id: int) -> bool:
        """Check if player has registered"""
        trainer = self.db.get_trainer(discord_user_id)
        return trainer is not None

    def create_player(
        self,
        discord_user_id: int,
        trainer_name: str,
        avatar_url: str = None,
        boon_stat: str = None,
        bane_stat: str = None,
        pronouns: str = None,
        age: str = None,
        birthday: str = None,
        home_region: str = None,
        bio: str = None,
    ) -> bool:
        """
        Create a new trainer profile

        Args:
            discord_user_id: Discord user ID
            trainer_name: Chosen trainer name
            avatar_url: Avatar image URL
            boon_stat: Social stat to boost (Rank 2)
            bane_stat: Social stat to lower (Rank 0)
            pronouns: Trainer pronouns
            age: Trainer age
            birthday: Trainer birthday (MM/DD format)
            home_region: Home region
            bio: Short bio

        Returns:
            True if created successfully, False if already exists
        """
        return self.db.create_trainer(
            discord_user_id=discord_user_id,
            trainer_name=trainer_name,
            avatar_url=avatar_url,
            boon_stat=boon_stat,
            bane_stat=bane_stat,
            pronouns=pronouns,
            age=age,
            birthday=birthday,
            home_region=home_region,
            bio=bio,
        )
    
    def update_player(self, discord_user_id: int, **kwargs):
        """Update trainer fields"""
        self.db.update_trainer(discord_user_id, **kwargs)

    def get_level_cap_for_trainer(self, trainer: Trainer) -> int:
        """Return the maximum level allowed for a trainer's Pokémon based on rank."""

        tier = getattr(trainer, "rank_tier_number", None) or 1
        return self.LEVEL_CAP_BY_TIER.get(tier, 20)

    def is_on_battle_cooldown(self, discord_user_id: int, target_type: str, target_identifier: str) -> tuple[bool, Optional[int]]:
        """Check if a trainer is on cooldown for a specific opponent."""

        now = int(time.time())
        self.db.clear_expired_cooldowns(now)
        expires_at = self.db.get_battle_cooldown(discord_user_id, target_type, target_identifier)
        if expires_at is None:
            return False, None
        if expires_at < 0:
            return True, None
        if expires_at <= now:
            return False, None
        return True, expires_at - now

    def set_battle_cooldown(
        self,
        discord_user_id: int,
        target_type: str,
        target_identifier: str,
        duration_seconds: Optional[int],
    ):
        """Persist a battle cooldown for a trainer."""

        expires_at = -1
        if duration_seconds:
            expires_at = int(time.time()) + int(duration_seconds)
        self.db.set_battle_cooldown(discord_user_id, target_type, target_identifier, expires_at)

    def consume_stamina(self, discord_user_id: int, amount: int) -> tuple[bool, int]:
        """Consume a specific amount of stamina for a trainer."""
        if amount <= 0:
            return False, 0

        trainer_data = self.db.get_trainer(discord_user_id)
        if not trainer_data:
            return False, 0

        trainer_data = self._apply_passive_stamina(trainer_data)
        current = int(trainer_data.get("stamina_current", 0))

        if current < amount:
            return False, current

        new_current = max(0, current - amount)
        self.db.update_trainer(
            discord_user_id,
            stamina_current=new_current,
            last_stamina_update=int(time.time()),
        )
        return True, new_current

    def restore_stamina(self, discord_user_id: int, amount: int) -> tuple[bool, int]:
        """Restore stamina, clamped to the trainer's maximum."""
        if amount <= 0:
            return False, 0

        trainer_data = self.db.get_trainer(discord_user_id)
        if not trainer_data:
            return False, 0

        trainer_data = self._apply_passive_stamina(trainer_data)
        stamina_max = int(trainer_data.get("stamina_max", 0))
        current = int(trainer_data.get("stamina_current", 0))

        if stamina_max <= 0:
            return False, current

        new_current = min(stamina_max, current + amount)
        self.db.update_trainer(
            discord_user_id,
            stamina_current=new_current,
            last_stamina_update=int(time.time()),
        )
        return True, new_current
        
    def update_location(self, discord_id: int, location_id: str) -> bool:
        """
        Update player's current location
        
        Args:
            discord_id: Discord user ID
            location_id: New location identifier
            
        Returns:
            True if successful, False if player not found
        """
        trainer = self.db.get_trainer(discord_id)
        if not trainer:
            return False

        self.db.update_trainer(discord_id, current_location_id=location_id)
        return True

    def delete_player(self, discord_user_id: int) -> bool:
        """Delete a trainer profile and all associated data."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM pokemon_instances WHERE owner_discord_id = ?",
                (discord_user_id,)
            )
            cursor.execute(
                "DELETE FROM inventory WHERE discord_user_id = ?",
                (discord_user_id,)
            )
            cursor.execute(
                "DELETE FROM pokedex WHERE discord_user_id = ?",
                (discord_user_id,)
            )
            cursor.execute(
                "DELETE FROM trainers WHERE discord_user_id = ?",
                (discord_user_id,)
            )
            deleted = cursor.rowcount
            conn.commit()
        finally:
            conn.close()

        user_key = str(discord_user_id)
        if user_key in self._inventory_cache:
            self._inventory_cache.pop(user_key, None)
            self._save_inventory_cache()

        return deleted > 0
    
    # ============================================================
    # POKEMON OPERATIONS
    # ============================================================
    
    def add_pokemon_to_party(self, pokemon: Pokemon, position: int = None) -> str:
        """
        Add a Pokemon to trainer's party
        
        Args:
            pokemon: Pokemon object to add
            position: Party slot (0-5), auto if None
        
        Returns:
            Pokemon ID
        """
        # Get current party
        party = self.get_party(pokemon.owner_discord_id)
        
        if len(party) >= 6:
            # Party full, add to box instead
            return self.add_pokemon_to_box(pokemon)
        
        # Set party position
        if position is None:
            position = len(party)
        
        pokemon.in_party = True
        pokemon.party_position = position
        
        return self.db.add_pokemon(pokemon.to_dict())
    
    def add_pokemon_to_box(self, pokemon: Pokemon) -> str:
        """Add a Pokemon to storage box"""
        boxes = self.get_boxes(pokemon.owner_discord_id)
        
        pokemon.in_party = False
        pokemon.box_position = len(boxes)
        
        return self.db.add_pokemon(pokemon.to_dict())
    
    def get_pokemon(self, pokemon_id: str) -> Optional[Dict]:
        """Get a specific Pokemon by ID"""
        return self.db.get_pokemon(pokemon_id)

    def update_pokemon(self, discord_user_id: int, pokemon: Dict) -> bool:
        """Persist Pokemon changes after validating ownership."""
        if not pokemon:
            return False

        pokemon_id = pokemon.get('pokemon_id')
        if not pokemon_id:
            return False

        owner_id = pokemon.get('owner_discord_id')
        if owner_id is not None and owner_id != discord_user_id:
            return False

        allowed_fields = {
            'owner_discord_id',
            'species_dex_number',
            'form',
            'nickname',
            'level',
            'exp',
            'gender',
            'nature',
            'ability',
            'held_item',
            'pokeball',
            'current_hp',
            'max_hp',
            'status_condition',
            'iv_hp',
            'iv_attack',
            'iv_defense',
            'iv_sp_attack',
            'iv_sp_defense',
            'iv_speed',
            'ev_hp',
            'ev_attack',
            'ev_defense',
            'ev_sp_attack',
            'ev_sp_defense',
            'ev_speed',
            'moves',
            'friendship',
            'bond_level',
            'in_party',
            'party_position',
            'box_position',
            'is_shiny',
            'can_mega_evolve',
            'tera_type',
            'is_partner',
        }

        updates: Dict = {}
        for key in allowed_fields:
            if key in pokemon:
                updates[key] = pokemon[key]

        # Backwards-compatible mapping for status field used by some callers
        if 'status' in pokemon and 'status_condition' not in updates:
            updates['status_condition'] = pokemon['status']

        moves = updates.get('moves')
        if isinstance(moves, list):
            updates['moves'] = json.dumps(moves)

        if not updates:
            return False

        return self.db.update_pokemon(pokemon_id, updates)
    
    def get_party(self, discord_user_id: int) -> List[Dict]:
        """Get trainer's party"""
        return self.db.get_trainer_party(discord_user_id)

    def get_players_in_location(self, location_id: str, exclude_user_id: Optional[int] = None) -> List[Trainer]:
        """Return Trainer objects for everyone currently in the given location."""
        if not location_id:
            return []

        rows = self.db.get_players_in_location(location_id)
        trainers: List[Trainer] = []
        for row in rows:
            discord_id = row.get('discord_user_id')
            if exclude_user_id is not None and discord_id == exclude_user_id:
                continue
            trainers.append(Trainer(row))
        return trainers

    def get_boxes(self, discord_user_id: int) -> List[Dict]:
        """Get trainer's boxed Pokemon"""
        return self.db.get_trainer_boxes(discord_user_id)
    
    def get_all_pokemon(self, discord_user_id: int) -> List[Dict]:
        """Get all Pokemon owned by trainer"""
        return self.get_party(discord_user_id) + self.get_boxes(discord_user_id)

    def heal_party(self, discord_user_id: int) -> int:
        """Fully restore every Pokémon currently in the trainer's party."""
        return self.db.heal_party(discord_user_id)
    
    # ============================================================
    # POKEDEX OPERATIONS
    # ============================================================
    
    def add_pokedex_seen(self, discord_user_id: int, species_dex_number: int):
        """Mark a species as seen in Pokedex"""
        self.db.add_pokedex_entry(discord_user_id, species_dex_number)
    
    def get_pokedex(self, discord_user_id: int) -> List[int]:
        """Get list of seen species"""
        return self.db.get_pokedex(discord_user_id)
    
    def has_seen_species(self, discord_user_id: int, species_dex_number: int) -> bool:
        """Check if trainer has seen this species"""
        seen = self.get_pokedex(discord_user_id)
        return species_dex_number in seen
    
    # ============================================================
    # INVENTORY OPERATIONS
    # ============================================================
    
    def get_inventory(self, discord_user_id: int) -> List[Dict]:
        """Get trainer's inventory"""
        rows = self.db.get_inventory(discord_user_id)
        inventory = self._rows_to_inventory(rows)
        if inventory:
            return inventory

        cached_items = self._inventory_cache.get(str(discord_user_id), {})
        return [
            {"discord_user_id": discord_user_id, "item_id": item_id, "quantity": qty}
            for item_id, qty in cached_items.items()
            if qty > 0
        ]
    
    def add_item(self, discord_user_id: int, item_id: str, quantity: int = 1):
        """Add item(s) to trainer's inventory"""
        self.db.add_item(discord_user_id, item_id, quantity)
        self._bump_cached_quantity(discord_user_id, item_id, quantity)

    def remove_item(self, discord_user_id: int, item_id: str, quantity: int = 1) -> bool:
        """Remove item(s) from trainer's inventory. Returns True if successful."""
        success = self.db.remove_item(discord_user_id, item_id, quantity)
        if success:
            self._bump_cached_quantity(discord_user_id, item_id, -quantity)
        return success
    
    def get_item_quantity(self, discord_user_id: int, item_id: str) -> int:
        """Get quantity of a specific item"""
        return self.db.get_item_quantity(discord_user_id, item_id)
    
    # ============================================================
    # POKEMON MANAGEMENT OPERATIONS
    # ============================================================
    
    def deposit_pokemon(self, discord_user_id: int, pokemon_id: str) -> tuple[bool, str]:
        """
        Move Pokemon from party to box
        Returns: (success, message)
        """
        pokemon = self.get_pokemon(pokemon_id)
        
        if not pokemon:
            return False, "[X] Pokemon not found!"
        
        if pokemon['owner_discord_id'] != discord_user_id:
            return False, "[X] This isn't your Pokemon!"
        
        if not pokemon.get('in_party'):
            return False, "[X] This Pokemon is already in a box!"
        
        party = self.get_party(discord_user_id)
        
        if len(party) <= 1:
            return False, "[X] You must have at least one Pokemon in your party!"
        
        # Get current box count for position
        boxes = self.get_boxes(discord_user_id)
        box_position = len(boxes)
        
        # Update Pokemon
        self.db.update_pokemon(pokemon_id, {
            'in_party': 0,
            'party_position': None,
            'box_position': box_position
        })
        
        # Reorder party positions
        for i, p in enumerate(party):
            if p['pokemon_id'] != pokemon_id:
                self.db.update_pokemon(p['pokemon_id'], {'party_position': i})
        
        species_name = pokemon.get('nickname', '')
        if not species_name and self.species_db:
            # Get species name from database
            species_data = self.species_db.get_species(pokemon['species_dex_number'])
            species_name = species_data['name'] if species_data else "Pokemon"
        elif not species_name:
            species_name = "Pokemon"
        
        return True, f"[OK] **{species_name}** was moved to the box!"
    
    def withdraw_pokemon(self, discord_user_id: int, pokemon_id: str) -> tuple[bool, str]:
        """
        Move Pokemon from box to party
        Returns: (success, message)
        """
        pokemon = self.get_pokemon(pokemon_id)
        
        if not pokemon:
            return False, "[X] Pokemon not found!"
        
        if pokemon['owner_discord_id'] != discord_user_id:
            return False, "[X] This isn't your Pokemon!"
        
        if pokemon.get('in_party'):
            return False, "[X] This Pokemon is already in your party!"
        
        party = self.get_party(discord_user_id)
        
        if len(party) >= 6:
            return False, "[X] Your party is full! Deposit a Pokemon first."
        
        party_position = len(party)
        
        # Update Pokemon
        self.db.update_pokemon(pokemon_id, {
            'in_party': 1,
            'party_position': party_position,
            'box_position': None
        })
        
        # Reorder box positions
        boxes = self.get_boxes(discord_user_id)
        for i, p in enumerate(boxes):
            self.db.update_pokemon(p['pokemon_id'], {'box_position': i})
        
        species_name = pokemon.get('nickname', '')
        if not species_name and self.species_db:
            species_data = self.species_db.get_species(pokemon['species_dex_number'])
            species_name = species_data['name'] if species_data else "Pokemon"
        elif not species_name:
            species_name = "Pokemon"
        
        return True, f"[OK] **{species_name}** was added to your party!"
    
    def release_pokemon(self, discord_user_id: int, pokemon_id: str) -> tuple[bool, str]:
        """
        Release a Pokemon permanently
        Returns: (success, message)
        """
        pokemon = self.get_pokemon(pokemon_id)
        
        if not pokemon:
            return False, "[X] Pokemon not found!"
        
        if pokemon['owner_discord_id'] != discord_user_id:
            return False, "[X] This isn't your Pokemon!"
        
        # Check if this is the last Pokemon in party
        if pokemon.get('in_party'):
            party = self.get_party(discord_user_id)
            if len(party) <= 1:
                return False, "[X] You cannot release your last Pokemon!"
        
        species_name = pokemon.get('nickname', '')
        if not species_name and self.species_db:
            species_data = self.species_db.get_species(pokemon['species_dex_number'])
            species_name = species_data['name'] if species_data else "Pokemon"
        elif not species_name:
            species_name = "Pokemon"
        
        # Delete Pokemon
        self.db.delete_pokemon(pokemon_id)
        
        # Reorder positions
        if pokemon.get('in_party'):
            party = self.get_party(discord_user_id)
            for i, p in enumerate(party):
                self.db.update_pokemon(p['pokemon_id'], {'party_position': i})
        else:
            boxes = self.get_boxes(discord_user_id)
            for i, p in enumerate(boxes):
                self.db.update_pokemon(p['pokemon_id'], {'box_position': i})
        
        return True, f"[OK] **{species_name}** was released. Farewell!"
    
    def set_nickname(self, discord_user_id: int, pokemon_id: str, nickname: str) -> tuple[bool, str]:
        """
        Set Pokemon nickname
        Returns: (success, message)
        """
        pokemon = self.get_pokemon(pokemon_id)
        
        if not pokemon:
            return False, "[X] Pokemon not found!"
        
        if pokemon['owner_discord_id'] != discord_user_id:
            return False, "[X] This isn't your Pokemon!"
        
        self.db.update_pokemon(pokemon_id, {'nickname': nickname})
        
        if nickname:
            return True, f"[OK] Nickname changed to **{nickname}**!"
        else:
            if self.species_db:
                species_data = self.species_db.get_species(pokemon['species_dex_number'])
                species_name = species_data['name'] if species_data else "Pokemon"
            else:
                species_name = "Pokemon"
            return True, f"[OK] Nickname reset to **{species_name}**!"
    
    def give_item(self, discord_user_id: int, pokemon_id: str, item_id: str) -> tuple[bool, str]:
        """
        Give held item to Pokemon
        Returns: (success, message)
        """
        pokemon = self.get_pokemon(pokemon_id)
        
        if not pokemon:
            return False, "[X] Pokemon not found!"
        
        if pokemon['owner_discord_id'] != discord_user_id:
            return False, "[X] This isn't your Pokemon!"
        
        # Check if player has the item
        if self.get_item_quantity(discord_user_id, item_id) <= 0:
            return False, "[X] You don't have this item!"
        
        # Check if Pokemon is already holding an item
        if pokemon.get('held_item'):
            return False, "[X] This Pokemon is already holding an item! Take it first."
        
        # Give item to Pokemon and remove from inventory
        self.db.update_pokemon(pokemon_id, {'held_item': item_id})
        self.remove_item(discord_user_id, item_id, 1)
        
        if self.items_db:
            item_data = self.items_db.get_item(item_id)
            item_name = item_data['name'] if item_data else item_id
        else:
            item_name = item_id
        
        return True, f"[OK] Gave **{item_name}** to Pokemon!"
    
    def take_item(self, discord_user_id: int, pokemon_id: str) -> tuple[bool, str]:
        """
        Take held item from Pokemon
        Returns: (success, message)
        """
        pokemon = self.get_pokemon(pokemon_id)
        
        if not pokemon:
            return False, "[X] Pokemon not found!"
        
        if pokemon['owner_discord_id'] != discord_user_id:
            return False, "[X] This isn't your Pokemon!"
        
        if not pokemon.get('held_item'):
            return False, "[X] This Pokemon isn't holding an item!"
        
        item_id = pokemon['held_item']
        
        # Remove item from Pokemon and add to inventory
        self.db.update_pokemon(pokemon_id, {'held_item': None})
        self.add_item(discord_user_id, item_id, 1)
        
        if self.items_db:
            item_data = self.items_db.get_item(item_id)
            item_name = item_data['name'] if item_data else item_id
        else:
            item_name = item_id
        
        return True, f"[OK] Took **{item_name}** from Pokemon!"
    
    def swap_party_positions(self, discord_user_id: int, pokemon_id_1: str, pokemon_id_2: str) -> tuple[bool, str]:
        """
        Swap positions of two Pokemon in party
        Returns: (success, message)
        """
        pokemon1 = self.get_pokemon(pokemon_id_1)
        pokemon2 = self.get_pokemon(pokemon_id_2)
        
        if not pokemon1 or not pokemon2:
            return False, "[X] One or both Pokemon not found!"
        
        if pokemon1['owner_discord_id'] != discord_user_id or pokemon2['owner_discord_id'] != discord_user_id:
            return False, "[X] These aren't your Pokemon!"
        
        if not pokemon1.get('in_party') or not pokemon2.get('in_party'):
            return False, "[X] Both Pokemon must be in your party!"
        
        # Swap positions
        pos1 = pokemon1['party_position']
        pos2 = pokemon2['party_position']
        
        self.db.update_pokemon(pokemon_id_1, {'party_position': pos2})
        self.db.update_pokemon(pokemon_id_2, {'party_position': pos1})
        
        return True, "[OK] Pokemon positions swapped!"

    def reorder_party(self, discord_user_id: int, ordered_pokemon_ids: list[str]) -> tuple[bool, str]:
        """Set an explicit order for the trainer's party.

        ordered_pokemon_ids should contain each of the current party's Pokémon IDs exactly once.
        Positions will be assigned 0..N-1 in the order provided.
        """
        # Load current party to validate IDs and ownership
        party = self.get_party(discord_user_id)
        if not party:
            return False, "[X] You don't have any Pokémon in your party!"

        current_ids = {str(p['pokemon_id']) for p in party}
        provided_ids = [str(pid) for pid in ordered_pokemon_ids]

        if len(provided_ids) != len(current_ids):
            return False, "[X] Please select every Pokémon in your party exactly once."

        if set(provided_ids) != current_ids:
            return False, "[X] One or more selected Pokémon don't match your current party."

        # Apply new positions
        for idx, pid in enumerate(provided_ids):
            self.db.update_pokemon(pid, {'party_position': idx})

        return True, "[OK] Party order updated!"


    # ============================================================
    # MOVE MANAGEMENT OPERATIONS
    # ============================================================

    def sort_pokemon_moves(self, pokemon_id: str, key: str = "name", descending: bool = False) -> bool:
        """Sort a Pokemon's moves in the database.

        This only changes move order; it does not add or remove moves.
        """
        pokemon = self.get_pokemon(pokemon_id)
        if not pokemon:
            return False

        moves = pokemon.get('moves') or []
        if not moves:
            return False

        moves_db = MovesDatabase('data/moves.json')

        def sort_key(move_obj: Dict):
            move_id = move_obj.get('move_id')
            move_data = moves_db.get_move(move_id) or {}
            k = (key or "name").lower()

            if k == "power":
                return move_data.get('power') or 0
            if k == "accuracy":
                acc = move_data.get('accuracy')
                if isinstance(acc, (int, float)):
                    return acc
                # Treat non-numeric accuracy (e.g., always-hit moves) as slightly better than 100
                return 101
            if k == "type":
                return (move_data.get('type') or "").lower()
            if k == "category":
                return (move_data.get('category') or "").lower()
            # Default: name
            return (move_data.get('name') or "").lower()

        moves_sorted = sorted(moves, key=sort_key, reverse=descending)
        # Persist back to DB (moves column is JSON text in the database)
        self.db.update_pokemon(pokemon_id, {'moves': json.dumps(moves_sorted)})
        return True

    def get_available_moves_for_pokemon(self, pokemon_id: str) -> Dict[str, Dict]:
        """Return all moves this Pokemon could reasonably learn at its current level.

        Includes:
          - All level-up moves up to the Pokemon's current level
          - All TM moves from its learnset

        Returns a mapping of move_id -> move_data.
        """
        pokemon = self.get_pokemon(pokemon_id)
        if not pokemon:
            return {}

        # Get species data
        species_db = self.species_db or SpeciesDatabase('data/pokemon_species.json')
        species = species_db.get_species(pokemon['species_dex_number'])
        if not species:
            return {}

        species_name = species.get('name')
        if not species_name:
            return {}

        from learnset_database import LearnsetDatabase  # Local import to avoid circulars
        learnset_db = LearnsetDatabase('data/learnsets.json')
        learnset = learnset_db.get_learnset(species_name)
        if not learnset:
            return {}

        level = pokemon.get('level', 1)
        level_up_ids: List[str] = []
        current_move_ids: List[str] = []

        for m in pokemon.get('moves', []):
            mid = str(m.get('move_id', '')).lower()
            if mid:
                current_move_ids.append(mid)

        # Learnset format: { "level_up_moves": [ {"level": int, "move_id": str, "gen": int}, ... ] }
        for move_entry in learnset.get('level_up_moves', []):
            try:
                move_level = int(move_entry.get('level', 1))
            except (TypeError, ValueError):
                continue
            if move_level <= level:
                move_id = str(move_entry.get('move_id', '')).lower()
                if move_id:
                    level_up_ids.append(move_id)

        # Only expose TM moves that this Pokémon has actually learned via TM usage.
        # We do this by intersecting its current move list with the species' TM list.
        collapse = lambda mid: re.sub(r'[\s_-]+', '', str(mid).lower())

        all_tm_ids = {collapse(m) for m in learnset.get('tm_moves', [])}
        learned_tm_ids: List[str] = []
        for m in pokemon.get('moves', []):
            raw_mid = str(m.get('move_id', '')).lower()
            if raw_mid:
                collapsed_mid = collapse(raw_mid)
                if collapsed_mid in all_tm_ids:
                    learned_tm_ids.append(raw_mid)

        tm_ids = learned_tm_ids

        # De-duplicate while preserving order (current moves first to avoid dropping them)
        move_ids: List[str] = []
        seen = set()

        for mid in current_move_ids + level_up_ids + tm_ids:
            normalized_mid = (mid or "").lower()
            if normalized_mid and normalized_mid not in seen:
                seen.add(normalized_mid)
                move_ids.append(mid)

        moves_db = MovesDatabase('data/moves.json')
        available: Dict[str, Dict] = {}
        for mid in move_ids:
            move_data = moves_db.get_move(mid)
            if move_data:
                canonical_id = move_data.get('id', mid.lower())
                if canonical_id not in available:
                    available[canonical_id] = move_data
        return available

    def level_up_pokemon(self, discord_user_id: int, pokemon_id: str, set_level: int | None = None) -> Optional[Dict]:
        """
        Simple level-up helper used by the item system (e.g. Rare Candy).
        Updates the Pokemon's level (and max HP if species data is available)
        and persists changes to the database.

        Returns a dict shaped roughly like LevelUpResult, or None on failure.
        """
        # Fetch Pokemon from DB
        pokemon = self.get_pokemon(pokemon_id)
        if not pokemon:
            return None

        # Ensure the Pokemon belongs to this trainer
        owner_id = pokemon.get("owner_discord_id")
        if owner_id is not None and owner_id != discord_user_id:
            return None

        old_level = int(pokemon.get("level", 1))
        # Cap between 1 and 100
        if set_level is None:
            new_level = min(old_level + 1, 100)
        else:
            new_level = max(1, min(int(set_level), 100))

        if new_level == old_level:
            # Nothing to do
            return None

        # Default to keeping existing max_hp/current_hp if we can't recalc
        old_max_hp = int(pokemon.get("max_hp", 10))
        new_max_hp = old_max_hp

        # If we have species data, rebuild a Pokemon model and recalc stats
        if self.species_db is not None:
            species_data = self.species_db.get_species(pokemon["species_dex_number"])
        else:
            species_data = None

        if species_data:
            # Reconstruct a Pokemon object with the new level for stat calculation
            from models import Pokemon as PokemonModel

            # IVs
            ivs = {
                "hp": pokemon.get("iv_hp", 31),
                "attack": pokemon.get("iv_attack", 31),
                "defense": pokemon.get("iv_defense", 31),
                "sp_attack": pokemon.get("iv_sp_attack", 31),
                "sp_defense": pokemon.get("iv_sp_defense", 31),
                "speed": pokemon.get("iv_speed", 31),
            }

            # Create model and plug in EVs
            p_model = PokemonModel(
                species_data=species_data,
                level=new_level,
                owner_discord_id=owner_id,
                nature=pokemon.get("nature"),
                ability=pokemon.get("ability"),
                moves=[m["move_id"] for m in pokemon.get("moves", [])] if isinstance(pokemon.get("moves"), list) else [],
                ivs=ivs,
                is_shiny=bool(pokemon.get("is_shiny", 0)),
            )

            p_model.evs = {
                "hp": pokemon.get("ev_hp", 0),
                "attack": pokemon.get("ev_attack", 0),
                "defense": pokemon.get("ev_defense", 0),
                "sp_attack": pokemon.get("ev_sp_attack", 0),
                "sp_defense": pokemon.get("ev_sp_defense", 0),
                "speed": pokemon.get("ev_speed", 0),
            }
            # Recalculate stats with EVs applied
            p_model._calculate_stats()

            new_max_hp = int(p_model.max_hp)

        # Simple rule: heal to full on level-up from items like Rare Candy
        new_current_hp = new_max_hp

        # Persist to database
        updates = {
            "level": new_level,
            "max_hp": new_max_hp,
            "current_hp": new_current_hp,
        }
        self.db.update_pokemon(pokemon_id, updates)

        # Shape result similar to LevelUpResult so callers can introspect if needed
        levelup_result = {
            "old_level": old_level,
            "new_level": new_level,
            "stat_gains": {},  # We don't currently calculate per-stat deltas here
            "new_moves_learned": [],
            "moves_available_to_learn": [],
        }
        return levelup_result

    def grant_experience(self, discord_user_id: int, pokemon_id: str, exp_amount: int) -> Optional[Dict]:
        """Grant flat EXP to a Pokemon and handle level-ups."""
        if exp_amount <= 0:
            return None

        pokemon = self.get_pokemon(pokemon_id)
        if not pokemon:
            return None

        if pokemon.get("owner_discord_id") != discord_user_id:
            return None

        species_db = self.species_db or SpeciesDatabase('data/pokemon_species.json')
        species_data = species_db.get_species(pokemon['species_dex_number']) if species_db else None
        growth_rate = species_data.get('growth_rate', 'medium_fast') if species_data else 'medium_fast'

        current_exp = int(pokemon.get('exp', 0))
        old_level = int(pokemon.get('level', 1))
        exp_amount = ExpSystem.apply_partner_bonus(exp_amount, pokemon)
        new_total_exp = max(0, current_exp + exp_amount)
        new_level = ExpSystem._calculate_level_from_exp(new_total_exp, growth_rate)

        level_up_data = None
        if new_level > old_level:
            level_up_data = self.level_up_pokemon(discord_user_id, pokemon_id, set_level=new_level)

        self.db.update_pokemon(
            pokemon_id,
            {
                'exp': new_total_exp,
                'level': new_level,
            }
        )

        return {
            'old_level': old_level,
            'new_level': new_level,
            'new_exp': new_total_exp,
            'level_up_data': level_up_data,
        }

    def equip_pokemon_moves(self, discord_user_id: int, pokemon_id: str, new_move_ids: List[str]) -> tuple[bool, str]:
        """Equip a new set of moves (1–4) for a Pokemon and persist to the DB.

        Returns:
            (success, message)
        """
        pokemon = self.get_pokemon(pokemon_id)
        if not pokemon:
            return False, "[X] Pokemon not found!"

        if pokemon.get('owner_discord_id') != discord_user_id:
            return False, "[X] This isn't your Pokemon!"

        if not new_move_ids:
            return False, "[X] You must select at least one move."

        # Clamp to four moves, like the main games
        new_move_ids = [str(mid).lower() for mid in new_move_ids][:4]

        moves_db = MovesDatabase('data/moves.json')
        move_objects: List[Dict] = []
        for move_id in new_move_ids:
            move_data = moves_db.get_move(move_id)
            if not move_data:
                continue
            move_objects.append({
                "move_id": move_id,
                "pp": move_data.get("pp", 5),
                "max_pp": move_data.get("pp", 5),
            })

        if not move_objects:
            return False, "[X] None of the selected moves are valid."

        # Persist the new moveset
        self.db.update_pokemon(pokemon_id, {"moves": json.dumps(move_objects)})

        # Build display name for feedback
        species_name = pokemon.get('nickname')
        if not species_name:
            species_db = self.species_db or SpeciesDatabase('data/pokemon_species.json')
            species_data = species_db.get_species(pokemon['species_dex_number'])
            species_name = species_data['name'] if species_data else "Pokemon"

        return True, f"[OK] Updated **{species_name}**'s moves!"