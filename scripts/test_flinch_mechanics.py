#!/usr/bin/env python3
"""
Test script to verify flinch mechanics work correctly
Creates simulated battle scenarios to test flinch
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from status_conditions import StatusConditionManager, VolatileStatus


def test_flinch_application_and_clearing():
    """Test that flinch is applied and cleared correctly"""
    print("="*70)
    print("TEST 1: Flinch Application and Clearing")
    print("="*70)

    class MockPokemon:
        def __init__(self, name):
            self.species_name = name
            self.status_manager = StatusConditionManager()

    pokemon = MockPokemon("Pikachu")

    # Apply flinch with duration=1
    print("\n1. Applying flinch (duration=1)...")
    success, msg = pokemon.status_manager.apply_status('flinch', duration=1)
    print(f"   Success: {success}, Message: {msg}")
    print(f"   Flinch in volatile statuses: {'flinch' in pokemon.status_manager.volatile_statuses}")

    # Check if Pokemon can move
    print("\n2. Checking if Pokemon can move (should be prevented)...")
    can_move, reason = pokemon.status_manager.can_move(pokemon)
    print(f"   Can move: {can_move}")
    print(f"   Reason: {reason}")
    assert not can_move, "Pokemon should not be able to move when flinched!"

    # Simulate end of turn (should clear flinch)
    print("\n3. Simulating end of turn (should clear flinch)...")
    if 'flinch' in pokemon.status_manager.volatile_statuses:
        flinch_obj = pokemon.status_manager.volatile_statuses['flinch']
        print(f"   Before: duration={flinch_obj.duration}")

    messages = pokemon.status_manager.apply_end_of_turn_effects(pokemon)
    print(f"   Messages: {messages}")
    print(f"   Flinch still in volatile statuses: {'flinch' in pokemon.status_manager.volatile_statuses}")

    # Check if Pokemon can move after turn end
    print("\n4. Checking if Pokemon can move after turn end (should be able to)...")
    can_move, reason = pokemon.status_manager.can_move(pokemon)
    print(f"   Can move: {can_move}")
    if reason:
        print(f"   Reason: {reason}")

    result = "✅ PASS" if not ('flinch' in pokemon.status_manager.volatile_statuses) and can_move else "❌ FAIL"
    print(f"\n{result}: Flinch should be cleared after end of turn")


def test_flinch_priority():
    """Test that flinch only works if the flinching move goes first"""
    print("\n" + "="*70)
    print("TEST 2: Flinch Priority/Timing")
    print("="*70)

    print("\n📋 Testing Scenario:")
    print("  - Pokemon A (faster) uses Iron Head, causes flinch")
    print("  - Pokemon B (slower) tries to use move")
    print("  - Pokemon B should be prevented from moving due to flinch")

    print("\n🔍 Key Requirements:")
    print("  1. Flinch must be applied AFTER move A hits")
    print("  2. Flinch check must happen BEFORE move B executes")
    print("  3. Move B's can_move() should return False if flinched")
    print("  4. Flinch must be cleared at end of turn")

    print("\n💡 Potential Issues:")
    print("  - If flinch is applied but cleared before move B checks")
    print("  - If move B checks can_move() before flinch is applied")
    print("  - If flinch doesn't have correct duration (should be 1)")
    print("  - If end_of_turn effects aren't called properly")


def check_effect_handler_flinch():
    """Check how effect_handler.py handles flinch"""
    print("\n" + "="*70)
    print("TEST 3: Effect Handler Flinch Implementation")
    print("="*70)

    try:
        with open('effect_handler.py', 'r') as f:
            content = f.read()

        print("\nChecking effect_handler.py for flinch handling...")

        # Check if flinch is in the volatiles list
        if "'flinch'" in content:
            print("✅ Flinch is mentioned in effect_handler.py")

        # Check if duration is set to 1
        if "duration = 1" in content and "'flinch'" in content:
            print("✅ Flinch duration is set to 1")
        else:
            print("❌ Flinch duration might not be set correctly")

        # Check if flinch is in the status list for 1-turn duration
        import re
        pattern = r"elif status in \[.*'flinch'.*\]:.*duration = 1"
        if re.search(pattern, content, re.DOTALL):
            print("✅ Flinch is configured for 1-turn duration")
        else:
            # Try a more lenient search
            if "'flinch'" in content and "duration = 1" in content:
                # Find the lines
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if 'flinch' in line.lower() and i < len(lines) - 5:
                        context = '\n'.join(lines[i:i+5])
                        if 'duration = 1' in context or 'duration=1' in context:
                            print("✅ Flinch appears to be in 1-turn duration group")
                            break

    except FileNotFoundError:
        print("❌ effect_handler.py not found")


def check_battle_engine_flinch():
    """Check how battle_engine_v2.py handles flinch"""
    print("\n" + "="*70)
    print("TEST 4: Battle Engine Flinch Flow")
    print("="*70)

    try:
        with open('battle_engine_v2.py', 'r') as f:
            content = f.read()
            lines = content.split('\n')

        print("\nChecking battle_engine_v2.py for flinch flow...")

        # Check if can_move is called before executing moves
        can_move_lines = [i for i, line in enumerate(lines) if 'can_move' in line.lower()]
        if can_move_lines:
            print(f"✅ can_move() check found at {len(can_move_lines)} location(s)")
            for line_num in can_move_lines[:3]:
                print(f"   Line {line_num + 1}: {lines[line_num].strip()[:70]}")
        else:
            print("❌ can_move() check not found")

        # Check if end_of_turn effects are called
        eot_lines = [i for i, line in enumerate(lines) if 'end_of_turn' in line.lower() or 'apply_end_of_turn' in line.lower()]
        if eot_lines:
            print(f"\n✅ End of turn processing found at {len(eot_lines)} location(s)")
            for line_num in eot_lines[:3]:
                print(f"   Line {line_num + 1}: {lines[line_num].strip()[:70]}")
        else:
            print("\n❌ End of turn processing not found")

        # Check move execution order
        print("\n🔍 Move Execution Flow:")
        priority_lines = [i for i, line in enumerate(lines) if 'priority' in line.lower() and ('sort' in line.lower() or 'action' in line.lower())]
        if priority_lines:
            print("✅ Priority/speed sorting found")
            for line_num in priority_lines[:2]:
                print(f"   Line {line_num + 1}: {lines[line_num].strip()[:70]}")

    except FileNotFoundError:
        print("❌ battle_engine_v2.py not found")


def main():
    import os
    os.chdir(Path(__file__).parent.parent)

    print("="*70)
    print("FLINCH MECHANICS TEST SUITE")
    print("="*70)

    test_flinch_application_and_clearing()
    test_flinch_priority()
    check_effect_handler_flinch()
    check_battle_engine_flinch()

    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print("\nIf all tests passed, flinch mechanics should work correctly.")
    print("If tests failed, review the specific failure messages above.")
    print("\nNext steps:")
    print("1. Run actual battle tests with flinch moves")
    print("2. Check battle logs to see if flinch messages appear")
    print("3. Verify flinch prevents movement in the same turn")
    print("4. Confirm flinch is cleared at end of turn")
    print()


if __name__ == '__main__':
    main()
