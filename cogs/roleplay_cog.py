"""Roleplay Cog - Handles RP session tracking in location channels."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands


WORD_RE = re.compile(r"[A-Za-z0-9']+")
PAREN_RE = re.compile(r"\([^)]*\)")
RP_EXP_WORD_RATIO = 10

# Temporary placeholder rewards until per-location tuning is provided.
# Keys should be location_id values from LocationManager.
ROLEPLAY_CHANNEL_STAT_REWARDS: Dict[str, Dict[str, int]] = {
    # "lights_district_plaza": {"charisma": 1},
    # "residential_district_library": {"insight": 1},
}
DEFAULT_STAT_REWARD: Dict[str, int] = {"heart": 1}


@dataclass
class RoleplaySession:
    user_id: int
    channel_id: int
    location_id: str
    word_count: int = 0


class RPStartConfirmView(discord.ui.View):
    """Confirmation view for beginning an RP session."""

    def __init__(self, cog: "RoleplayCog", user_id: int, channel_id: int, location_id: str):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.channel_id = channel_id
        self.location_id = location_id

    async def _validate_user(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This confirmation isn't for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validate_user(interaction):
            return

        created = self.cog.start_session(self.user_id, self.channel_id, self.location_id)
        if not created:
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="⚠️ Already Roleplaying",
                    description="You're already in an RP session. End it first with `/rotom_roleplay`.",
                    color=discord.Color.orange(),
                ),
                view=None,
            )
            return

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="🎭 RP Started",
                description=(
                    "Your roleplay session is now active in this channel.\n"
                    "I'll count your words until you run `/rotom_roleplay` again."
                ),
                color=discord.Color.green(),
            ),
            view=None,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validate_user(interaction):
            return

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Cancelled",
                description="No RP session was started.",
                color=discord.Color.blurple(),
            ),
            view=None,
        )


class RPSpendStaminaView(discord.ui.View):
    """Optional stamina spend after RP ends."""

    def __init__(
        self,
        cog: "RoleplayCog",
        user_id: int,
        location_id: str,
        word_count: int,
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.location_id = location_id
        self.word_count = word_count

    async def _validate_user(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This prompt isn't for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Use 1 Stamina", style=discord.ButtonStyle.success, emoji="⚡")
    async def use_stamina(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validate_user(interaction):
            return

        trainer = self.cog.bot.player_manager.get_player(self.user_id)
        if not trainer:
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="❌ No Trainer Data",
                    description="Could not find your trainer profile.",
                    color=discord.Color.red(),
                ),
                view=None,
            )
            return

        success, remaining = self.cog.bot.player_manager.consume_stamina(self.user_id, 1)
        if not success:
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="⚠️ Not Enough Stamina",
                    description="You don't have enough stamina to claim extra RP rewards.",
                    color=discord.Color.orange(),
                ),
                view=None,
            )
            return

        stat_rewards = self.cog.get_stat_reward_for_location(self.location_id)
        applied_lines = []
        for stat_key, amount in stat_rewards.items():
            outcome = self.cog.apply_social_points(trainer, stat_key, amount)
            applied_lines.append(
                f"• **{stat_key.title()}** +{amount} → Rank {outcome['new_rank']}"
            )

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="✨ Bonus Rewards Claimed",
                description=(
                    f"You spent **1 stamina** (remaining: **{remaining}**).\n"
                    f"RP EXP awarded: **{self.word_count}** to each party Pokémon.\n\n"
                    "Social stat rewards:\n"
                    + "\n".join(applied_lines)
                ),
                color=discord.Color.gold(),
            ),
            view=None,
        )

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary, emoji="➡️")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validate_user(interaction):
            return

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="RP Rewards Complete",
                description="Skipped stamina bonus. Your RP EXP was still applied.",
                color=discord.Color.blurple(),
            ),
            view=None,
        )


class RPEndConfirmView(discord.ui.View):
    """Confirmation view for ending an RP session."""

    def __init__(self, cog: "RoleplayCog", session: RoleplaySession):
        super().__init__(timeout=120)
        self.cog = cog
        self.session = session

    async def _validate_user(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.session.user_id:
            await interaction.response.send_message("❌ This confirmation isn't for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="End RP", style=discord.ButtonStyle.danger, emoji="🛑")
    async def end_rp(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validate_user(interaction):
            return

        session = self.cog.end_session(self.session.user_id)
        if not session:
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="⚠️ RP Session Missing",
                    description="I couldn't find your active RP session anymore.",
                    color=discord.Color.orange(),
                ),
                view=None,
            )
            return

        exp_amount = max(0, session.word_count // RP_EXP_WORD_RATIO)
        exp_results = self.cog.award_party_exp(self.session.user_id, exp_amount)
        summary_lines = [
            f"• EXP per party Pokémon: **{exp_amount}** (1 EXP per {RP_EXP_WORD_RATIO} words)",
        ]

        if exp_results:
            summary_lines.append("\n**Party EXP results:**")
            for line in exp_results:
                summary_lines.append(f"• {line}")
        else:
            summary_lines.append("\nNo eligible party Pokémon found for EXP.")

        location_name = self.cog.bot.location_manager.get_location_name(session.location_id) or session.location_id
        embed = discord.Embed(
            title="🎬 RP Ended",
            description="\n".join(summary_lines),
            color=discord.Color.green(),
        )
        embed.set_footer(text=f"Location: {location_name}")

        await interaction.response.edit_message(embed=embed, view=None)

        bonus_embed = discord.Embed(
            title="⚡ Bonus Prompt",
            description=(
                "Spend **1 stamina** to claim this channel's social stat reward.\n"
                "(This is in addition to the RP EXP you already received.)"
            ),
            color=discord.Color.blurple(),
        )
        await interaction.followup.send(
            embed=bonus_embed,
            view=RPSpendStaminaView(self.cog, self.session.user_id, session.location_id, exp_amount),
            ephemeral=True,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validate_user(interaction):
            return

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Continue RP",
                description="Your roleplay session is still active.",
                color=discord.Color.blurple(),
            ),
            view=None,
        )


class RoleplayCog(commands.Cog):
    """Tracks channel-based roleplay sessions and rewards."""

    def __init__(self, bot):
        self.bot = bot
        self.active_sessions: Dict[int, RoleplaySession] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message or message.author.bot or not message.guild:
            return

        user_id = message.author.id
        session = self.active_sessions.get(user_id)
        if not session:
            return

        if message.channel.id != session.channel_id:
            return

        session.word_count += self.count_words(message.content)

    @app_commands.command(name="rotom_roleplay", description="Start or end a roleplay session in an RP travel channel")
    async def rotom_roleplay(self, interaction: discord.Interaction):
        player_data = self.bot.player_manager.get_player(interaction.user.id)
        if not player_data:
            await interaction.response.send_message(
                "❌ You need to register first with `/register`.",
                ephemeral=True,
            )
            return

        location_manager = getattr(self.bot, "location_manager", None)
        if not location_manager:
            await interaction.response.send_message(
                "❌ Location system is unavailable right now.",
                ephemeral=True,
            )
            return

        parent_id = interaction.channel.parent_id if isinstance(interaction.channel, discord.Thread) else None
        location_id = location_manager.get_location_by_channel(interaction.channel_id, parent_id=parent_id)
        if not location_id:
            await interaction.response.send_message(
                "❌ You can only use this command in mapped RP/travel channels.",
                ephemeral=True,
            )
            return

        current_session = self.active_sessions.get(interaction.user.id)
        if current_session:
            if interaction.channel_id != current_session.channel_id:
                await interaction.response.send_message(
                    "❌ You're already in an RP session in another channel. Return there and run `/rotom_roleplay` to end it.",
                    ephemeral=True,
                )
                return

            embed = discord.Embed(
                title="🛑 End Roleplay?",
                description=(
                    "Do you want to end this RP session now?"
                ),
                color=discord.Color.orange(),
            )
            await interaction.response.send_message(
                embed=embed,
                view=RPEndConfirmView(self, current_session),
                ephemeral=True,
            )
            return

        location_name = location_manager.get_location_name(location_id) or location_id
        start_embed = discord.Embed(
            title="🎭 Start Roleplay?",
            description=(
                f"Location: **{location_name}**\n\n"
                "If you confirm, I'll begin counting your RP words in this channel."
            ),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(
            embed=start_embed,
            view=RPStartConfirmView(self, interaction.user.id, interaction.channel_id, location_id),
            ephemeral=True,
        )

    def start_session(self, user_id: int, channel_id: int, location_id: str) -> bool:
        if user_id in self.active_sessions:
            return False

        self.active_sessions[user_id] = RoleplaySession(
            user_id=user_id,
            channel_id=channel_id,
            location_id=location_id,
            word_count=0,
        )
        return True

    def end_session(self, user_id: int) -> Optional[RoleplaySession]:
        return self.active_sessions.pop(user_id, None)

    @staticmethod
    def count_words(content: str) -> int:
        if not content:
            return 0

        stripped = PAREN_RE.sub(" ", content)
        words = WORD_RE.findall(stripped)
        return len(words)

    def award_party_exp(self, user_id: int, exp_amount: int) -> list[str]:
        if exp_amount <= 0:
            return []

        party = self.bot.player_manager.get_party(user_id)
        results = []
        for pokemon in party:
            pokemon_id = pokemon.get("pokemon_id")
            if not pokemon_id:
                continue

            result = self.bot.player_manager.grant_experience(user_id, pokemon_id, exp_amount)
            if not result:
                continue

            name = pokemon.get("nickname") or pokemon.get("species_name", "Pokemon")
            old_level = result.get("old_level")
            new_level = result.get("new_level")
            if old_level is not None and new_level is not None and new_level > old_level:
                results.append(f"{name}: +{exp_amount} EXP (Lv {old_level} → {new_level})")
            else:
                results.append(f"{name}: +{exp_amount} EXP")

        return results

    def get_stat_reward_for_location(self, location_id: str) -> Dict[str, int]:
        if not location_id:
            return dict(DEFAULT_STAT_REWARD)
        rewards = ROLEPLAY_CHANNEL_STAT_REWARDS.get(location_id)
        if rewards:
            return dict(rewards)
        return dict(DEFAULT_STAT_REWARD)

    def apply_social_points(self, trainer, stat_key: str, amount: int) -> Dict[str, int]:
        from social_stats import calculate_max_stamina, clamp_points, get_stat_cap, points_to_rank

        if amount <= 0:
            current_points = getattr(trainer, f"{stat_key}_points", 0)
            cap = trainer.get_stat_cap(stat_key)
            return {
                "new_rank": getattr(trainer, f"{stat_key}_rank", 0),
                "new_points": current_points,
                "cap": cap,
            }

        cap = get_stat_cap(stat_key, trainer.boon_stat, trainer.bane_stat)
        old_points = getattr(trainer, f"{stat_key}_points", 0)
        new_points = clamp_points(old_points + amount, cap)
        new_rank = points_to_rank(new_points, cap)

        updates = {
            f"{stat_key}_points": new_points,
            f"{stat_key}_rank": new_rank,
        }

        if stat_key == "fortitude":
            new_max = calculate_max_stamina(new_rank)
            current_stamina = min(getattr(trainer, "stamina_current", new_max), new_max)
            updates["stamina_max"] = new_max
            updates["stamina_current"] = current_stamina
            trainer.stamina_max = new_max
            trainer.stamina_current = current_stamina

        self.bot.player_manager.update_player(trainer.discord_user_id, **updates)

        setattr(trainer, f"{stat_key}_points", new_points)
        setattr(trainer, f"{stat_key}_rank", new_rank)
        if hasattr(trainer, "social_stats") and stat_key in trainer.social_stats:
            trainer.social_stats[stat_key]["points"] = new_points
            trainer.social_stats[stat_key]["rank"] = new_rank

        return {
            "new_rank": new_rank,
            "new_points": new_points,
            "cap": cap,
        }


async def setup(bot):
    await bot.add_cog(RoleplayCog(bot))
