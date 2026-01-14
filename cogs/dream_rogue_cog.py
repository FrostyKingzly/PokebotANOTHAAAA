"""
Dream Dive Cog

Commands and orchestration for the Dream Dive roguelike gamemode
"""

import discord
from discord.ext import commands
from typing import List, Optional, Union
import asyncio
import random

from dream_rogue_manager import DreamRogueManager
from database import PlayerDatabase, SpeciesDatabase
from models import Pokemon
from session_manager import SessionManager
from ui.dream_rogue_embeds import DreamRogueEmbeds
from ui.dream_rogue_views import (
    DiveStartView,
    FloorNavigationView,
    VotingView,
    InstanceActionView,
)


class DreamRogueCog(commands.Cog):
    """Dream Dive gamemode commands"""

    def __init__(self, bot):
        self.bot = bot
        self.dream_manager = DreamRogueManager()
        self.player_db = PlayerDatabase()
        self.session_manager = SessionManager(self.player_db)

    async def start_dive_from_session(self, interaction: discord.Interaction, layer_name: str, intensity: int):
        """
        Start a dive from session mode (called from session controls)

        Args:
            interaction: Discord interaction
            layer_name: Dream layer name
            intensity: Dive intensity (1-10)
        """
        # Get active session
        session = self.session_manager.get_active_session_by_guild(interaction.guild_id)

        if not session:
            await interaction.response.send_message(
                "❌ No active session found!",
                ephemeral=True
            )
            return

        # Check if user is session admin
        if interaction.user.id != session["admin_id"]:
            await interaction.response.send_message(
                "❌ Only the session admin can start a Dream Dive dive!",
                ephemeral=True
            )
            return

        # Get session participants
        participants = self.session_manager.get_participants(session["session_id"])

        if not participants:
            await interaction.response.send_message(
                "❌ No participants in session!",
                ephemeral=True
            )
            return

        # Move session to Dreamyard location
        try:
            self.session_manager.move_session_to_location(
                session["session_id"],
                "residential_district_dreamyard",
                stamina_cost=0  # No cost for Dream Dive entry
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to move session to Dreamyard: {e}",
                ephemeral=True
            )
            return

        # Create Dream Dive run
        if layer_name == DreamRogueManager.TEST_PATH_LAYER and intensity != 1:
            await interaction.response.send_message(
                "❌ Test Path dives must use intensity **1**.",
                ephemeral=True
            )
            return

        run_id = self.dream_manager.create_run(
            guild_id=interaction.guild_id,
            initiator_id=interaction.user.id,
            intensity=intensity,
            layer_name=layer_name,
            starting_floor=1,  # Always start at floor 1
            session_id=session["session_id"]
        )

        # Add all session participants
        for participant in participants:
            if participant["discord_user_id"] != interaction.user.id:
                self.dream_manager.add_participant(run_id, participant["discord_user_id"])

        snapshot_users = {interaction.user.id} | {p["discord_user_id"] for p in participants}
        for user_id in snapshot_users:
            party = self.player_db.get_trainer_party(user_id)
            self.dream_manager.record_party_snapshot(run_id, user_id, party)

        # Show dive start embed
        participants_list = [interaction.user.id] + [p["discord_user_id"] for p in participants if p["discord_user_id"] != interaction.user.id]

        embed = DreamRogueEmbeds.dive_start(layer_name, intensity, participants_list)

        await interaction.response.send_message(embed=embed)

        if layer_name == DreamRogueManager.TEST_PATH_LAYER:
            await asyncio.sleep(1)
            await self._send_test_path_area_embed(interaction, run_id, area_index=1)
        else:
            # Start first node selection
            await asyncio.sleep(2)
            await self._offer_next_nodes(interaction, run_id)

    async def start_dive_solo(self, interaction: discord.Interaction, layer_name: str, intensity: int):
        """
        Start a solo dive or create invite (from Dreamyard location)

        Args:
            interaction: Discord interaction
            layer_name: Dream layer name
            intensity: Dive intensity (1-10)
        """
        # Check location
        trainer = self.player_db.get_trainer(interaction.user.id)
        if not trainer:
            await interaction.response.send_message(
                "❌ You need to be registered first!",
                ephemeral=True
            )
            return

        current_location = trainer.get("current_location_id", "")
        if current_location != "residential_district_dreamyard":
            await interaction.response.send_message(
                "❌ You must be at the Dreamyard to dive!",
                ephemeral=True
            )
            return

        # Check stamina
        stamina = trainer.get("stamina_current", 0)
        if stamina < 1:
            await interaction.response.send_message(
                "❌ You need at least 1 stamina to dive!",
                ephemeral=True
            )
            return

        # Create run
        run_id = self.dream_manager.create_run(
            guild_id=interaction.guild_id,
            initiator_id=interaction.user.id,
            intensity=intensity,
            layer_name=layer_name,
            starting_floor=1  # Always start at floor 1
        )
        party = self.player_db.get_trainer_party(interaction.user.id)
        self.dream_manager.record_party_snapshot(run_id, interaction.user.id, party)

        # Show join/start embed
        participants = self.dream_manager.get_participants(run_id)
        run = self.dream_manager.get_run(run_id)
        floor_range = self.dream_manager.get_floor_level_range(intensity, 1)

        embed = DreamRogueEmbeds.run_status(run, participants, floor_range)
        embed.description += "\n\n*Waiting for participants... Click 'Start Dive' when ready.*"

        view = DiveStartView(
            self.bot,
            run_id,
            interaction.user.id,
            self._update_dive_lobby
        )

        await interaction.response.send_message(embed=embed, view=view)

    async def _update_dive_lobby(self, interaction: discord.Interaction, start: bool = False):
        """Update dive lobby or start dive"""
        # Extract run_id from view
        view = interaction.message.components[0] if interaction.message.components else None

        if not view:
            return

        # Get run_id from the view
        # This is a simplified approach - you'd need to track this properly
        # For now, get active run
        run = self.dream_manager.get_active_run_by_guild(interaction.guild_id)

        if not run:
            await interaction.followup.send("❌ Run not found!", ephemeral=True)
            return

        run_id = run["run_id"]

        if start:
            # Deduct stamina from all participants
            participants = self.dream_manager.get_participants(run_id)

            for p in participants:
                self.session_manager.adjust_participant_stamina(p["discord_user_id"], -1)

            # Show dive start
            intensity = run.get("intensity", run.get("stage_level", 1))
            layer_name = run.get("layer_name", "Somnia Prima")
            embed = DreamRogueEmbeds.dive_start(
                layer_name,
                intensity,
                [p["discord_user_id"] for p in participants]
            )

            await interaction.response.edit_message(embed=embed, view=None)

            # Start first node selection
            await asyncio.sleep(2)
            await self._offer_next_nodes(interaction, run_id)

        else:
            # Just update lobby
            participants = self.dream_manager.get_participants(run_id)
            intensity = run.get("intensity", run.get("stage_level", 1))
            floor_range = self.dream_manager.get_floor_level_range(intensity, run["starting_floor"])

            embed = DreamRogueEmbeds.run_status(run, participants, floor_range)
            embed.description += "\n\n*Waiting for participants... Click 'Start Dive' when ready.*"

            # Don't change view
            await interaction.response.defer()

    async def _offer_next_nodes(self, interaction: discord.Interaction, run_id: str):
        """Prompt the team to choose the next node."""
        run = self.dream_manager.get_run(run_id)
        if not run:
            return

        current_node = self.dream_manager.get_current_node(run_id)
        next_nodes = self.dream_manager.get_next_nodes(run_id)
        if not current_node or not next_nodes:
            return

        if len(next_nodes) == 1:
            await self._enter_node(interaction, run_id, next_nodes[0])
            return

        vote_id = self.dream_manager.create_vote(
            run_id,
            "Choose the next node:",
            [
                {
                    "name": self._node_option_name(node),
                    "description": self._node_option_description(node),
                }
                for node in next_nodes
            ],
        )

        vote = self.dream_manager.get_vote(vote_id)
        percentages = self.dream_manager.get_vote_percentages(vote_id)
        intensity = run.get("intensity", run.get("stage_level", 1))
        layer_name = run.get("layer_name", "Somnia Prima")
        embed = DreamRogueEmbeds.node_selection(current_node, next_nodes, layer_name, intensity)

        view = VotingView(
            self.bot,
            vote_id,
            run_id,
            lambda i, result: self._on_node_vote_complete(i, run_id, next_nodes, result)
        )

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view)

    def _node_option_name(self, node: dict) -> str:
        node_type = node.get("node_type", "event")
        label_map = {
            "combat": "Combat",
            "event": "Event",
            "rest": "Rest",
            "mini_boss": "Mini Boss",
            "boss": "Boss",
        }
        name = label_map.get(node_type, "Unknown")
        if node.get("has_shop"):
            name += " + Shop"
        return name

    def _node_option_description(self, node: dict) -> str:
        node_type = node.get("node_type", "event")
        description_map = {
            "combat": "A battle against roaming foes.",
            "event": "A mysterious encounter with choices.",
            "rest": "Recover some HP at the campfire.",
            "mini_boss": "A tougher fight with better rewards.",
            "boss": "The floor guardian awaits.",
        }
        return description_map.get(node_type, "An unknown path.")

    async def _on_node_vote_complete(
        self,
        interaction: discord.Interaction,
        run_id: str,
        next_nodes: List[dict],
        result_index: int
    ):
        """Handle node vote resolution."""
        if not isinstance(result_index, int) or result_index >= len(next_nodes):
            return
        await self._enter_node(interaction, run_id, next_nodes[result_index])

    async def _enter_node(self, interaction: discord.Interaction, run_id: str, node: dict):
        """Advance into the selected node and start its instances."""
        self.dream_manager.set_current_node(run_id, node["node_id"])
        run = self.dream_manager.get_run(run_id)

        stage_embed = DreamRogueEmbeds.stage_intro(node.get("depth", run["current_floor"]))
        await self._send_embed(interaction, stage_embed)

        if node.get("node_type") == "boss":
            boss_embed = DreamRogueEmbeds.boss_intro(node.get("depth", run["current_floor"]))
            await self._send_embed(interaction, boss_embed)

        instances = self.dream_manager.generate_node_instances(run_id, node)

        if not instances:
            await self._offer_next_nodes(interaction, run_id)
            return

        if len(instances) > 1:
            embed = DreamRogueEmbeds.instance_selection(instances[0], node.get("depth", run["current_floor"]))
            view = FloorNavigationView(
                self.bot,
                run_id,
                instances,
                lambda i, chosen: self._show_instance(i, run_id, node, chosen, [chosen])
            )

            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.response.send_message(embed=embed, view=view)
            return

        await self._show_instance(interaction, run_id, node, instances[0], instances)

    async def _show_instance(
        self,
        interaction: discord.Interaction,
        run_id: str,
        node: dict,
        instance: dict,
        remaining_instances: list
    ):
        """Show an instance to the team"""
        run = self.dream_manager.get_run(run_id)
        floor = run["current_floor"]

        # Create instance embed
        embed = DreamRogueEmbeds.instance_selection(instance, floor)

        # Check if team-wide or individual
        scope = instance.get("scope", "team")

        if scope == "team":
            # Team-wide instance - show to everyone
            view = InstanceActionView(
                self.bot,
                run_id,
                instance,
                lambda i, result: self._on_instance_complete(i, run_id, node, instance, result, remaining_instances),
                origin_channel_id=interaction.channel.id
            )

            # Use followup if response already sent, otherwise response
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.response.send_message(embed=embed, view=view)

        else:
            # Individual instance - show public notice with private view button
            participants = self.dream_manager.get_participants(run_id)

            # Create a view with a button for participants to view their instance
            from ui.dream_rogue_views import IndividualInstanceView

            view = IndividualInstanceView(
                self.bot,
                run_id,
                instance,
                [p["discord_user_id"] for p in participants],
                lambda i, result: self._on_instance_complete(i, run_id, node, instance, result, remaining_instances)
            )

            notice_embed = discord.Embed(
                title="📨 Individual Instance",
                description=f"**{instance.get('name', 'Unknown')}** is a private choice.\n\nClick the button below to view and make your decision.",
                color=DreamRogueEmbeds.DREAM_COLOR
            )

            if interaction.response.is_done():
                await interaction.followup.send(embed=notice_embed, view=view)
            else:
                await interaction.response.send_message(embed=notice_embed, view=view)

    async def _on_instance_complete(
        self,
        interaction: discord.Interaction,
        run_id: str,
        node: dict,
        instance: dict,
        result: str,
        remaining_instances: list
    ):
        """Handle instance completion"""
        # Remove current instance from remaining
        if remaining_instances:
            remaining_instances = remaining_instances[1:]

        run = self.dream_manager.get_run(run_id)
        floor = run["current_floor"]

        if result in {"battle_complete", "boss_defeated"}:
            participants = self.dream_manager.get_participants(run_id)
            effect_data = instance.get("effect_data", {})
            multiplier = max(1, int(effect_data.get("dreamlite_multiplier", 1)))
            dreamlites_gained = random.randint(20, 40) * multiplier

            # Check if we have battle results tracked (for individual battles)
            battle_results = getattr(interaction, '_battle_results', {})

            winners = []
            losers = []

            if battle_results:
                # Individual battles - track wins and losses
                for participant in participants:
                    user_id = participant["discord_user_id"]
                    participant_result = battle_results.get(user_id, 'trainer')
                    if participant_result == 'trainer':
                        winners.append(participant)
                    else:
                        losers.append(participant)

                # Check if all won or all lost or mixed
                all_won = len(winners) == len(participants)
                all_lost = len(losers) == len(participants)
                mixed_results = not all_won and not all_lost

                if all_won:
                    # Everyone wins - full rewards
                    for participant in participants:
                        self.dream_manager.add_dreamlites(
                            run_id,
                            participant["discord_user_id"],
                            dreamlites_gained
                        )
                    buffs = []
                    if node.get("depth", floor) <= 2 and result == "battle_complete":
                        buffs = self.dream_manager.grant_positive_buffs(run_id, count=2)

                    reward_embed = DreamRogueEmbeds.battle_reward(
                        victory=True,
                        dreamlites_gained=dreamlites_gained,
                        exp_gained=0,
                        buffs_applied=buffs
                    )
                    await interaction.followup.send(embed=reward_embed)
                elif mixed_results:
                    # Mixed results - winners get rewards, losers lose dreamlites
                    for winner in winners:
                        self.dream_manager.add_dreamlites(
                            run_id,
                            winner["discord_user_id"],
                            dreamlites_gained
                        )

                    dreamlites_lost = random.randint(10, 20)
                    for loser in losers:
                        self.dream_manager.add_dreamlites(
                            run_id,
                            loser["discord_user_id"],
                            -dreamlites_lost
                        )

                    # Send message about mixed results
                    winner_names = ", ".join([f"<@{w['discord_user_id']}>" for w in winners])
                    loser_names = ", ".join([f"<@{l['discord_user_id']}>" for l in losers])

                    embed = discord.Embed(
                        title="⚔️ Mixed Results",
                        description=f"**Victors:** {winner_names}\n**Defeated:** {loser_names}",
                        color=discord.Color.gold()
                    )
                    embed.add_field(
                        name="Rewards",
                        value=f"✅ Winners gained **{dreamlites_gained}** Dreamlites\n❌ Losers lost **{dreamlites_lost}** Dreamlites"
                    )
                    await interaction.followup.send(embed=embed)
                else:
                    # All lost - show defeat
                    dreamlites_lost = random.randint(10, 20)
                    for participant in participants:
                        self.dream_manager.add_dreamlites(
                            run_id,
                            participant["discord_user_id"],
                            -dreamlites_lost
                        )

                    reward_embed = DreamRogueEmbeds.battle_reward(
                        victory=False,
                        dreamlites_gained=-dreamlites_lost,
                        exp_gained=0,
                        buffs_applied=[]
                    )
                    await interaction.followup.send(embed=reward_embed)
            else:
                # Raid/multi battles or no tracking - assume all won if this callback is triggered
                for participant in participants:
                    self.dream_manager.add_dreamlites(
                        run_id,
                        participant["discord_user_id"],
                        dreamlites_gained
                    )

                buffs = []
                if node.get("depth", floor) <= 2 and result == "battle_complete":
                    buffs = self.dream_manager.grant_positive_buffs(run_id, count=2)

                reward_embed = DreamRogueEmbeds.battle_reward(
                    victory=True,
                    dreamlites_gained=dreamlites_gained,
                    exp_gained=0,
                    buffs_applied=buffs
                )
                await interaction.followup.send(embed=reward_embed)

        if "rest" not in instance.get("categories", []) and "battle" not in instance.get("categories", []):
            participants = self.dream_manager.get_participants(run_id)
            dreamlites_gained = random.randint(10, 25)
            for participant in participants:
                self.dream_manager.add_dreamlites(run_id, participant["discord_user_id"], dreamlites_gained)
            await interaction.followup.send(
                f"💎 The dream rewards your progress. Everyone gains **{dreamlites_gained}** Dreamlites."
            )

        if not remaining_instances:
            # Floor complete!
            # Check if boss defeated or regular floor
            if node.get("node_type") == "boss" and "boss" in result.lower():
                # Boss defeated - run complete!
                from dream_dive_rewards import (
                    calculate_dream_dive_exp,
                    apply_dream_dive_exp,
                    restore_dream_dive_party_levels,
                )

                participants = self.dream_manager.get_participants(run_id)
                total_dreamlites = sum(p["dreamlites"] for p in participants)

                exp_rewards = {}
                for participant in participants:
                    user_id = participant["discord_user_id"]
                    restore_dream_dive_party_levels(self.bot, run_id, user_id)
                    intensity = run.get("intensity", run.get("stage_level", 1))
                    exp_amount = calculate_dream_dive_exp(intensity, participant["dreamlites"])
                    apply_dream_dive_exp(self.bot, user_id, exp_amount)
                    exp_rewards[user_id] = exp_amount

                self.dream_manager.end_run(run_id, extracted=True)

                embed = DreamRogueEmbeds.extraction_summary(
                    run,
                    participants,
                    floor,
                    total_dreamlites,
                    exp_rewards=exp_rewards,
                )

                await interaction.followup.send(embed=embed)

            else:
                await self._offer_next_nodes(interaction, run_id)

        else:
            # More instances on this floor
            await self._show_instance(interaction, run_id, node, remaining_instances[0], remaining_instances)

    async def _send_test_path_area_embed(self, interaction: discord.Interaction, run_id: str, area_index: int):
        embed = DreamRogueEmbeds.test_path_area(area_index)
        state = self.dream_manager.get_script_state(run_id)
        state["area_index"] = area_index
        state["action_index"] = 0
        state["nidoking_battle_id"] = None
        self.dream_manager.update_script_state(run_id, state)
        await self._send_embed(interaction, embed)

    async def _get_active_test_path_run(self, interaction: discord.Interaction):
        session = self.session_manager.get_active_session_by_guild(interaction.guild_id)
        if not session:
            await interaction.response.send_message(
                "❌ No active session found!",
                ephemeral=True
            )
            return None, None
        if interaction.user.id != session["admin_id"]:
            await interaction.response.send_message(
                "❌ Only the session admin can control Test Path actions.",
                ephemeral=True
            )
            return None, None

        run = self.dream_manager.get_active_run_by_session(session["session_id"])
        if not run or run.get("layer_name") != DreamRogueManager.TEST_PATH_LAYER:
            await interaction.response.send_message(
                "❌ No active Test Path dive found for this session.",
                ephemeral=True
            )
            return None, None

        return session, run

    async def advance_test_path_area(self, interaction: discord.Interaction):
        """Advance to the next Test Path area."""
        session, run = await self._get_active_test_path_run(interaction)
        if not run:
            return

        state = self.dream_manager.get_script_state(run["run_id"])
        area_index = state.get("area_index", 1)
        action_index = state.get("action_index", 0)

        if area_index == 1:
            await self._send_test_path_area_embed(interaction, run["run_id"], area_index=2)
            return

        if area_index == 2 and action_index < 2:
            await interaction.response.send_message(
                "❌ Resolve the pending actions before moving on.",
                ephemeral=True
            )
            return

        if area_index >= 3:
            await interaction.response.send_message(
                "ℹ️ The party is already in the final area.",
                ephemeral=True
            )
            return

        await self._send_test_path_area_embed(interaction, run["run_id"], area_index=3)

    async def trigger_test_path_action(self, interaction: discord.Interaction):
        """Trigger the next scripted Test Path action."""
        session, run = await self._get_active_test_path_run(interaction)
        if not run:
            return

        state = self.dream_manager.get_script_state(run["run_id"])
        area_index = state.get("area_index", 1)
        action_index = state.get("action_index", 0)

        if area_index == 1:
            await interaction.response.send_message(
                "ℹ️ There is nothing to act on here yet.",
                ephemeral=True
            )
            return

        if area_index == 2:
            if action_index == 0:
                # Defer the interaction first
                if not interaction.response.is_done():
                    await interaction.response.defer()

                battle_id = await self._start_test_path_raid(
                    interaction,
                    session,
                    run,
                    opponents=self._build_test_path_aipom_pack(),
                    raid_opponent_slots=4,
                    on_complete=None
                )
                if battle_id:
                    state["action_index"] = 1
                    self.dream_manager.update_script_state(run["run_id"], state)
                else:
                    await interaction.followup.send("❌ Failed to start battle - check logs for details")
                return

            if action_index == 1:
                # Defer the interaction first
                if not interaction.response.is_done():
                    await interaction.response.defer()

                battle_id = await self._start_test_path_raid(
                    interaction,
                    session,
                    run,
                    opponents=self._build_test_path_ambipom(),
                    raid_opponent_slots=3,
                    on_complete=None
                )
                if battle_id:
                    state["action_index"] = 2
                    self.dream_manager.update_script_state(run["run_id"], state)
                else:
                    await interaction.followup.send("❌ Failed to start battle - check logs for details")
                return

            if action_index == 2:
                await self._send_test_path_area_embed(interaction, run["run_id"], area_index=3)
                return

            await interaction.response.send_message(
                "ℹ️ No further actions remain in this area.",
                ephemeral=True
            )
            return

        if area_index == 3:
            if action_index == 0:
                await self._send_embed(
                    interaction,
                    DreamRogueEmbeds.test_path_action(
                        "🎬 Action 3 — The Silent King",
                        "A towering Nidoking emerges. It does not attack — it only watches."
                    )
                )
                battle_id = await self._start_test_path_raid(
                    interaction,
                    session,
                    run,
                    opponents=self._build_test_path_nidoking(),
                    raid_opponent_slots=1,
                    on_complete=None,
                    scripted_sequence="nidoking_test",
                )
                if battle_id:
                    state["action_index"] = 1
                    state["nidoking_battle_id"] = battle_id
                    self.dream_manager.update_script_state(run["run_id"], state)
                return

            if action_index == 1:
                battle_id = state.get("nidoking_battle_id")
                battle_cog = self.bot.get_cog("BattleCog")
                battle = battle_cog.battle_engine.get_battle(battle_id) if battle_cog and battle_id else None
                if not battle or not getattr(battle, "scripted_locked", False):
                    await interaction.response.send_message(
                        "ℹ️ Nidoking is still approaching...",
                        ephemeral=True
                    )
                    return

                await self._send_nidoking_horn_drill(interaction, battle)
                state["action_index"] = 2
                self.dream_manager.update_script_state(run["run_id"], state)
                return

            await interaction.response.send_message(
                "ℹ️ No further actions remain in this area.",
                ephemeral=True
            )
            return


    async def _send_nidoking_horn_drill(self, interaction: discord.Interaction, battle):
        from sprite_helper import PokemonSpriteHelper
        nidoking = (battle.opponent.get_active_pokemon() or [None])[0]
        embed = discord.Embed(
            title="Nidoking used horn drill!",
            description="",
            color=discord.Color.dark_red()
        )
        sprite_url = PokemonSpriteHelper.get_sprite(
            getattr(nidoking, "species_name", None),
            getattr(nidoking, "species_dex_number", None),
            style="animated",
            gender=getattr(nidoking, "gender", None),
            shiny=getattr(nidoking, "is_shiny", False),
            use_fallback=False
        )
        if sprite_url:
            embed.set_thumbnail(url=sprite_url)
        await self._send_embed(interaction, embed)

    def _build_test_path_aipom_pack(self) -> List[Pokemon]:
        species_db = getattr(self.bot, "species_db", SpeciesDatabase("data/pokemon_species.json"))
        species_data = species_db.get_species("aipom")
        pack = []
        for _ in range(4):
            aipom = Pokemon(species_data=species_data, level=2, owner_discord_id=None)
            aipom._calculate_stats()
            aipom.current_hp = aipom.max_hp
            pack.append(aipom)
        return pack

    def _build_test_path_ambipom(self) -> List[Pokemon]:
        species_db = getattr(self.bot, "species_db", SpeciesDatabase("data/pokemon_species.json"))
        species_data = species_db.get_species("ambipom")
        ambipom = Pokemon(
            species_data=species_data,
            level=5,
            owner_discord_id=None,
            moves=["tail_whip", "sand_attack", "double_hit", "dual_chop", "rally_cry"],
        )
        ambipom.is_alpha = True
        ambipom.raid_kind = "alpha"
        ambipom.ensure_moveset_size(4, 4)
        ambipom.scripted_ai = "ambipom_raid"
        ambipom._calculate_stats()
        ambipom.current_hp = ambipom.max_hp
        return [ambipom]

    def _build_test_path_nidoking(self) -> List[Pokemon]:
        species_db = getattr(self.bot, "species_db", SpeciesDatabase("data/pokemon_species.json"))
        species_data = species_db.get_species("nidoking")
        nidoking = Pokemon(
            species_data=species_data,
            level=100,
            owner_discord_id=None,
            moves=["nidoking_wait"],
        )
        nidoking.is_raid_boss = True
        nidoking.raid_kind = "rogue"
        nidoking.scripted_immune_damage = True
        nidoking.scripted_immune_status = True
        nidoking._calculate_stats()
        nidoking.current_hp = nidoking.max_hp
        return [nidoking]

    async def _start_test_path_raid(
        self,
        interaction: discord.Interaction,
        session: dict,
        run: dict,
        opponents: List[Pokemon],
        raid_opponent_slots: int,
        on_complete,
        scripted_sequence: Optional[str] = None,
    ) -> Optional[str]:
        from battle_engine_v2 import BattleFormat, BattleType

        battle_cog = self.bot.get_cog("BattleCog")
        if not battle_cog:
            if interaction.response.is_done():
                await interaction.followup.send("❌ Battle system unavailable!")
            else:
                await interaction.response.send_message("❌ Battle system unavailable!", ephemeral=True)
            return None

        participants = self.session_manager.get_session_participants(session["session_id"])

        # Clean up any stale battle states before checking eligibility
        for user_id in participants:
            if user_id in battle_cog.user_battles:
                battle_id = battle_cog.user_battles.get(user_id)
                battle = battle_cog.battle_engine.get_battle(battle_id) if battle_id else None
                if battle_id:
                    battle_cog.battle_engine.end_battle(battle_id)
                if battle:
                    battle_cog._unregister_battle(battle)
                else:
                    battle_cog.user_battles.pop(user_id, None)

        eligible = []
        skip_missing_member = 0
        skip_in_battle = 0
        skip_no_party = 0
        for user_id in participants:
            user = interaction.guild.get_member(user_id)
            if not user:
                try:
                    user = await interaction.guild.fetch_member(user_id)
                except (discord.NotFound, discord.HTTPException):
                    skip_missing_member += 1
                    continue
            if not user:
                skip_missing_member += 1
                continue
            if user_id in battle_cog.user_battles:
                skip_in_battle += 1
                continue
            trainer_pokemon = self._build_trainer_party(user_id)
            if not trainer_pokemon:
                skip_no_party += 1
                continue
            eligible.append((user, trainer_pokemon))

        if not eligible:
            details = (
                f"(participants: {len(participants)}, "
                f"missing members: {skip_missing_member}, "
                f"in battle: {skip_in_battle}, "
                f"no party: {skip_no_party})"
            )
            if interaction.response.is_done():
                await interaction.followup.send(
                    f"❌ No eligible participants for this battle. {details}"
                )
            else:
                await interaction.response.send_message(
                    f"❌ No eligible participants for this battle. {details}",
                    ephemeral=True
                )
            return None

        raid_entries = [
            {"user_id": user.id, "trainer_name": user.display_name, "party": party}
            for user, party in eligible
        ]

        battle_id = battle_cog.battle_engine.start_battle(
            trainer_id=raid_entries[0]["user_id"],
            trainer_name=", ".join([entry["trainer_name"] for entry in raid_entries]) or "Raid Team",
            trainer_party=raid_entries[0]["party"],
            opponent_party=opponents,
            battle_type=BattleType.TRAINER,
            opponent_is_ai=True,
            opponent_name="Test Path Encounter",
            battle_format=BattleFormat.RAID,
            raid_participants=raid_entries,
            raid_opponent_slots=raid_opponent_slots,
        )

        battle = battle_cog.battle_engine.get_battle(battle_id)
        if battle:
            battle.raid_participants = raid_entries
            battle.no_exp = True
            battle.raid_opponent_slots = raid_opponent_slots
            if scripted_sequence:
                battle.scripted_sequence = scripted_sequence

        for entry in raid_entries:
            battle_cog.user_battles[entry["user_id"]] = battle_id

        parent_channel = interaction.channel
        if isinstance(parent_channel, discord.Thread) and parent_channel.parent:
            parent_channel = parent_channel.parent

        if not isinstance(parent_channel, discord.TextChannel):
            if interaction.response.is_done():
                await interaction.followup.send("❌ Battles can only start in text channels.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Battles can only start in text channels.", ephemeral=True)
            return None

        try:
            mock_interaction = self._create_channel_interaction(parent_channel, interaction.user)
            await battle_cog.prompt_and_start_battle_ui(
                interaction=mock_interaction,
                battle_id=battle_id,
                battle_type=BattleType.TRAINER
            )
        except Exception:
            message = "❌ The Test Path battle couldn't start. Please check logs for details."
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
            return None

        if interaction.channel != parent_channel:
            notice = f"⚔️ Test Path battle started in {parent_channel.mention}."
            if interaction.response.is_done():
                await interaction.followup.send(notice)
            else:
                await interaction.response.send_message(notice)

        if on_complete:
            if not hasattr(self.bot, "dream_rogue_battle_callbacks"):
                self.bot.dream_rogue_battle_callbacks = {}

            async def _battle_done_callback(battle, result, battle_interaction):
                if result == "opponent":
                    await parent_channel.send(embed=DreamRogueEmbeds.test_path_loss())
                completion = on_complete(result)
                if asyncio.iscoroutine(completion):
                    await completion

            self.bot.dream_rogue_battle_callbacks[battle_id] = _battle_done_callback

        return battle_id

    def _build_trainer_party(self, user_id: int) -> List[Pokemon]:
        species_db = getattr(self.bot, "species_db", SpeciesDatabase("data/pokemon_species.json"))
        party_data = self.player_db.get_trainer_party(user_id)
        trainer_pokemon = []
        from ui.buttons import reconstruct_pokemon_from_data
        for poke_data in party_data:
            species_data = species_db.get_species(poke_data["species_dex_number"])
            if not species_data:
                continue
            trainer_pokemon.append(reconstruct_pokemon_from_data(poke_data, species_data))
        return trainer_pokemon

    def _create_channel_interaction(
        self,
        channel: Union[discord.TextChannel, discord.Thread],
        user: discord.Member
    ):
        class MockInteraction:
            def __init__(self, channel, user):
                self.channel = channel
                self.user = user
                self.guild = channel.guild
                self._response_done = False

            @property
            def response(self):
                class Response:
                    def __init__(self, parent):
                        self.parent = parent

                    async def defer(self):
                        self.parent._response_done = True

                    def is_done(self):
                        return self.parent._response_done

                return Response(self)

            @property
            def followup(self):
                class Followup:
                    def __init__(self, parent):
                        self.parent = parent

                    async def send(self, *args, **kwargs):
                        return await self.parent.channel.send(*args, **kwargs)

                return Followup(self)

        return MockInteraction(channel, user)

    async def _send_embed(self, interaction: discord.Interaction, embed: discord.Embed):
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed)
        else:
            await interaction.response.send_message(embed=embed)


async def setup(bot):
    """Load the cog"""
    await bot.add_cog(DreamRogueCog(bot))
