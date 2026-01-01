#!/usr/bin/env python3
"""
Script to update trainer Red's rank and omni ring gimmicks
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path to import database
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import PlayerDatabase

def main():
    db = PlayerDatabase("data/players.db")
    conn = db.get_connection()
    cursor = conn.cursor()

    # Check if Red exists
    cursor.execute("SELECT discord_user_id, trainer_name, rank_tier_number, omni_ring_gimmicks FROM trainers WHERE trainer_name = 'Red'")
    red = cursor.fetchone()

    if red:
        print(f"Found trainer Red (ID: {red['discord_user_id']})")
        print(f"Current rank: Tier {red['rank_tier_number']}")
        print(f"Current gimmicks: {red['omni_ring_gimmicks']}")

        # Update Red's rank to Challenger 1 (tier 8) and add mega evolution
        cursor.execute("""
            UPDATE trainers
            SET rank_tier_number = 8,
                rank_tier_name = 'Challenger',
                ladder_points = 100,
                has_omni_ring = 1,
                omni_ring_gimmicks = 'mega',
                updated_at = CURRENT_TIMESTAMP
            WHERE trainer_name = 'Red'
        """)

        conn.commit()
        print("\n✓ Updated Red's profile:")
        print("  - Rank: Challenger 1 (Tier 8)")
        print("  - Omni Ring: Enabled with Mega Evolution")
    else:
        print("Trainer Red not found in database!")
        print("Available trainers:")
        cursor.execute("SELECT trainer_name FROM trainers LIMIT 10")
        for row in cursor.fetchall():
            print(f"  - {row['trainer_name']}")

    conn.close()

if __name__ == "__main__":
    main()
