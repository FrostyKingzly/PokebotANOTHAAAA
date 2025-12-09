"""
Diagnostic script to find what's failing in anime_battle_engine.py
"""

print("Testing anime_battle_engine.py imports step-by-step...\n")

# Test 1: Basic imports
print("1. Testing standard library imports...")
try:
    import re
    import random
    import json
    from typing import Dict, List, Optional, Tuple
    from dataclasses import dataclass
    print("   ✅ Standard library imports OK")
except Exception as e:
    print(f"   ❌ Failed: {e}")
    exit(1)

# Test 2: OpenAI import
print("\n2. Testing openai import...")
try:
    import openai
    print(f"   ✅ openai imported OK (version: {openai.__version__})")
except Exception as e:
    print(f"   ❌ Failed: {e}")
    exit(1)

# Test 3: Local imports
print("\n3. Testing local module imports...")
try:
    from models import Pokemon
    print("   ✅ models.Pokemon imported OK")
except Exception as e:
    print(f"   ❌ Failed to import models.Pokemon: {e}")
    exit(1)

# Test 4: Try to import the whole module
print("\n4. Testing full anime_battle_engine import...")
try:
    import anime_battle_engine
    print("   ✅ anime_battle_engine module loaded!")
except Exception as e:
    print(f"   ❌ Failed to import anime_battle_engine: {e}")
    print("\n   Full traceback:")
    import traceback
    traceback.print_exc()
    exit(1)

# Test 5: Try to import specific class
print("\n5. Testing AnimeBattleEngine class import...")
try:
    from anime_battle_engine import AnimeBattleEngine
    print("   ✅ AnimeBattleEngine class imported OK!")
except Exception as e:
    print(f"   ❌ Failed to import AnimeBattleEngine: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n" + "="*50)
print("🎉 ALL TESTS PASSED!")
print("="*50)
print("\nIf this works but wild_cog.py doesn't, the issue is")
print("in how wild_cog.py is importing. Check that file.")
