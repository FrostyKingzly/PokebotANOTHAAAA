
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
candidates = [
    ROOT/"cogs"/"battle_cog.py",
    ROOT/"pokemon_battle_patch_9"/"cogs"/"battle_cog.py",
    ROOT/"pokemon_battle_patch_8"/"cogs"/"battle_cog.py",
    Path("cogs/battle_cog.py"),
]

target = None
for c in candidates:
    if c.exists():
        target = c
        break

if not target:
    print("❌ Could not find cogs/battle_cog.py near this hotfix. Place this tools/ folder at your project root.")
    sys.exit(1)

code = target.read_text(encoding="utf-8")

sbi_idx = code.find("async def start_battle_ui(")
if sbi_idx == -1:
    print("❌ start_battle_ui not found; no changes made.")
    sys.exit(2)

block_end = code.find("\\n    def ", sbi_idx)
if block_end == -1:
    block_end = code.find("class BattleView", sbi_idx)
    if block_end == -1:
        block_end = len(code)

block = code[sbi_idx:block_end]

if "interaction.response.defer()" not in block:
    block = block.replace(
        "battle = self.battle_engine.get_battle(battle_id)",
        "battle = self.battle_engine.get_battle(battle_id)\\n        # Ensure multiple sends from select callback\\n        try:\\n            if not interaction.response.is_done():\\n                await interaction.response.defer()\\n        except Exception:\\n            pass"
    )

block = block.replace("await interaction.response.send_message(", "await interaction.followup.send(")

code = code[:sbi_idx] + block + code[block_end:]

if "_create_battle_view(self, battle)" not in code:
    bv_start = code.find("class BattleView")
    if bv_start == -1:
        print("❌ Could not locate class BattleView. Aborting to avoid breaking your file.")
        sys.exit(3)
    code = code[:bv_start] + '\n    def _create_battle_view(self, battle) -> discord.ui.View:\n        """Factory for the main battle buttons view."""\n        return BattleView(\n            battle_id=battle.battle_id,\n            battler_id=battle.trainer.battler_id,\n            battle_engine=self.battle_engine,\n        )\n'[1:-1] + code[bv_start:]

backup = target.with_suffix(".py.bak")
backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
target.write_text(code, encoding="utf-8")

print(f"✅ Hotfix applied to {target}. A backup was saved to {backup}.")
