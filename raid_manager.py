"""Raid encounter manager and placeholder raid boss generation."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from database import MovesDatabase
from learnset_database import LearnsetDatabase
from models import Pokemon


@dataclass
class RaidPokemonConfig:
    """Lightweight configuration for a raid boss."""

    pokemon: Pokemon
    move_ids: List[str]
    source: str = "random"
    raid_stat_multiplier: float = 2.0
    enrages_after_turns: Optional[int] = None


@dataclass
class RaidEncounter:
    """Represents an active raid encounter at a location."""

    raid_id: str
    location_id: str
    created_by: int
    created_at: float
    pokemon_config: RaidPokemonConfig

    @property
    def summary(self) -> Dict:
        """Expose a dict summary for embed builders/views."""

        pokemon = self.pokemon_config.pokemon
        return {
            "raid_id": self.raid_id,
            "species_name": pokemon.species_name,
            "species_dex_number": pokemon.species_dex_number,
            "level": pokemon.level,
            "source": self.pokemon_config.source,
            "move_ids": list(self.pokemon_config.move_ids),
        }


class RaidManager:
    """Tracks active raid encounters and provides simple raid boss scaffolding."""

    MAX_LEVEL = 300

    def __init__(self, species_db):
        self.species_db = species_db
        self.moves_db = MovesDatabase("data/moves.json")
        self.learnset_db = LearnsetDatabase("data/learnsets.json")
        self.active_raids: Dict[str, RaidEncounter] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def create_manual_raid(
        self,
        location_id: str,
        species_identifier: str,
        level: int,
        *,
        created_by: int,
        move_ids: Optional[List[str]] = None,
        source: str = "manual",
    ) -> RaidEncounter:
        """Create a raid encounter using species + level (and optional moves)."""

        level = max(1, min(level, self.MAX_LEVEL))
        species_data = self.species_db.get_species(species_identifier)
        if not species_data:
            raise ValueError(f"Unknown species: {species_identifier}")

        pokemon = Pokemon(
            species_data=species_data,
            level=level,
            owner_discord_id=None,
        )
        # Mark this Pokemon as a raid boss for downstream systems
        pokemon.is_raid_boss = True
        pokemon.raid_stat_multiplier = 2.0
        pokemon.raid_level_cap = self.MAX_LEVEL

        resolved_moves = move_ids or self._generate_raid_moveset(species_data["name"], level)

        config = RaidPokemonConfig(
            pokemon=pokemon,
            move_ids=resolved_moves,
            source=source,
        )

        encounter = RaidEncounter(
            raid_id=str(uuid.uuid4()),
            location_id=location_id,
            created_by=created_by,
            created_at=time.time(),
            pokemon_config=config,
        )

        self.active_raids[location_id] = encounter
        return encounter

    def get_raid(self, location_id: str) -> Optional[RaidEncounter]:
        """Return the active raid for a given location, if any."""

        return self.active_raids.get(location_id)

    def clear_raid(self, location_id: str) -> None:
        """Remove an active raid from a location."""

        self.active_raids.pop(location_id, None)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _generate_raid_moveset(self, species_name: str, level: int) -> List[str]:
        """Pick up to six moves, prioritizing attacking moves."""

        available_moves = self.learnset_db.get_moves_at_level(species_name, level)
        attack_moves: List[str] = []
        support_moves: List[str] = []

        for move_id in available_moves:
            move_data = self.moves_db.get_move(move_id) or {}
            if move_data.get("category") in {"physical", "special"}:
                if move_id not in attack_moves:
                    attack_moves.append(move_id)
            else:
                if move_id not in support_moves:
                    support_moves.append(move_id)

        # Fill with attacking options first
        selected: List[str] = attack_moves[:4]
        selected.extend(support_moves[: max(0, 6 - len(selected))])

        if len(selected) < 6:
            fallback = self.learnset_db.get_starting_moves(species_name, level=level, max_moves=6)
            for move_id in fallback:
                if move_id not in selected:
                    selected.append(move_id)
                if len(selected) >= 6:
                    break

        return selected[:6]
