"""Community event detection for bumps and server boosts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Set

import discord
from discord.ext import commands

DISBOARD_BOT_ID = 302050872383242240
USER_MENTION_PATTERN = re.compile(r"<@!?(\d+)>")
REVERIE_GUILD_ID = 1477425059147677878
REVERIE_WELCOME_CHANNEL_ID = 1477876580284891197
REVERIE_RULES_CHANNEL_ID = 1477614227052167250
REVERIE_INTRODUCTIONS_CHANNEL_ID = 1478527442795630683
REVERIE_WELCOME_GIF_URL = "https://tenor.com/view/joie-pikachu-pokemon-bohneur-gif-20062195"
REVERIE_WELCOME_COLOR = discord.Color.orange()


@dataclass
class BumpRecord:
    """Metadata captured when a bump success message is detected."""

    bumper_user_id: Optional[int]
    detected_at: datetime
    source_message_id: int
    source_channel_id: int


def _extract_user_id_from_text(text: str) -> Optional[int]:
    """Extract the first mentioned user ID from a message body."""

    if not text:
        return None
    match = USER_MENTION_PATTERN.search(text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def _normalize_text(text: str) -> str:
    """Normalize text for case-insensitive matching."""

    return re.sub(r"\s+", " ", (text or "").strip().lower())


class CommunityEventsCog(commands.Cog):
    """Tracks community events so other systems can reward them later."""

    BUMP_SUCCESS_MARKERS = (
        "bump done",
        "you can bump again",
        "server bumped",
        "successfully bumped",
    )

    def __init__(self, bot):
        self.bot = bot
        self.latest_bumps_by_guild: Dict[int, BumpRecord] = {}
        self.boosters_by_guild: Dict[int, Set[int]] = {}

    async def _send_reverie_welcome(self, member: discord.Member):
        if member.guild.id != REVERIE_GUILD_ID:
            return

        channel = member.guild.get_channel(REVERIE_WELCOME_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            return

        description = (
            f"Welcome to Reverie City, {member.mention}!\n\n"
            f"We're glad you've arrived. Be sure to check out our <#{REVERIE_RULES_CHANNEL_ID}> "
            f"and <#{REVERIE_INTRODUCTIONS_CHANNEL_ID}> if you want to introduce yourself! "
            "When you're ready to make a character, the rp information category is available "
            "to read before you step into the night.\n\n"
            "May all your dreams come true in Reverie!\n\n"
            f"{REVERIE_WELCOME_GIF_URL}"
        )

        embed = discord.Embed(description=description, color=REVERIE_WELCOME_COLOR)
        await channel.send(embed=embed)

    async def cog_load(self):
        """Prime booster caches from member state at startup."""

        self._refresh_all_boosters()

    def _refresh_all_boosters(self):
        for guild in self.bot.guilds:
            self._refresh_guild_boosters(guild)

    def _refresh_guild_boosters(self, guild: discord.Guild):
        booster_ids = {
            member.id
            for member in guild.members
            if getattr(member, "premium_since", None) is not None
        }
        self.boosters_by_guild[guild.id] = booster_ids

    def get_latest_bump(self, guild_id: int) -> Optional[BumpRecord]:
        return self.latest_bumps_by_guild.get(guild_id)

    def get_current_boosters(self, guild_id: int) -> Set[int]:
        return set(self.boosters_by_guild.get(guild_id, set()))

    def is_current_booster(self, guild_id: int, user_id: int) -> bool:
        return user_id in self.boosters_by_guild.get(guild_id, set())

    def _is_bump_success_message(self, message: discord.Message) -> bool:
        if not message.author.bot:
            return False

        author_id = getattr(message.author, "id", None)
        if author_id is not None and author_id != DISBOARD_BOT_ID:
            return False

        text_blobs = [message.content]
        for embed in message.embeds:
            text_blobs.extend([
                embed.title or "",
                embed.description or "",
                embed.footer.text if embed.footer else "",
            ])

        normalized = _normalize_text(" ".join(text_blobs))
        if not normalized:
            return False

        return any(marker in normalized for marker in self.BUMP_SUCCESS_MARKERS)

    def _extract_bumper_user_id(self, message: discord.Message) -> Optional[int]:
        interaction = getattr(message, "interaction", None)
        interaction_user = getattr(interaction, "user", None)
        if interaction_user:
            return interaction_user.id

        metadata = getattr(message, "interaction_metadata", None)
        metadata_user = getattr(metadata, "user", None)
        if metadata_user:
            return metadata_user.id

        metadata_user_id = getattr(metadata, "user_id", None)
        if metadata_user_id:
            return int(metadata_user_id)

        if message.mentions:
            return message.mentions[0].id

        text_candidates = [message.content]
        for embed in message.embeds:
            text_candidates.append(embed.description or "")
        for text in text_candidates:
            user_id = _extract_user_id_from_text(text)
            if user_id:
                return user_id

        return None

    def _record_bump(self, message: discord.Message):
        if not message.guild:
            return

        bumper_user_id = self._extract_bumper_user_id(message)
        self.latest_bumps_by_guild[message.guild.id] = BumpRecord(
            bumper_user_id=bumper_user_id,
            detected_at=datetime.now(timezone.utc),
            source_message_id=message.id,
            source_channel_id=message.channel.id,
        )

    @commands.Cog.listener()
    async def on_ready(self):
        self._refresh_all_boosters()

    @commands.Cog.listener()
    async def on_guild_available(self, guild: discord.Guild):
        self._refresh_guild_boosters(guild)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self._send_reverie_welcome(member)

        if member.premium_since is None:
            return
        self.boosters_by_guild.setdefault(member.guild.id, set()).add(member.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild_boosters = self.boosters_by_guild.get(member.guild.id)
        if guild_boosters is not None:
            guild_boosters.discard(member.id)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        guild_boosters = self.boosters_by_guild.setdefault(after.guild.id, set())

        before_boosting = before.premium_since is not None
        after_boosting = after.premium_since is not None

        if after_boosting:
            guild_boosters.add(after.id)
        else:
            guild_boosters.discard(after.id)

        if before_boosting != after_boosting:
            # Kept as no-op marker for future reward hooks.
            return

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return

        if not self._is_bump_success_message(message):
            return

        self._record_bump(message)


async def setup(bot):
    await bot.add_cog(CommunityEventsCog(bot))
