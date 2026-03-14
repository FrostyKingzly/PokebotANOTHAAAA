"""
Battle Theme Configuration
Loads local battle and victory themes from disk.
"""

from typing import List, Tuple
import random
from pathlib import Path


MUSIC_ROOT = Path("PokeMusic")
CASUAL_DIR = MUSIC_ROOT / "Casual"
BOSS_DIR = MUSIC_ROOT / "Boss"
VICTORY_DIR = MUSIC_ROOT / "Victory"
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".opus"}


def _list_audio_files(directory: Path) -> List[str]:
    """Return sorted playable audio file paths from a directory."""
    if not directory.exists() or not directory.is_dir():
        return []

    files = [
        str(path)
        for path in sorted(directory.iterdir())
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
    ]
    return files


def _pick_random(files: List[str], fallback_files: List[str]) -> str:
    """Pick a random file from files, falling back to fallback_files."""
    pool = files or fallback_files
    if not pool:
        raise RuntimeError("No music files found. Add tracks under PokeMusic/Casual, PokeMusic/Boss, and PokeMusic/Victory.")
    return random.choice(pool)


def get_all_theme_tracks() -> List[str]:
    """Return all known local tracks used by the battle music system."""
    all_tracks = _list_audio_files(CASUAL_DIR) + _list_audio_files(BOSS_DIR) + _list_audio_files(VICTORY_DIR)
    # Deduplicate while preserving order
    return list(dict.fromkeys(all_tracks))


def get_random_npc_theme() -> Tuple[str, str]:
    """Get random casual battle + victory tracks from local folders."""
    casual_tracks = _list_audio_files(CASUAL_DIR)
    boss_tracks = _list_audio_files(BOSS_DIR)
    victory_tracks = _list_audio_files(VICTORY_DIR)

    battle_theme = _pick_random(casual_tracks, boss_tracks)
    victory_theme = _pick_random(victory_tracks, casual_tracks + boss_tracks)
    return battle_theme, victory_theme


def get_ranked_npc_theme() -> Tuple[str, str]:
    """Get random boss/ranked battle + victory tracks from local folders."""
    boss_tracks = _list_audio_files(BOSS_DIR)
    casual_tracks = _list_audio_files(CASUAL_DIR)
    victory_tracks = _list_audio_files(VICTORY_DIR)

    battle_theme = _pick_random(boss_tracks, casual_tracks)
    victory_theme = _pick_random(victory_tracks, boss_tracks + casual_tracks)
    return battle_theme, victory_theme


def get_raid_theme() -> Tuple[str, str]:
    """Use the boss track pool for raid battles."""
    return get_ranked_npc_theme()
