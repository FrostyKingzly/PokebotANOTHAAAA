"""Weather Manager

Handles region-based weather rotations with manual overrides and random rolls.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Dict, Optional


class WeatherManager:
    """Track and rotate weather for cities and wild areas."""

    DEFAULT_STATE_PATH = Path("config/weather_state.json")

    # Allowed weather options per region
    REGION_SETTINGS: Dict[str, Dict] = {
        "city": {
            "display_name": "Reverie City",
            "allowed_weathers": [
                "cloudy",
                "sunshine",
                "rain",
                "snowing",
                "thunder_storm",
                "gentle_skies",
            ],
            "random_duration_minutes": (30, 90),
        },
        "wild_area_alpha": {
            "display_name": "Wild Area Alpha (Forest)",
            # Same as city but without snowing or sunshine
            "allowed_weathers": ["cloudy", "rain", "thunder_storm", "gentle_skies"],
            "random_duration_minutes": (30, 90),
        },
        "wild_area_beta": {
            "display_name": "Wild Area Beta (Canyon)",
            "allowed_weathers": [
                "cloudy",
                "sunshine",
                "rain",
                "thunder_storm",
                "gentle_skies",
            ],
            "random_duration_minutes": (30, 90),
        },
        "wild_area_charlie": {
            "display_name": "Wild Area Charlie (Desert)",
            "allowed_weathers": ["sunshine", "heatwave", "sandstorm"],
            "random_duration_minutes": (30, 90),
        },
        "wild_area_delta": {
            "display_name": "Wild Area Delta (Tundra)",
            "allowed_weathers": ["cloudy", "snowing", "blizzard"],
            "random_duration_minutes": (30, 90),
        },
    }

    def __init__(self, state_path: Path | str = DEFAULT_STATE_PATH):
        self.state_path = Path(state_path)
        self.state: Dict[str, Dict] = {}
        self._load_state()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def _load_state(self):
        if self.state_path.exists():
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.state = data
            except (json.JSONDecodeError, OSError):
                self.state = {}

        # Ensure defaults for every region
        for region_id, settings in self.REGION_SETTINGS.items():
            default_allowed = settings.get("allowed_weathers", [])
            self.state.setdefault(
                region_id,
                {
                    "mode": "random",  # "random" or "manual"
                    "current_weather": None,
                    "expires_at": 0,
                    "random_pool": list(default_allowed),
                },
            )

            # Backfill random pools for existing state files
            region_state = self.state.get(region_id, {})
            if not region_state.get("random_pool"):
                region_state["random_pool"] = list(default_allowed)

        self._save_state()

    def _save_state(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)

    # ------------------------------------------------------------------
    # Region resolution helpers
    # ------------------------------------------------------------------
    def resolve_region(
        self,
        location_id: Optional[str] = None,
        wild_area_state: Optional[Dict] = None,
    ) -> Optional[str]:
        """Determine which weather region should be used.

        Preference order:
        1. Active wild area state (area_id must match a known region)
        2. City (used for all standard locations)
        """

        if wild_area_state:
            area_id = wild_area_state.get("area_id")
            if area_id in self.REGION_SETTINGS:
                return area_id
            # Fallback to city weather if the wild area isn't registered
            if not location_id:
                return "city"

        # If there's a location_id but no matching wild area, treat it as city weather
        if location_id:
            return "city"

        return None

    # ------------------------------------------------------------------
    # Weather state management
    # ------------------------------------------------------------------
    def _roll_random_weather(self, region_id: str, now: Optional[float] = None) -> Dict:
        now = now or time.time()
        settings = self.REGION_SETTINGS[region_id]
        pool = self.state.get(region_id, {}).get("random_pool") or settings.get(
            "allowed_weathers", []
        )

        if not pool:
            pool = settings.get("allowed_weathers", [])

        weather = random.choice(pool)
        expires_at = now + (12 * 60 * 60)  # Rotate every 12 hours

        self.state[region_id].update(
            {
                "mode": "random",
                "current_weather": weather,
                "expires_at": expires_at,
                "random_pool": list(pool),
            }
        )
        self._save_state()
        return self.state[region_id]

    def _maybe_refresh_region(self, region_id: str, now: Optional[float] = None):
        now = now or time.time()
        region_state = self.state.get(region_id)
        if not region_state:
            return

        mode = region_state.get("mode", "random")
        expires_at = region_state.get("expires_at", 0) or 0

        if mode == "random" and (not region_state.get("current_weather") or expires_at <= now):
            self._roll_random_weather(region_id, now=now)

    def get_region_weather(
        self, region_id: str, *, now: Optional[float] = None
    ) -> Optional[Dict]:
        """Return the active weather for a region, refreshing if needed."""

        if region_id not in self.REGION_SETTINGS:
            return None

        self._maybe_refresh_region(region_id, now=now)
        return self.state.get(region_id)

    def get_weather_for_context(
        self,
        location_id: Optional[str] = None,
        wild_area_state: Optional[Dict] = None,
        *,
        now: Optional[float] = None,
    ) -> Optional[Dict]:
        """Resolve and return weather data for a player context."""

        region_id = self.resolve_region(location_id, wild_area_state)
        if not region_id:
            return None

        weather_state = self.get_region_weather(region_id, now=now)
        if not weather_state:
            return None

        return {
            **weather_state,
            "region_id": region_id,
            "region_name": self.REGION_SETTINGS[region_id]["display_name"],
            "allowed_weathers": self.REGION_SETTINGS[region_id]["allowed_weathers"],
        }

    def set_weather(self, region_id: str, weather: str) -> Dict:
        """Force-set weather for a region indefinitely until changed."""

        if region_id not in self.REGION_SETTINGS:
            raise ValueError("Unknown region")

        normalized = weather.lower().strip()
        allowed = self.REGION_SETTINGS[region_id]["allowed_weathers"]
        if normalized not in allowed:
            raise ValueError(
                f"Weather '{weather}' is not allowed for {self.REGION_SETTINGS[region_id]['display_name']}"
            )

        self.state[region_id].update(
            {
                "mode": "manual",
                "current_weather": normalized,
                "expires_at": 0,
            }
        )
        self._save_state()
        return self.state[region_id]

    def set_random_mode(
        self, region_id: str, *, allowed_weathers: Optional[list[str]] = None, reroll: bool = True
    ) -> Dict:
        """Return a region to random weather rotation."""

        if region_id not in self.REGION_SETTINGS:
            raise ValueError("Unknown region")

        region_allowed = self.REGION_SETTINGS[region_id].get("allowed_weathers", [])
        pool = allowed_weathers or list(region_allowed)

        if not pool:
            raise ValueError("At least one weather type must be provided for random rotation")

        invalid = [w for w in pool if w not in region_allowed]
        if invalid:
            allowed_display = ", ".join(region_allowed)
            raise ValueError(
                f"Weather options {', '.join(invalid)} are not allowed for this region. "
                f"Allowed values: {allowed_display}"
            )

        self.state.setdefault(region_id, {})["random_pool"] = list(pool)

        if reroll or self.state.get(region_id, {}).get("mode") != "random":
            return self._roll_random_weather(region_id)

        self.state[region_id]["mode"] = "random"
        self._maybe_refresh_region(region_id)
        self._save_state()
        return self.state[region_id]

