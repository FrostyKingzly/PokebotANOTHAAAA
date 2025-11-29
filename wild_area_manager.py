"""
Wild Area Manager - Handles wild areas, zones, parties, and stamina
"""

import json
import sqlite3
import uuid
from typing import Optional, Dict, List, Any
from pathlib import Path
from database import PlayerDatabase


class WildAreaManager:
    """Manages wild areas, zones, and player progression"""

    def __init__(self, db: PlayerDatabase):
        self.db = db

    # ============================================================
    # WILD AREA OPERATIONS
    # ============================================================

    def create_wild_area(self, area_id: str, name: str, description: str = None) -> bool:
        """Create a new wild area"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO wild_areas (area_id, name, description)
                VALUES (?, ?, ?)
            """, (area_id, name, description))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def get_wild_area(self, area_id: str) -> Optional[Dict]:
        """Get wild area by ID"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM wild_areas WHERE area_id = ?", (area_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def get_all_wild_areas(self) -> List[Dict]:
        """Get all wild areas"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM wild_areas")
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    # ============================================================
    # ZONE OPERATIONS
    # ============================================================

    def create_zone(self, zone_id: str, area_id: str, name: str,
                   description: str = None, has_pokemon_station: bool = False,
                   zone_travel_cost: int = 5, encounters: List[Dict] = None,
                   npc_trainers: List[Dict] = None) -> bool:
        """Create a new zone in a wild area"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO wild_area_zones (
                    zone_id, area_id, name, description, has_pokemon_station,
                    zone_travel_cost, encounters, npc_trainers
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                zone_id,
                area_id,
                name,
                description,
                1 if has_pokemon_station else 0,
                zone_travel_cost,
                json.dumps(encounters or []),
                json.dumps(npc_trainers or [])
            ))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def get_zone(self, zone_id: str) -> Optional[Dict]:
        """Get zone by ID"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM wild_area_zones WHERE zone_id = ?", (zone_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            zone = dict(row)
            zone['encounters'] = json.loads(zone['encounters']) if zone['encounters'] else []
            zone['npc_trainers'] = json.loads(zone['npc_trainers']) if zone['npc_trainers'] else []
            return zone
        return None

    def get_zones_in_area(self, area_id: str) -> List[Dict]:
        """Get all zones in a wild area"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM wild_area_zones WHERE area_id = ?", (area_id,))
        rows = cursor.fetchall()
        conn.close()

        zones = []
        for row in rows:
            zone = dict(row)
            zone['encounters'] = json.loads(zone['encounters']) if zone['encounters'] else []
            zone['npc_trainers'] = json.loads(zone['npc_trainers']) if zone['npc_trainers'] else []
            zones.append(zone)

        return zones

    def update_zone(self, zone_id: str, **kwargs) -> bool:
        """Update zone fields"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        # Handle JSON fields
        if 'encounters' in kwargs:
            kwargs['encounters'] = json.dumps(kwargs['encounters'])
        if 'npc_trainers' in kwargs:
            kwargs['npc_trainers'] = json.dumps(kwargs['npc_trainers'])

        fields = ', '.join([f"{key} = ?" for key in kwargs.keys()])
        values = list(kwargs.values()) + [zone_id]

        cursor.execute(f"""
            UPDATE wild_area_zones
            SET {fields}
            WHERE zone_id = ?
        """, values)

        conn.commit()
        conn.close()
        return True

    # ============================================================
    # PLAYER WILD AREA STATE
    # ============================================================

    def enter_wild_area(self, discord_user_id: int, area_id: str, starting_zone_id: str) -> bool:
        """Initialize player state when entering a wild area"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        # Get current player state
        cursor.execute("SELECT * FROM trainers WHERE discord_user_id = ?", (discord_user_id,))
        trainer = cursor.fetchone()

        if not trainer:
            conn.close()
            return False

        trainer = dict(trainer)

        # Get inventory snapshot
        cursor.execute("SELECT * FROM inventory WHERE discord_user_id = ?", (discord_user_id,))
        inventory_rows = cursor.fetchall()
        inventory_snapshot = {row['item_id']: row['quantity'] for row in inventory_rows}

        # Get Pokemon EXP snapshot
        cursor.execute("SELECT pokemon_id, exp FROM pokemon_instances WHERE owner_discord_id = ?", (discord_user_id,))
        pokemon_rows = cursor.fetchall()
        pokemon_exp_snapshot = {row['pokemon_id']: row['exp'] for row in pokemon_rows}

        # Create wild area state
        try:
            cursor.execute("""
                INSERT INTO trainer_wild_area_states (
                    discord_user_id, area_id, current_zone_id,
                    entry_stamina, current_stamina, snapshot_money,
                    snapshot_inventory, snapshot_pokemon_exp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                discord_user_id,
                area_id,
                starting_zone_id,
                trainer['stamina_current'],
                trainer['stamina_current'],
                trainer['money'],
                json.dumps(inventory_snapshot),
                json.dumps(pokemon_exp_snapshot)
            ))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Already in a wild area - update instead
            cursor.execute("""
                UPDATE trainer_wild_area_states
                SET area_id = ?, current_zone_id = ?, entry_stamina = ?,
                    current_stamina = ?, snapshot_money = ?,
                    snapshot_inventory = ?, snapshot_pokemon_exp = ?
                WHERE discord_user_id = ?
            """, (
                area_id,
                starting_zone_id,
                trainer['stamina_current'],
                trainer['stamina_current'],
                trainer['money'],
                json.dumps(inventory_snapshot),
                json.dumps(pokemon_exp_snapshot),
                discord_user_id
            ))
            conn.commit()
            return True
        finally:
            conn.close()

    def get_wild_area_state(self, discord_user_id: int) -> Optional[Dict]:
        """Get player's current wild area state"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM trainer_wild_area_states
            WHERE discord_user_id = ?
        """, (discord_user_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            state = dict(row)
            state['snapshot_inventory'] = json.loads(state['snapshot_inventory'])
            state['snapshot_pokemon_exp'] = json.loads(state['snapshot_pokemon_exp'])
            return state
        return None

    def is_in_wild_area(self, discord_user_id: int) -> bool:
        """Check if player is currently in a wild area"""
        return self.get_wild_area_state(discord_user_id) is not None

    def exit_wild_area(self, discord_user_id: int, success: bool = True) -> bool:
        """
        Exit wild area. If success=False (blacked out), revert items and exp.
        Caught Pokemon are always kept.
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        # Get wild area state
        cursor.execute("""
            SELECT * FROM trainer_wild_area_states
            WHERE discord_user_id = ?
        """, (discord_user_id,))

        state_row = cursor.fetchone()

        if not state_row:
            conn.close()
            return False

        state = dict(state_row)

        if not success:
            # Revert money and items
            snapshot_inventory = json.loads(state['snapshot_inventory'])
            snapshot_pokemon_exp = json.loads(state['snapshot_pokemon_exp'])

            # Revert money
            cursor.execute("""
                UPDATE trainers
                SET money = ?
                WHERE discord_user_id = ?
            """, (state['snapshot_money'], discord_user_id))

            # Revert inventory
            cursor.execute("DELETE FROM inventory WHERE discord_user_id = ?", (discord_user_id,))
            for item_id, quantity in snapshot_inventory.items():
                cursor.execute("""
                    INSERT INTO inventory (discord_user_id, item_id, quantity)
                    VALUES (?, ?, ?)
                """, (discord_user_id, item_id, quantity))

            # Revert Pokemon EXP (but keep caught Pokemon)
            for pokemon_id, exp in snapshot_pokemon_exp.items():
                cursor.execute("""
                    UPDATE pokemon_instances
                    SET exp = ?
                    WHERE pokemon_id = ? AND owner_discord_id = ?
                """, (exp, pokemon_id, discord_user_id))

        # Delete wild area state
        cursor.execute("""
            DELETE FROM trainer_wild_area_states
            WHERE discord_user_id = ?
        """, (discord_user_id,))

        conn.commit()
        conn.close()
        return True

    def move_to_zone(self, discord_user_id: int, new_zone_id: str,
                     stamina_cost: int = 5) -> tuple[bool, str]:
        """
        Move player to a new zone and deduct stamina.
        Returns (success, message)
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        # Get wild area state
        cursor.execute("""
            SELECT * FROM trainer_wild_area_states
            WHERE discord_user_id = ?
        """, (discord_user_id,))

        state_row = cursor.fetchone()

        if not state_row:
            conn.close()
            return False, "You're not in a wild area."

        state = dict(state_row)

        # Check stamina
        if state['current_stamina'] < stamina_cost:
            conn.close()
            return False, f"Not enough stamina! Need {stamina_cost}, have {state['current_stamina']}."

        # Deduct stamina
        new_stamina = state['current_stamina'] - stamina_cost

        # Update state
        cursor.execute("""
            UPDATE trainer_wild_area_states
            SET current_zone_id = ?, current_stamina = ?
            WHERE discord_user_id = ?
        """, (new_zone_id, new_stamina, discord_user_id))

        conn.commit()
        conn.close()

        if new_stamina <= 0:
            return True, f"Moved to new zone! **WARNING:** You're out of stamina!"

        return True, f"Moved to new zone! Stamina: {new_stamina}"

    def deduct_stamina(self, discord_user_id: int, amount: int, reason: str = "") -> tuple[bool, int]:
        """
        Deduct stamina from player in wild area.
        Returns (success, new_stamina)
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        # Get wild area state
        cursor.execute("""
            SELECT current_stamina FROM trainer_wild_area_states
            WHERE discord_user_id = ?
        """, (discord_user_id,))

        row = cursor.fetchone()

        if not row:
            conn.close()
            return False, 0

        current_stamina = row['current_stamina']
        new_stamina = max(0, current_stamina - amount)

        # Update stamina
        cursor.execute("""
            UPDATE trainer_wild_area_states
            SET current_stamina = ?
            WHERE discord_user_id = ?
        """, (new_stamina, discord_user_id))

        conn.commit()
        conn.close()

        return True, new_stamina

    def check_and_deduct_fainted_stamina(self, discord_user_id: int, party_pokemon: list,
                                        stamina_per_faint: int = 2) -> tuple[bool, int, int]:
        """
        Check party for fainted Pokemon and deduct stamina accordingly.
        Returns (success, fainted_count, new_stamina)
        """
        if not self.is_in_wild_area(discord_user_id):
            return False, 0, 0

        # Count fainted Pokemon
        fainted_count = sum(1 for mon in party_pokemon if getattr(mon, 'current_hp', 0) <= 0)

        if fainted_count == 0:
            state = self.get_wild_area_state(discord_user_id)
            return True, 0, state['current_stamina']

        # Deduct stamina
        total_stamina_cost = fainted_count * stamina_per_faint
        success, new_stamina = self.deduct_stamina(discord_user_id, total_stamina_cost, "fainted_pokemon")

        return success, fainted_count, new_stamina


class PartyManager:
    """Manages party/team formation and operations"""

    def __init__(self, db: PlayerDatabase):
        self.db = db

    # ============================================================
    # PARTY OPERATIONS
    # ============================================================

    def create_party(self, leader_discord_id: int, party_name: str,
                    area_id: str, starting_zone_id: str) -> str:
        """Create a new party. Returns party_id"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        party_id = str(uuid.uuid4())

        cursor.execute("""
            INSERT INTO parties (
                party_id, party_name, leader_discord_id,
                area_id, current_zone_id
            )
            VALUES (?, ?, ?, ?, ?)
        """, (party_id, party_name, leader_discord_id, area_id, starting_zone_id))

        # Add leader as first member
        cursor.execute("""
            INSERT INTO party_members (party_id, discord_user_id)
            VALUES (?, ?)
        """, (party_id, leader_discord_id))

        conn.commit()
        conn.close()

        return party_id

    def join_party(self, party_id: str, discord_user_id: int) -> bool:
        """Join an existing party"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO party_members (party_id, discord_user_id)
                VALUES (?, ?)
            """, (party_id, discord_user_id))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # Already in party
        finally:
            conn.close()

    def leave_party(self, discord_user_id: int) -> bool:
        """Leave current party"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        # Get current party
        cursor.execute("""
            SELECT party_id FROM party_members
            WHERE discord_user_id = ?
        """, (discord_user_id,))

        row = cursor.fetchone()

        if not row:
            conn.close()
            return False

        party_id = row['party_id']

        # Remove from party
        cursor.execute("""
            DELETE FROM party_members
            WHERE discord_user_id = ?
        """, (discord_user_id,))

        # Check if party is now empty
        cursor.execute("""
            SELECT COUNT(*) as count FROM party_members
            WHERE party_id = ?
        """, (party_id,))

        count = cursor.fetchone()['count']

        if count == 0:
            # Delete empty party
            cursor.execute("DELETE FROM parties WHERE party_id = ?", (party_id,))
        else:
            # Check if leader left
            cursor.execute("""
                SELECT leader_discord_id FROM parties
                WHERE party_id = ?
            """, (party_id,))

            party = cursor.fetchone()

            if party and party['leader_discord_id'] == discord_user_id:
                # Assign new leader (first remaining member)
                cursor.execute("""
                    SELECT discord_user_id FROM party_members
                    WHERE party_id = ?
                    LIMIT 1
                """, (party_id,))

                new_leader = cursor.fetchone()

                if new_leader:
                    cursor.execute("""
                        UPDATE parties
                        SET leader_discord_id = ?
                        WHERE party_id = ?
                    """, (new_leader['discord_user_id'], party_id))

        conn.commit()
        conn.close()
        return True

    def get_party(self, party_id: str) -> Optional[Dict]:
        """Get party by ID"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM parties WHERE party_id = ?", (party_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def get_player_party(self, discord_user_id: int) -> Optional[Dict]:
        """Get party that player is currently in"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT p.* FROM parties p
            JOIN party_members pm ON p.party_id = pm.party_id
            WHERE pm.discord_user_id = ?
        """, (discord_user_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def get_party_members(self, party_id: str) -> List[int]:
        """Get list of Discord user IDs in party"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT discord_user_id FROM party_members
            WHERE party_id = ?
            ORDER BY joined_at
        """, (party_id,))

        rows = cursor.fetchall()
        conn.close()

        return [row['discord_user_id'] for row in rows]

    def get_parties_in_area(self, area_id: str) -> List[Dict]:
        """Get all parties currently in a wild area"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM parties
            WHERE area_id = ?
        """, (area_id,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def is_in_party(self, discord_user_id: int) -> bool:
        """Check if player is in a party"""
        return self.get_player_party(discord_user_id) is not None

    def disband_party(self, party_id: str) -> bool:
        """Disband a party (leader only)"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        # Delete all members
        cursor.execute("DELETE FROM party_members WHERE party_id = ?", (party_id,))

        # Delete party
        cursor.execute("DELETE FROM parties WHERE party_id = ?", (party_id,))

        conn.commit()
        conn.close()
        return True

    def move_party_to_zone(self, party_id: str, new_zone_id: str,
                          stamina_cost_per_member: int = 5) -> tuple[bool, str]:
        """
        Move entire party to new zone, deducting stamina from all members.
        Returns (success, message)
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        # Get party members
        cursor.execute("""
            SELECT discord_user_id FROM party_members
            WHERE party_id = ?
        """, (party_id,))

        members = [row['discord_user_id'] for row in cursor.fetchall()]

        if not members:
            conn.close()
            return False, "Party has no members."

        # Check if all members have enough stamina
        insufficient_members = []
        for member_id in members:
            cursor.execute("""
                SELECT current_stamina FROM trainer_wild_area_states
                WHERE discord_user_id = ?
            """, (member_id,))

            row = cursor.fetchone()

            if not row or row['current_stamina'] < stamina_cost_per_member:
                cursor.execute("""
                    SELECT trainer_name FROM trainers
                    WHERE discord_user_id = ?
                """, (member_id,))

                trainer = cursor.fetchone()
                name = trainer['trainer_name'] if trainer else f"User {member_id}"
                insufficient_members.append(name)

        if insufficient_members:
            conn.close()
            return False, f"Not enough stamina: {', '.join(insufficient_members)}"

        # Deduct stamina from all members
        for member_id in members:
            cursor.execute("""
                UPDATE trainer_wild_area_states
                SET current_stamina = current_stamina - ?
                WHERE discord_user_id = ?
            """, (stamina_cost_per_member, member_id))

        # Update party location
        cursor.execute("""
            UPDATE parties
            SET current_zone_id = ?
            WHERE party_id = ?
        """, (new_zone_id, party_id))

        conn.commit()
        conn.close()

        return True, f"Party moved to new zone! Stamina cost: {stamina_cost_per_member} per member."

    def share_stamina(self, from_user_id: int, to_user_id: int, amount: int) -> tuple[bool, str]:
        """
        Share stamina from one party member to another.
        Returns (success, message)
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        # Check if both users are in same party
        cursor.execute("""
            SELECT party_id FROM party_members
            WHERE discord_user_id IN (?, ?)
        """, (from_user_id, to_user_id))

        rows = cursor.fetchall()

        if len(rows) != 2:
            conn.close()
            return False, "Both users must be in the same party."

        party_ids = [row['party_id'] for row in rows]

        if party_ids[0] != party_ids[1]:
            conn.close()
            return False, "Both users must be in the same party."

        # Get stamina states
        cursor.execute("""
            SELECT discord_user_id, current_stamina FROM trainer_wild_area_states
            WHERE discord_user_id IN (?, ?)
        """, (from_user_id, to_user_id))

        stamina_rows = cursor.fetchall()
        stamina_map = {row['discord_user_id']: row['current_stamina'] for row in stamina_rows}

        if from_user_id not in stamina_map or to_user_id not in stamina_map:
            conn.close()
            return False, "One or both users are not in a wild area."

        if stamina_map[from_user_id] < amount:
            conn.close()
            return False, "Not enough stamina to share."

        # Transfer stamina
        cursor.execute("""
            UPDATE trainer_wild_area_states
            SET current_stamina = current_stamina - ?
            WHERE discord_user_id = ?
        """, (amount, from_user_id))

        cursor.execute("""
            UPDATE trainer_wild_area_states
            SET current_stamina = current_stamina + ?
            WHERE discord_user_id = ?
        """, (amount, to_user_id))

        conn.commit()
        conn.close()

        return True, f"Shared {amount} stamina!"


class StaticEncounterManager:
    """Manages static encounters in wild areas"""

    def __init__(self, db: PlayerDatabase):
        self.db = db

    def create_static_encounter(self, zone_id: str, encounter_type: str,
                               pokemon_data: Dict = None, trainer_data: Dict = None,
                               battle_format: str = "singles",
                               target_player_id: int = None) -> str:
        """
        Create a static encounter.

        encounter_type: 'public_wild', 'player_specific', 'forced'
        battle_format: 'singles', 'doubles', 'multi', 'raid'

        Returns encounter_id
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        encounter_id = str(uuid.uuid4())

        cursor.execute("""
            INSERT INTO static_encounters (
                encounter_id, zone_id, encounter_type, target_player_id,
                pokemon_data, trainer_data, battle_format, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            encounter_id,
            zone_id,
            encounter_type,
            target_player_id,
            json.dumps(pokemon_data) if pokemon_data else None,
            json.dumps(trainer_data) if trainer_data else None,
            battle_format
        ))

        conn.commit()
        conn.close()

        return encounter_id

    def get_active_encounters_in_zone(self, zone_id: str,
                                     player_id: int = None) -> List[Dict]:
        """Get active static encounters in a zone (optionally filtered by player)"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        if player_id:
            cursor.execute("""
                SELECT * FROM static_encounters
                WHERE zone_id = ? AND is_active = 1
                AND (encounter_type = 'public_wild' OR target_player_id = ?)
            """, (zone_id, player_id))
        else:
            cursor.execute("""
                SELECT * FROM static_encounters
                WHERE zone_id = ? AND is_active = 1
            """, (zone_id,))

        rows = cursor.fetchall()
        conn.close()

        encounters = []
        for row in rows:
            encounter = dict(row)
            if encounter['pokemon_data']:
                encounter['pokemon_data'] = json.loads(encounter['pokemon_data'])
            if encounter['trainer_data']:
                encounter['trainer_data'] = json.loads(encounter['trainer_data'])
            encounters.append(encounter)

        return encounters

    def deactivate_encounter(self, encounter_id: str) -> bool:
        """Deactivate (complete) a static encounter"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE static_encounters
            SET is_active = 0
            WHERE encounter_id = ?
        """, (encounter_id,))

        conn.commit()
        conn.close()
        return True

    def delete_encounter(self, encounter_id: str) -> bool:
        """Permanently delete a static encounter"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM static_encounters
            WHERE encounter_id = ?
        """, (encounter_id,))

        conn.commit()
        conn.close()
        return True
