"""
Session Manager - Handles admin-led group sessions
Allows admins to create sessions where players join and are controlled as a group
"""

import json
import sqlite3
import uuid
from typing import Optional, Dict, List, Any
from database import PlayerDatabase


class SessionManager:
    """Manages admin-led group sessions"""

    def __init__(self, db: PlayerDatabase):
        self.db = db

    # ============================================================
    # SESSION OPERATIONS
    # ============================================================

    def create_session(self, guild_id: int, admin_id: int, session_name: str,
                      channel_id: int, current_location_id: str = None) -> str:
        """
        Create a new session.
        Returns session_id
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        session_id = str(uuid.uuid4())

        try:
            cursor.execute("""
                INSERT INTO sessions (
                    session_id, guild_id, admin_id, session_name,
                    channel_id, current_location_id, is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """, (session_id, guild_id, admin_id, session_name, channel_id, current_location_id))

            conn.commit()
            return session_id
        except Exception as e:
            print(f"Error creating session: {e}")
            return None
        finally:
            conn.close()

    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session by ID"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def get_active_session_by_guild(self, guild_id: int) -> Optional[Dict]:
        """Get active session for a guild"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM sessions
            WHERE guild_id = ? AND is_active = 1
            ORDER BY created_at DESC
            LIMIT 1
        """, (guild_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def update_session_location(self, session_id: str, location_id: str) -> bool:
        """Update session's current location"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE sessions
            SET current_location_id = ?
            WHERE session_id = ?
        """, (location_id, session_id))

        conn.commit()
        conn.close()
        return True

    def set_join_message(self, session_id: str, message_id: int, channel_id: int) -> bool:
        """Store the join message ID and channel for later updates"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE sessions
            SET join_message_id = ?, join_message_channel_id = ?
            WHERE session_id = ?
        """, (message_id, channel_id, session_id))

        conn.commit()
        conn.close()
        return True

    def end_session(self, session_id: str) -> bool:
        """End a session and release all participants"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # Get all participants
            cursor.execute("""
                SELECT discord_user_id FROM session_participants
                WHERE session_id = ?
            """, (session_id,))

            participants = [row['discord_user_id'] for row in cursor.fetchall()]

            # Remove session participants
            cursor.execute("""
                DELETE FROM session_participants
                WHERE session_id = ?
            """, (session_id,))

            # Mark session as inactive
            cursor.execute("""
                UPDATE sessions
                SET is_active = 0, ended_at = CURRENT_TIMESTAMP
                WHERE session_id = ?
            """, (session_id,))

            conn.commit()
            return True
        except Exception as e:
            print(f"Error ending session: {e}")
            return False
        finally:
            conn.close()

    # ============================================================
    # PARTICIPANT OPERATIONS
    # ============================================================

    def add_participant(self, session_id: str, discord_user_id: int) -> bool:
        """Add a participant to a session"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        # Get current player location for snapshot
        cursor.execute("""
            SELECT current_location_id FROM trainers
            WHERE discord_user_id = ?
        """, (discord_user_id,))

        trainer_row = cursor.fetchone()

        if not trainer_row:
            conn.close()
            return False

        snapshot_location = trainer_row['current_location_id']

        try:
            cursor.execute("""
                INSERT INTO session_participants (
                    session_id, discord_user_id, snapshot_location
                )
                VALUES (?, ?, ?)
            """, (session_id, discord_user_id, snapshot_location))

            # Update player's location to match session location
            cursor.execute("""
                UPDATE trainers
                SET current_location_id = (
                    SELECT current_location_id FROM sessions WHERE session_id = ?
                )
                WHERE discord_user_id = ?
            """, (session_id, discord_user_id))

            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Already in session
            return False
        finally:
            conn.close()

    def remove_participant(self, discord_user_id: int) -> bool:
        """Remove a participant from their current session"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        # Get participant's snapshot location
        cursor.execute("""
            SELECT snapshot_location FROM session_participants
            WHERE discord_user_id = ?
        """, (discord_user_id,))

        row = cursor.fetchone()

        if not row:
            conn.close()
            return False

        snapshot_location = row['snapshot_location']

        # Remove from session
        cursor.execute("""
            DELETE FROM session_participants
            WHERE discord_user_id = ?
        """, (discord_user_id,))

        # Restore original location
        if snapshot_location:
            cursor.execute("""
                UPDATE trainers
                SET current_location_id = ?
                WHERE discord_user_id = ?
            """, (snapshot_location, discord_user_id))

        conn.commit()
        conn.close()
        return True

    def get_session_participants(self, session_id: str) -> List[int]:
        """Get list of Discord user IDs in session"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT discord_user_id FROM session_participants
            WHERE session_id = ?
            ORDER BY joined_at
        """, (session_id,))

        rows = cursor.fetchall()
        conn.close()

        return [row['discord_user_id'] for row in rows]

    def is_in_session(self, discord_user_id: int) -> bool:
        """Check if player is in a session"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 1 FROM session_participants
            WHERE discord_user_id = ?
        """, (discord_user_id,))

        result = cursor.fetchone()
        conn.close()

        return result is not None

    def get_player_session(self, discord_user_id: int) -> Optional[Dict]:
        """Get the session a player is currently in"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT s.* FROM sessions s
            JOIN session_participants sp ON s.session_id = sp.session_id
            WHERE sp.discord_user_id = ? AND s.is_active = 1
        """, (discord_user_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    # ============================================================
    # GROUP OPERATIONS
    # ============================================================

    def move_session_to_location(self, session_id: str, location_id: str,
                                 stamina_cost: int = 0) -> tuple[bool, str]:
        """
        Move entire session to a new location, deducting stamina from all participants.
        Returns (success, message)
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        # Get all participants
        cursor.execute("""
            SELECT discord_user_id FROM session_participants
            WHERE session_id = ?
        """, (session_id,))

        participants = [row['discord_user_id'] for row in cursor.fetchall()]

        if not participants:
            conn.close()
            return False, "Session has no participants."

        # Check if all participants have enough stamina (if cost > 0)
        if stamina_cost > 0:
            insufficient_members = []
            for user_id in participants:
                cursor.execute("""
                    SELECT stamina_current, trainer_name FROM trainers
                    WHERE discord_user_id = ?
                """, (user_id,))

                row = cursor.fetchone()

                if not row or row['stamina_current'] < stamina_cost:
                    name = row['trainer_name'] if row else f"User {user_id}"
                    insufficient_members.append(name)

            if insufficient_members:
                conn.close()
                return False, f"Not enough stamina: {', '.join(insufficient_members)}"

            # Deduct stamina from all participants
            for user_id in participants:
                cursor.execute("""
                    UPDATE trainers
                    SET stamina_current = stamina_current - ?
                    WHERE discord_user_id = ?
                """, (stamina_cost, user_id))

        # Update all participant locations
        for user_id in participants:
            cursor.execute("""
                UPDATE trainers
                SET current_location_id = ?
                WHERE discord_user_id = ?
            """, (location_id, user_id))

        # Update session location
        cursor.execute("""
            UPDATE sessions
            SET current_location_id = ?
            WHERE session_id = ?
        """, (location_id, session_id))

        conn.commit()
        conn.close()

        if stamina_cost > 0:
            return True, f"Session moved to new location! Stamina cost: {stamina_cost} per person."
        else:
            return True, "Session moved to new location!"

    def adjust_participant_stamina(self, discord_user_id: int, amount: int) -> tuple[bool, int]:
        """
        Adjust stamina for a participant. Can be positive or negative.
        Returns (success, new_stamina)
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT stamina_current, stamina_max FROM trainers
            WHERE discord_user_id = ?
        """, (discord_user_id,))

        row = cursor.fetchone()

        if not row:
            conn.close()
            return False, 0

        current_stamina = row['stamina_current']
        max_stamina = row['stamina_max']

        # Calculate new stamina (clamped between 0 and max)
        new_stamina = max(0, min(max_stamina, current_stamina + amount))

        cursor.execute("""
            UPDATE trainers
            SET stamina_current = ?
            WHERE discord_user_id = ?
        """, (new_stamina, discord_user_id))

        conn.commit()
        conn.close()

        return True, new_stamina

    def restore_participant_stamina(self, discord_user_id: int) -> tuple[bool, int]:
        """
        Restore participant's stamina to max.
        Returns (success, new_stamina)
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT stamina_max FROM trainers
            WHERE discord_user_id = ?
        """, (discord_user_id,))

        row = cursor.fetchone()

        if not row:
            conn.close()
            return False, 0

        max_stamina = row['stamina_max']

        cursor.execute("""
            UPDATE trainers
            SET stamina_current = stamina_max
            WHERE discord_user_id = ?
        """, (discord_user_id,))

        conn.commit()
        conn.close()

        return True, max_stamina
