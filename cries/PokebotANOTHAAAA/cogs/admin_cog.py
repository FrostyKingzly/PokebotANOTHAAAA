"""
Admin Cog - Admin commands for testing and management
Commands for giving Pokemon, items, and money to players
"""

import math
import random
import re
import time

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Dict

from guild_config import set_rank_announcement_channel
from weather_manager import WeatherManager

from models import Pokemon
from sprite_helper import PokemonSpriteHelper
from social_stats import (
    SOCIAL_STAT_DEFINITIONS,
    SOCIAL_STAT_ORDER,
    build_stat_line,
    points_to_rank,
    clamp_points,
    calculate_max_stamina,
)


def is_admin(interaction: discord.Interaction) -> bool:
    """Return True when the invoking user has administrator permissions."""
    return interaction.user.guild_permissions.administrator


STAT_ROLL_DICE_SIDES = 20
STAT_ROLL_MODIFIER_PER_RANK = 2

SOCIAL_STAT_CHOICES = [
    app_commands.Choice(name=SOCIAL_STAT_DEFINITIONS[key].display_name, value=key)
    for key in SOCIAL_STAT_ORDER
]

WEATHER_REGION_CHOICES = [
    app_commands.Choice(name=data["display_name"], value=region_id)
    for region_id, data in WeatherManager.REGION_SETTINGS.items()
]

WEATHER_CONDITION_CHOICES = [
    app_commands.Choice(name=condition.replace('_', ' ').title(), value=condition)
    for condition in sorted({
        weather
        for settings in WeatherManager.REGION_SETTINGS.values()
        for weather in settings["allowed_weathers"]
    })
]

# Exp Candy image URLs for RP rewards
EXP_CANDY_IMAGES = {
    'exp_candy_xs': 'https://cdn.discordapp.com/attachments/1430369965642485843/1447678477263306952/Bag_Exp.png?ex=69387f25&is=69372da5&hm=56c401771d4ef6b43bed9ec54ddfdce477f83c61ef58b2523d138c02a26acf0e&',
    'exp_candy_s': 'https://cdn.discordapp.com/attachments/1430369965642485843/1447678516509413529/Bag_Exp.png?ex=69387f2e&is=69372dae&hm=fe9f11cf62d54af65141e4865799405176738ee04dd7e54dc92cc55ed52f195f&',
    'exp_candy_m': 'https://cdn.discordapp.com/attachments/1430369965642485843/1447678560813977600/Bag_Exp.png?ex=69387f39&is=69372db9&hm=616aa799b2d3500d7a7568e645e6af94fb4c069ded75ec1b3b0a4e48c8506909&',
    'exp_candy_l': 'https://cdn.discordapp.com/attachments/1430369965642485843/1447678689210011850/Bag_Exp.png?ex=69387f58&is=69372dd8&hm=72c7cbcff36f82246f4360a8359be4de0cecee73ff6a88e927259468103d174d&',
    'exp_candy_xl': 'https://cdn.discordapp.com/attachments/1430369965642485843/1447678720369492152/Bag_Exp.png?ex=69387f5f&is=69372ddf&hm=8502ce3cb0c405c843df6cb415ceee18686f794cd4b00d73129d9b306868f2a6&',
}


class ChannelLocationSelectView(discord.ui.View):
    """Dropdown view for mapping channels to locations"""

    def __init__(
        self,
        bot,
        channel_id: int,
        locations: Dict[str, Dict],
        current_mapping: Optional[str]
    ):
        super().__init__(timeout=120)
        self.bot = bot
        self.channel_id = channel_id
        self.current_mapping = current_mapping

        # Discord selects support up to 25 options
        sorted_locations = sorted(
            locations.items(),
            key=lambda item: item[1].get('name', item[0].replace('_', ' ').title())
        )[:25]

        options = []
        for location_id, location_data in sorted_locations:
            label = location_data.get('name', location_id.replace('_', ' ').title())
            description = location_data.get('description', '')[:100]
            options.append(
                discord.SelectOption(
                    label=label[:100],
                    value=location_id,
                    description=description,
                    default=(location_id == current_mapping)
                )
            )

        select = discord.ui.Select(
            placeholder="Choose a location for this channel...",
            options=options
        )
        select.callback = self.location_selected
        self.add_item(select)

    async def location_selected(self, interaction: discord.Interaction):
        """Handle selection of a location for this channel"""
        location_id = interaction.data['values'][0]

        # Prevent duplicate assignments
        if location_id == self.current_mapping:
            location_name = self.bot.location_manager.get_location_name(location_id)
            await interaction.response.send_message(
                f"ℹ️ {interaction.channel.mention} is already linked to **{location_name}**.",
                ephemeral=True
            )
            return

        # Remove existing mapping if necessary
        existing_mapping = self.bot.location_manager.get_location_by_channel(self.channel_id)
        if existing_mapping and existing_mapping != location_id:
            self.bot.location_manager.remove_channel_from_location(self.channel_id)

        success = self.bot.location_manager.add_channel_to_location(
            self.channel_id,
            location_id
        )

        if not success:
            await interaction.response.send_message(
                "❌ Failed to map this channel to the selected location. Please try again.",
                ephemeral=True
            )
            return

        location_name = self.bot.location_manager.get_location_name(location_id)

        # Disable the view to prevent further edits
        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            content=(
                f"✅ {interaction.channel.mention} is now mapped to **{location_name}**.\n"
                "Players must use this channel for that location's encounters."
            ),
            embed=None,
            view=self
        )
        self.stop()


class AdminCog(commands.Cog):
    """Admin commands for bot management and testing"""

    def __init__(self, bot):
        self.bot = bot
    
    # ============================================================
    # GIVE POKEMON - SHOWDOWN FORMAT
    # ============================================================
    
    @app_commands.command(name="give_pokemon", description="[ADMIN] Give a Pokemon to a player using Showdown format")
    @app_commands.describe(
        user="The user to give the Pokemon to",
        showdown_text="Pokemon in Showdown format (see /help_showdown for format)"
    )
    @app_commands.check(is_admin)
    async def give_pokemon(
        self, 
        interaction: discord.Interaction,
        user: discord.User,
        showdown_text: str
    ):
        """Give a Pokemon using Pokemon Showdown import format"""
        
        # Check if target player exists
        if not self.bot.player_manager.player_exists(user.id):
            await interaction.response.send_message(
                f"❌ {user.mention} hasn't registered yet! They need to use `/register` first.",
                ephemeral=True
            )
            return
        
        try:
            pokemon_entries = self.parse_showdown_import(showdown_text)

            created_pokemon = []

            for pokemon_data in pokemon_entries:
                # Get species data
                species_name = pokemon_data['species']
                species_data = self.bot.species_db.get_species(species_name)

                if not species_data:
                    await interaction.response.send_message(
                        f"â�Ž Could not find species: {pokemon_data['species']}",
                        ephemeral=True
                    )
                    return

                # Create the Pokemon
                pokemon = Pokemon(
                    species_data=species_data,
                    level=pokemon_data['level'],
                    owner_discord_id=user.id,
                    nature=pokemon_data['nature'],
                    ability=pokemon_data['ability'],
                    moves=pokemon_data['moves'],
                    ivs=pokemon_data['ivs'],
                    is_shiny=pokemon_data['shiny'],
                    gender=pokemon_data['gender'],
                    pokeball=pokemon_data['pokeball']
                )

                # Set EVs
                pokemon.evs = pokemon_data['evs']

                # Set held item
                pokemon.held_item = pokemon_data['held_item']

                # Set nickname if provided
                if pokemon_data['nickname']:
                    pokemon.nickname = pokemon_data['nickname']

                # Set tera type if provided
                if pokemon_data['tera_type']:
                    pokemon.tera_type = pokemon_data['tera_type']

                # Recalculate stats with EVs
                pokemon._calculate_stats()
                pokemon.current_hp = pokemon.max_hp

                # Add to party or box
                pokemon_id = self.bot.player_manager.add_pokemon_to_party(pokemon)

                created_pokemon.append((pokemon, species_data))

            summary_lines = []
            for pokemon, _species_data in created_pokemon:
                shiny_indicator = "✨ " if pokemon.is_shiny else ""
                summary_lines.append(f"{shiny_indicator}**{pokemon.get_display_name()}** (Lv. {pokemon.level})")

            embed_kwargs = {
                "description": "\n".join(summary_lines),
                "color": discord.Color.gold() if any(pokemon.is_shiny for pokemon, _ in created_pokemon) else discord.Color.green(),
            }

            if len(created_pokemon) > 1:
                embed_kwargs["title"] = f"{user.display_name} received {len(created_pokemon)} Pokémon!"

            embed = discord.Embed(**embed_kwargs)

            if created_pokemon:
                first_pokemon, first_species_data = created_pokemon[0]
                sprite_url = PokemonSpriteHelper.get_sprite(
                    first_pokemon.species_name,
                    first_species_data['dex_number'],
                    style='animated',
                    gender=first_pokemon.gender,
                    shiny=first_pokemon.is_shiny
                )

                # get_sprite may return a list when a static fallback is provided; Discord
                # embeds require a single URL string.
                if isinstance(sprite_url, list):
                    sprite_url = sprite_url[0]

                embed.set_image(url=sprite_url)

            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(
                f"âŒ Error creating Pokemon: {str(e)}\n\nMake sure your format is correct. Use `/help_showdown` for examples.",
                ephemeral=True
            )
    
    def parse_showdown_import(self, text: str) -> list[dict]:
        """Parse one or more Pokemon Showdown sets from a single paste."""
        entries = self._split_showdown_entries(text)

        if not entries:
            raise ValueError("No Pokemon data found in Showdown text")

        return [self.parse_showdown_format(entry) for entry in entries]

    def _split_showdown_entries(self, text: str) -> list[str]:
        """Split a pasted Showdown team into individual Pokemon blocks."""
        if not text:
            return []

        normalized = text.replace('\r\n', '\n').replace('\r', '\n').strip()

        if not normalized:
            return []

        entries = re.split(r'\n\s*\n+', normalized)
        entries = [entry.strip() for entry in entries if entry.strip()]

        return entries or [normalized]

    def parse_showdown_format(self, text: str) -> dict:
        """
        Parse Pokemon Showdown format text into a dictionary

        Example format:
        Pikachu @ Light Ball
        Ability: Static
        Level: 50
        Shiny: Yes
        EVs: 252 SpA / 4 SpD / 252 Spe
        Modest Nature
        IVs: 31 HP / 31 Atk / 31 Def / 31 SpA / 31 SpD / 31 Spe
        - Thunderbolt
        - Grass Knot
        - Hidden Power Ice
        - Volt Switch
        """
        # Normalize user input and gently fix flattened single-line submissions
        text = self._normalize_showdown_text(text)

        # Normalize line endings and split into lines
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        lines = text.strip().split('\n')
        
        # Default values
        result = {
            'species': None,
            'nickname': None,
            'gender': None,
            'held_item': None,
            'pokeball': 'poke_ball',
            'ability': None,
            'level': 5,
            'shiny': False,
            'nature': 'hardy',
            'ivs': {'hp': 31, 'attack': 31, 'defense': 31, 'sp_attack': 31, 'sp_defense': 31, 'speed': 31},
            'evs': {'hp': 0, 'attack': 0, 'defense': 0, 'sp_attack': 0, 'sp_defense': 0, 'speed': 0},
            'moves': [],
            'tera_type': None
        }
        
        # Parse first line (species, gender, and item)
        first_line = lines[0].strip()

        # Split out held item first to simplify gender parsing
        species_gender_part, _, item_part = first_line.partition('@')
        species_gender_part = species_gender_part.strip()

        if item_part:
            item_text = item_part.strip()
            # If we still see a colon, the user likely pasted everything in one line; take the
            # portion before the next field marker as the held item.
            if ':' in item_text:
                item_text = item_text.split(':', 1)[0].strip()
            result['held_item'] = self._normalize_identifier(item_text)

        # Look for trailing gender marker like "(F)" or "(M)" and remove it from species parsing
        gender = None
        gender_match = re.search(r'\((M|F)\)\s*$', species_gender_part, re.IGNORECASE)
        if gender_match:
            gender = gender_match.group(1)
            species_gender_part = species_gender_part[:gender_match.start()].strip()

        # Check for nickname: "Nickname (Species)"
        nickname_match = re.match(r'^(.+?)\s*\((.+?)\)$', species_gender_part)
        if nickname_match:
            result['nickname'] = nickname_match.group(1).strip()
            result['species'] = nickname_match.group(2).strip()
        else:
            # No nickname: "Species"
            species_match = re.match(r'^(.+?)$', species_gender_part)
            if species_match:
                result['species'] = species_match.group(1).strip()

        if gender:
            gender = gender.upper()
            result['gender'] = 'female' if gender == 'F' else 'male'

        # Parse remaining lines
        for line in lines[1:]:
            line = line.strip()
            
            # Ability
            if line.startswith('Ability:'):
                ability = line.split(':', 1)[1].strip()
                result['ability'] = self._normalize_identifier(ability)
            
            # Level
            elif line.startswith('Level:'):
                level = line.split(':', 1)[1].strip()
                result['level'] = int(level)

            # Poké Ball
            elif line.lower().startswith('pokeball:') or line.lower().startswith('ball:'):
                ball_text = line.split(':', 1)[1].strip()
                result['pokeball'] = self._normalize_identifier(ball_text)
            
            # Shiny
            elif line.lower().startswith('shiny:'):
                shiny = line.split(':', 1)[1].strip().lower()
                result['shiny'] = shiny in ['yes', 'true', '1']
            
            # Tera Type
            elif line.startswith('Tera Type:'):
                tera_type = line.split(':', 1)[1].strip()
                result['tera_type'] = self._normalize_identifier(tera_type)
            
            # EVs
            elif line.startswith('EVs:'):
                evs_text = line.split(':', 1)[1].strip()
                result['evs'] = self._parse_stats(evs_text, default_value=0)
            
            # IVs
            elif line.startswith('IVs:'):
                ivs_text = line.split(':', 1)[1].strip()
                result['ivs'] = self._parse_stats(ivs_text, default_value=31)
            
            # Nature
            elif 'Nature' in line:
                nature = line.replace('Nature', '').strip()
                result['nature'] = nature.lower()
            
            # Moves (lines starting with -)
            elif line.startswith('-'):
                move = line[1:].strip()
                normalized_move = self._normalize_identifier(move)
                if normalized_move:
                    result['moves'].append(normalized_move)
        
        # Validate we have at least species
        if not result['species']:
            raise ValueError("Could not parse species name from first line")
        
        # Ensure we have at least one move
        if not result['moves']:
            result['moves'] = ['tackle']  # Default move
        
        return result

    def _normalize_showdown_text(self, text: str) -> str:
        """Best-effort formatter that restores expected newlines for collapsed input."""
        if not text:
            return ''

        normalized = text.replace('\r\n', '\n').replace('\r', '\n').strip()

        # Insert newlines before known field markers when the text has been flattened.
        markers = [
            r'Ability:',
            r'Level:',
            r'Shiny:',
            r'Pokeball:',
            r'Tera Type:',
            r'EVs:',
            r'IVs:',
            r'[A-Za-z]+ Nature',
        ]

        for marker in markers:
            normalized = re.sub(
                rf'\s*({marker})',
                lambda m: f"\n{m.group(1)}",
                normalized,
                flags=re.IGNORECASE,
            )

        # Ensure moves are on their own lines without disrupting hyphenated species names
        normalized = re.sub(r'(?<!\S)-\s*', '\n- ', normalized)

        # Collapse multiple blank lines that may have been introduced
        normalized = re.sub(r'\n+', '\n', normalized).strip()

        return normalized
    
    def _parse_stats(self, stats_text: str, default_value: int = 0) -> dict:
        """
        Parse stat string like "252 SpA / 4 SpD / 252 Spe"
        Returns dict with full stat names
        """
        stat_map = {
            'hp': 'hp',
            'atk': 'attack',
            'def': 'defense',
            'spa': 'sp_attack',
            'spd': 'sp_defense',
            'spe': 'speed',
            'attack': 'attack',
            'defense': 'defense',
            'sp. atk': 'sp_attack',
            'sp. def': 'sp_defense',
            'special attack': 'sp_attack',
            'special defense': 'sp_defense',
            'speed': 'speed'
        }
        
        stats = {stat: default_value for stat in ['hp', 'attack', 'defense', 'sp_attack', 'sp_defense', 'speed']}
        
        # Split by /
        parts = stats_text.split('/')
        
        for part in parts:
            part = part.strip()
            # Match "252 SpA" pattern
            match = re.match(r'(\d+)\s+(.+)', part)
            if match:
                value = int(match.group(1))
                stat_name = match.group(2).strip().lower()
                
                # Map abbreviated name to full name
                full_stat_name = stat_map.get(stat_name)
                if full_stat_name:
                    stats[full_stat_name] = value
        
        return stats

    def _normalize_identifier(self, text: Optional[str]) -> Optional[str]:
        """Convert Showdown names (moves, abilities, items) into database IDs"""
        if not text:
            return None

        normalized = text.strip().lower()
        normalized = normalized.replace('♀', 'f').replace('♂', 'm')
        normalized = normalized.replace('’', '').replace("'", '')
        normalized = normalized.replace('-', ' ')
        normalized = normalized.replace('.', ' ')
        normalized = normalized.replace('/', ' ')
        normalized = re.sub(r'[^a-z0-9 ]+', ' ', normalized)
        normalized = re.sub(r'\s+', '_', normalized).strip('_')

        return normalized if normalized else None
    
    # ============================================================
    # SHOWDOWN FORMAT HELP
    # ============================================================
    
    @app_commands.command(name="help_showdown", description="Show Pokemon Showdown format examples")
    async def help_showdown(self, interaction: discord.Interaction):
        """Show examples of Showdown format"""
        
        embed = discord.Embed(
            title="📋 Pokemon Showdown Format Guide",
            description="Use this format with `/give_pokemon` to create Pokemon",
            color=discord.Color.blue()
        )
        
        # Basic format
        basic_example = """```
Pikachu
Ability: Static
Level: 50
Modest Nature
- Thunderbolt
- Quick Attack
```"""
        
        embed.add_field(
            name="Basic Format",
            value=basic_example,
            inline=False
        )
        
        # With item
        item_example = """```
Charizard @ Charcoal
Ability: Blaze
Level: 75
Adamant Nature
- Flare Blitz
- Dragon Claw
- Earthquake
- Roost
```"""
        
        embed.add_field(
            name="With Held Item",
            value=item_example,
            inline=False
        )
        
        # With EVs/IVs
        competitive_example = """```
Gardevoir @ Choice Specs
Ability: Trace
Level: 100
Shiny: Yes
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
IVs: 31 HP / 31 SpA / 31 Spe
- Psychic
- Moonblast
- Shadow Ball
- Focus Blast
```"""
        
        embed.add_field(
            name="Competitive (Full Stats)",
            value=competitive_example,
            inline=False
        )
        
        # With nickname
        nickname_example = """```
Sparky (Pikachu) @ Light Ball
Ability: Static
Level: 50
Shiny: Yes
EVs: 252 SpA / 252 Spe
Modest Nature
- Thunderbolt
- Grass Knot
```"""
        
        embed.add_field(
            name="With Nickname",
            value=nickname_example,
            inline=False
        )
        
        # Important notes
        embed.add_field(
            name="📝 Important Notes",
            value=(
                "â€¢ Species name is required on first line\n"
                "â€¢ Level defaults to 5 if not specified\n"
                "â€¢ Nature defaults to Hardy if not specified\n"
                "â€¢ IVs default to 31 (perfect) if not specified\n"
                "â€¢ EVs default to 0 if not specified\n"
                "â€¢ At least one move is required\n"
                "â€¢ Use the exact format shown above"
            ),
            inline=False
        )
        
        # Stat abbreviations
        embed.add_field(
            name="📊 Stat Abbreviations",
            value=(
                "â€¢ **HP** - Hit Points\n"
                "â€¢ **Atk** - Attack\n"
                "â€¢ **Def** - Defense\n"
                "â€¢ **SpA** - Special Attack\n"
                "â€¢ **SpD** - Special Defense\n"
                "â€¢ **Spe** - Speed"
            ),
            inline=False
        )
        
        embed.set_footer(text="Use /give_pokemon @user <paste format here>")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    # ============================================================
    # GIVE ITEM
    # ============================================================
    
    @app_commands.command(name="give_item", description="[ADMIN] Give an item to a player")
    @app_commands.describe(
        user="The user to give the item to",
        item="Item ID (e.g., 'potion', 'poke_ball', 'rare_candy')",
        quantity="Amount to give (default: 1)"
    )
    @app_commands.check(is_admin)
    async def give_item(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        item: str,
        quantity: int = 1
    ):
        """Give items to a player"""
        
        # Check if target player exists
        if not self.bot.player_manager.player_exists(user.id):
            await interaction.response.send_message(
                f"âŒ {user.mention} hasn't registered yet! They need to use `/register` first.",
                ephemeral=True
            )
            return
        
        # Validate item exists
        item_id = item.lower().replace(' ', '_')
        item_data = self.bot.items_db.get_item(item_id)
        
        if not item_data:
            await interaction.response.send_message(
                f"âŒ Item not found: {item}\n\nCheck the items.json file for valid item IDs.",
                ephemeral=True
            )
            return
        
        # Validate quantity
        if quantity < 1:
            await interaction.response.send_message(
                "âŒ Quantity must be at least 1!",
                ephemeral=True
            )
            return
        
        # Give the item
        self.bot.player_manager.add_item(user.id, item_id, quantity)
        
        # Create success embed
        embed = discord.Embed(
            title="✅ Item Given!",
            description=f"Gave **{quantity}x {item_data['name']}** to {user.mention}",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="Item",
            value=item_data['name'],
            inline=True
        )
        
        embed.add_field(
            name="Quantity",
            value=str(quantity),
            inline=True
        )
        
        embed.add_field(
            name="Category",
            value=item_data.get('category', 'Unknown').title(),
            inline=True
        )
        
        if 'description' in item_data:
            embed.add_field(
                name="Description",
                value=item_data['description'],
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
    
    # ============================================================
    # GIVE MONEY
    # ============================================================
    
    @app_commands.command(name="give_money", description="[ADMIN] Give money to a player")
    @app_commands.describe(
        user="The user to give money to",
        amount="Amount of money to give"
    )
    @app_commands.check(is_admin)
    async def give_money(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        amount: int
    ):
        """Give money to a player"""
        
        # Check if target player exists
        if not self.bot.player_manager.player_exists(user.id):
            await interaction.response.send_message(
                f"âŒ {user.mention} hasn't registered yet! They need to use `/register` first.",
                ephemeral=True
            )
            return
        
        # Validate amount
        if amount <= 0:
            await interaction.response.send_message(
                "âŒ Amount must be positive!",
                ephemeral=True
            )
            return
        
        # Get current money
        player = self.bot.player_manager.get_player(user.id)
        old_money = player.money
        new_money = old_money + amount
        
        # Update money
        self.bot.player_manager.update_player(user.id, money=new_money)
        
        # Create success embed
        embed = discord.Embed(
            title="✅ Money Given!",
            description=f"Gave **${amount:,}** to {user.mention}",
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name="Previous Balance",
            value=f"${old_money:,}",
            inline=True
        )
        
        embed.add_field(
            name="Amount Given",
            value=f"${amount:,}",
            inline=True
        )
        
        embed.add_field(
            name="New Balance",
            value=f"${new_money:,}",
            inline=True
        )
        
        await interaction.response.send_message(embed=embed)
    
    # ============================================================
    # VIEW PLAYER INFO (ADMIN)
    # ============================================================
    
    @app_commands.command(name="view_player", description="[ADMIN] View detailed player information")
    @app_commands.describe(user="The user to view")
    @app_commands.check(is_admin)
    async def view_player(
        self,
        interaction: discord.Interaction,
        user: discord.User
    ):
        """View detailed player information for debugging"""
        
        # Check if player exists
        if not self.bot.player_manager.player_exists(user.id):
            await interaction.response.send_message(
                f"âŒ {user.mention} hasn't registered yet!",
                ephemeral=True
            )
            return
        
        # Get player data
        player = self.bot.player_manager.get_player(user.id)
        party = self.bot.player_manager.get_party(user.id)
        boxes = self.bot.player_manager.get_boxes(user.id)
        inventory = self.bot.player_manager.get_inventory(user.id)
        
        # Create embed
        embed = discord.Embed(
            title=f"🔍 Player Info: {player.trainer_name}",
            description=f"Discord: {user.mention}",
            color=discord.Color.blue()
        )
        
        # Basic info
        embed.add_field(
            name="💰 Money",
            value=f"${player.money:,}",
            inline=True
        )
        
        embed.add_field(
            name="📍 Location",
            value=player.current_location_id.replace('_', ' ').title(),
            inline=True
        )
        
        embed.add_field(
            name="🏆 Rank",
            value=player.get_rank_display(),
            inline=True
        )
        
        # Star traits
        social_stats = player.get_social_stats_dict()
        stats_text = "\n".join([
            f"**{name}:** Rank {info['rank']} ({info['points']}/{info['cap']} pts)"
            for name, info in social_stats.items()
        ])
        embed.add_field(
            name="📊 Star Traits",
            value=stats_text,
            inline=False
        )

        embed.add_field(
            name="💪 Stamina",
            value=player.get_stamina_display(),
            inline=False
        )
        
        # Pokemon count
        embed.add_field(
            name="👥 Party",
            value=f"{len(party)}/6 Pokemon",
            inline=True
        )
        
        embed.add_field(
            name="📦 Storage",
            value=f"{len(boxes)} Pokemon",
            inline=True
        )
        
        embed.add_field(
            name="🎒 Items",
            value=f"{len(inventory)} types",
            inline=True
        )
        
        # List party Pokemon
        if party:
            party_list = []
            for p in party[:6]:  # Max 6
                species_data = self.bot.species_db.get_species(p['species_dex_number'])
                name = p['nickname'] if p['nickname'] else species_data['name']
                shiny = "âœ¨ " if p['is_shiny'] else ""
                party_list.append(f"{shiny}**{name}** - Lv.{p['level']}")
            
            embed.add_field(
                name="👥 Party Pokémon",
                value="\n".join(party_list),
                inline=False
            )
        
        embed.set_footer(text=f"User ID: {user.id}")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ============================================================
    # STAT ROLL UTILITY
    # ============================================================

    @app_commands.command(name="stat_roll", description="[ADMIN] Roll a social stat check for a player")
    @app_commands.describe(
        user="Which trainer is attempting the check (defaults to yourself)",
        difficulty="Target number to meet or exceed",
        stat_one="Primary stat to include",
        stat_two="Optional secondary stat",
        stat_three="Optional tertiary stat",
        reason="Optional note about what this roll represents"
    )
    @app_commands.choices(
        stat_one=SOCIAL_STAT_CHOICES,
        stat_two=SOCIAL_STAT_CHOICES,
        stat_three=SOCIAL_STAT_CHOICES,
    )
    @app_commands.check(is_admin)
    async def stat_roll(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.User],
        difficulty: int,
        stat_one: app_commands.Choice[str],
        stat_two: Optional[app_commands.Choice[str]] = None,
        stat_three: Optional[app_commands.Choice[str]] = None,
        reason: Optional[str] = None,
    ):
        """Roll a d20 and add modifiers from one or more social stats."""

        target = user or interaction.user

        player = self.bot.player_manager.get_player(target.id)
        if not player:
            await interaction.response.send_message(
                f"❌ {target.mention} hasn't registered yet!",
                ephemeral=True
            )
            return

        stat_keys = []
        for choice in (stat_one, stat_two, stat_three):
            if choice and choice.value not in stat_keys:
                stat_keys.append(choice.value)

        if not stat_keys:
            await interaction.response.send_message(
                "❌ You must pick at least one stat to roll!",
                ephemeral=True
            )
            return

        roll = random.randint(1, STAT_ROLL_DICE_SIDES)
        modifiers = []
        modifier_total = 0
        for key in stat_keys:
            stat_info = player.get_stat_info(key)
            display_name = SOCIAL_STAT_DEFINITIONS[key].display_name
            bonus = stat_info['rank'] * STAT_ROLL_MODIFIER_PER_RANK
            modifier_total += bonus
            modifiers.append(f"{display_name}: Rank {stat_info['rank']} → +{bonus}")

        total = roll + modifier_total
        success = total >= difficulty

        color = discord.Color.green() if success else discord.Color.red()
        embed = discord.Embed(
            title="🎲 Stat Roll",
            description=(
                f"{target.mention} **{'succeeds' if success else 'fails'}** the check!"
                if difficulty > 0 else f"{target.mention} rolls the dice!"
            ),
            color=color,
        )

        if reason:
            embed.add_field(name="Context", value=reason, inline=False)

        embed.add_field(name="Difficulty", value=str(difficulty), inline=True)
        embed.add_field(name="d20", value=str(roll), inline=True)
        embed.add_field(name="Stat Bonus", value=f"+{modifier_total}", inline=True)
        embed.add_field(name="Total", value=str(total), inline=True)

        if modifiers:
            embed.add_field(name="Modifiers", value="\n".join(modifiers), inline=False)

        stats_lines = [
            build_stat_line(
                SOCIAL_STAT_DEFINITIONS[key].display_name,
                player.get_stat_rank(key),
                player.get_stat_info(key)['points'],
                player.get_stat_info(key)['cap'],
            )
            for key in stat_keys
        ]
        embed.add_field(name="Stat Snapshots", value="\n".join(stats_lines), inline=False)

        await interaction.response.send_message(embed=embed)


    # ============================================================
    # SOCIAL STAT GRANT
    # ============================================================

    @app_commands.command(
        name="give_social",
        description="[ADMIN] Give social stat points to a player"
    )
    @app_commands.describe(
        user="The player to give points to",
        stat="Which social stat to increase",
        amount="How many points to add (in raw points, e.g. 50 = ~1 rank for normal stats)"
    )
    @app_commands.choices(
        stat=SOCIAL_STAT_CHOICES,
    )
    @app_commands.check(is_admin)
    async def give_social(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        stat: app_commands.Choice[str],
        amount: int,
    ):
        """Give social stat points to a player."""

        # Validate amount
        if amount <= 0:
            await interaction.response.send_message(
                "❌ Amount must be a positive number of points!",
                ephemeral=True,
            )
            return

        # Check if target player exists
        if not self.bot.player_manager.player_exists(user.id):
            await interaction.response.send_message(
                f"❌ {user.mention} hasn't registered yet! They need to use `/register` first.",
                ephemeral=True,
            )
            return

        # Load current player data
        player = self.bot.player_manager.get_player(user.id)
        stat_key = stat.value  # "heart", "insight", etc.
        display_name = SOCIAL_STAT_DEFINITIONS[stat_key].display_name

        # Get current stat state
        stat_state = player.social_stats.get(
            stat_key,
            {
                "rank": 0,
                "points": 0,
                "cap": player.get_stat_cap(stat_key),
            },
        )
        old_points = stat_state["points"]
        old_rank = stat_state["rank"]
        cap = stat_state["cap"]

        # Compute new points and rank
        new_points = clamp_points(old_points + amount, cap)
        new_rank = points_to_rank(new_points, cap)

        # Prepare DB updates
        updates: Dict[str, int] = {
            f"{stat_key}_points": new_points,
            f"{stat_key}_rank": new_rank,
        }

        # Keep stamina in sync if Fortitude changes
        if stat_key == "fortitude":
            old_max = calculate_max_stamina(old_rank)
            new_max = calculate_max_stamina(new_rank)
            updates["stamina_max"] = new_max
            # Keep current stamina within the new max; preserve it if possible
            updates["stamina_current"] = min(player.stamina_current, new_max)

        # Persist to database
        self.bot.player_manager.update_player(user.id, **updates)

        # Update in-memory player object so subsequent uses see fresh values
        stat_state["points"] = new_points
        stat_state["rank"] = new_rank
        setattr(player, f"{stat_key}_points", new_points)
        setattr(player, f"{stat_key}_rank", new_rank)
        if stat_key == "fortitude":
            player.stamina_max = updates["stamina_max"]
            player.stamina_current = updates["stamina_current"]

        # Build response embed
        # Only show how many points were added, and whether a rank up occurred.
        if new_rank > old_rank:
            rank_change_text = f"✅ Rank up! Rank {old_rank} → Rank {new_rank}"
        elif new_rank == old_rank:
            rank_change_text = f"No rank up (still Rank {new_rank})."
        else:
            # This shouldn't happen with positive amounts, but handle gracefully.
            rank_change_text = f"Rank changed: Rank {old_rank} → Rank {new_rank}"

        embed = discord.Embed(
            title="📈 Social Stat Updated",
            description=(
                f"{user.mention} gained **{amount}** points in **{display_name}**."
            ),
            color=discord.Color.green(),
        )
        embed.add_field(
            name="Points Added",
            value=str(amount),
            inline=True,
        )
        embed.add_field(
            name="Rank Change",
            value=rank_change_text,
            inline=False,
        )

        await interaction.response.send_message(embed=embed)
    

    # ============================================================
    # CHALLENGER POINTS / TICKET GRANT
    # ============================================================
    @app_commands.command(
        name="give_challenger",
        description="[ADMIN] Give Challenger points and/or a Challenger ticket to a player"
    )
    @app_commands.describe(
        user="The player to modify",
        points="How many Challenger points to add (0 to skip)",
        grant_ticket="Whether to grant a Challenger promotion ticket"
    )
    @app_commands.check(is_admin)
    async def give_challenger(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        points: int = 0,
        grant_ticket: bool = False,
    ):
        """Admin-only helper to adjust ranked Challenger progress."""

        # Ensure the target has registered
        manager = getattr(self.bot, "player_manager", None)
        if not manager or not manager.player_exists(user.id):
            await interaction.response.send_message(
                f"❌ {user.mention} hasn't registered yet! They need to use `/register` first.",
                ephemeral=True,
            )
            return

        trainer = manager.get_player(user.id)
        if not trainer:
            await interaction.response.send_message(
                f"❌ Could not load trainer data for {user.mention}.",
                ephemeral=True,
            )
            return

        old_points = getattr(trainer, "ladder_points", 0) or 0
        old_has_ticket = bool(getattr(trainer, "has_promotion_ticket", False))

        updates: Dict[str, int] = {}
        new_points = old_points

        # Apply point changes
        if points != 0:
            new_points = max(0, old_points + points)
            updates["ladder_points"] = new_points

        # Apply ticket change
        new_has_ticket = old_has_ticket
        if grant_ticket and not old_has_ticket:
            new_has_ticket = True
            updates["has_promotion_ticket"] = 1

        if not updates:
            await interaction.response.send_message(
                "ℹ️ No changes were applied (no points added and ticket not granted).",
                ephemeral=True,
            )
            return

        # Persist to database
        manager.update_player(user.id, **updates)

        # Update in-memory trainer object
        trainer.ladder_points = new_points
        trainer.has_promotion_ticket = new_has_ticket

        # Build response embed
        embed = discord.Embed(
            title="🏆 Challenger Progress Updated",
            description=f"{user.mention}'s ranked progression has been adjusted.",
            color=discord.Color.green(),
        )

        if "ladder_points" in updates:
            embed.add_field(
                name="Challenger Points",
                value=f"{old_points} → {new_points} (Δ {points:+})",
                inline=False,
            )

        if "has_promotion_ticket" in updates:
            ticket_text = "🎟️ Challenger ticket granted." if new_has_ticket and not old_has_ticket else "Ticket state unchanged."
            embed.add_field(
                name="Ticket",
                value=ticket_text,
                inline=False,
            )
        else:
            embed.add_field(
                name="Ticket",
                value="No change.",
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ============================================================
    # RP REWARDS
    # ============================================================
    @app_commands.command(
        name="give_rp_rewards",
        description="[ADMIN] Give RP rewards (stats + exp candies) to players based on their rank"
    )
    @app_commands.describe(
        users="Players to reward (mention them)",
        heart="Heart points to give (before boon/bane)",
        insight="Insight points to give (before boon/bane)",
        charisma="Charisma points to give (before boon/bane)",
        fortitude="Fortitude points to give (before boon/bane)",
        will="Will points to give (before boon/bane)"
    )
    @app_commands.check(is_admin)
    async def give_rp_rewards(
        self,
        interaction: discord.Interaction,
        users: str,
        heart: int = 0,
        insight: int = 0,
        charisma: int = 0,
        fortitude: int = 0,
        will: int = 0,
    ):
        """Give RP rewards to one or more players with automatic boon/bane and exp candy calculation."""

        # Parse user mentions from the string
        user_ids = []
        for mention in users.split():
            # Extract user ID from mention format <@123456789> or <@!123456789>
            match = re.match(r'<@!?(\d+)>', mention)
            if match:
                user_ids.append(int(match.group(1)))

        if not user_ids:
            await interaction.response.send_message(
                "❌ No valid user mentions found! Mention users with @username.",
                ephemeral=True,
            )
            return

        # Check if any stats were specified
        stat_rewards = {
            'heart': heart,
            'insight': insight,
            'charisma': charisma,
            'fortitude': fortitude,
            'will': will,
        }

        if all(amount == 0 for amount in stat_rewards.values()):
            await interaction.response.send_message(
                "❌ You must specify at least one stat to reward!",
                ephemeral=True,
            )
            return

        # Exp candy mapping by rank tier
        exp_candy_by_tier = {
            1: ('exp_candy_xs', 5),   # Qualifier/Unranked
            2: ('exp_candy_xs', 10),  # Challenger 1
            3: ('exp_candy_s', 5),    # Challenger 2
            4: ('exp_candy_s', 10),   # Great 1
            5: ('exp_candy_m', 5),    # Great 2
            6: ('exp_candy_m', 10),   # Ultra 1
            7: ('exp_candy_l', 5),    # Ultra 2
            8: ('exp_candy_l', 10),   # Master
        }

        # Process each user
        results = []
        manager = self.bot.player_manager

        for user_id in user_ids:
            try:
                user = await self.bot.fetch_user(user_id)
            except discord.NotFound:
                results.append(f"❌ Could not find user with ID {user_id}")
                continue

            if not manager.player_exists(user_id):
                results.append(f"❌ {user.mention} hasn't registered yet!")
                continue

            player = manager.get_player(user_id)
            if not player:
                results.append(f"❌ Could not load data for {user.mention}")
                continue

            # Get player's boon and bane
            boon_stat = getattr(player, 'boon_stat', None)
            bane_stat = getattr(player, 'bane_stat', None)

            # Apply stat rewards with boon/bane modifiers
            stat_updates = {}
            stat_summary = []

            for stat_key, base_amount in stat_rewards.items():
                if base_amount == 0:
                    continue

                # Apply boon/bane modifier
                actual_amount = base_amount
                modifier_text = ""
                if stat_key == boon_stat:
                    actual_amount += 1
                    modifier_text = " (+1 boon)"
                elif stat_key == bane_stat:
                    actual_amount -= 1
                    modifier_text = " (-1 bane)"

                # Skip if final amount is 0 or negative
                if actual_amount <= 0:
                    continue

                # Get current stat state
                current_points = getattr(player, f'{stat_key}_points', 0)
                current_rank = getattr(player, f'{stat_key}_rank', 0)
                cap = player.get_stat_cap(stat_key)

                # Calculate new values
                new_points = clamp_points(current_points + actual_amount, cap)
                new_rank = points_to_rank(new_points, cap)

                # Prepare updates
                stat_updates[f'{stat_key}_points'] = new_points
                stat_updates[f'{stat_key}_rank'] = new_rank

                # Track for summary
                display_name = SOCIAL_STAT_DEFINITIONS[stat_key].display_name
                rank_change = ""
                if new_rank > current_rank:
                    rank_change = f" (Rank {current_rank}→{new_rank})"

                stat_summary.append(f"**{display_name}**: +{actual_amount}{modifier_text}{rank_change}")

                # Handle stamina updates for fortitude
                if stat_key == 'fortitude' and new_rank != current_rank:
                    new_max_stamina = calculate_max_stamina(new_rank)
                    stat_updates['stamina_max'] = new_max_stamina
                    stat_updates['stamina_current'] = min(player.stamina_current, new_max_stamina)

            # Apply stat updates to database
            if stat_updates:
                manager.update_player(user_id, **stat_updates)

            # Give exp candies based on rank tier
            rank_tier = getattr(player, 'rank_tier_number', None) or 1
            candy_type, candy_amount = exp_candy_by_tier.get(rank_tier, ('exp_candy_xs', 5))

            # Add candies to inventory
            manager.add_item(user_id, candy_type, candy_amount)

            # Get candy display name
            candy_item = self.bot.items_db.get_item(candy_type)
            candy_name = candy_item.get('name', candy_type) if candy_item else candy_type

            # Build result message
            result_lines = [f"✅ **{user.mention}**"]
            if stat_summary:
                result_lines.extend(stat_summary)
            result_lines.append(f"🍬 {candy_amount}x {candy_name}")

            results.append("\n".join(result_lines))

        # Build response embed
        embed = discord.Embed(
            title="RP Rewards!",
            description="\n\n".join(results) if results else "No rewards given.",
            color=discord.Color.purple(),
        )

        # Add candy thumbnail based on first player's rank
        if user_ids:
            first_user_id = user_ids[0]
            if manager.player_exists(first_user_id):
                player = manager.get_player(first_user_id)
                rank_tier = getattr(player, 'rank_tier_number', None) or 1
                candy_type, _ = exp_candy_by_tier.get(rank_tier, ('exp_candy_xs', 5))
                # Use custom candy images
                candy_image_url = EXP_CANDY_IMAGES.get(candy_type, EXP_CANDY_IMAGES['exp_candy_xs'])
                embed.set_thumbnail(url=candy_image_url)

        await interaction.response.send_message(embed=embed)

# ============================================================
    # PLAYER RESET
    # ============================================================

    @app_commands.command(
        name="delete_character",
        description="[ADMIN] Delete a player's character data so they can register again"
    )
    @app_commands.describe(user="The player whose data should be deleted")
    @app_commands.check(is_admin)
    async def delete_character(self, interaction: discord.Interaction, user: discord.User):
        """Allow admins to wipe a trainer profile and all stored progress."""
        manager = getattr(self.bot, "player_manager", None)
        if manager is None:
            await interaction.response.send_message(
                "⚠️ Player manager is not available.",
                ephemeral=True
            )
            return

        if not manager.player_exists(user.id):
            await interaction.response.send_message(
                f"ℹ️ {user.mention} doesn't have a registered character.",
                ephemeral=True
            )
            return

        deleted = manager.delete_player(user.id)
        if not deleted:
            await interaction.response.send_message(
                "❌ Something went wrong while deleting that character.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"✅ Deleted {user.mention}'s trainer data. They can register again whenever they're ready.",
            ephemeral=True
        )

    # ============================================================
    # WEATHER CONTROL
    # ============================================================

    @app_commands.command(name="set_weather", description="[ADMIN] Force weather for a region")
    @app_commands.describe(
        region="Which region should be affected?",
        weather="Which weather condition to set?",
    )
    @app_commands.choices(region=WEATHER_REGION_CHOICES, weather=WEATHER_CONDITION_CHOICES)
    @app_commands.check(is_admin)
    async def set_weather(
        self,
        interaction: discord.Interaction,
        region: app_commands.Choice[str],
        weather: app_commands.Choice[str],
    ):
        """Manually set weather for a region until changed again."""

        manager = getattr(self.bot, "weather_manager", None)
        if not manager:
            await interaction.response.send_message(
                "⚠️ Weather manager is not configured.",
                ephemeral=True,
            )
            return

        try:
            state = manager.set_weather(region.value, weather.value)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        region_name = WeatherManager.REGION_SETTINGS[region.value]["display_name"]
        weather_display = weather.value.replace('_', ' ').title()

        await interaction.response.send_message(
            f"✅ Set weather for **{region_name}** to **{weather_display}** until changed again.",
            ephemeral=True,
        )

    @app_commands.command(name="set_weather_random", description="[ADMIN] Return a region to random weather")
    @app_commands.describe(
        region="Which region should roll random weather?",
        weather_options="Optional comma-separated list of weather types to rotate between",
    )
    @app_commands.choices(region=WEATHER_REGION_CHOICES)
    @app_commands.check(is_admin)
    async def set_weather_random(
        self,
        interaction: discord.Interaction,
        region: app_commands.Choice[str],
        weather_options: Optional[str] = None,
    ):
        """Resume random weather changes for a region and roll the next condition."""

        manager = getattr(self.bot, "weather_manager", None)
        if not manager:
            await interaction.response.send_message(
                "⚠️ Weather manager is not configured.",
                ephemeral=True,
            )
            return

        allowed_list: Optional[list[str]] = None
        if weather_options:
            parsed = [w.strip().lower().replace(" ", "_") for w in weather_options.split(",")]
            allowed_list = [w for w in parsed if w]

        try:
            state = manager.set_random_mode(region.value, allowed_weathers=allowed_list, reroll=True)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        region_name = WeatherManager.REGION_SETTINGS[region.value]["display_name"]
        weather_display = (state.get("current_weather") or "Unknown").replace('_', ' ').title()
        pool = state.get("random_pool") or WeatherManager.REGION_SETTINGS[region.value].get("allowed_weathers", [])
        pool_display = ", ".join([w.replace('_', ' ').title() for w in pool])

        await interaction.response.send_message(
            f"🔀 {region_name} weather is now random. Current roll: **{weather_display}**.\n"
            f"Rotating every 12 hours between: {pool_display}.",
            ephemeral=True,
        )

    # ============================================================
    # ERROR HANDLING
    # ============================================================
    
    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ):
        """Handle errors for this cog"""
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "âŒ You need administrator permissions to use this command!",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"âŒ An error occurred: {str(error)}",
                ephemeral=True
            )


    
    # ============================================================
    # LOCATION MANAGEMENT
    # ============================================================
    
    @app_commands.command(name="set_location", description="[ADMIN] Map this channel to a location")
    @app_commands.check(is_admin)
    async def set_location(
        self,
        interaction: discord.Interaction,
    ):
        """Show a dropdown to map the current channel to a location"""

        all_locations = self.bot.location_manager.get_all_locations()
        if not all_locations:
            await interaction.response.send_message(
                "❌ No locations are configured yet.",
                ephemeral=True
            )
            return

        current_mapping = self.bot.location_manager.get_location_by_channel(
            interaction.channel_id
        )

        embed = discord.Embed(
            title="Map this channel to a location",
            description=(
                "Select a location from the dropdown below. Players will only be able to use "
                "location-specific commands (like wild encounters) from the channel linked to "
                "that location."
            ),
            color=discord.Color.blurple()
        )

        if current_mapping:
            location_name = self.bot.location_manager.get_location_name(current_mapping)
            embed.add_field(
                name="Current mapping",
                value=f"This channel is currently linked to **{location_name}**.",
                inline=False
            )

        if len(all_locations) > 25:
            embed.set_footer(text="Showing the first 25 locations. Update data/locations.json to reorder if needed.")

        view = ChannelLocationSelectView(
            bot=self.bot,
            channel_id=interaction.channel_id,
            locations=all_locations,
            current_mapping=current_mapping
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="unset_location", description="[ADMIN] Remove location mapping from this channel")
    @app_commands.check(is_admin)
    async def unset_location(
        self,
        interaction: discord.Interaction
    ):
        """Remove location mapping from a channel"""
        
        # Check if channel is mapped
        location_id = self.bot.location_manager.get_location_by_channel(interaction.channel_id)
        if not location_id:
            await interaction.response.send_message(
                "❌ This channel isn't mapped to any location!",
                ephemeral=True
            )
            return
        
        # Remove mapping
        success = self.bot.location_manager.remove_channel_from_location(interaction.channel_id)
        
        if success:
            await interaction.response.send_message(
                f"✅ Removed location mapping from this channel!",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Failed to remove mapping. Try again!",
                ephemeral=True
            )
    
    @app_commands.command(name="list_locations", description="[ADMIN] List all locations and their channels")
    @app_commands.check(is_admin)
    async def list_locations(
        self,
        interaction: discord.Interaction
    ):
        """List all locations and mapped channels"""
        
        all_locations = self.bot.location_manager.get_all_locations()
        
        if not all_locations:
            await interaction.response.send_message(
                "❌ No locations found!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="🗺️ Locations and Channel Mappings",
            description="List of all locations and their mapped Discord channels",
            color=discord.Color.blue()
        )
        
        for location_id, location_data in all_locations.items():
            location_name = location_data.get('name', location_id)
            channel_ids = location_data.get('channel_ids', [])
            
            # Format channel list
            if channel_ids:
                channels = []
                for channel_id in channel_ids:
                    channel = interaction.guild.get_channel(channel_id)
                    if channel:
                        channels.append(f"<#{channel_id}>")
                    else:
                        channels.append(f"Unknown Channel ({channel_id})")
                channel_text = "\n".join(channels)
            else:
                channel_text = "*No channels mapped*"
            
            # Count encounters
            encounter_count = len(location_data.get('encounters', []))
            
            embed.add_field(
                name=f"{location_name} (`{location_id}`)",
                value=f"**Channels:** {channel_text}\n**Encounters:** {encounter_count} species",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


    @app_commands.command(name="create_wild_area", description="[ADMIN] Create a new wild area")
    @app_commands.describe(
        area_id="Unique ID for the area (e.g., 'viridian_forest')",
        name="Display name of the area",
        description="Description of the wild area"
    )
    @app_commands.check(is_admin)
    async def create_wild_area(
        self,
        interaction: discord.Interaction,
        area_id: str,
        name: str,
        description: str = None
    ):
        """Create a new wild area"""
        from wild_area_manager import WildAreaManager

        wild_area_manager = WildAreaManager(self.bot.player_manager.db)

        # Create area
        success = wild_area_manager.create_wild_area(area_id, name, description)

        if success:
            await interaction.response.send_message(
                f"✅ Created wild area **{name}** (ID: `{area_id}`)",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Failed to create wild area. Area with ID `{area_id}` may already exist.",
                ephemeral=True
            )

    @app_commands.command(name="create_zone", description="[ADMIN] Create a zone in a wild area")
    @app_commands.describe(
        zone_id="Unique ID for the zone",
        area_id="Wild area ID this zone belongs to",
        name="Display name of the zone",
        description="Description of the zone",
        has_station="Whether this zone has a Pokemon station",
        travel_cost="Stamina cost to travel to this zone (default: 5)"
    )
    @app_commands.check(is_admin)
    async def create_zone(
        self,
        interaction: discord.Interaction,
        zone_id: str,
        area_id: str,
        name: str,
        description: str = None,
        has_station: bool = False,
        travel_cost: int = 5
    ):
        """Create a zone in a wild area"""
        from wild_area_manager import WildAreaManager

        wild_area_manager = WildAreaManager(self.bot.player_manager.db)

        # Create zone
        success = wild_area_manager.create_zone(
            zone_id=zone_id,
            area_id=area_id,
            name=name,
            description=description,
            has_pokemon_station=has_station,
            zone_travel_cost=travel_cost
        )

        if success:
            station_text = "🏥 with Pokemon Station" if has_station else ""
            await interaction.response.send_message(
                f"✅ Created zone **{name}** {station_text} (ID: `{zone_id}`) in area `{area_id}`\n"
                f"Travel Cost: {travel_cost} stamina",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Failed to create zone. Zone with ID `{zone_id}` may already exist, or area `{area_id}` doesn't exist.",
                ephemeral=True
            )

    @app_commands.command(name="enter_wild_area", description="[ADMIN] Enter a player into a wild area")
    @app_commands.describe(
        user="The player to enter",
        area_id="Wild area ID",
        zone_id="Starting zone ID"
    )
    @app_commands.check(is_admin)
    async def enter_wild_area(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        area_id: str,
        zone_id: str
    ):
        """Enter a player into a wild area"""
        from wild_area_manager import WildAreaManager

        wild_area_manager = WildAreaManager(self.bot.player_manager.db)

        # Check if player exists
        if not self.bot.player_manager.player_exists(user.id):
            await interaction.response.send_message(
                f"❌ {user.mention} hasn't registered yet!",
                ephemeral=True
            )
            return

        # Enter wild area
        success = wild_area_manager.enter_wild_area(user.id, area_id, zone_id)

        if success:
            await interaction.response.send_message(
                f"✅ {user.mention} entered **{area_id}** at zone **{zone_id}**!",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Failed to enter wild area. Area or zone may not exist.",
                ephemeral=True
            )

    @app_commands.command(name="exit_wild_area", description="[ADMIN] Remove a player from wild area")
    @app_commands.describe(
        user="The player to exit",
        success="Whether the exit was successful (true) or player blacked out (false)"
    )
    @app_commands.check(is_admin)
    async def exit_wild_area(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        success: bool = True
    ):
        """Exit a player from a wild area"""
        from wild_area_manager import WildAreaManager

        wild_area_manager = WildAreaManager(self.bot.player_manager.db)

        # Exit wild area
        exited = wild_area_manager.exit_wild_area(user.id, success)

        if exited:
            if success:
                await interaction.response.send_message(
                    f"✅ {user.mention} successfully exited the wild area!",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"⚠️ {user.mention} blacked out! Items and EXP reverted, but caught Pokemon kept.",
                    ephemeral=True
                )
        else:
            await interaction.response.send_message(
                f"❌ {user.mention} is not in a wild area.",
                ephemeral=True
            )

    @app_commands.command(name="create_static_encounter", description="[ADMIN] Create a static encounter")
    @app_commands.describe(
        zone_id="Zone ID where encounter appears",
        encounter_type="Type: public_wild, player_specific, or forced",
        species="Pokemon species (name or dex number)",
        level="Pokemon level",
        target_user="Target player (for player_specific or forced encounters)",
        battle_format="Battle format: singles, doubles, multi, or raid"
    )
    @app_commands.check(is_admin)
    async def create_static_encounter(
        self,
        interaction: discord.Interaction,
        zone_id: str,
        encounter_type: str,
        species: str,
        level: int,
        target_user: Optional[discord.User] = None,
        battle_format: str = "singles"
    ):
        """Create a static encounter"""
        from wild_area_manager import StaticEncounterManager

        static_encounter_manager = StaticEncounterManager(self.bot.player_manager.db)

        # Validate encounter type
        valid_types = ['public_wild', 'player_specific', 'forced']
        if encounter_type not in valid_types:
            await interaction.response.send_message(
                f"❌ Invalid encounter type. Must be one of: {', '.join(valid_types)}",
                ephemeral=True
            )
            return

        # Validate battle format
        valid_formats = ['singles', 'doubles', 'multi', 'raid']
        if battle_format not in valid_formats:
            await interaction.response.send_message(
                f"❌ Invalid battle format. Must be one of: {', '.join(valid_formats)}",
                ephemeral=True
            )
            return

        # Get species
        species_data = self.bot.species_db.get_species(species)
        if not species_data:
            await interaction.response.send_message(
                f"❌ Could not find species: {species}",
                ephemeral=True
            )
            return

        # Create pokemon data
        pokemon_data = {
            'species_dex_number': species_data['dex_number'],
            'species_name': species_data['name'],
            'level': level
        }

        # Create encounter
        encounter_id = static_encounter_manager.create_static_encounter(
            zone_id=zone_id,
            encounter_type=encounter_type,
            pokemon_data=pokemon_data,
            battle_format=battle_format,
            target_player_id=target_user.id if target_user else None
        )

        target_text = f" for {target_user.mention}" if target_user else ""
        await interaction.response.send_message(
            f"✅ Created {encounter_type} encounter:\n"
            f"**{species_data['name']}** (Lv. {level})\n"
            f"Zone: `{zone_id}`\n"
            f"Format: {battle_format}{target_text}\n"
            f"Encounter ID: `{encounter_id}`",
            ephemeral=True
        )

    async def raid_location_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Provide up to 25 location choices for raid spawning."""

        location_manager = getattr(self.bot, "location_manager", None)
        if not location_manager:
            return []

        locations = location_manager.get_all_locations() or {}
        current_lower = (current or "").lower()

        choices = []
        for location_id, data in sorted(
            locations.items(),
            key=lambda item: item[1].get("name", item[0].replace("_", " ").title()),
        ):
            display_name = data.get("name") or location_id.replace("_", " ").title()
            label = f"{display_name} ({location_id})" if display_name != location_id else display_name

            if current_lower and current_lower not in label.lower():
                continue

            choices.append(
                app_commands.Choice(name=label[:100], value=location_id)
            )

            if len(choices) >= 25:
                break

        return choices

    @app_commands.command(name="create_raid", description="[ADMIN] Spawn a raid encounter at a location")
    @app_commands.autocomplete(location_id=raid_location_autocomplete)
    @app_commands.describe(
        location_id="Location/channel mapping ID where the raid appears",
        species="Pokemon species (name or dex number)",
        level="Raid level (1-300)",
        showdown_text="Optional Showdown import to fully define the raid boss",
    )
    @app_commands.check(is_admin)
    async def create_raid(
        self,
        interaction: discord.Interaction,
        location_id: str,
        species: str,
        level: int,
        showdown_text: Optional[str] = None,
    ):
        """Spawn a raid encounter that will show beneath the next wild roll."""

        if not self.bot.location_manager.get_location(location_id):
            await interaction.response.send_message(
                f"❌ Unknown location `{location_id}`. Link a channel to it first.",
                ephemeral=True,
            )
            return

        move_ids = None
        raid_level = level
        raid_species = species
        raid_source = "manual"

        if showdown_text:
            try:
                parsed = self.parse_showdown_import(showdown_text)
                if parsed:
                    entry = parsed[0]
                    move_ids = entry.get("moves") or None
                    raid_level = entry.get("level") or level
                    raid_species = entry.get("species") or species
                    raid_source = "showdown"
            except Exception as exc:
                await interaction.response.send_message(
                    f"❌ Failed to parse Showdown text: {exc}",
                    ephemeral=True,
                )
                return

        try:
            raid = self.bot.raid_manager.create_manual_raid(
                location_id=location_id,
                species_identifier=raid_species,
                level=raid_level,
                created_by=interaction.user.id,
                move_ids=move_ids,
                source=raid_source,
            )
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        embed = discord.Embed(
            title="⚠️ Raid Spawned",
            description=(
                f"A raid featuring **{raid.summary['species_name']}** now lurks in `{location_id}`.\n"
                "It will appear beneath the next wild encounter roll for that location."
            ),
            color=discord.Color.orange(),
        )
        embed.add_field(name="Raid Level", value=raid.summary["level"], inline=True)
        embed.add_field(name="Move Count", value=len(raid.summary.get("move_ids", [])), inline=True)
        embed.add_field(name="Origin", value=raid.summary.get("source", "manual").title(), inline=True)
        embed.set_footer(text=f"Raid ID: {raid.summary['raid_id']}")

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="list_wild_areas", description="[ADMIN] List all wild areas")
    @app_commands.check(is_admin)
    async def list_wild_areas(self, interaction: discord.Interaction):
        """List all wild areas"""
        from wild_area_manager import WildAreaManager

        wild_area_manager = WildAreaManager(self.bot.player_manager.db)
        areas = wild_area_manager.get_all_wild_areas()

        if not areas:
            await interaction.response.send_message(
                "No wild areas found.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🗺️ Wild Areas",
            color=discord.Color.blue()
        )

        for area in areas:
            zones = wild_area_manager.get_zones_in_area(area['area_id'])
            embed.add_field(
                name=f"{area['name']} (`{area['area_id']}`)",
                value=f"{area.get('description', 'No description')}\n**Zones:** {len(zones)}",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    """Setup function for loading the cog"""
    await bot.add_cog(AdminCog(bot))
