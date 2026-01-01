#!/usr/bin/env python3
"""
Script to reset all trainer data to a clean slate.
Keeps registration info but removes Pokemon, items, rank, points, etc.
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'players.db')

def reset_all_trainer_data():
    """Reset all trainer data while preserving registration information."""

    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Get all trainers first
        cursor.execute("SELECT discord_user_id, trainer_name FROM trainers")
        trainers = cursor.fetchall()

        if not trainers:
            print("No trainers found in database.")
            return

        print(f"Found {len(trainers)} trainer(s) to reset.")
        print("\nResetting trainer data...")

        # 1. Delete all Pokemon instances
        cursor.execute("DELETE FROM pokemon_instances")
        pokemon_deleted = cursor.rowcount
        print(f"  - Deleted {pokemon_deleted} Pokemon")

        # 2. Delete all inventory items
        cursor.execute("DELETE FROM inventory")
        items_deleted = cursor.rowcount
        print(f"  - Deleted {items_deleted} inventory items")

        # 3. Delete all Pokedex entries
        cursor.execute("DELETE FROM pokedex")
        pokedex_deleted = cursor.rowcount
        print(f"  - Deleted {pokedex_deleted} Pokedex entries")

        # 4. Delete all parties
        cursor.execute("DELETE FROM parties")
        parties_deleted = cursor.rowcount
        print(f"  - Deleted {parties_deleted} parties")

        # 5. Delete all Pokemon memories
        cursor.execute("DELETE FROM pokemon_memories")
        memories_deleted = cursor.rowcount
        print(f"  - Deleted {memories_deleted} Pokemon memories")

        # 6. Delete all battle cooldowns
        cursor.execute("DELETE FROM battle_cooldowns")
        cooldowns_deleted = cursor.rowcount
        print(f"  - Deleted {cooldowns_deleted} battle cooldowns")

        # 7. Reset trainer stats to initial values
        # The initial setup from registration:
        # - Boon stat starts at rank 2
        # - Bane stat starts at rank 0
        # - Other stats start at rank 1
        # - All points start at 0
        # - Money starts at 5000
        # - Rank starts at Qualifier (tier 1, 0 points)

        for discord_user_id, trainer_name in trainers:
            # Get the trainer's boon and bane stats
            cursor.execute("""
                SELECT boon_stat, bane_stat
                FROM trainers
                WHERE discord_user_id = ?
            """, (discord_user_id,))

            result = cursor.fetchone()
            if not result:
                continue

            boon_stat, bane_stat = result

            # Calculate initial ranks based on boon/bane
            heart_rank = 2 if boon_stat == 'heart' else (0 if bane_stat == 'heart' else 1)
            insight_rank = 2 if boon_stat == 'insight' else (0 if bane_stat == 'insight' else 1)
            charisma_rank = 2 if boon_stat == 'charisma' else (0 if bane_stat == 'charisma' else 1)
            fortitude_rank = 2 if boon_stat == 'fortitude' else (0 if bane_stat == 'fortitude' else 1)
            will_rank = 2 if boon_stat == 'will' else (0 if bane_stat == 'will' else 1)

            # Calculate initial stamina based on fortitude rank
            stamina_max = 5 + fortitude_rank

            # Update the trainer with reset values
            cursor.execute("""
                UPDATE trainers
                SET
                    money = 5000,
                    heart_rank = ?,
                    heart_points = 0,
                    insight_rank = ?,
                    insight_points = 0,
                    charisma_rank = ?,
                    charisma_points = 0,
                    fortitude_rank = ?,
                    fortitude_points = 0,
                    will_rank = ?,
                    will_points = 0,
                    stamina_current = ?,
                    stamina_max = ?,
                    last_stamina_update = ?,
                    rank_tier_name = 'Qualifier',
                    rank_tier_number = 1,
                    ladder_points = 0,
                    has_promotion_ticket = 0,
                    ticket_tier = NULL,
                    rank_pending_tier = NULL,
                    has_omni_ring = 0,
                    omni_ring_gimmicks = NULL,
                    following_pokemon_id = NULL,
                    partner_pokemon_id = NULL,
                    battle_theme_url = NULL,
                    victory_theme_url = NULL,
                    current_location_id = NULL,
                    updated_at = ?
                WHERE discord_user_id = ?
            """, (
                heart_rank, insight_rank, charisma_rank, fortitude_rank, will_rank,
                stamina_max, stamina_max,  # Start with full stamina
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                discord_user_id
            ))

            print(f"  - Reset trainer: {trainer_name}")

        # Commit all changes
        conn.commit()

        print(f"\n✓ Successfully reset {len(trainers)} trainer(s) to clean slate!")
        print("\nTrainers can now start fresh with:")
        print("  • 5000 Pokédollars")
        print("  • Initial social stat ranks (based on their boon/bane)")
        print("  • Qualifier rank (tier 1)")
        print("  • No Pokemon, items, or Pokedex entries")

    except Exception as e:
        print(f"\n✗ Error resetting trainer data: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    print("=" * 60)
    print("TRAINER DATA RESET UTILITY")
    print("=" * 60)
    print("\nThis will reset ALL trainer data to a clean slate.")
    print("Registration info will be preserved, but:")
    print("  - All Pokemon will be deleted")
    print("  - All items will be deleted")
    print("  - All Pokedex entries will be deleted")
    print("  - Rank will be reset to Qualifier")
    print("  - Social stats will be reset to initial values")
    print("  - Money will be reset to 5000")
    print("\n" + "=" * 60)

    response = input("\nAre you sure you want to proceed? (yes/no): ").strip().lower()

    if response == 'yes':
        print()
        reset_all_trainer_data()
    else:
        print("\nReset cancelled.")
