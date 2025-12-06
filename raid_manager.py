"""Raid encounter manager and placeholder raid boss generation."""

import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

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
    raid_hp_multiplier: float = 5.0
    enrages_after_turns: Optional[int] = None


@dataclass
class RaidEncounter:
    """Represents an active raid encounter at a location."""

    raid_id: str
    location_id: str
    created_by: int
    created_at: float
    pokemon_config: RaidPokemonConfig
    participants: Dict[int, bool] = field(default_factory=dict)
    invited: Set[int] = field(default_factory=set)
    join_order: List[int] = field(default_factory=list)

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
            "ready_count": len([pid for pid, ready in self.participants.items() if ready]),
            "participant_count": len(self.participants),
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

        resolved_moves = move_ids or self._generate_raid_moveset(species_data["name"], level)

        pokemon = Pokemon(
            species_data=species_data,
            level=level,
            owner_discord_id=None,
            moves=resolved_moves,
        )
        # Mark this Pokemon as a raid boss for downstream systems
        pokemon.is_raid_boss = True
        pokemon.raid_stat_multiplier = 2.0
        pokemon.raid_hp_multiplier = 5.0
        pokemon.raid_level_cap = self.MAX_LEVEL
        pokemon._calculate_stats()
        pokemon.current_hp = pokemon.max_hp

        config = RaidPokemonConfig(
            pokemon=pokemon,
            move_ids=resolved_moves,
            source=source,
            raid_hp_multiplier=5.0,
        )

        encounter = RaidEncounter(
            raid_id=str(uuid.uuid4()),
            location_id=location_id,
            created_by=created_by,
            created_at=time.time(),
            pokemon_config=config,
            participants={created_by: False},
            invited=set(),
            join_order=[created_by],
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
    # Raid party management
    # ------------------------------------------------------------------
    def add_participant(self, location_id: str, user_id: int) -> Optional[RaidEncounter]:
        raid = self.active_raids.get(location_id)
        if not raid:
            return None

        if user_id not in raid.participants:
            raid.participants[user_id] = False
            raid.join_order.append(user_id)
        return raid

    def invite_participant(self, location_id: str, inviter_id: int, invited_id: int) -> Optional[RaidEncounter]:
        raid = self.active_raids.get(location_id)
        if not raid:
            return None

        raid.invited.add(invited_id)
        self.add_participant(location_id, invited_id)
        return raid

    def set_ready(self, location_id: str, user_id: int, ready: bool) -> Optional[RaidEncounter]:
        raid = self.active_raids.get(location_id)
        if not raid:
            return None

        raid.participants[user_id] = ready
        if user_id not in raid.join_order:
            raid.join_order.append(user_id)
        return raid

    def build_raid_boss(self, raid: RaidEncounter) -> Pokemon:
        """Instantiate a fresh raid boss instance for battle start."""

        base = raid.pokemon_config
        pokemon = Pokemon(
            species_data=base.pokemon.species_data,
            level=base.pokemon.level,
            owner_discord_id=None,
        )
        pokemon.is_raid_boss = True
        pokemon.raid_stat_multiplier = base.raid_stat_multiplier
        pokemon.raid_hp_multiplier = base.raid_hp_multiplier
        pokemon.raid_level_cap = self.MAX_LEVEL
        pokemon.moves = pokemon._create_move_objects(list(base.move_ids))
        pokemon._calculate_stats()
        pokemon.current_hp = pokemon.max_hp
        return pokemon

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

        random.shuffle(attack_moves)
        random.shuffle(support_moves)

        selected: List[str] = []

        # Guarantee at least three attacking moves when available
        selected.extend(attack_moves[:3])

        # Add extra attacking and support variety
        selected.extend(attack_moves[3:5])  # Prefer a couple more offense options
        selected.extend(support_moves[:2])

        # Fill remaining slots, favoring unused attack moves first
        remaining_slots = 6 - len(selected)
        if remaining_slots > 0:
            remaining_attacks = [m for m in attack_moves if m not in selected]
            random.shuffle(remaining_attacks)
            selected.extend(remaining_attacks[:remaining_slots])
            remaining_slots = 6 - len(selected)

        if remaining_slots > 0:
            remaining_support = [m for m in support_moves if m not in selected]
            random.shuffle(remaining_support)
            selected.extend(remaining_support[:remaining_slots])
            remaining_slots = 6 - len(selected)

        if remaining_slots > 0:
            fallback = self.learnset_db.get_starting_moves(species_name, level=level, max_moves=6)
            for move_id in fallback:
                if move_id not in selected:
                    selected.append(move_id)
                if len(selected) >= 6:
                    break

        # Ensure exactly 6 moves by padding with basic fallback moves
        basic_fallbacks = ['tackle', 'scratch', 'pound', 'growl', 'tail-whip', 'leer']
        while len(selected) < 6:
            for fallback_move in basic_fallbacks:
                if fallback_move not in selected:
                    selected.append(fallback_move)
                    break
            # Safety check to prevent infinite loop
            if len(selected) >= 6 or len([m for m in basic_fallbacks if m not in selected]) == 0:
                break

        return selected[:6]
