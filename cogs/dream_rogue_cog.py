"""
Dream Dive Cog

Commands and orchestration for the Dream Dive roguelike gamemode
"""

import discord
from discord.ext import commands
from typing import List
import asyncio
import random

from dream_rogue_manager import DreamRogueManager
from database import PlayerDatabase
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

    async def _send_embed(self, interaction: discord.Interaction, embed: discord.Embed):
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed)
        else:
            await interaction.response.send_message(embed=embed)


async def setup(bot):
    """Load the cog"""
    await bot.add_cog(DreamRogueCog(bot))
