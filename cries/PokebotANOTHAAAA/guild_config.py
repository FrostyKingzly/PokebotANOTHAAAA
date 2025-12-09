"""
Guild-level configuration helpers (e.g., ranked announcement channels).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

CONFIG_PATH = Path("config/guild_config.json")


def _load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
            json.dump({}, handle, indent=2)
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _save_config(data: Dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def set_rank_announcement_channel(guild_id: int, channel_id: int) -> None:
    """Remember which channel should receive ranked match announcements."""
    data = _load_config()
    entry = data.get(str(guild_id)) or {}
    entry["rank_announcement_channel_id"] = int(channel_id)
    data[str(guild_id)] = entry
    _save_config(data)


def get_rank_announcement_channel_id(guild_id: int) -> Optional[int]:
    """Return the announcement channel id for this guild, if configured."""
    data = _load_config()
    entry = data.get(str(guild_id)) or {}
    chan = entry.get("rank_announcement_channel_id")
    return int(chan) if chan is not None else None
