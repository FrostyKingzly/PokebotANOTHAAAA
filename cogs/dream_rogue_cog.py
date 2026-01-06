"""
Dream Rogue Cog

Commands and orchestration for the Dream Rogue roguelike gamemode
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
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
    FloorSelectModal
)


class DreamRogueCog(commands.Cog):
    """Dream Rogue gamemode commands"""

    def __init__(self, bot):
        self.bot = bot
        self.dream_manager = DreamRogueManager()
        self.player_db = PlayerDatabase()
        self.session_manager = SessionManager(self.player_db)

    @app_commands.command(name="dream_stats", description="View your Dream Rogue statistics")
    async def dream_stats(self, interaction: discord.Interaction):
        """View Dream Rogue stats"""
        user_id = interaction.user.id

        # Get persistent Dreamlites
        total_dreamlites = self.dream_manager.get_persistent_dreamlites(user_id)

        # Get stats
        import sqlite3
        conn = sqlite3.connect(self.dream_manager.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM dream_rogue_stats
            WHERE discord_user_id = ?
        """, (user_id,))

        stats_row = cursor.fetchone()
        conn.close()

        if stats_row:
            stats = dict(stats_row)
        else:
            stats = {
                "total_runs": 0,
                "successful_extractions": 0,
                "bosses_defeated": 0,
                "highest_floor": 0,
                "total_battles_won": 0,
                "total_battles_lost": 0
            }

        # Build embed
        embed = discord.Embed(
            title=f"{DreamRogueEmbeds.DREAMLITE_EMOJI} Dream Rogue Statistics",
            description=f"**{interaction.user.display_name}**'s dream journey",
            color=DreamRogueEmbeds.DREAM_COLOR
        )

        embed.add_field(
            name="Dreamlites",
            value=f"{DreamRogueEmbeds.DREAMLITE_EMOJI} **{total_dreamlites}**",
            inline=False
        )

        embed.add_field(
            name="Runs",
            value=f"**Total:** {stats['total_runs']}\n**Successful:** {stats['successful_extractions']}",
            inline=True
        )

        embed.add_field(
            name="Progress",
            value=f"**Highest Floor:** {stats['highest_floor']}\n**Bosses Defeated:** {stats['bosses_defeated']}",
            inline=True
        )

        if stats['total_battles_won'] + stats['total_battles_lost'] > 0:
            win_rate = (stats['total_battles_won'] / (stats['total_battles_won'] + stats['total_battles_lost'])) * 100
            embed.add_field(
                name="Battles",
                value=f"**Won:** {stats['total_battles_won']}\n**Lost:** {stats['total_battles_lost']}\n**Win Rate:** {win_rate:.1f}%",
                inline=True
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def start_dive_from_session(self, interaction: discord.Interaction, stage_level: int):
        """
        Start a dive from session mode (called from session controls)

        Args:
            interaction: Discord interaction
            stage_level: Stage level (10, 20, 30, etc.)
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
                "❌ Only the session admin can start a Dream Rogue dive!",
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
                stamina_cost=0  # No cost for Dream Rogue entry
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to move session to Dreamyard: {e}",
                ephemeral=True
            )
            return

        # Create Dream Rogue run
        run_id = self.dream_manager.create_run(
            guild_id=interaction.guild_id,
            initiator_id=interaction.user.id,
            stage_level=stage_level,
            starting_floor=1,  # Always start at floor 1
            session_id=session["session_id"]
        )

        # Add all session participants
        for participant in participants:
            if participant["discord_user_id"] != interaction.user.id:
                self.dream_manager.add_participant(run_id, participant["discord_user_id"])

        # Show dive start embed
        participants_list = [interaction.user.id] + [p["discord_user_id"] for p in participants if p["discord_user_id"] != interaction.user.id]

        embed = DreamRogueEmbeds.dive_start(stage_level, participants_list)

        await interaction.response.send_message(embed=embed)

        # Start first floor
        await asyncio.sleep(2)
        await self._start_floor(interaction, run_id)

    async def start_dive_solo(self, interaction: discord.Interaction, stage_level: int):
        """
        Start a solo dive or create invite (from Dreamyard location)

        Args:
            interaction: Discord interaction
            stage_level: Stage level (10, 20, 30, etc.)
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
            stage_level=stage_level,
            starting_floor=1  # Always start at floor 1
        )

        # Show join/start embed
        participants = self.dream_manager.get_participants(run_id)
        run = self.dream_manager.get_run(run_id)
        floor_range = self.dream_manager.get_floor_level_range(stage_level, 1)

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
            embed = DreamRogueEmbeds.dive_start(
                run["starting_floor"],
                [p["discord_user_id"] for p in participants]
            )

            await interaction.response.edit_message(embed=embed, view=None)

            # Start first floor
            await asyncio.sleep(2)
            await self._start_floor(interaction, run_id)

        else:
            # Just update lobby
            participants = self.dream_manager.get_participants(run_id)
            floor_range = self.dream_manager.get_floor_level_range(run["starting_floor"])

            embed = DreamRogueEmbeds.run_status(run, participants, floor_range)
            embed.description += "\n\n*Waiting for participants... Click 'Start Dive' when ready.*"

            # Don't change view
            await interaction.response.defer()

    async def _start_floor(self, interaction: discord.Interaction, run_id: str):
        """Start a new floor"""
        run = self.dream_manager.get_run(run_id)
        floor = run["current_floor"]

        stage_embed = DreamRogueEmbeds.stage_intro(floor)
        await self._send_embed(interaction, stage_embed)

        # Generate instances for floor
        instances = self.dream_manager.generate_floor_instances(run_id, floor)

        if not instances:
            await interaction.followup.send("❌ Failed to generate floor instances!")
            return

        # Show first instance
        await self._show_instance(interaction, run_id, instances[0], instances)

    async def _show_instance(
        self,
        interaction: discord.Interaction,
        run_id: str,
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
                lambda i, result: self._on_instance_complete(i, run_id, instance, result, remaining_instances),
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
                lambda i, result: self._on_instance_complete(i, run_id, instance, result, remaining_instances)
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

            for participant in participants:
                self.dream_manager.add_dreamlites(
                    run_id,
                    participant["discord_user_id"],
                    dreamlites_gained
                )

            buffs = []
            if floor == 1 and result == "battle_complete":
                buffs = self.dream_manager.grant_positive_buffs(run_id, count=2)

            reward_embed = DreamRogueEmbeds.battle_reward(
                victory=True,
                dreamlites_gained=dreamlites_gained,
                exp_gained=0,
                buffs_applied=buffs
            )
            await interaction.followup.send(embed=reward_embed)

        if not remaining_instances:
            # Floor complete!
            # Check if boss defeated or regular floor
            if floor == 10 and "boss" in result.lower():
                # Boss defeated - run complete!
                participants = self.dream_manager.get_participants(run_id)
                total_dreamlites = sum(p["dreamlites"] for p in participants)

                self.dream_manager.end_run(run_id, extracted=True)

                embed = DreamRogueEmbeds.extraction_summary(run, participants, floor, total_dreamlites)

                await interaction.followup.send(embed=embed)

            else:
                # Advance to next floor
                new_floor = self.dream_manager.advance_floor(run_id)

                embed = DreamRogueEmbeds.stage_travel(floor, new_floor)

                await interaction.followup.send(embed=embed)

                # Start next floor after delay
                await asyncio.sleep(3)
                await self._start_floor(interaction, run_id)

        else:
            # More instances on this floor
            await self._show_instance(interaction, run_id, remaining_instances[0], remaining_instances)

    async def _send_embed(self, interaction: discord.Interaction, embed: discord.Embed):
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed)
        else:
            await interaction.response.send_message(embed=embed)


async def setup(bot):
    """Load the cog"""
    await bot.add_cog(DreamRogueCog(bot))
