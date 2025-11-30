"""
Items Cog - Commands for using items on Pokemon
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, Select
from typing import Optional


class ItemsCog(commands.Cog):
    """Commands for using items"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="use", description="Use an item on a Pokemon")
    @app_commands.describe(
        item_name="The name of the item to use (e.g., 'Rare Candy', 'TM01', 'Fire Stone')",
        pokemon_slot="The party slot of the Pokemon (1-6)"
    )
    async def use_command(
        self,
        interaction: discord.Interaction,
        item_name: str,
        pokemon_slot: int
    ):
        """Use an item on a Pokemon"""
        # Check player exists
        player_data = self.bot.player_manager.get_player(interaction.user.id)
        if not player_data:
            await interaction.response.send_message(
                "[X] You haven't started your journey yet! Use `/register` to begin.",
                ephemeral=True
            )
            return

        # Validate slot
        if pokemon_slot < 1 or pokemon_slot > 6:
            await interaction.response.send_message(
                "[X] Pokemon slot must be between 1 and 6!",
                ephemeral=True
            )
            return

        # Get party
        party = self.bot.player_manager.get_party(interaction.user.id)
        if not party or len(party) < pokemon_slot:
            await interaction.response.send_message(
                f"[X] You don't have a Pokemon in slot {pokemon_slot}!",
                ephemeral=True
            )
            return

        pokemon = party[pokemon_slot - 1]

        # Find item by name (case-insensitive)
        inventory = self.bot.player_manager.get_inventory(interaction.user.id)
        item_id = None
        for inv_item in inventory:
            item_data = self.bot.items_db.get_item(inv_item['item_id'])
            if item_data and item_data['name'].lower() == item_name.lower():
                if inv_item['quantity'] > 0:
                    item_id = inv_item['item_id']
                    break

        if not item_id:
            await interaction.response.send_message(
                f"[X] You don't have any '{item_name}' in your inventory!",
                ephemeral=True
            )
            return

        # Use the item
        result = self.bot.item_usage_manager.use_item(
            interaction.user.id,
            pokemon['pokemon_id'],
            item_id
        )

        # Build response message
        if result.success:
            message = f"✅ {result.message}"

            # Add extra details
            if result.new_level:
                message += f"\n📊 **Level:** {result.new_level}"
            if result.learned_move:
                message += f"\n📖 **Learned:** {result.learned_move}"
            if result.evolved_into:
                species = self.bot.species_db.get_species(result.evolved_into)
                if species:
                    message += f"\n✨ **Evolved into:** {species['name']}!"
        else:
            message = f"[X] {result.message}"

        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="inventory", description="View your item inventory")
    async def inventory_command(self, interaction: discord.Interaction):
        """View player's inventory"""
        # Check player exists
        player_data = self.bot.player_manager.get_player(interaction.user.id)
        if not player_data:
            await interaction.response.send_message(
                "[X] You haven't started your journey yet! Use `/register` to begin.",
                ephemeral=True
            )
            return

        inventory = self.bot.player_manager.get_inventory(interaction.user.id)

        # Group items by category
        categories = {
            'medicine': [],
            'pokeball': [],
            'battle_item': [],
            'evolution': [],
            'tms': [],
            'berries': [],
            'other': []
        }

        for inv_item in inventory:
            if inv_item['quantity'] <= 0:
                continue

            item_data = self.bot.items_db.get_item(inv_item['item_id'])
            if not item_data:
                continue

            category = item_data.get('category', 'other')
            if category not in categories:
                category = 'other'

            categories[category].append({
                'name': item_data['name'],
                'quantity': inv_item['quantity'],
                'description': item_data.get('description', 'No description')
            })

        # Build embed
        embed = discord.Embed(
            title="🎒 Item Inventory",
            description=f"Use `/use [item_name] [pokemon_slot]` to use an item",
            color=discord.Color.blue()
        )

        # Add fields for each category
        for category, items in categories.items():
            if not items:
                continue

            # Format category name
            category_name = category.replace('_', ' ').title()

            # Build item list
            item_list = []
            for item in sorted(items, key=lambda x: x['name'])[:10]:  # Limit to 10 per category
                item_list.append(f"**{item['name']}** x{item['quantity']}")

            if len(items) > 10:
                item_list.append(f"... and {len(items) - 10} more")

            embed.add_field(
                name=f"📦 {category_name}",
                value="\n".join(item_list) if item_list else "None",
                inline=False
            )

        # Check if inventory is empty
        if all(len(items) == 0 for items in categories.values()):
            embed.description = "Your inventory is empty! Visit the PokeMart with `/buy` to purchase items."

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    """Load the cog"""
    await bot.add_cog(ItemsCog(bot))
