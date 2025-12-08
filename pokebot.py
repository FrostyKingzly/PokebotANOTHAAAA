"""
Pokemon Discord Bot - Main Entry Point
Modern discord.py with slash commands and button UI
"""

from dotenv import load_dotenv
load_dotenv()  # Load .env file

import discord
from discord import app_commands
from guild_config import set_rank_announcement_channel
from discord.ext import commands
import asyncio
import os
from version import BUILD_TAG
from pathlib import Path

# Import our systems
from player_manager import PlayerManager
from encounter_system import EncounterSystem
from location_manager import LocationManager
from raid_manager import RaidManager
from ui.embeds import EmbedBuilder
from ui.buttons import MainMenuView
from database import (SpeciesDatabase, MovesDatabase, AbilitiesDatabase,
                     ItemsDatabase, NaturesDatabase, TypeChart)
from rank_manager import RankManager
from item_usage_manager import ItemUsageManager
from weather_manager import WeatherManager
from wild_area_manager import WildAreaManager


class PokemonBot(commands.Bot):
    """Main Pokemon Bot class"""
    
    def __init__(self):
        # Set up intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(
            command_prefix="!",  # Fallback prefix, mainly using slash commands
            intents=intents,
            help_command=None
        )
        
        # Initialize managers and systems (will be set up properly after databases load)
        self.player_manager = None
        self.encounter_system = None
        self.location_manager = None
        self.rank_manager = None
        self.item_usage_manager = None
        self.weather_manager = None
        self.wild_area_manager = None
        
        # Load databases
        self.species_db = None
        self.moves_db = None
        self.abilities_db = None
        self.items_db = None
        self.natures_db = None
        self.type_chart = None
        
        # Temp storage for registration flow
        self.temp_registration_data = {}

        # Track the latest rolled encounters per player so they can revisit them
        self.active_encounters = {}
    
    async def setup_hook(self):
        """Called when the bot is starting up"""
        print("🔧 Setting up bot...")
        
        # Load databases
        await self.load_databases()
        
        # Initialize systems that need databases
        self.player_manager = PlayerManager(
            species_db=self.species_db,
            items_db=self.items_db
        )
        self.rank_manager = RankManager(self.player_manager)
        self.encounter_system = EncounterSystem(self.species_db, self.moves_db)
        self.location_manager = LocationManager(
            "data/locations.json",
            channel_map_path="config/channel_locations.json"
        )
        self.raid_manager = RaidManager(self.species_db)
        self.item_usage_manager = ItemUsageManager(self)
        self.wild_area_manager = WildAreaManager(self.player_manager.db)
        self.weather_manager = WeatherManager()

        # Load cogs
        await self.load_cogs()
        
        # Sync slash commands
        print("🔄 Syncing commands...")
        await self.tree.sync()
        print("✅ Commands synced!")
        print(f"🔧 Build: {BUILD_TAG}")
    
    async def load_databases(self):
        """Load all game databases"""
        print("📚 Loading databases...")
        
        try:
            self.species_db = SpeciesDatabase("data/pokemon_species.json")
            self.moves_db = MovesDatabase("data/moves.json")
            self.abilities_db = AbilitiesDatabase("data/abilities.json")
            self.items_db = ItemsDatabase("data/items.json")
            self.natures_db = NaturesDatabase("data/natures.json")
            self.type_chart = TypeChart("data/type_chart.json")
            print("✅ All databases loaded!")
        except Exception as e:
            print(f"❌ Error loading databases: {e}")
            raise
    
    async def load_cogs(self):
        """Load bot cogs/extensions"""
        cogs = [
            'cogs.registration_cog',
            'cogs.battle_cog',
            'cogs.shop_cog',
            'cogs.wild_cog',
            'cogs.pokemon_cog',
            'cogs.pokemon_management_cog',
            'cogs.items_cog',
            'cogs.rank_cog',
            'cogs.admin_cog',
        ]
        
        for cog in cogs:
            try:
                await self.load_extension(cog)
                print(f"✅ Loaded {cog}")
            except Exception as e:
                print(f"❌ Failed to load {cog}: {e}")
    
    async def on_ready(self):
        """Called when bot is ready"""
        print("=" * 50)
        print(f"🎮 {self.user} is online!")
        print(f"📊 Servers: {len(self.guilds)}")
        print(f"👥 Users: {sum(g.member_count for g in self.guilds)}")
        print("=" * 50)
        
        # Set status
        await self.change_presence(
            activity=discord.Game(name="Pokemon | /register to begin!")
        )


# ============================================================
# MAIN MENU COMMAND
# ============================================================

@discord.app_commands.command(name="phone", description="Open your Rotom-Phone")
async def phone_command(interaction: discord.Interaction):
    """Rotom-Phone - hub for all bot features"""
    
    # Check if player exists
    player_data = interaction.client.player_manager.get_player(interaction.user.id)
    
    if not player_data:
        embed = discord.Embed(
            title="❌ No Save Data",
            description="You haven't started your journey yet!\nUse `/register` to begin!",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Create main menu embed
    rank_manager = getattr(interaction.client, "rank_manager", None)
    location_manager = getattr(interaction.client, "location_manager", None)
    wild_area_manager = getattr(interaction.client, "wild_area_manager", None)
    weather_manager = getattr(interaction.client, "weather_manager", None)
    wild_area_state = (
        wild_area_manager.get_wild_area_state(interaction.user.id)
        if wild_area_manager
        else None
    )

    embed = EmbedBuilder.main_menu(
        player_data,
        rank_manager=rank_manager,
        location_manager=location_manager,
        wild_area_manager=wild_area_manager,
        wild_area_state=wild_area_state,
        weather_manager=weather_manager,
    )

    # Create main menu view with buttons (pass user_id for wild area detection)
    view = MainMenuView(interaction.client, user_id=interaction.user.id)

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@discord.app_commands.command(name="set_rank_announcement", description="[ADMIN] Set this channel for ranked match announcements")
@app_commands.checks.has_permissions(administrator=True)
async def set_rank_announcement(interaction: discord.Interaction):
    """Set this channel as the ranked promotion announcements channel."""
    if not interaction.guild:
        await interaction.response.send_message(
            "❌ This command can only be used inside a server.",
            ephemeral=True,
        )
        return

    set_rank_announcement_channel(interaction.guild.id, interaction.channel_id)
    await interaction.response.send_message(
        "✅ This channel will now receive **ranked promotion match** announcements.",
        ephemeral=True,
    )




# ============================================================
# RUN BOT
# ============================================================

def main():
    """Main entry point"""
    
    # Check for token
    token = os.getenv("DISCORD_BOT_TOKEN")
    
    if not token:
        print("=" * 50)
        print("❌ ERROR: No bot token found!")
        print("=" * 50)
        print("\nPlease set your Discord bot token:")
        print("1. Create a bot at: https://discord.com/developers/applications")
        print("2. Enable these intents:")
        print("   - Presence Intent")
        print("   - Server Members Intent")
        print("   - Message Content Intent")
        print("3. Set the token as an environment variable:")
        print("   export DISCORD_BOT_TOKEN='your_token_here'")
        print("\nOr create a .env file with:")
        print("DISCORD_BOT_TOKEN=your_token_here")
        print("=" * 50)
        return
    
    # Create and run bot
    bot = PokemonBot()
    
    # Register global commands
    bot.tree.add_command(phone_command)
    
    try:
        bot.run(token)
    except discord.LoginFailure:
        print("❌ Invalid token! Please check your bot token.")
    except Exception as e:
        print(f"❌ Error running bot: {e}")


if __name__ == "__main__":
    main()
