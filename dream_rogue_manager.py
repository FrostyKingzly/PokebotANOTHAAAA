"""
Dream Rogue Gamemode Manager

Handles all Dream Rogue roguelike mode operations including:
- Run creation and management
- Floor progression and instance selection
- Voting system for team decisions
- Buff/curse application and tracking
- Dreamlite economy
- Battle integration
"""

import sqlite3
import uuid
import json
import random
import time
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime


class DreamRogueManager:
    """Manages Dream Rogue roguelike runs"""

    def __init__(self, db_path: str = "data/players.db"):
        self.db_path = db_path
        self._init_database()
        self._load_instance_templates()

    def _init_database(self):
        """Initialize Dream Rogue tables from schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Read and execute schema
        try:
            with open("dream_rogue_schema.sql", "r") as f:
                schema = f.read()
                cursor.executescript(schema)
            conn.commit()
        except FileNotFoundError:
            print("Warning: dream_rogue_schema.sql not found, skipping schema init")
        finally:
            conn.close()

    def _load_instance_templates(self):
        """Load instance templates from JSON"""
        try:
            with open("data/dream_instances.json", "r") as f:
                self.instance_templates = json.load(f)
        except FileNotFoundError:
            print("Warning: dream_instances.json not found")
            self.instance_templates = {}

    # ===== RUN MANAGEMENT =====

    def create_run(
        self,
        guild_id: int,
        initiator_id: int,
        starting_floor: int = 1,
        session_id: Optional[str] = None
    ) -> str:
        """
        Create a new Dream Rogue run

        Args:
            guild_id: Discord guild ID
            initiator_id: Discord user ID of initiator
            starting_floor: Which floor to start on (1-10)
            session_id: Optional session ID if started from session mode

        Returns:
            run_id: UUID string
        """
        run_id = str(uuid.uuid4())
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO dream_rogue_runs (
                run_id, session_id, guild_id, initiator_id,
                current_floor, starting_floor, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (run_id, session_id, guild_id, initiator_id, starting_floor, starting_floor))

        # Add initiator as first participant
        starting_dreamlites = self._calculate_starting_dreamlites(starting_floor)
        cursor.execute("""
            INSERT INTO dream_rogue_participants (run_id, discord_user_id, dreamlites)
            VALUES (?, ?, ?)
        """, (run_id, initiator_id, starting_dreamlites))

        conn.commit()
        conn.close()
        return run_id

    def _calculate_starting_dreamlites(self, starting_floor: int) -> int:
        """Calculate starting Dreamlites based on floor"""
        # Base 100 + 20 per floor above 1
        return 100 + ((starting_floor - 1) * 20)

    def add_participant(self, run_id: str, discord_user_id: int) -> bool:
        """
        Add a participant to an active run

        Returns:
            True if added successfully, False if already in run
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check if already in run
        cursor.execute("""
            SELECT 1 FROM dream_rogue_participants
            WHERE run_id = ? AND discord_user_id = ?
        """, (run_id, discord_user_id))

        if cursor.fetchone():
            conn.close()
            return False

        # Get starting floor to calculate Dreamlites
        cursor.execute("SELECT starting_floor FROM dream_rogue_runs WHERE run_id = ?", (run_id,))
        result = cursor.fetchone()
        if not result:
            conn.close()
            return False

        starting_floor = result[0]
        starting_dreamlites = self._calculate_starting_dreamlites(starting_floor)

        cursor.execute("""
            INSERT INTO dream_rogue_participants (run_id, discord_user_id, dreamlites)
            VALUES (?, ?, ?)
        """, (run_id, discord_user_id, starting_dreamlites))

        conn.commit()
        conn.close()
        return True

    def get_run(self, run_id: str) -> Optional[Dict]:
        """Get run data"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM dream_rogue_runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def get_active_run_by_guild(self, guild_id: int) -> Optional[Dict]:
        """Get currently active run in a guild"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM dream_rogue_runs
            WHERE guild_id = ? AND is_active = 1
            ORDER BY created_at DESC
            LIMIT 1
        """, (guild_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def get_participants(self, run_id: str) -> List[Dict]:
        """Get all participants in a run"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM dream_rogue_participants
            WHERE run_id = ?
            ORDER BY joined_at ASC
        """, (run_id,))

        participants = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return participants

    def end_run(self, run_id: str, extracted: bool = False):
        """
        End a Dream Rogue run

        Args:
            run_id: Run to end
            extracted: Whether run ended via extraction (success) or failure
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        timestamp = datetime.now().isoformat()

        if extracted:
            cursor.execute("""
                UPDATE dream_rogue_runs
                SET is_active = 0, extracted_at = ?
                WHERE run_id = ?
            """, (timestamp, run_id))
        else:
            cursor.execute("""
                UPDATE dream_rogue_runs
                SET is_active = 0, completed_at = ?
                WHERE run_id = ?
            """, (timestamp, run_id))

        # Transfer remaining Dreamlites to personal currency
        cursor.execute("""
            SELECT discord_user_id, dreamlites FROM dream_rogue_participants
            WHERE run_id = ?
        """, (run_id,))

        for user_id, dreamlites in cursor.fetchall():
            self._add_persistent_dreamlites(user_id, dreamlites, cursor)

        # Update stats
        cursor.execute("SELECT current_floor FROM dream_rogue_runs WHERE run_id = ?", (run_id,))
        current_floor = cursor.fetchone()[0]

        for user_id, _ in cursor.execute("SELECT discord_user_id, dreamlites FROM dream_rogue_participants WHERE run_id = ?", (run_id,)).fetchall():
            self._update_stats(user_id, extracted, current_floor, cursor)

        conn.commit()
        conn.close()

    def _add_persistent_dreamlites(self, user_id: int, amount: int, cursor: sqlite3.Cursor):
        """Add Dreamlites to user's persistent currency"""
        cursor.execute("""
            INSERT INTO dream_rogue_currency (discord_user_id, total_dreamlites, lifetime_earned)
            VALUES (?, ?, ?)
            ON CONFLICT(discord_user_id) DO UPDATE SET
                total_dreamlites = total_dreamlites + ?,
                lifetime_earned = lifetime_earned + ?
        """, (user_id, amount, amount, amount, amount))

    def _update_stats(self, user_id: int, extracted: bool, floor: int, cursor: sqlite3.Cursor):
        """Update player stats after run"""
        cursor.execute("""
            INSERT INTO dream_rogue_stats (discord_user_id, total_runs, successful_extractions, highest_floor)
            VALUES (?, 1, ?, ?)
            ON CONFLICT(discord_user_id) DO UPDATE SET
                total_runs = total_runs + 1,
                successful_extractions = successful_extractions + ?,
                highest_floor = MAX(highest_floor, ?)
        """, (user_id, 1 if extracted else 0, floor, 1 if extracted else 0, floor))

    # ===== DREAMLITE ECONOMY =====

    def get_dreamlites(self, run_id: str, user_id: int) -> int:
        """Get user's current Dreamlites in run"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT dreamlites FROM dream_rogue_participants
            WHERE run_id = ? AND discord_user_id = ?
        """, (run_id, user_id))

        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0

    def add_dreamlites(self, run_id: str, user_id: int, amount: int) -> int:
        """
        Add Dreamlites to user (can be negative to subtract)

        Returns:
            New Dreamlite balance
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE dream_rogue_participants
            SET dreamlites = MAX(0, dreamlites + ?)
            WHERE run_id = ? AND discord_user_id = ?
        """, (amount, run_id, user_id))

        cursor.execute("""
            SELECT dreamlites FROM dream_rogue_participants
            WHERE run_id = ? AND discord_user_id = ?
        """, (run_id, user_id))

        new_balance = cursor.fetchone()[0]
        conn.commit()
        conn.close()
        return new_balance

    def can_afford(self, run_id: str, user_id: int, cost: int) -> bool:
        """Check if user can afford cost"""
        return self.get_dreamlites(run_id, user_id) >= cost

    def get_persistent_dreamlites(self, user_id: int) -> int:
        """Get user's total persistent Dreamlites"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT total_dreamlites FROM dream_rogue_currency
            WHERE discord_user_id = ?
        """, (user_id,))

        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0

    # ===== FLOOR PROGRESSION =====

    def advance_floor(self, run_id: str) -> int:
        """
        Advance to next floor

        Returns:
            New floor number
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE dream_rogue_runs
            SET current_floor = current_floor + 1
            WHERE run_id = ?
        """, (run_id,))

        cursor.execute("SELECT current_floor FROM dream_rogue_runs WHERE run_id = ?", (run_id,))
        new_floor = cursor.fetchone()[0]

        # Remove floor-duration buffs
        cursor.execute("""
            DELETE FROM dream_rogue_buffs
            WHERE run_id = ? AND duration = 'floor'
        """, (run_id,))

        # Decrement floor counters on floor-limited buffs
        cursor.execute("""
            UPDATE dream_rogue_buffs
            SET floors_remaining = floors_remaining - 1
            WHERE run_id = ? AND floors_remaining IS NOT NULL
        """, (run_id,))

        cursor.execute("""
            DELETE FROM dream_rogue_buffs
            WHERE run_id = ? AND floors_remaining <= 0
        """, (run_id,))

        conn.commit()
        conn.close()
        return new_floor

    def get_floor_level_range(self, floor: int) -> Tuple[int, int]:
        """
        Get min/max level for a floor

        Returns:
            (min_level, max_level) tuple
        """
        # Floor 1: Level 8-12
        # Each floor adds ~2-3 levels
        base_min = 8 + (floor - 1) * 2
        base_max = 12 + (floor - 1) * 3

        return (base_min, base_max)

    def generate_floor_instances(self, run_id: str, floor: int) -> List[Dict]:
        """
        Generate instances for a floor

        Args:
            run_id: Active run
            floor: Floor number (1-10)

        Returns:
            List of instance dicts
        """
        instances = []

        if floor == 1:
            # Floor 1: Easy setup floor
            # 1-2 battles, 1 economy, 1 buff/trial
            instances.extend(self._get_instances_by_category(["battle"], 2))
            instances.extend(self._get_instances_by_category(["economy", "reward"], 1))
            instances.extend(self._get_instances_by_category(["buff", "trial"], 1))
            instances.extend(self._get_instances_by_category(["rest"], 1))

        elif floor == 10:
            # Floor 10: Boss floor
            # Safe room, then boss raid
            instances.append(self._create_instance("rest", "safe_camp"))
            instances.append(self._create_boss_instance(floor))

        else:
            # Floors 2-9: Mix of instance types
            # 40% battle, 20% gambling/risk, 20% buff/curse, 20% economy/reward
            num_instances = random.randint(4, 6)

            # At least 2 battles
            battle_count = max(2, int(num_instances * 0.4))
            instances.extend(self._get_instances_by_category(["battle"], battle_count))

            remaining = num_instances - battle_count

            # Mix other types
            if remaining > 0:
                other_categories = ["gambling", "trial", "buff", "economy", "reward", "social"]
                for _ in range(remaining):
                    category = random.choice(other_categories)
                    inst = self._get_instances_by_category([category], 1)
                    if inst:
                        instances.extend(inst)

            # Always add 1 rest/safe room
            instances.extend(self._get_instances_by_category(["rest"], 1))

        # Shuffle so order is random
        random.shuffle(instances)

        return instances

    def _get_instances_by_category(self, categories: List[str], count: int) -> List[Dict]:
        """Get random instances matching categories"""
        matching = []

        for category_group, templates in self.instance_templates.items():
            for template_id, template in templates.items():
                template_categories = template.get("categories", [])
                if any(cat in template_categories for cat in categories):
                    instance = template.copy()
                    instance["template_id"] = f"{category_group}.{template_id}"
                    matching.append(instance)

        if not matching:
            return []

        # Return random sample
        return random.sample(matching, min(count, len(matching)))

    def _create_instance(self, category: str, template_id: str) -> Dict:
        """Create specific instance by template ID"""
        for category_group, templates in self.instance_templates.items():
            if template_id in templates:
                instance = templates[template_id].copy()
                instance["template_id"] = f"{category_group}.{template_id}"
                return instance

        # Fallback
        return {"template_id": template_id, "name": "Unknown Instance"}

    def _create_boss_instance(self, floor: int) -> Dict:
        """Create boss raid instance"""
        return {
            "template_id": "boss_raid",
            "name": f"Floor {floor} Boss",
            "description": "Face the floor guardian in an epic raid battle!",
            "categories": ["battle", "boss", "raid"],
            "scope": "team",
            "risk_level": "extreme",
            "effect_data": {
                "type": "boss_raid",
                "floor": floor
            }
        }

    # ===== BUFF/CURSE MANAGEMENT =====

    def apply_buff(
        self,
        run_id: str,
        buff_type: str,
        buff_name: str,
        buff_description: str,
        scope: str,
        effect_data: Dict,
        duration: str,
        target_user_id: Optional[int] = None,
        battles_remaining: Optional[int] = None,
        floors_remaining: Optional[int] = None
    ) -> str:
        """
        Apply a buff or curse to participant(s)

        Args:
            run_id: Active run
            buff_type: 'buff', 'curse', 'domain', 'nightmare'
            buff_name: Display name
            buff_description: Description text
            scope: 'individual' or 'team'
            effect_data: JSON-serializable effect parameters
            duration: 'battle', 'floor', 'run', 'permanent'
            target_user_id: Required if scope is 'individual'
            battles_remaining: For battle-duration buffs
            floors_remaining: For floor-limited buffs

        Returns:
            buff_id: UUID string
        """
        buff_id = str(uuid.uuid4())
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO dream_rogue_buffs (
                buff_id, run_id, buff_type, buff_name, buff_description,
                scope, target_user_id, effect_data, duration,
                battles_remaining, floors_remaining
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            buff_id, run_id, buff_type, buff_name, buff_description,
            scope, target_user_id, json.dumps(effect_data), duration,
            battles_remaining, floors_remaining
        ))

        conn.commit()
        conn.close()
        return buff_id

    def get_active_buffs(self, run_id: str, user_id: Optional[int] = None) -> List[Dict]:
        """
        Get active buffs for run or specific user

        Args:
            run_id: Active run
            user_id: If provided, only get buffs for this user (individual + team)
                     If None, get all team buffs
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if user_id:
            cursor.execute("""
                SELECT * FROM dream_rogue_buffs
                WHERE run_id = ?
                AND (scope = 'team' OR (scope = 'individual' AND target_user_id = ?))
            """, (run_id, user_id))
        else:
            cursor.execute("""
                SELECT * FROM dream_rogue_buffs
                WHERE run_id = ? AND scope = 'team'
            """, (run_id,))

        buffs = []
        for row in cursor.fetchall():
            buff = dict(row)
            buff["effect_data"] = json.loads(buff["effect_data"])
            buffs.append(buff)

        conn.close()
        return buffs

    def remove_buff(self, buff_id: str):
        """Remove a specific buff"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM dream_rogue_buffs WHERE buff_id = ?", (buff_id,))
        conn.commit()
        conn.close()

    def decrement_battle_buffs(self, run_id: str):
        """Decrement battle counters and remove expired buffs"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Decrement counters
        cursor.execute("""
            UPDATE dream_rogue_buffs
            SET battles_remaining = battles_remaining - 1
            WHERE run_id = ? AND battles_remaining IS NOT NULL
        """, (run_id,))

        # Remove expired
        cursor.execute("""
            DELETE FROM dream_rogue_buffs
            WHERE run_id = ? AND battles_remaining <= 0
        """, (run_id,))

        conn.commit()
        conn.close()

    # ===== VOTING SYSTEM =====

    def create_vote(
        self,
        run_id: str,
        vote_prompt: str,
        vote_options: List[Dict],
        instance_template_id: Optional[str] = None
    ) -> str:
        """
        Create a team vote

        Args:
            run_id: Active run
            vote_prompt: Question being voted on
            vote_options: List of option dicts with 'name' and 'description'
            instance_template_id: Optional template ID for tracking

        Returns:
            vote_id: UUID string
        """
        vote_id = str(uuid.uuid4())
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO dream_rogue_votes (
                vote_id, run_id, instance_template_id, vote_prompt, vote_options, votes
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (vote_id, run_id, instance_template_id, vote_prompt, json.dumps(vote_options), "{}"))

        conn.commit()
        conn.close()
        return vote_id

    def cast_vote(self, vote_id: str, user_id: int, option_index: int) -> bool:
        """
        Cast or change a vote

        Returns:
            True if vote recorded successfully
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get current votes
        cursor.execute("SELECT votes FROM dream_rogue_votes WHERE vote_id = ?", (vote_id,))
        result = cursor.fetchone()
        if not result:
            conn.close()
            return False

        votes = json.loads(result[0])
        votes[str(user_id)] = option_index

        cursor.execute("""
            UPDATE dream_rogue_votes
            SET votes = ?
            WHERE vote_id = ?
        """, (json.dumps(votes), vote_id))

        conn.commit()
        conn.close()
        return True

    def get_vote(self, vote_id: str) -> Optional[Dict]:
        """Get vote data"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM dream_rogue_votes WHERE vote_id = ?", (vote_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            vote = dict(row)
            vote["vote_options"] = json.loads(vote["vote_options"])
            vote["votes"] = json.loads(vote["votes"])
            return vote
        return None

    def resolve_vote(self, vote_id: str) -> int:
        """
        Resolve vote using weighted random based on vote percentages

        Returns:
            Winning option index
        """
        vote = self.get_vote(vote_id)
        if not vote:
            return 0

        votes = vote["votes"]
        vote_options = vote["vote_options"]

        if not votes:
            # No votes, random choice
            return random.randint(0, len(vote_options) - 1)

        # Count votes per option
        vote_counts = {}
        for user_id_str, option_idx in votes.items():
            vote_counts[option_idx] = vote_counts.get(option_idx, 0) + 1

        total_votes = sum(vote_counts.values())

        # Weighted random selection
        rand = random.uniform(0, total_votes)
        cumulative = 0

        for option_idx, count in vote_counts.items():
            cumulative += count
            if rand <= cumulative:
                result_index = option_idx
                break
        else:
            result_index = list(vote_counts.keys())[0]

        # Mark as resolved
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE dream_rogue_votes
            SET is_active = 0, resolved_at = ?, result_index = ?
            WHERE vote_id = ?
        """, (datetime.now().isoformat(), result_index, vote_id))

        conn.commit()
        conn.close()

        return result_index

    def get_vote_percentages(self, vote_id: str) -> Dict[int, float]:
        """
        Get vote percentages for each option

        Returns:
            Dict mapping option_index -> percentage (0-100)
        """
        vote = self.get_vote(vote_id)
        if not vote or not vote["votes"]:
            return {}

        votes = vote["votes"]
        vote_counts = {}

        for user_id_str, option_idx in votes.items():
            vote_counts[option_idx] = vote_counts.get(option_idx, 0) + 1

        total_votes = sum(vote_counts.values())
        percentages = {}

        for option_idx, count in vote_counts.items():
            percentages[option_idx] = (count / total_votes) * 100

        return percentages

    # ===== FLOOR HISTORY =====

    def record_floor_completion(
        self,
        run_id: str,
        floor_number: int,
        instance_template_id: str,
        instance_type: str,
        outcome: str,
        dreamlites_gained: int = 0,
        dreamlites_spent: int = 0
    ):
        """Record completed floor instance"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        history_id = str(uuid.uuid4())

        cursor.execute("""
            INSERT INTO dream_rogue_floor_history (
                history_id, run_id, floor_number, instance_template_id,
                instance_type, outcome, dreamlites_gained, dreamlites_spent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            history_id, run_id, floor_number, instance_template_id,
            instance_type, outcome, dreamlites_gained, dreamlites_spent
        ))

        conn.commit()
        conn.close()

    def get_floor_history(self, run_id: str, floor_number: Optional[int] = None) -> List[Dict]:
        """Get floor completion history"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if floor_number:
            cursor.execute("""
                SELECT * FROM dream_rogue_floor_history
                WHERE run_id = ? AND floor_number = ?
                ORDER BY completed_at ASC
            """, (run_id, floor_number))
        else:
            cursor.execute("""
                SELECT * FROM dream_rogue_floor_history
                WHERE run_id = ?
                ORDER BY floor_number ASC, completed_at ASC
            """, (run_id,))

        history = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return history
