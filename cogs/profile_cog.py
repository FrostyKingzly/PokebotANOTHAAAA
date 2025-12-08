"""
Profile Cog
Commands for managing trainer profile settings including battle themes.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from battle_themes import AVAILABLE_PLAYER_THEMES, get_theme_name_from_urls
from ui.embeds import EmbedBuilder


class BattleThemeSelect(discord.ui.Select):
    """Dropdown for selecting battle themes"""

    def __init__(self, current_battle_theme: Optional[str], current_victory_theme: Optional[str]):
        self.current_battle = current_battle_theme
        self.current_victory = current_victory_theme

        # Create options from available themes
        options = []
        current_theme_name = get_theme_name_from_urls(
            current_battle_theme or "",
            current_victory_theme or ""
        ) if current_battle_theme else "Gen 5 - Unova Epic (Default)"

        for theme_name, (battle_url, victory_url) in AVAILABLE_PLAYER_THEMES.items():
            is_current = (battle_url == current_battle_theme and
                         victory_url == current_victory_theme)

            options.append(discord.SelectOption(
                label=theme_name,
                description=f"Battle & Victory themes from {theme_name.split('-')[0].strip()}",
                value=theme_name,
                default=is_current,
                emoji="🎵" if is_current else "🎶"
            ))

        # Add custom theme option
        has_custom = (current_battle_theme and
                     current_battle_theme not in [t[0] for t in AVAILABLE_PLAYER_THEMES.values()])
        options.append(discord.SelectOption(
            label="Custom Theme",
            description="Set your own YouTube URLs (use /setcustomtheme)",
            value="custom",
            default=has_custom,
            emoji="⚙️"
        ))

        super().__init__(
            placeholder=f"Current: {current_theme_name}",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]

        if selected == "custom":
            await interaction.response.send_message(
                "To set a custom theme, use `/setcustomtheme <battle_url> <victory_url>` "
                "with YouTube URLs for your battle and victory themes.",
                ephemeral=True
            )
            return

        # Get the selected theme URLs
        battle_url, victory_url = AVAILABLE_PLAYER_THEMES[selected]

        # Update trainer themes
        player_manager = interaction.client.player_manager
        if not player_manager:
            await interaction.response.send_message(
                "Error: Player manager not available.",
                ephemeral=True
            )
            return

        try:
            player_manager.update_trainer(
                interaction.user.id,
                battle_theme_url=battle_url,
                victory_theme_url=victory_url
            )

            embed = discord.Embed(
                title="🎵 Battle Theme Updated!",
                description=f"Your battle theme has been set to **{selected}**",
                color=discord.Color.green()
            )
            embed.add_field(
                name="When will this play?",
                value="This theme will play in PvP battles when you're the challenger!",
                inline=False
            )
            embed.set_footer(text="Use /battletheme to change it anytime")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(
                f"Error updating theme: {e}",
                ephemeral=True
            )


class BattleThemeView(discord.ui.View):
    """View for battle theme selection"""

    def __init__(self, current_battle_theme: Optional[str], current_victory_theme: Optional[str]):
        super().__init__(timeout=180)
        self.add_item(BattleThemeSelect(current_battle_theme, current_victory_theme))


class ProfileCog(commands.Cog):
    """Commands for managing trainer profile settings"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="battletheme",
        description="Choose your battle theme that plays in PvP battles"
    )
    async def battle_theme(self, interaction: discord.Interaction):
        """Set your custom battle theme"""
        await interaction.response.defer(ephemeral=True)

        player_manager = self.bot.player_manager
        if not player_manager:
            embed = EmbedBuilder.error("Error", "Player manager not available")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Check if user is registered
        if not player_manager.player_exists(interaction.user.id):
            embed = EmbedBuilder.error(
                "Not Registered",
                "You need to register first! Use `/register` to create your trainer profile."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Get current themes
        try:
            trainer = player_manager.get_trainer(interaction.user.id)
            current_battle = getattr(trainer, 'battle_theme_url', None)
            current_victory = getattr(trainer, 'victory_theme_url', None)
        except:
            current_battle = None
            current_victory = None

        # Create info embed
        theme_name = get_theme_name_from_urls(
            current_battle or "",
            current_victory or ""
        ) if current_battle else "Gen 5 - Unova Epic (Default)"

        embed = discord.Embed(
            title="🎵 Battle Theme Settings",
            description=(
                "Choose the music that plays during your battles!\n\n"
                "Your theme will play:\n"
                "• In **PvP battles** when you're the challenger\n"
                "• The **battle theme** plays during combat\n"
                "• The **victory theme** plays for 1 minute after you win"
            ),
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Current Theme",
            value=f"**{theme_name}**",
            inline=False
        )
        embed.add_field(
            name="Available Themes",
            value="Select from Gen 1-9 themes below, or set a custom YouTube URL",
            inline=False
        )
        embed.set_footer(text="Themes are from official Pokémon games")

        view = BattleThemeView(current_battle, current_victory)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(
        name="setcustomtheme",
        description="Set custom YouTube URLs for your battle and victory themes"
    )
    @app_commands.describe(
        battle_url="YouTube URL for your battle theme",
        victory_url="YouTube URL for your victory theme"
    )
    async def set_custom_theme(
        self,
        interaction: discord.Interaction,
        battle_url: str,
        victory_url: str
    ):
        """Set custom battle and victory theme URLs"""
        await interaction.response.defer(ephemeral=True)

        player_manager = self.bot.player_manager
        if not player_manager:
            embed = EmbedBuilder.error("Error", "Player manager not available")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Check if user is registered
        if not player_manager.player_exists(interaction.user.id):
            embed = EmbedBuilder.error(
                "Not Registered",
                "You need to register first! Use `/register` to create your trainer profile."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Validate URLs (basic check)
        if not (battle_url.startswith("http") and victory_url.startswith("http")):
            embed = EmbedBuilder.error(
                "Invalid URLs",
                "Please provide valid YouTube URLs starting with http:// or https://"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Update trainer themes
        try:
            player_manager.update_trainer(
                interaction.user.id,
                battle_theme_url=battle_url,
                victory_theme_url=victory_url
            )

            embed = discord.Embed(
                title="🎵 Custom Battle Theme Set!",
                description="Your custom theme has been updated!",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Battle Theme",
                value=f"[Link]({battle_url})",
                inline=False
            )
            embed.add_field(
                name="Victory Theme",
                value=f"[Link]({victory_url})",
                inline=False
            )
            embed.set_footer(text="Use /battletheme to change back to preset themes")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            embed = EmbedBuilder.error("Error", f"Failed to update theme: {e}")
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="viewtheme",
        description="View your current battle theme settings"
    )
    async def view_theme(self, interaction: discord.Interaction):
        """View current battle theme"""
        await interaction.response.defer(ephemeral=True)

        player_manager = self.bot.player_manager
        if not player_manager:
            embed = EmbedBuilder.error("Error", "Player manager not available")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Check if user is registered
        if not player_manager.player_exists(interaction.user.id):
            embed = EmbedBuilder.error(
                "Not Registered",
                "You need to register first! Use `/register` to create your trainer profile."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Get current themes
        try:
            trainer = player_manager.get_trainer(interaction.user.id)
            current_battle = getattr(trainer, 'battle_theme_url', None)
            current_victory = getattr(trainer, 'victory_theme_url', None)

            theme_name = get_theme_name_from_urls(
                current_battle or "",
                current_victory or ""
            ) if current_battle else "Gen 5 - Unova Epic (Default)"

            embed = discord.Embed(
                title="🎵 Your Battle Theme",
                description=f"**{theme_name}**",
                color=discord.Color.blue()
            )

            if current_battle:
                embed.add_field(
                    name="Battle Theme",
                    value=f"[Listen]({current_battle})",
                    inline=False
                )
            if current_victory:
                embed.add_field(
                    name="Victory Theme",
                    value=f"[Listen]({current_victory})",
                    inline=False
                )

            if not current_battle:
                embed.add_field(
                    name="Note",
                    value="You're using the default theme. Use `/battletheme` to customize!",
                    inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            embed = EmbedBuilder.error("Error", f"Failed to retrieve theme: {e}")
            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    """Load the ProfileCog"""
    await bot.add_cog(ProfileCog(bot))
