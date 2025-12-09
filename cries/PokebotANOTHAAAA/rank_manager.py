"""Rank progression, tickets, and promotion match management."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Rank definitions: eight tiers spread across five named ranks
RANK_TIER_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "tier": 1,
        "name": "Qualifiers",
        "group": "Qualifiers",
        "ticket_threshold": 100,
        "point_cap": 200,
        "description": "Earn enough points to prove you're worthy of the Challenger ladder.",
    },
    {
        "tier": 2,
        "name": "Challenger I",
        "group": "Challenger",
        "ticket_threshold": 160,
        "point_cap": 240,
        "description": "Official entry into the Challenger Circuit.",
    },
    {
        "tier": 3,
        "name": "Challenger II",
        "group": "Challenger",
        "ticket_threshold": 200,
        "point_cap": 260,
        "description": "Prove consistent success to earn an audience with the Great rank.",
    },
    {
        "tier": 4,
        "name": "Great I",
        "group": "Great",
        "ticket_threshold": 220,
        "point_cap": 280,
        "description": "Elite competition with access to refined facilities.",
    },
    {
        "tier": 5,
        "name": "Great II",
        "group": "Great",
        "ticket_threshold": 240,
        "point_cap": 300,
        "description": "Final proving grounds before the Ultra League.",
    },
    {
        "tier": 6,
        "name": "Ultra I",
        "group": "Ultra",
        "ticket_threshold": 260,
        "point_cap": 320,
        "description": "Battle-tested contenders eyeing Mastery.",
    },
    {
        "tier": 7,
        "name": "Ultra II",
        "group": "Ultra",
        "ticket_threshold": 300,
        "point_cap": 340,
        "description": "The final wall before the Masters gauntlet.",
    },
    {
        "tier": 8,
        "name": "Masters",
        "group": "Masters",
        "ticket_threshold": 0,
        "point_cap": 0,
        "description": "Top of the league. Maintain supremacy.",
    },
]

GIMMICK_OPTIONS: Dict[str, str] = {
    "mega": "Mega Evolution",
    "zmove": "Z-Moves",
    "dynamax": "Dynamax",
    "terastal": "Terastalization",
}


def get_rank_tier_definition(tier: int) -> Dict[str, Any]:
    """Return the tier definition. Defaults to tier 1 if unknown."""

    for definition in RANK_TIER_DEFINITIONS:
        if definition["tier"] == tier:
            return definition
    return RANK_TIER_DEFINITIONS[0]


def get_max_gimmick_slots(tier: int) -> int:
    """Return how many gimmick slots a tier should have.

    Slots unlock at Challenger (tier 2) and at the first tier of each
    major rank afterwards (Great I, Ultra I, Masters).
    """

    slots = 0
    if tier >= 2:
        slots = 1
    if tier >= 4:
        slots = 2
    if tier >= 6:
        slots = 3
    if tier >= 8:
        slots = 4
    return slots


@dataclass
class RankMatch:
    """Represents a scheduled promotion match."""

    match_id: str
    tier: int
    format: str
    participants: List[Dict[str, Any]]
    created_by: int
    status: str = "pending"
    notes: Optional[str] = None
    created_at: str = datetime.utcnow().isoformat(timespec="seconds")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "match_id": self.match_id,
            "tier": self.tier,
            "format": self.format,
            "participants": self.participants,
            "created_by": self.created_by,
            "status": self.status,
            "notes": self.notes,
            "created_at": self.created_at,
        }


class RankManager:
    """Centralized controller for rank progression and promotion matches."""

    def __init__(
        self,
        player_manager,
        state_path: str = "config/rank_state.json",
        matches_path: str = "config/rank_matches.json",
    ):
        self.player_manager = player_manager
        self.state_path = Path(state_path)
        self.matches_path = Path(matches_path)
        self._state = self._load_state()
        self._matches = self._load_matches()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def _load_state(self) -> Dict[str, Any]:
        default_state = {
            "highest_unlocked_tier": 1,
            "twilight_invite_active": False,
            "twilight_started": False,
            "twilight_participants": [],
        }

        if self.state_path.exists():
            try:
                with open(self.state_path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                    if isinstance(data, dict):
                        # Merge in any newly added defaults
                        merged = {**default_state, **data}
                        # Ensure list fields always exist even if missing or wrong type
                        if not isinstance(merged.get("twilight_participants"), list):
                            merged["twilight_participants"] = []
                        return merged
            except (OSError, json.JSONDecodeError):
                pass

        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as handle:
            json.dump(default_state, handle, indent=2)
        return default_state

    def _save_state(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as handle:
            json.dump(self._state, handle, indent=2)

    def _load_matches(self) -> List[RankMatch]:
        if self.matches_path.exists():
            try:
                with open(self.matches_path, "r", encoding="utf-8") as handle:
                    raw = json.load(handle) or []
                    matches: List[RankMatch] = []
                    for entry in raw:
                        if not isinstance(entry, dict):
                            continue
                        matches.append(
                            RankMatch(
                                match_id=entry.get("match_id") or uuid.uuid4().hex,
                                tier=int(entry.get("tier", 1)),
                                format=entry.get("format", "singles"),
                                participants=list(entry.get("participants") or []),
                                created_by=int(entry.get("created_by", 0)),
                                status=entry.get("status", "pending"),
                                notes=entry.get("notes"),
                                created_at=entry.get("created_at")
                                or datetime.utcnow().isoformat(timespec="seconds"),
                            )
                        )
                    return matches
            except (OSError, json.JSONDecodeError):
                pass
        self.matches_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.matches_path, "w", encoding="utf-8") as handle:
            json.dump([], handle, indent=2)
        return []

    def _save_matches(self):
        self.matches_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.matches_path, "w", encoding="utf-8") as handle:
            json.dump([match.to_dict() for match in self._matches], handle, indent=2)

    # ------------------------------------------------------------------
    # Rank state accessors
    # ------------------------------------------------------------------
    def get_highest_unlocked_tier(self) -> int:
        return int(self._state.get("highest_unlocked_tier", 1))

    def is_tier_unlocked(self, tier: int) -> bool:
        return tier <= self.get_highest_unlocked_tier()

    def unlock_up_to(self, tier: int) -> List[Dict[str, Any]]:
        tier = max(1, min(8, int(tier)))
        if tier <= self.get_highest_unlocked_tier():
            return []
        self._state["highest_unlocked_tier"] = tier
        self._save_state()
        return self._apply_pending_promotions(tier)

    # ------------------------------------------------------------------
    # Leaderboards & queues
    # ------------------------------------------------------------------
    def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        rows = self.player_manager.db.get_top_ranked_players(limit)
        return rows or []

    def get_ticket_queue(self) -> List[Dict[str, Any]]:
        rows = self.player_manager.db.get_ticket_holders()
        return rows or []

    # ------------------------------------------------------------------
    # Match helpers
    # ------------------------------------------------------------------
    def list_matches(self, include_completed: bool = False) -> List[RankMatch]:
        if include_completed:
            return list(self._matches)
        return [match for match in self._matches if match.status == "pending"]

    def has_pending_match(self, discord_id: int) -> bool:
        return self._find_match_for_pair(discord_id) is not None

    def get_pending_match_for_player(self, discord_id: int) -> Optional['RankMatch']:
        """Return the pending RankMatch this player is assigned to, if any."""
        return self._find_match_for_pair(discord_id)

    def schedule_match(
        self,
        tier: int,
        format_name: str,
        player_ids: Iterable[int],
        created_by: int,
        npc_participant: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
    ) -> RankMatch:
        tier = max(1, min(8, int(tier)))
        participants: List[Dict[str, Any]] = []
        for discord_id in player_ids:
            participants.append({"type": "player", "id": int(discord_id)})
        if npc_participant:
            participants.append({"type": "npc", **npc_participant})
        match = RankMatch(
            match_id=f"RM-{uuid.uuid4().hex[:8].upper()}",
            tier=tier,
            format=format_name,
            participants=participants,
            created_by=int(created_by),
            status="pending",
            notes=notes,
        )
        self._matches.append(match)
        self._save_matches()
        return match

    def get_match(self, match_id: str) -> Optional[RankMatch]:
        for match in self._matches:
            if match.match_id == match_id:
                return match
        return None

    def _find_match_for_pair(
        self,
        challenger_id: int,
        opponent_id: Optional[int] = None,
        npc_name: Optional[str] = None,
    ) -> Optional[RankMatch]:
        for match in self._matches:
            if match.status != "pending":
                continue
            players = {p["id"] for p in match.participants if p.get("type") == "player"}
            npcs = {p.get("name") for p in match.participants if p.get("type") == "npc"}

            if opponent_id is not None and players == {challenger_id, opponent_id}:
                return match
            if npc_name and players == {challenger_id} and npc_name in npcs:
                return match
            if opponent_id is None and npc_name is None and challenger_id in players:
                return match
        return None

    # ------------------------------------------------------------------
    # Ranked matchmaking gates
    # ------------------------------------------------------------------
    def player_locked_from_ranked(self, discord_id: int) -> Optional[str]:
        trainer = self.player_manager.get_player(discord_id)
        if not trainer:
            return "You need a registered trainer before battling."

        if not self._state.get("twilight_started", False):
            return "⚠️ Ranked battles are locked until the Twilight Summit officially begins."

        if not self.is_twilight_participant(discord_id):
            return (
                "🚫 You haven't signed up for the Twilight Summit yet. Use your Rotom-Phone alerts "
                "to join and unlock ranked battles."
            )

        if getattr(trainer, "has_promotion_ticket", False):
            match = self._find_match_for_pair(trainer.discord_user_id)
            if match is None:
                return (
                    "🎟️ You currently hold a Challenger Ticket. Wait for league staff "
                    "to schedule your promotion match before taking on other ranked battles."
                )
        return None

    def prepare_ranked_battle(
        self,
        challenger_id: int,
        opponent_id: Optional[int] = None,
        npc_name: Optional[str] = None,
        format_name: str = "singles",
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        lock_message = self.player_locked_from_ranked(challenger_id)
        if lock_message:
            return False, lock_message, {}

        trainer = self.player_manager.get_player(challenger_id)
        if not trainer:
            return False, "You must register before battling.", {}

        match_context = self._find_match_for_pair(challenger_id, opponent_id, npc_name)
        if trainer.has_promotion_ticket:
            if not match_context:
                return (
                    False,
                    "You have a Challenger Ticket. An admin needs to schedule your promotion match before you battle ranked again.",
                    {},
                )
            if match_context.format != format_name:
                return (
                    False,
                    f"Your promotion match is locked to {match_context.format.title()} format.",
                    {},
                )

        if opponent_id is not None:
            opponent = self.player_manager.get_player(opponent_id)
            if opponent and opponent.has_promotion_ticket:
                opponent_match = self._find_match_for_pair(opponent.discord_user_id, challenger_id)
                if not opponent_match:
                    return (
                        False,
                        f"{opponent.trainer_name} is waiting for a scheduled promotion match and can't accept other ranked battles.",
                        {},
                    )
                if match_context and opponent_match.match_id != match_context.match_id:
                    return (
                        False,
                        f"{opponent.trainer_name} is scheduled to battle a different opponent for their promotion.",
                        {},
                    )
                if opponent_match.format != format_name:
                    return (
                        False,
                        f"{opponent.trainer_name}'s promotion match must use {opponent_match.format.title()} format.",
                        {},
                    )

        context: Dict[str, Any] = {}
        if match_context:
            context["match_id"] = match_context.match_id
            context["match_tier"] = match_context.tier
        return True, None, context

    # ------------------------------------------------------------------
    # Twilight Summit & alerts
    # ------------------------------------------------------------------
    def activate_twilight_invite(self) -> None:
        """Enable the Twilight Summit invite for all players."""

        self._state["twilight_invite_active"] = True
        self._state.setdefault("twilight_started", False)
        self._state.setdefault("twilight_participants", [])
        self._save_state()

    def twilight_invite_active(self) -> bool:
        return bool(self._state.get("twilight_invite_active", False))

    def begin_twilight_summit(self) -> None:
        """Unlock ranked battles for participants by starting the event."""

        self._state["twilight_invite_active"] = True
        self._state["twilight_started"] = True
        self._save_state()

    def twilight_started(self) -> bool:
        return bool(self._state.get("twilight_started", False))

    def is_twilight_participant(self, discord_id: int) -> bool:
        participants = self._state.get("twilight_participants") or []
        return int(discord_id) in {int(pid) for pid in participants}

    def register_twilight_participant(self, discord_id: int) -> tuple[bool, str]:
        if not self._state.get("twilight_invite_active", False):
            return False, "There is no active Twilight Summit invite to join right now."

        if self.is_twilight_participant(discord_id):
            return False, "You're already registered for the Twilight Summit."

        participants = self._state.setdefault("twilight_participants", [])
        participants.append(int(discord_id))
        self._state["twilight_participants"] = participants
        self._save_state()

        trainer = self.player_manager.get_player(discord_id)
        if trainer:
            rank_name = "Qualifier"
            rank_number = trainer.rank_tier_number or 1
            if rank_number < 1:
                rank_number = 1
            self.player_manager.update_player(
                discord_user_id=discord_id,
                rank_tier_name=rank_name,
                rank_tier_number=rank_number,
            )
        return True, "You've signed up for the Twilight Summit! Ranked progress is now unlocked."

    def get_alerts_for_player(self, trainer: Any) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []
        if not trainer:
            return alerts

        invite_active = self._state.get("twilight_invite_active", False)
        started = self._state.get("twilight_started", False)
        if invite_active:
            participant = self.is_twilight_participant(trainer.discord_user_id)
            body_lines = [
                "The Twilight Summit is about to begin.",
                "Please sign up here to participate.",
            ]
            if started:
                body_lines.append("Ranked battles are now live for registered participants.")

            alerts.append(
                {
                    "id": "twilight_summit_invite",
                    "title": "Twilight Summit Invitation",
                    "summary": "Join the Summit to unlock your ranked profile.",
                    "details": "\n".join(body_lines),
                    "action": "sign_up",
                    "status": "joined" if participant else "pending",
                    "cta_label": "Sign Up" if not participant else "Already Signed",
                }
            )

        return alerts

    # ------------------------------------------------------------------
    # Battle resolution
    # ------------------------------------------------------------------
    def process_ranked_battle_result(self, battle, player_manager) -> Optional[Dict[str, Any]]:
        from battle_engine_v2 import BattleType  # Local import to avoid circular deps

        if getattr(battle, "winner", None) not in {"trainer", "opponent"}:
            return None
        winner_battler = battle.trainer if battle.winner == "trainer" else battle.opponent
        loser_battler = battle.opponent if battle.winner == "trainer" else battle.trainer
        winner_id = getattr(winner_battler, "battler_id", None)
        if not isinstance(winner_id, int) or winner_id <= 0:
            return None

        winner_trainer = player_manager.get_player(winner_id)
        if not winner_trainer:
            return None

        loser_id = getattr(loser_battler, "battler_id", None)
        loser_trainer = player_manager.get_player(loser_id) if isinstance(loser_id, int) and loser_id > 0 else None

        ranked_context = getattr(battle, "ranked_context", {}) or {}
        match_id = ranked_context.get("match_id")
        match = self.get_match(match_id) if match_id else None

        opponent_rank = None
        opponent_label = getattr(loser_battler, "battler_name", "Opponent")
        opponent_is_player = False

        if getattr(battle, "battle_type", None) == BattleType.PVP and loser_trainer:
            opponent_is_player = True
            opponent_rank = loser_trainer.rank_tier_number or 1
            opponent_label = loser_trainer.trainer_name
        else:
            opponent_rank = ranked_context.get("npc_rank") or 1
            opponent_label = ranked_context.get("npc_name", opponent_label)

        if match and match.status == "pending":
            return self._resolve_promotion_match(
                match,
                winner_trainer,
                loser_trainer,
                opponent_label,
            )

        return self._apply_standard_points(
            winner_trainer,
            loser_trainer,
            opponent_rank,
            opponent_is_player,
            opponent_label,
        )

    # ------------------------------------------------------------------
    # Internal helpers for points/promotions
    # ------------------------------------------------------------------
    def _apply_standard_points(
        self,
        winner: Any,
        loser: Optional[Any],
        opponent_rank: int,
        opponent_is_player: bool,
        opponent_label: str,
    ) -> Optional[Dict[str, Any]]:
        winner_rank = winner.rank_tier_number or 1
        points_awarded = self._calculate_point_reward(winner_rank, opponent_rank, opponent_is_player)
        if points_awarded == 0:
            return None

        summary_lines = []
        old_points = getattr(winner, "ladder_points", 0) or 0
        new_points = self._update_points(winner, points_awarded)
        summary_lines.append(f"{old_points} → {new_points} (Δ +{points_awarded})")

        ticket_awarded = self._maybe_grant_ticket(winner)
        if ticket_awarded:
            summary_lines.append("🎟️ Challenger ticket earned!")

        loser_summary = None
        if loser and not getattr(loser, "has_promotion_ticket", False):
            penalty = max(5, points_awarded // 2)
            old_loser_points = getattr(loser, "ladder_points", 0) or 0
            new_loser_points = self._update_points(loser, -penalty)
            loser_summary = f"{loser.trainer_name}: {old_loser_points} → {new_loser_points} (Δ −{penalty})"

        result = {
            "title": "🏆 Challenger Points Updated",
            "description": f"{winner.trainer_name} defeated {opponent_label} and earned Challenger points.",
            "fields": [
                {"name": "Points", "value": "\n".join(summary_lines), "inline": False}
            ],
        }

        if loser_summary:
            result["fields"].append({"name": "Opponent Penalty", "value": loser_summary, "inline": False})

        return result

    def _resolve_promotion_match(
        self,
        match: RankMatch,
        winner: Any,
        loser: Optional[Any],
        opponent_label: str,
    ) -> Optional[Dict[str, Any]]:
        current_tier = winner.rank_tier_number or 1
        target_tier = min(8, current_tier + 1)

        promotion_embed_lines = []
        pending = False
        if self.is_tier_unlocked(target_tier):
            self._apply_rank_promotion(winner, target_tier)
            promotion_embed_lines.append(f"Rank advanced to **{get_rank_tier_definition(target_tier)['name']}**!")
        else:
            pending = True
            self._set_pending_promotion(winner, target_tier)
            promotion_embed_lines.append(
                f"Rank up secured, awaiting league unlock for tier {target_tier}."
            )

        self._consume_ticket(winner)
        self._mark_match_complete(match, winner.discord_user_id)

        loser_text = None
        if loser:
            old_points = getattr(loser, "ladder_points", 0) or 0
            new_points = self._update_points(loser, -(old_points // 2))
            self._consume_ticket(loser)
            loser_text = f"{loser.trainer_name}: {old_points} → {new_points} (lost promotion ticket)"

        result = {
            "title": "🎟️ Promotion Match Resolved",
            "description": f"{winner.trainer_name} won their promotion match against {opponent_label}!",
            "fields": [
                {
                    "name": "Rank Status",
                    "value": "\n".join(promotion_embed_lines),
                    "inline": False,
                }
            ],
        }

        gimmick_line = self._maybe_unlock_omni_reward(winner)
        if gimmick_line:
            result["fields"].append({"name": "Omni Ring", "value": gimmick_line, "inline": False})

        if loser_text:
            result["fields"].append({"name": "Opponent", "value": loser_text, "inline": False})

        if pending:
            result["footer"] = "This promotion will activate automatically once the tier is unlocked."

        return result

    def _mark_match_complete(self, match: RankMatch, winner_id: int):
        match.status = "completed"
        match.notes = (match.notes or "") + f" (Winner: {winner_id})"
        self._save_matches()

    def _consume_ticket(self, trainer):
        updates = {"has_promotion_ticket": 0, "ticket_tier": None}
        self.player_manager.update_player(trainer.discord_user_id, **updates)
        trainer.has_promotion_ticket = False
        trainer.ticket_tier = None

    def _set_pending_promotion(self, trainer, target_tier: int):
        self.player_manager.update_player(trainer.discord_user_id, rank_pending_tier=target_tier)
        trainer.rank_pending_tier = target_tier

    def _apply_rank_promotion(self, trainer, new_tier: int):
        definition = get_rank_tier_definition(new_tier)
        updates = {
            "rank_tier_number": new_tier,
            "rank_tier_name": definition["group"],
            "ladder_points": 0,
            "rank_pending_tier": None,
        }
        self.player_manager.update_player(trainer.discord_user_id, **updates)
        trainer.rank_tier_number = new_tier
        trainer.rank_tier_name = definition["group"]
        trainer.ladder_points = 0
        trainer.rank_pending_tier = None

    def _maybe_unlock_omni_reward(self, trainer) -> Optional[str]:
        tier = trainer.rank_tier_number or 1
        slots = get_max_gimmick_slots(tier)
        gimmicks = list(getattr(trainer, "omni_ring_gimmicks", []) or [])
        text_fragments = []
        if tier >= 2 and not getattr(trainer, "has_omni_ring", False):
            self.player_manager.update_player(trainer.discord_user_id, has_omni_ring=1)
            trainer.has_omni_ring = True
            text_fragments.append("Received the Omni Ring! Use /rank_select_gimmick to attune it.")
        if len(gimmicks) < slots:
            remaining = slots - len(gimmicks)
            text_fragments.append(
                f"You have {remaining} open gimmick slot(s). Choose them with /rank_select_gimmick."
            )
        return "\n".join(text_fragments) if text_fragments else None

    def _update_points(self, trainer, delta: int) -> int:
        tier = trainer.rank_tier_number or 1
        definition = get_rank_tier_definition(tier)
        cap = definition.get("point_cap") or 0
        current = getattr(trainer, "ladder_points", 0) or 0
        new_value = current + delta
        if cap > 0:
            new_value = max(0, min(cap, new_value))
        else:
            new_value = max(0, new_value)
        self.player_manager.update_player(trainer.discord_user_id, ladder_points=new_value)
        trainer.ladder_points = new_value
        return new_value

    def _maybe_grant_ticket(self, trainer) -> bool:
        if getattr(trainer, "has_promotion_ticket", False):
            return False
        tier = trainer.rank_tier_number or 1
        threshold = get_rank_tier_definition(tier).get("ticket_threshold", 0)
        if threshold <= 0:
            return False
        if (trainer.ladder_points or 0) < threshold:
            return False
        updates = {"has_promotion_ticket": 1, "ticket_tier": tier}
        self.player_manager.update_player(trainer.discord_user_id, **updates)
        trainer.has_promotion_ticket = True
        trainer.ticket_tier = tier
        return True

    def _calculate_point_reward(self, winner_rank: int, opponent_rank: int, opponent_is_player: bool) -> int:
        opponent_rank = opponent_rank or winner_rank or 1
        winner_rank = winner_rank or 1
        if opponent_is_player:
            if opponent_rank > winner_rank:
                return 60
            if opponent_rank == winner_rank:
                return 35
            return 20
        if opponent_rank > winner_rank:
            return 25
        if opponent_rank == winner_rank:
            return 15
        return 8

    def _apply_pending_promotions(self, unlocked_tier: int) -> List[Dict[str, Any]]:
        rows = self.player_manager.db.get_trainers_with_pending_promotions(unlocked_tier)
        promoted: List[Dict[str, Any]] = []
        for row in rows:
            trainer = self.player_manager.get_player(row["discord_user_id"])
            if not trainer:
                continue
            target_tier = row.get("rank_pending_tier")
            if not target_tier:
                continue
            self._apply_rank_promotion(trainer, target_tier)
            gimmick_text = self._maybe_unlock_omni_reward(trainer)
            promoted.append(
                {
                    "discord_user_id": trainer.discord_user_id,
                    "trainer_name": trainer.trainer_name,
                    "new_tier": target_tier,
                    "omni_text": gimmick_text,
                }
            )
        return promoted

    # ------------------------------------------------------------------
    # Omni Ring utilities
    # ------------------------------------------------------------------
    def get_available_gimmicks(self, trainer) -> Tuple[int, List[str]]:
        tier = trainer.rank_tier_number or 1
        slots = get_max_gimmick_slots(tier)
        owned = list(getattr(trainer, "omni_ring_gimmicks", []) or [])
        return slots, owned

    def select_gimmick(self, trainer, gimmick_id: str) -> Tuple[bool, str]:
        gimmick_id = gimmick_id.lower()
        if gimmick_id not in GIMMICK_OPTIONS:
            return False, "Unknown gimmick choice."
        if not getattr(trainer, "has_omni_ring", False):
            return False, "You need the Omni Ring before selecting gimmicks."
        slots, owned = self.get_available_gimmicks(trainer)
        if len(owned) >= slots:
            return False, "You don't have any open Omni Ring slots right now."
        if gimmick_id in owned:
            return False, "That gimmick is already unlocked on your ring."
        owned.append(gimmick_id)
        self.player_manager.update_player(
            trainer.discord_user_id,
            omni_ring_gimmicks=json.dumps(owned),
        )
        trainer.omni_ring_gimmicks = owned
        return True, f"Added {GIMMICK_OPTIONS[gimmick_id]} to your Omni Ring."
