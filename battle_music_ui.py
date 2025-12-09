"""
Battle Music UI Components
Provides UI views for music opt-in and queue display.
"""

import discord
from typing import Optional, Callable


class MusicOptInView(discord.ui.View):
    """
    View presented when a battle starts, asking if player wants music.
    """

    def __init__(self, on_yes: Callable, on_no: Callable, on_my_theme: Optional[Callable] = None, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.on_yes = on_yes
        self.on_no = on_no
        self.on_my_theme = on_my_theme
        self.choice = None
        self.use_custom_theme = False

    @discord.ui.button(label="Yes, play music!", style=discord.ButtonStyle.green, emoji="🎵")
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """User wants music for their battle (random NPC theme)"""
        self.choice = True
        self.use_custom_theme = False
        await self.on_yes(interaction)
        self.stop()

    @discord.ui.button(label="Use my battle theme", style=discord.ButtonStyle.blurple, emoji="🎼")
    async def my_theme_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """User wants to use their custom theme"""
        if self.on_my_theme:
            self.choice = True
            self.use_custom_theme = True
            await self.on_my_theme(interaction)
            self.stop()
        else:
            await interaction.response.send_message(
                "❌ Custom themes not available for this battle type!",
                ephemeral=True
            )

    @discord.ui.button(label="No, battle silently", style=discord.ButtonStyle.gray, emoji="🔇")
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """User doesn't want music"""
        self.choice = False
        await self.on_no(interaction)
        self.stop()

    async def on_timeout(self):
        """Disable buttons on timeout"""
        for item in self.children:
            item.disabled = True


class MusicQueueView(discord.ui.View):
    """
    View for displaying the music queue and allowing users to join/leave.
    """

    def __init__(self, music_manager, user_id: int, battle_id: str,
                 voice_channel_id: int, battle_type: str, generation: Optional[int] = None):
        super().__init__(timeout=60.0)
        self.music_manager = music_manager
        self.user_id = user_id
        self.battle_id = battle_id
        self.voice_channel_id = voice_channel_id
        self.battle_type = battle_type
        self.generation = generation
        self.joined_queue = False

    @discord.ui.button(label="Join Music Queue", style=discord.ButtonStyle.blurple, emoji="⏰")
    async def join_queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Join the music queue"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This is not your battle!",
                ephemeral=True
            )
            return

        # Try to join queue
        username = interaction.user.display_name
        can_start, message, position = await self.music_manager.request_music(
            self.battle_id,
            self.user_id,
            username,
            self.voice_channel_id,
            self.battle_type,
            self.generation
        )

        if can_start:
            await interaction.response.send_message(
                f"{message} Your music will start when the battle begins!",
                ephemeral=True
            )
            self.joined_queue = True
            # Disable the button
            button.disabled = True
            await interaction.message.edit(view=self)
        elif "already" in message.lower():
            await interaction.response.send_message(
                message,
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"{message} Your battle music will start when the current session ends.",
                ephemeral=True
            )
            self.joined_queue = True
            # Disable the button
            button.disabled = True
            await interaction.message.edit(view=self)

    @discord.ui.button(label="Battle Without Music", style=discord.ButtonStyle.gray, emoji="▶️")
    async def skip_music_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Skip music and start battle immediately"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This is not your battle!",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Starting your battle without music!",
            ephemeral=True
        )
        self.stop()


def create_music_opt_in_embed() -> discord.Embed:
    """Create embed for music opt-in prompt"""
    embed = discord.Embed(
        title="🎵 Battle Music",
        description=(
            "Would you like music for your battle?\n\n"
            "**Note:** The music bot can only play for one battle at a time. "
            "If someone else is using it, you can join the queue or battle without music."
        ),
        color=discord.Color.blue()
    )
    embed.add_field(
        name="🎵 With Music",
        value="The bot will join your voice channel and play battle themes",
        inline=True
    )
    embed.add_field(
        name="🔇 Silent Battle",
        value="Battle proceeds normally without music",
        inline=True
    )
    return embed


def create_queue_status_embed(queue_data: list, voice_channel_name: str) -> discord.Embed:
    """
    Create embed showing the current music queue status.

    Args:
        queue_data: List of dicts with 'position', 'username', 'battle_type', 'status'
        voice_channel_name: Name of the voice channel for music
    """
    embed = discord.Embed(
        title="🎵 Battle Music Queue",
        description=f"Music will play in voice channel: **{voice_channel_name}**",
        color=discord.Color.orange()
    )

    if not queue_data:
        embed.add_field(
            name="Queue Status",
            value="No active music sessions",
            inline=False
        )
        return embed

    # Current session
    current = next((q for q in queue_data if q['status'] == 'active'), None)
    if current:
        embed.add_field(
            name="🎵 Now Playing",
            value=f"**{current['username']}** ({current['battle_type'].upper()} battle)",
            inline=False
        )

    # Waiting in queue
    waiting = [q for q in queue_data if q['status'] == 'queued']
    if waiting:
        queue_text = "\n".join([
            f"{q['position']}. **{q['username']}** ({q['battle_type'].upper()} battle)"
            for q in waiting
        ])
        embed.add_field(
            name="⏰ Waiting in Queue",
            value=queue_text,
            inline=False
        )

    embed.set_footer(text="You can join the queue or battle without music")
    return embed


def create_music_starting_embed(voice_channel_name: str, theme_name: str = "battle theme") -> discord.Embed:
    """Create embed for when music is starting"""
    embed = discord.Embed(
        title="🎵 Battle Music Starting!",
        description=(
            f"Join **{voice_channel_name}** to hear your {theme_name}!\n\n"
            "Music will play throughout the battle and switch to the victory theme when you win."
        ),
        color=discord.Color.green()
    )
    return embed


def create_victory_music_embed(winner_name: str) -> discord.Embed:
    """Create embed for when victory music plays"""
    embed = discord.Embed(
        title="🎉 Victory!",
        description=f"**{winner_name}** wins! Playing victory theme...",
        color=discord.Color.gold()
    )
    embed.set_footer(text="Music will fade out in 1 minute")
    return embed
