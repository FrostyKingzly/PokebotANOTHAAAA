"""Commands for viewing and managing the ranked ladder."""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List

from rank_manager import (
    GIMMICK_OPTIONS,
    get_rank_tier_definition,
)
from ui.embeds import EmbedBuilder
from guild_config import get_rank_announcement_channel_id


def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator


class RankCog(commands.Cog):
    """Public and admin utilities for the ranked ladder."""

    def __init__(self, bot):
        self.bot = bot

    def _get_manager(self):
        return getattr(self.bot, "rank_manager", None)

    # ------------------------------------------------------------------
    # Public commands
    # ------------------------------------------------------------------
    @app_commands.command(name="rankings", description="Show the current Challenger leaderboard")
    async def rankings(self, interaction: discord.Interaction):
        manager = self._get_manager()
        if not manager:
            await interaction.response.send_message("⚠️ Ranked ladder is still booting.", ephemeral=True)
            return
        rows = manager.get_leaderboard(limit=15)
        description_lines: List[str] = []
        for idx, row in enumerate(rows, start=1):
            tier_number = row.get("rank_tier_number") or 1
            tier_name = get_rank_tier_definition(tier_number)["name"]
            ticket = " 🎟️" if row.get("has_promotion_ticket") else ""
            description_lines.append(
                f"**{idx}. {row['trainer_name']}** — {tier_name} · {row['ladder_points']} pts{ticket}"
            )
        if not description_lines:
            description_lines.append("No ranked data yet. Win some ranked battles to appear here!")

        embed = discord.Embed(
            title="🏆 League Leaderboard",
            description="\n".join(description_lines),
            color=discord.Color.gold(),
        )
        embed.set_footer(text=f"Highest unlocked tier: {manager.get_highest_unlocked_tier()}/8")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rank_info", description="Check your ranked progress")
    async def rank_info(self, interaction: discord.Interaction):
        trainer = self.bot.player_manager.get_player(interaction.user.id)
        if not trainer:
            await interaction.response.send_message("You need to `/register` before battling ranked!", ephemeral=True)
            return
        manager = self._get_manager()
        if not manager:
            await interaction.response.send_message("⚠️ Ranked ladder is unavailable right now.", ephemeral=True)
            return
        tier_number = trainer.rank_tier_number or 1
        definition = get_rank_tier_definition(tier_number)
        threshold = definition.get("ticket_threshold", 0)
        progress = EmbedBuilder.format_rank_progress(trainer) if 'EmbedBuilder' in globals() else f"{trainer.ladder_points} pts"
        info_lines = [
            f"**Tier:** {definition['name']} (#{tier_number})",
            f"**Points:** {trainer.ladder_points} / {threshold or '—'}",
            f"**Ticket:** {'🎟️ Ready' if trainer.has_promotion_ticket else 'Not earned'}",
        ]
        if trainer.rank_pending_tier:
            info_lines.append(f"**Pending Promotion:** Tier {trainer.rank_pending_tier}")
        elif trainer.has_promotion_ticket:
            info_lines.append("Awaiting promotion match assignment.")
        if getattr(trainer, "omni_ring_gimmicks", None):
            readable = ", ".join(GIMMICK_OPTIONS.get(g, g.title()) for g in trainer.omni_ring_gimmicks)
            info_lines.append(f"**Omni Ring:** {readable}")
        elif trainer.has_omni_ring:
            info_lines.append("**Omni Ring:** Unconfigured. Use /rank_select_gimmick.")

        embed = discord.Embed(
            title=f"{trainer.trainer_name}'s Ranked Profile",
            description="\n".join(info_lines),
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Progress", value=progress, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="rank_select_gimmick", description="Assign a gimmick to your Omni Ring")
    @app_commands.describe(gimmick="Which battle gimmick to unlock (mega/zmove/dynamax/terastal)")
    async def rank_select_gimmick(self, interaction: discord.Interaction, gimmick: str):
        trainer = self.bot.player_manager.get_player(interaction.user.id)
        if not trainer:
            await interaction.response.send_message("You need to register first!", ephemeral=True)
            return
        manager = self._get_manager()
        if not manager:
            await interaction.response.send_message("Ranked ladder unavailable.", ephemeral=True)
            return
        success, message = manager.select_gimmick(trainer, gimmick)
        if success:
            await interaction.response.send_message(f"✅ {message}", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)

    # ------------------------------------------------------------------
    # Admin commands
    # ------------------------------------------------------------------
    @app_commands.command(name="rank_queue", description="[ADMIN] View all trainers with Challenger tickets")
    @app_commands.check(is_admin)
    async def rank_queue(self, interaction: discord.Interaction):
        manager = self._get_manager()
        if not manager:
            await interaction.response.send_message("Rank system offline.", ephemeral=True)
            return
        rows = manager.get_ticket_queue()
        if not rows:
            await interaction.response.send_message("No trainers currently hold Challenger tickets.", ephemeral=True)
            return
        tiers: dict[int, List[str]] = {}
        for row in rows:
            tier = row.get("ticket_tier") or row.get("rank_tier_number") or 1
            tiers.setdefault(tier, []).append(
                f"<@{row['discord_user_id']}> — {row['ladder_points']} pts"
            )
        embed = discord.Embed(title="🎟️ Challenger Ticket Queue", color=discord.Color.orange())
        for tier, lines in sorted(tiers.items()):
            embed.add_field(
                name=f"Tier {tier} · {get_rank_tier_definition(tier)['name']}",
                value="\n".join(lines),
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="twilight_invite", description="[ADMIN] Send Twilight Summit invites to all trainers")
    @app_commands.check(is_admin)
    async def twilight_invite(self, interaction: discord.Interaction):
        manager = self._get_manager()
        if not manager:
            await interaction.response.send_message("Rank system offline.", ephemeral=True)
            return

        manager.activate_twilight_invite()
        await interaction.response.send_message(
            "✅ Twilight Summit invites have been delivered. New trainers will see the alert automatically.",
            ephemeral=True,
        )

    @app_commands.command(name="twilight_begin", description="[ADMIN] Begin the Twilight Summit and unlock ranked battles")
    @app_commands.check(is_admin)
    async def twilight_begin(self, interaction: discord.Interaction):
        manager = self._get_manager()
        if not manager:
            await interaction.response.send_message("Rank system offline.", ephemeral=True)
            return

        manager.begin_twilight_summit()
        participants = manager._state.get("twilight_participants") or []
        await interaction.response.send_message(
            f"✅ The Twilight Summit has begun for {len(participants)} registered trainers.",
            ephemeral=True,
        )

    @app_commands.command(name="rank_unlock", description="[ADMIN] Unlock the next rank tier")
    @app_commands.describe(tier="Highest tier (1-8) that should be unlocked")
    @app_commands.check(is_admin)
    async def rank_unlock(self, interaction: discord.Interaction, tier: int):
        manager = self._get_manager()
        if not manager:
            await interaction.response.send_message("Rank system offline.", ephemeral=True)
            return
        promoted = manager.unlock_up_to(tier)
        lines = [f"Unlocked up to Tier {manager.get_highest_unlocked_tier()}."]
        if promoted:
            for entry in promoted:
                text = f"{entry['trainer_name']} → {get_rank_tier_definition(entry['new_tier'])['name']}"
                if entry.get("omni_text"):
                    text += f" ({entry['omni_text']})"
                lines.append(text)
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="rank_matches", description="[ADMIN] List pending promotion matches")
    @app_commands.check(is_admin)
    async def rank_matches(self, interaction: discord.Interaction):
        manager = self._get_manager()
        if not manager:
            await interaction.response.send_message("Rank system offline.", ephemeral=True)
            return
        matches = manager.list_matches()
        if not matches:
            await interaction.response.send_message("No promotion matches are currently scheduled.", ephemeral=True)
            return
        embed = discord.Embed(title="📋 Scheduled Promotion Matches", color=discord.Color.green())
        for match in matches:
            players = [p for p in match.participants if p.get("type") == "player"]
            npcs = [p for p in match.participants if p.get("type") == "npc"]
            player_text = ", ".join(f"<@{p['id']}>" for p in players) if players else "—"
            npc_text = ", ".join(p.get("name", "NPC") for p in npcs) if npcs else "—"
            value = f"Players: {player_text}\nNPCs: {npc_text}\nFormat: {match.format.title()}"
            if match.notes:
                value += f"\nNotes: {match.notes}"
            embed.add_field(
                name=f"{match.match_id} · Tier {match.tier}",
                value=value,
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="rank_schedule", description="[ADMIN] Schedule a promotion match")
    @app_commands.check(is_admin)
    @app_commands.describe(
        tier="Tier the players are attempting to promote from",
        player_one="Primary challenger",
        player_two="Optional second player",
        player_three="Optional third player (for multi battles)",
        player_four="Optional fourth player",
        npc_name="Optional NPC opponent name",
        npc_rank="NPC rank tier (defaults to the provided tier)",
        notes="Optional notes to show staff",
    )
    @app_commands.choices(
        format=[
            app_commands.Choice(name="Singles", value="singles"),
            app_commands.Choice(name="Doubles", value="doubles"),
            app_commands.Choice(name="Multi (2v2)", value="multi"),
        ]
    )
    async def rank_schedule(
        self,
        interaction: discord.Interaction,
        tier: int,
        format: app_commands.Choice[str],
        player_one: discord.User,
        player_two: Optional[discord.User] = None,
        player_three: Optional[discord.User] = None,
        player_four: Optional[discord.User] = None,
        npc_name: Optional[str] = None,
        npc_rank: Optional[int] = None,
        notes: Optional[str] = None,
    ):
        manager = self._get_manager()
        if not manager:
            await interaction.response.send_message("Rank system offline.", ephemeral=True)
            return
        tier = max(1, min(8, tier))
        players = [p for p in [player_one, player_two, player_three, player_four] if p is not None]
        if not players:
            await interaction.response.send_message("At least one player is required.", ephemeral=True)
            return
        if npc_name and len(players) != 1:
            await interaction.response.send_message("NPC promotion matches can only involve one player.", ephemeral=True)
            return
        player_ids = []
        for user in players:
            trainer = self.bot.player_manager.get_player(user.id)
            if not trainer:
                await interaction.response.send_message(f"{user.mention} is not registered.", ephemeral=True)
                return
            if not trainer.has_promotion_ticket or (trainer.ticket_tier or tier) != tier:
                await interaction.response.send_message(
                    f"{user.mention} does not hold a ticket for tier {tier}.",
                    ephemeral=True,
                )
                return
            if manager.has_pending_match(user.id):
                await interaction.response.send_message(
                    f"{user.mention} already has a pending promotion match.",
                    ephemeral=True,
                )
                return
            player_ids.append(user.id)
        npc_payload = None
        if npc_name:
            npc_payload = {"name": npc_name, "rank_tier_number": npc_rank or tier}
        match = manager.schedule_match(
            tier=tier,
            format_name=format.value,
            player_ids=player_ids,
            created_by=interaction.user.id,
            npc_participant=npc_payload,
            notes=notes,
        )

        # Let the admin know privately
        await interaction.response.send_message(
            f"Scheduled match {match.match_id} for tier {tier} ({format.name}).",
            ephemeral=True,
        )

        # Broadcast a hype embed to the configured announcement channel, if any
        if interaction.guild:
            announce_channel_id = get_rank_announcement_channel_id(interaction.guild.id)
            if announce_channel_id:
                channel = interaction.guild.get_channel(announce_channel_id) or self.bot.get_channel(announce_channel_id)
                if channel:
                    tier_def = get_rank_tier_definition(tier)
                    tier_name = tier_def.get("name") or f"Tier {tier}"
                    players = [p for p in match.participants if p.get("type") == "player"]
                    npcs = [p for p in match.participants if p.get("type") == "npc"]

                    player_mentions = ", ".join(f"<@{p['id']}>" for p in players) if players else "—"
                    npc_names = ", ".join(p.get("name", "NPC") for p in npcs) if npcs else "—"

                    embed = discord.Embed(
                        title="🏆 Rank-Up Showdown Scheduled!",
                        description=(
                            f"A **Tier {tier_name}** promotion match has been scheduled!\n"
                            "Who will rise to the next rank?"
                        ),
                        color=discord.Color.gold(),
                    )
                    embed.add_field(name="Format", value=format.name, inline=True)
                    embed.add_field(name="Match ID", value=match.match_id, inline=True)
                    embed.add_field(name="Challenger(s)", value=player_mentions, inline=False)
                    embed.add_field(name="Opponent(s)", value=npc_names, inline=False)

                    if notes:
                        embed.add_field(name="Details", value=notes, inline=False)

                    embed.set_footer(text="Place your bets and cheer them on!")
                    await channel.send(embed=embed)



async def setup(bot):
    await bot.add_cog(RankCog(bot))
