"""
Wild Encounters Cog - Simplified Version (No /wild command)
All wild encounters now go through the menu buttons!
Only keeps the /catch command for catching wild Pokémon during battles.
"""

import discord
from discord.ext import commands
from discord import app_commands
import random
from typing import Optional

from battle_engine_v2 import BattleType
from models import Pokemon
from sprite_helper import PokemonSpriteHelper


class WildCog(commands.Cog):
    """Wild Pokemon encounters - button-only system"""
    
    def __init__(self, bot, player_manager, species_db, battle_cog):
        self.bot = bot
        self.player_manager = player_manager
        self.species_db = species_db
        self.battle_cog = battle_cog  # Reference to unified battle cog
    
    @app_commands.command(name="catch", description="Attempt to catch a wild Pokémon!")
    async def catch_wild(self, interaction: discord.Interaction, 
                         ball_type: Optional[str] = "poke_ball"):
        """
        Attempt to catch the wild Pokemon in current battle
        
        Args:
            ball_type: Type of Poke Ball to use (poke_ball, great_ball, ultra_ball, etc.)
        """
        # Check if user is in a battle
        if interaction.user.id not in self.battle_cog.user_battles:
            await interaction.response.send_message(
                "❌ You're not in a battle!",
                ephemeral=True
            )
            return
        
        battle_id = self.battle_cog.user_battles[interaction.user.id]
        battle = self.battle_cog.battle_engine.get_battle(battle_id)
        
        if not battle or battle.battle_type != BattleType.WILD:
            await interaction.response.send_message(
                "❌ You can only catch wild Pokémon!",
                ephemeral=True
            )
            return
        
        # Get wild Pokemon
        wild_pokemon = battle.opponent.get_active_pokemon()[0]
        
        # Calculate catch rate
        catch_rate = self._calculate_catch_rate(wild_pokemon, ball_type)
        
        await interaction.response.defer()
        
        # Attempt catch
        if random.random() < catch_rate:
            # Success!
            await self._catch_success(interaction, wild_pokemon, battle_id)
        else:
            # Failed
            await interaction.followup.send(
                f"Oh no! {wild_pokemon.species_name} broke free!"
            )
    
    def _calculate_catch_rate(self, pokemon: Pokemon, ball_type: str) -> float:
        """Calculate catch rate (0.0 to 1.0)"""
        # Base catch rate from species
        species_catch_rate = pokemon.species_data.get('catch_rate', 45)
        
        # Ball modifier
        ball_modifiers = {
            'poke_ball': 1.0,
            'great_ball': 1.5,
            'ultra_ball': 2.0,
            'master_ball': 255.0
        }
        ball_mod = ball_modifiers.get(ball_type, 1.0)
        
        # HP modifier
        hp_mod = 3.0 - 2.0 * (pokemon.current_hp / pokemon.max_hp)
        
        # Status modifier (TODO: implement when status system is ready)
        status_mod = 1.0
        
        # Calculate
        catch_value = (species_catch_rate * ball_mod * hp_mod * status_mod) / 255.0
        
        return min(catch_value, 1.0)
    
    async def _catch_success(self, interaction: discord.Interaction, 
                            pokemon: Pokemon, battle_id: str):
        """Handle successful catch"""
        # Set owner
        pokemon.owner_discord_id = interaction.user.id
        
        # Add to player's collection
        pokemon_id = self.player_manager.add_pokemon(
            discord_id=interaction.user.id,
            pokemon=pokemon
        )
        
        # End battle
        battle = self.battle_cog.battle_engine.get_battle(battle_id)
        battle.is_over = True
        battle.catch_attempted = True
        
        # Send success message
        embed = discord.Embed(
            title="🎉 Gotcha!",
            description=f"**{pokemon.species_name}** was caught!",
            color=discord.Color.gold()
        )

        # Add sprite
        sprite_url = PokemonSpriteHelper.get_sprite(
            pokemon.species_name,
            pokemon.species_dex_number,
            style='animated',
            gender=pokemon.gender,
            shiny=pokemon.is_shiny,
            use_fallback=False
        )
        embed.set_thumbnail(url=sprite_url)

        embed.add_field(
            name="Level",
            value=pokemon.level,
            inline=True
        )
        
        embed.add_field(
            name="Nature",
            value=pokemon.nature.title(),
            inline=True
        )
        
        embed.add_field(
            name="Ability",
            value=pokemon.ability.replace('_', ' ').title(),
            inline=True
        )
        
        if pokemon.is_shiny:
            embed.add_field(
                name="✨ Shiny!",
                value="This Pokémon is shiny!",
                inline=False
            )

        await interaction.followup.send(embed=embed)
        await self.battle_cog.send_return_to_encounter_prompt(interaction, interaction.user.id)

        # Clean up battle
        self.battle_cog.battle_engine.end_battle(battle_id)
        if interaction.user.id in self.battle_cog.user_battles:
            del self.battle_cog.user_battles[interaction.user.id]


async def setup(bot):
    """Setup function for the cog"""
    # Get required dependencies
    player_manager = bot.player_manager
    species_db = bot.species_db
    battle_cog = bot.get_cog('BattleCog')
    
    if not battle_cog:
        print("⚠️ BattleCog must be loaded before WildCog!")
        return
    
    await bot.add_cog(WildCog(bot, player_manager, species_db, battle_cog))
