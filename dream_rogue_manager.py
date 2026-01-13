"""
Dream Dive Gamemode Manager

Handles all Dream Dive roguelike mode operations including:
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
    """Manages Dream Dive roguelike runs"""

    TEST_PATH_LAYER = "Somnia Prima - Test Path"

    def __init__(self, db_path: str = "data/players.db"):
        self.db_path = db_path
        self._init_database()
        self._load_instance_templates()

    def _init_database(self):
        """Initialize Dream Dive tables from schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Read and execute schema
        try:
            with open("dream_rogue_schema.sql", "r", encoding="utf-8") as f:
                schema = f.read()
                cursor.executescript(schema)
            cursor.execute("PRAGMA table_info(dream_rogue_runs)")
            columns = {row[1] for row in cursor.fetchall()}
            if "map_data" not in columns:
                cursor.execute("ALTER TABLE dream_rogue_runs ADD COLUMN map_data TEXT")
            if "current_node_id" not in columns:
                cursor.execute("ALTER TABLE dream_rogue_runs ADD COLUMN current_node_id TEXT")
            if "intensity" not in columns:
                cursor.execute("ALTER TABLE dream_rogue_runs ADD COLUMN intensity INTEGER DEFAULT 1")
            if "layer_name" not in columns:
                cursor.execute("ALTER TABLE dream_rogue_runs ADD COLUMN layer_name TEXT DEFAULT 'Somnia Prima'")
            if "script_state" not in columns:
                cursor.execute("ALTER TABLE dream_rogue_runs ADD COLUMN script_state TEXT")
            conn.commit()
        except FileNotFoundError:
            print("Warning: dream_rogue_schema.sql not found, skipping schema init")
        finally:
            conn.close()

    def _load_instance_templates(self):
        """Load instance templates from JSON"""
        try:
            with open("data/dream_instances.json", "r", encoding="utf-8") as f:
                self.instance_templates = json.load(f)
        except FileNotFoundError:
            print("Warning: dream_instances.json not found")
            self.instance_templates = {}

    # ===== RUN MANAGEMENT =====

    def create_run(
        self,
        guild_id: int,
        initiator_id: int,
        intensity: int = 1,
        layer_name: str = "Somnia Prima",
        starting_floor: int = 1,
        session_id: Optional[str] = None
    ) -> str:
        """
        Create a new Dream Dive run

        Args:
            guild_id: Discord guild ID
            initiator_id: Discord user ID of initiator
            intensity: Dive intensity (1-10)
            layer_name: Dream layer name
            starting_floor: Which floor to start on (1-10)
            session_id: Optional session ID if started from session mode

        Returns:
            run_id: UUID string
        """
        run_id = str(uuid.uuid4())
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        is_test_path = layer_name == self.TEST_PATH_LAYER

        cursor.execute("""
            INSERT INTO dream_rogue_runs (
                run_id, session_id, guild_id, initiator_id,
                stage_level, intensity, layer_name, current_floor, starting_floor, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            run_id,
            session_id,
            guild_id,
            initiator_id,
            intensity,
            intensity,
            layer_name,
            starting_floor,
            starting_floor,
        ))

        # Add initiator as first participant
        starting_dreamlites = 0 if is_test_path else self._calculate_starting_dreamlites(intensity)
        cursor.execute("""
            INSERT INTO dream_rogue_participants (run_id, discord_user_id, dreamlites)
            VALUES (?, ?, ?)
        """, (run_id, initiator_id, starting_dreamlites))

        if is_test_path:
            map_data = self._generate_test_path_map(intensity)
        else:
            map_data = self._generate_dive_map(intensity)
        cursor.execute("""
            UPDATE dream_rogue_runs
            SET map_data = ?, current_node_id = ?, current_floor = ?, script_state = ?
            WHERE run_id = ?
        """, (
            json.dumps(map_data),
            map_data["start_node_id"],
            map_data["nodes"][map_data["start_node_id"]]["depth"],
            json.dumps(self._get_default_script_state() if is_test_path else {}),
            run_id,
        ))

        conn.commit()
        conn.close()
        return run_id

    def _calculate_starting_dreamlites(self, intensity: int) -> int:
        """Calculate starting Dreamlites based on intensity."""
        # Base 100 + (intensity * 5)
        # Intensity 1 = 105, Intensity 2 = 110, etc.
        return 100 + (intensity * 5)

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

        # Get stage level to calculate Dreamlites
        cursor.execute("""
            SELECT COALESCE(intensity, stage_level, 1)
            FROM dream_rogue_runs
            WHERE run_id = ?
        """, (run_id,))
        result = cursor.fetchone()
        if not result:
            conn.close()
            return False

        intensity = int(result[0] or 1)
        run = self.get_run(run_id) or {}
        is_test_path = run.get("layer_name") == self.TEST_PATH_LAYER
        starting_dreamlites = 0 if is_test_path else self._calculate_starting_dreamlites(intensity)

        cursor.execute("""
            INSERT INTO dream_rogue_participants (run_id, discord_user_id, dreamlites)
            VALUES (?, ?, ?)
        """, (run_id, discord_user_id, starting_dreamlites))

        conn.commit()
        conn.close()
        return True

    def record_party_snapshot(self, run_id: str, discord_user_id: int, party: List[Dict]):
        """Store party level/EXP snapshots for temporary dive effects."""
        if not party:
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        rows = []
        for pokemon in party:
            pokemon_id = pokemon.get("pokemon_id")
            if not pokemon_id:
                continue
            rows.append((
                run_id,
                discord_user_id,
                pokemon_id,
                int(pokemon.get("level", 1)),
                int(pokemon.get("exp", 0)),
                int(pokemon.get("stored_exp", 0)),
            ))

        cursor.executemany("""
            INSERT OR IGNORE INTO dream_rogue_party_snapshots (
                run_id, discord_user_id, pokemon_id,
                original_level, original_exp, original_stored_exp
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, rows)

        conn.commit()
        conn.close()

    def get_party_snapshots(self, run_id: str, discord_user_id: int) -> List[Dict]:
        """Fetch stored party level/EXP snapshots for a user in a run."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT *
            FROM dream_rogue_party_snapshots
            WHERE run_id = ? AND discord_user_id = ?
        """, (run_id, discord_user_id))

        snapshots = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return snapshots

    def clear_party_snapshots(self, run_id: str, discord_user_id: Optional[int] = None):
        """Clear stored party snapshots for a run or specific user."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        if discord_user_id is None:
            cursor.execute("""
                DELETE FROM dream_rogue_party_snapshots
                WHERE run_id = ?
            """, (run_id,))
        else:
            cursor.execute("""
                DELETE FROM dream_rogue_party_snapshots
                WHERE run_id = ? AND discord_user_id = ?
            """, (run_id, discord_user_id))
        conn.commit()
        conn.close()

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

    def get_active_run_by_session(self, session_id: str) -> Optional[Dict]:
        """Get currently active run for a session."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM dream_rogue_runs
            WHERE session_id = ? AND is_active = 1
            ORDER BY created_at DESC
            LIMIT 1
        """, (session_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def _get_default_script_state(self) -> Dict[str, Any]:
        return {
            "area_index": 1,
            "action_index": 0,
            "nidoking_battle_id": None,
        }

    def get_script_state(self, run_id: str) -> Dict[str, Any]:
        """Get scripted state for special runs."""
        run = self.get_run(run_id)
        if not run:
            return self._get_default_script_state()
        raw_state = run.get("script_state")
        if not raw_state:
            return self._get_default_script_state()
        try:
            state = json.loads(raw_state)
        except json.JSONDecodeError:
            state = {}
        base = self._get_default_script_state()
        base.update(state or {})
        return base

    def update_script_state(self, run_id: str, state: Dict[str, Any]) -> None:
        """Persist scripted state for special runs."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE dream_rogue_runs
            SET script_state = ?
            WHERE run_id = ?
        """, (json.dumps(state), run_id))
        conn.commit()
        conn.close()

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
        End a Dream Dive run

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

    def get_floor_level_range(self, intensity: int, floor: int) -> Tuple[int, int]:
        """
        Get min/max level for a floor based on stage and floor number

        Args:
            intensity: Dive intensity (1-10)
            floor: Floor number (1-10)

        Returns:
            (min_level, max_level) tuple

        Example for Intensity 2:
            Floor 1: 11-20
            Floor 5: 11-20
            Floor 10: 11-20
        """
        min_level = max(1, (intensity - 1) * 10 + 1)
        max_level = max(min_level, intensity * 10)

        return (min_level, max_level)

    # ===== MAP GENERATION =====

    def _generate_dive_map(self, intensity: int, total_depth: int = 10) -> Dict[str, Any]:
        """Generate a branching map for the run."""
        def _node_id(depth: int, index: int) -> str:
            return f"node_{depth}_{index}"

        def _node_type_for_depth(depth: int) -> str:
            if depth == 1:
                return "start"
            if depth == 2:
                return "combat"
            if depth == total_depth - 1:
                return "mini_boss"
            if depth == total_depth:
                return "boss"
            roll = random.random()
            if roll < 0.5:
                return "combat"
            if roll < 0.75:
                return "event"
            return "rest"

        nodes: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, str]] = []

        layer_counts = {1: 1, 2: 3, total_depth - 1: 2, total_depth: 1}
        for depth in range(3, total_depth - 1):
            layer_counts[depth] = random.choice([2, 3])

        rest_depth = 5 if total_depth >= 6 else 3
        rest_assigned = False

        for depth in range(1, total_depth + 1):
            count = layer_counts.get(depth, 1)
            for index in range(1, count + 1):
                node_id = _node_id(depth, index)
                node_type = _node_type_for_depth(depth)

                if depth == rest_depth and not rest_assigned and node_type not in {"boss", "mini_boss", "start"}:
                    node_type = "rest"
                    rest_assigned = True

                nodes[node_id] = {
                    "node_id": node_id,
                    "depth": depth,
                    "node_type": node_type,
                    "has_shop": node_type == "rest" and random.random() < 0.08,
                }

        for depth in range(1, total_depth):
            current_nodes = [n for n in nodes.values() if n["depth"] == depth]
            next_nodes = [n for n in nodes.values() if n["depth"] == depth + 1]
            if not next_nodes:
                continue

            for node in current_nodes:
                connections = random.sample(next_nodes, k=random.randint(1, min(2, len(next_nodes))))
                for next_node in connections:
                    edges.append({"from": node["node_id"], "to": next_node["node_id"]})

            for next_node in next_nodes:
                if not any(edge["to"] == next_node["node_id"] for edge in edges):
                    source = random.choice(current_nodes)
                    edges.append({"from": source["node_id"], "to": next_node["node_id"]})

        start_node_id = _node_id(1, 1)
        final_node_id = _node_id(total_depth, 1)

        return {
            "map_type": "random",
            "intensity": intensity,
            "start_node_id": start_node_id,
            "final_node_id": final_node_id,
            "nodes": nodes,
            "edges": edges,
            "total_depth": total_depth,
        }

    def _generate_test_path_map(self, intensity: int) -> Dict[str, Any]:
        """Generate a linear scripted map for the test path."""
        nodes = {
            "area_1": {"node_id": "area_1", "depth": 1, "node_type": "story", "has_shop": False},
            "area_2": {"node_id": "area_2", "depth": 2, "node_type": "story", "has_shop": False},
            "area_3": {"node_id": "area_3", "depth": 3, "node_type": "story", "has_shop": False},
        }
        edges = [
            {"from": "area_1", "to": "area_2"},
            {"from": "area_2", "to": "area_3"},
        ]
        return {
            "map_type": "test_path",
            "intensity": intensity,
            "start_node_id": "area_1",
            "final_node_id": "area_3",
            "nodes": nodes,
            "edges": edges,
            "total_depth": 3,
        }

    def get_map(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Fetch the stored map for a run."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT map_data FROM dream_rogue_runs WHERE run_id = ?", (run_id,))
        result = cursor.fetchone()
        conn.close()
        if not result or not result[0]:
            return None
        return json.loads(result[0])

    def get_current_node(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get the current node in the map."""
        run = self.get_run(run_id)
        if not run:
            return None
        node_id = run.get("current_node_id")
        if not node_id:
            return None
        map_data = self.get_map(run_id)
        if not map_data:
            return None
        return map_data["nodes"].get(node_id)

    def set_current_node(self, run_id: str, node_id: str) -> None:
        """Update the run to the selected node."""
        map_data = self.get_map(run_id)
        if not map_data or node_id not in map_data["nodes"]:
            return
        node_depth = map_data["nodes"][node_id]["depth"]
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE dream_rogue_runs
            SET current_node_id = ?, current_floor = ?
            WHERE run_id = ?
        """, (node_id, node_depth, run_id))
        conn.commit()
        conn.close()

    def get_next_nodes(self, run_id: str) -> List[Dict[str, Any]]:
        """Get available next nodes from the current node."""
        run = self.get_run(run_id)
        map_data = self.get_map(run_id)
        if not run or not map_data:
            return []
        current_node_id = run.get("current_node_id")
        if not current_node_id:
            return []
        next_node_ids = [
            edge["to"] for edge in map_data.get("edges", [])
            if edge.get("from") == current_node_id
        ]
        return [map_data["nodes"][node_id] for node_id in next_node_ids if node_id in map_data["nodes"]]

    def generate_node_instances(self, run_id: str, node: Dict[str, Any]) -> List[Dict]:
        """Generate instances for a specific node."""
        node_type = node.get("node_type")
        if node_type == "start":
            return []
        if node_type == "boss":
            return [self._create_boss_instance(node.get("depth", 10))]
        if node_type == "mini_boss":
            return [self._create_miniboss_instance(node.get("depth", 9))]
        if node_type == "rest":
            instance = self._create_instance("rest", "safe_camp")
            if node.get("has_shop"):
                shop_instance = self._get_instances_by_category(["shop"], 1)
                return [instance] + shop_instance
            return [instance]
        if node_type == "event":
            event_instances = self._get_instances_by_category(["event"], 1)
            if event_instances:
                return event_instances
            return self._get_instances_by_category(["social", "trial", "gambling", "reward", "economy"], 1)
        if node_type == "combat":
            battle_instances = self._get_instances_by_category(["battle"], 3)
            filtered = [b for b in battle_instances if "raid" not in b.get("categories", [])]
            if filtered:
                return [random.choice(filtered)]
            return self._get_instances_by_category(["battle"], 1)
        return self._get_instances_by_category(["battle"], 1)

    def generate_floor_instances(
        self,
        run_id: str,
        floor: int,
        category_override: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Generate instances for a floor

        Args:
            run_id: Active run
            floor: Floor number (1-10)
            category_override: Optional list of categories to force for this floor

        Returns:
            List of instance dicts
        """
        instances = []

        if floor == 10:
            # Stage 10: Boss battle
            instances.append(self._create_boss_instance(floor))
        elif category_override:
            instances.extend(self._get_instances_by_category(category_override, 1))
        elif floor == 1:
            # Stage 1: Randomize battle type (singles, doubles, multi, raid)
            # Generate multiple battle options with different formats
            battle_instances = self._get_instances_by_category(["battle"], 10)  # Get all battle types
            if battle_instances:
                # Pick a random battle type for the first floor
                instances.append(random.choice(battle_instances))
            else:
                # Fallback to standard battle
                instances.extend(self._get_instances_by_category(["battle"], 1))
        elif floor == 5:
            # Middle stage always a rest
            instances.extend(self._get_instances_by_category(["rest"], 1))
        else:
            option_count = 3 if random.random() <= 0.35 else 2

            room_weights = [
                (["battle"], 0.25),
                (["gambling"], 0.10),
                (["social"], 0.15),
                (["trial"], 0.10),
                (["domain"], 0.08),
                (["buff"], 0.08),
                (["nightmare", "curse"], 0.08),
                (["economy", "reward"], 0.08),
                (["rest"], 0.03),
                (["shop"], 0.05),
            ]

            def _roll_room_category() -> List[str]:
                roll = random.random()
                cumulative = 0.0
                chosen = ["battle"]
                for categories, weight in room_weights:
                    cumulative += weight
                    if roll <= cumulative:
                        chosen = categories
                        break
                return chosen

            def _pick_instance(categories: List[str], used_templates: set) -> Optional[Dict]:
                matching = []
                for category_group, templates in self.instance_templates.items():
                    for template_id, template in templates.items():
                        template_categories = template.get("categories", [])
                        if any(cat in template_categories for cat in categories):
                            instance = template.copy()
                            instance["template_id"] = f"{category_group}.{template_id}"
                            matching.append(instance)

                if not matching:
                    return None

                random.shuffle(matching)
                for instance in matching:
                    if instance["template_id"] not in used_templates:
                        return instance
                return random.choice(matching)

            # Allow multiple instances of same type, but ensure variety where possible
            category_counts = {}
            for _ in range(option_count):
                categories = _roll_room_category()

                # Track how many of this category type we've added
                category_key = tuple(sorted(categories))
                count = category_counts.get(category_key, 0)
                category_counts[category_key] = count + 1

                # For repeated categories, try to get different instances
                # but allow same instance if that's all that's available
                used_templates = set()
                for existing in instances:
                    if existing.get("template_id"):
                        existing_cats = existing.get("categories", [])
                        if any(cat in existing_cats for cat in categories):
                            used_templates.add(existing["template_id"])

                instance = _pick_instance(categories, used_templates)
                if not instance:
                    continue
                instances.append(instance)

        # Ensure we always return at least one instance per stage
        if not instances:
            instances.extend(self._get_instances_by_category(["battle"], 1))

        return instances

    def grant_positive_buffs(self, run_id: str, count: int = 2) -> List[Dict[str, str]]:
        """Grant positive buffs to the team and return their display data."""
        positive_templates = []
        for category_group, templates in self.instance_templates.items():
            for template_id, template in templates.items():
                categories = template.get("categories", [])
                if "buff" in categories and "curse" not in categories and "nightmare" not in categories:
                    positive_templates.append((category_group, template_id, template))

        if not positive_templates:
            return []

        selected = random.sample(positive_templates, min(count, len(positive_templates)))
        buff_summaries: List[Dict[str, str]] = []

        for _, template_id, template in selected:
            buff_name = template.get("name", "Dream Blessing")
            buff_description = template.get("description", "A gentle boon from the dream.")
            effect_data = template.get("effect_data", {})
            duration = template.get("duration", "floor")

            self.apply_buff(
                run_id=run_id,
                buff_type="buff",
                buff_name=buff_name,
                buff_description=buff_description,
                scope="team",
                effect_data=effect_data,
                duration=duration
            )
            buff_summaries.append({
                "name": buff_name,
                "description": buff_description,
            })

        return buff_summaries

    def get_active_run_for_user(self, guild_id: int, user_id: int) -> Optional[Dict]:
        """Get the currently active Dream Dive run for a specific user in a guild."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT r.*
            FROM dream_rogue_runs r
            JOIN dream_rogue_participants p ON r.run_id = p.run_id
            WHERE r.guild_id = ? AND r.is_active = 1 AND p.discord_user_id = ?
            ORDER BY r.created_at DESC
            LIMIT 1
        """, (guild_id, user_id))

        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

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

    def _create_miniboss_instance(self, floor: int) -> Dict:
        """Create a mini-boss instance."""
        return {
            "template_id": "mini_boss",
            "name": f"Mini Boss — Floor {floor}",
            "description": "A tougher foe stands in your way.",
            "categories": ["battle", "mini_boss"],
            "scope": "team",
            "risk_level": "high",
            "effect_data": {
                "type": "battle",
                "floor": floor,
                "battle_format": "doubles",
                "num_opponents": 2,
                "dreamlite_multiplier": 2,
                "miniboss": True
            }
        }

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
                "floor": floor,
                "battle_format": "raid",
                "num_opponents": 1,
                "raid_stat_multiplier": 2.5,
                "raid_hp_multiplier": 6.0
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
