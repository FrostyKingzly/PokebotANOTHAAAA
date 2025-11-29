"""
Pokemon Management Cog - Commands for managing party and boxes
"""

import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, Select, Modal
from typing import Optional
from ui.embeds import EmbedBuilder


class PokemonManagementCog(commands.Cog):
    """Commands for managing Pokemon party and boxes"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="party", description="View and manage your party Pokemon")
    async def party_command(self, interaction: discord.Interaction):
        """Show party with management options"""
        party = self.bot.player_manager.get_party(interaction.user.id)
        
        if not party:
            await interaction.response.send_message(
                "Your party is empty! This shouldn't happen - contact an admin.",
                ephemeral=True
            )
            return
        

        embed = EmbedBuilder.party_view(party, self.bot.species_db)
        view = PartyManagementView(self.bot, party)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @app_commands.command(name="boxes", description="View and manage your stored Pokemon")
    async def boxes_command(self, interaction: discord.Interaction):
        """Show storage boxes"""
        boxes = self.bot.player_manager.get_boxes(interaction.user.id)
        
        if not boxes:
            await interaction.response.send_message(
                "[BOX] Your storage boxes are empty! Catch more Pokemon to fill them up.",
                ephemeral=True
            )
            return
        

        embed = EmbedBuilder.box_view(boxes, self.bot.species_db, page=0, total_pages=max(1, (len(boxes) + 29) // 30))
        view = BoxManagementView(self.bot, boxes, page=0)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @app_commands.command(name="pokemon", description="View detailed information about a Pokemon")
    @app_commands.describe(pokemon_id="The ID of the Pokemon to view")
    async def pokemon_detail_command(self, interaction: discord.Interaction, pokemon_id: str):
        """Show detailed Pokemon information"""
        pokemon = self.bot.player_manager.get_pokemon(pokemon_id)
        
        if not pokemon:
            await interaction.response.send_message("[X] Pokemon not found!", ephemeral=True)
            return
        
        if pokemon['owner_discord_id'] != interaction.user.id:
            await interaction.response.send_message("[X] This isn't your Pokemon!", ephemeral=True)
            return
        
        # Get species and move data
        species = self.bot.species_db.get_species(pokemon['species_dex_number'])
        move_data_list = []
        for move in pokemon['moves']:
            move_data = self.bot.moves_db.get_move(move['move_id'])
            if move_data:
                move_data_list.append(move_data)
        

        embed = EmbedBuilder.pokemon_summary(pokemon, species, move_data_list)
        view = PokemonActionsView(self.bot, pokemon, species)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class PartyManagementView(View):
    """Party management interface with Pokemon selection"""
    
    def __init__(self, bot, party: list):
        super().__init__(timeout=300)
        self.bot = bot
        self.party = party
        
        if party:
            options = []
            for i, pokemon in enumerate(party[:6], 1):
                species = bot.species_db.get_species(pokemon['species_dex_number'])
                name = pokemon.get('nickname') or species['name']
                
                label = f"#{i} - {name} (Lv. {pokemon['level']})"
                description = f"{species['name']} â€¢ HP: {pokemon['current_hp']}/{pokemon['max_hp']}"
                
                options.append(
                    discord.SelectOption(
                        label=label[:100],
                        value=pokemon['pokemon_id'],
                        description=description[:100]
                    )
                )
            
            select = Select(
                placeholder="Select a Pokemon to view details...",
                options=options
            )
            select.callback = self.pokemon_selected
            self.add_item(select)
    
    async def pokemon_selected(self, interaction: discord.Interaction):
        """Handle Pokemon selection"""
        pokemon_id = interaction.data['values'][0]
        pokemon = self.bot.player_manager.get_pokemon(pokemon_id)
        
        if not pokemon:
            await interaction.response.send_message("[X] Pokemon not found!", ephemeral=True)
            return
        
        species = self.bot.species_db.get_species(pokemon['species_dex_number'])
        move_data_list = []
        for move in pokemon['moves']:
            move_data = self.bot.moves_db.get_move(move['move_id'])
            if move_data:
                move_data_list.append(move_data)
        

        embed = EmbedBuilder.pokemon_summary(pokemon, species, move_data_list)
        view = PokemonActionsView(self.bot, pokemon, species)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class BoxManagementView(View):
    """Box storage management with pagination"""
    
    def __init__(self, bot, boxes: list, page: int = 0):
        super().__init__(timeout=300)
        self.bot = bot
        self.boxes = boxes
        self.page = page
        self.total_pages = max(1, (len(boxes) + 29) // 30)
        
        # Add Pokemon selection dropdown for current page
        self.add_box_select()
        
        # Add navigation if needed
        if self.total_pages > 1:
            self.add_navigation_buttons()
    
    def add_box_select(self):
        """Add Pokemon selection dropdown"""
        start_idx = self.page * 30
        end_idx = min(start_idx + 30, len(self.boxes))
        page_boxes = self.boxes[start_idx:end_idx]
        
        if not page_boxes:
            return
        
        options = []
        for i, pokemon in enumerate(page_boxes[:25], start_idx + 1):  # Discord limit of 25
            species = self.bot.species_db.get_species(pokemon['species_dex_number'])
            name = pokemon.get('nickname') or species['name']
            
            label = f"#{i} - {name} (Lv. {pokemon['level']})"
            description = f"{species['name']}"
            
            options.append(
                discord.SelectOption(
                    label=label[:100],
                    value=pokemon['pokemon_id'],
                    description=description[:100]
                )
            )
        
        if options:
            select = Select(
                placeholder="Select a Pokemon to view or withdraw...",
                options=options
            )
            select.callback = self.pokemon_selected
            self.add_item(select)
    
    async def pokemon_selected(self, interaction: discord.Interaction):
        """Handle Pokemon selection from box"""
        pokemon_id = interaction.data['values'][0]
        pokemon = self.bot.player_manager.get_pokemon(pokemon_id)
        
        if not pokemon:
            await interaction.response.send_message("[X] Pokemon not found!", ephemeral=True)
            return
        
        species = self.bot.species_db.get_species(pokemon['species_dex_number'])
        move_data_list = []
        for move in pokemon['moves']:
            move_data = self.bot.moves_db.get_move(move['move_id'])
            if move_data:
                move_data_list.append(move_data)
        

        embed = EmbedBuilder.pokemon_summary(pokemon, species, move_data_list)
        view = PokemonActionsView(self.bot, pokemon, species)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    def add_navigation_buttons(self):
        """Add page navigation"""
        prev_button = Button(
            label="<< Previous",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page == 0)
        )
        prev_button.callback = self.previous_page
        self.add_item(prev_button)
        
        page_button = Button(
            label=f"Page {self.page + 1}/{self.total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True
        )
        self.add_item(page_button)
        
        next_button = Button(
            label="Next >>",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page >= self.total_pages - 1)
        )
        next_button.callback = self.next_page
        self.add_item(next_button)
    
    async def previous_page(self, interaction: discord.Interaction):
        """Go to previous page"""
        if self.page > 0:
            self.page -= 1
            await self.update_view(interaction)
    
    async def next_page(self, interaction: discord.Interaction):
        """Go to next page"""
        if self.page < self.total_pages - 1:
            self.page += 1
            await self.update_view(interaction)
    
    async def update_view(self, interaction: discord.Interaction):
        """Update the box view"""

        embed = EmbedBuilder.box_view(self.boxes, self.bot.species_db, page=self.page, total_pages=self.total_pages)
        new_view = BoxManagementView(self.bot, self.boxes, self.page)
        await interaction.response.edit_message(embed=embed, view=new_view)


class PokemonActionsView(View):
    """All actions available for a specific Pokemon"""

    def __init__(self, bot, pokemon: dict, species: dict):
        super().__init__(timeout=300)
        self.bot = bot
        self.pokemon = pokemon
        self.species = species

        # Check if Pokemon can evolve and add button dynamically
        if hasattr(bot, 'item_usage_manager'):
            can_evolve, method, evolution_data = bot.item_usage_manager.can_evolve(pokemon)
            if can_evolve:
                self.add_evolution_button()
    
    @discord.ui.button(label="Nickname", style=discord.ButtonStyle.primary, row=0)
    async def nickname_button(self, interaction: discord.Interaction, button: Button):
        """Change Pokemon nickname"""
        modal = NicknameModal(self.bot, self.pokemon)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Give Item", style=discord.ButtonStyle.primary, row=0)
    async def give_item_button(self, interaction: discord.Interaction, button: Button):
        """Give held item to Pokemon"""
        inventory = self.bot.player_manager.get_inventory(interaction.user.id)
        held_items = [item for item in inventory if item['quantity'] > 0]
        
        if not held_items:
            await interaction.response.send_message(
                "[X] You don't have any items to give!",
                ephemeral=True
            )
            return
        
        view = GiveItemView(self.bot, self.pokemon, held_items[:25])
        await interaction.response.send_message(
            "Select an item to give:",
            view=view,
            ephemeral=True
        )
    
    @discord.ui.button(label="Take Item", style=discord.ButtonStyle.primary, row=0)
    async def take_item_button(self, interaction: discord.Interaction, button: Button):
        """Take held item from Pokemon"""
        if not self.pokemon.get('held_item'):
            await interaction.response.send_message(
                "[X] This Pokemon isn't holding an item!",
                ephemeral=True
            )
            return
        
        success, message = self.bot.player_manager.take_item(
            interaction.user.id,
            self.pokemon['pokemon_id']
        )
        
        await interaction.response.send_message(message, ephemeral=True)
    
    

    @discord.ui.button(label="Moves", style=discord.ButtonStyle.success, row=0)
    async def manage_moves_button(self, interaction: discord.Interaction, button: Button):
        """Open a focused moves management menu for this Pokemon."""
        from ui.embeds import EmbedBuilder

        pokemon = self.bot.player_manager.get_pokemon(self.pokemon['pokemon_id'])
        if not pokemon:
            await interaction.response.send_message("[X] Pokemon not found!", ephemeral=True)
            return

        species = self.bot.species_db.get_species(pokemon['species_dex_number'])
        move_data_list = []
        for move in pokemon.get('moves', []):
            move_data = self.bot.moves_db.get_move(move['move_id'])
            if move_data:
                move_data_list.append(move_data)

        embed = EmbedBuilder.pokemon_summary(pokemon, species, move_data_list)
        view = MoveManagementView(self.bot, pokemon['pokemon_id'])
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    @discord.ui.button(label="Deposit", style=discord.ButtonStyle.secondary, row=1)
    async def deposit_button(self, interaction: discord.Interaction, button: Button):
        """Move Pokemon from party to box"""
        if not self.pokemon.get('in_party'):
            await interaction.response.send_message(
                "[X] This Pokemon is already in a box!",
                ephemeral=True
            )
            return
        
        success, message = self.bot.player_manager.deposit_pokemon(
            interaction.user.id,
            self.pokemon['pokemon_id']
        )
        
        await interaction.response.send_message(message, ephemeral=True)
    
    @discord.ui.button(label="Withdraw", style=discord.ButtonStyle.secondary, row=1)
    async def withdraw_button(self, interaction: discord.Interaction, button: Button):
        """Move Pokemon from box to party"""
        if self.pokemon.get('in_party'):
            await interaction.response.send_message(
                "[X] This Pokemon is already in your party!",
                ephemeral=True
            )
            return
        
        success, message = self.bot.player_manager.withdraw_pokemon(
            interaction.user.id,
            self.pokemon['pokemon_id']
        )
        
        await interaction.response.send_message(message, ephemeral=True)
    
    @discord.ui.button(label="Release", style=discord.ButtonStyle.danger, row=2)
    async def release_button(self, interaction: discord.Interaction, button: Button):
        """Release Pokemon (with confirmation)"""
        display_name = self.pokemon.get('nickname') or self.species['name']
        
        confirm_view = ConfirmReleaseView()
        await interaction.response.send_message(
            f"[!] **Warning!** Are you sure you want to release **{display_name}**?\n"
            f"This action cannot be undone!",
            view=confirm_view,
            ephemeral=True
        )
        
        await confirm_view.wait()
        
        if confirm_view.value:
            success, message = self.bot.player_manager.release_pokemon(
                interaction.user.id,
                self.pokemon['pokemon_id']
            )
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.followup.send("[OK] Release cancelled.", ephemeral=True)
    
    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, row=2)
    async def refresh_button(self, interaction: discord.Interaction, button: Button):
        """Refresh Pokemon display"""
        pokemon = self.bot.player_manager.get_pokemon(self.pokemon['pokemon_id'])
        
        if not pokemon:
            await interaction.response.send_message("[X] Pokemon not found!", ephemeral=True)
            return
        
        move_data_list = []
        for move in pokemon['moves']:
            move_data = self.bot.moves_db.get_move(move['move_id'])
            if move_data:
                move_data_list.append(move_data)
        

        embed = EmbedBuilder.pokemon_summary(pokemon, self.species, move_data_list)

        self.pokemon = pokemon
        await interaction.response.edit_message(embed=embed, view=self)

    def add_evolution_button(self):
        """Dynamically add evolution button"""
        button = Button(
            label="⭐ Evolve",
            style=discord.ButtonStyle.success,
            row=1
        )
        button.callback = self.evolve_button
        self.add_item(button)

    async def evolve_button(self, interaction: discord.Interaction):
        """Handle Pokemon evolution with animation sequence"""
        # Check evolution eligibility
        can_evolve, method, evolution_data = self.bot.item_usage_manager.can_evolve(self.pokemon)

        if not can_evolve:
            await interaction.response.send_message(
                "[X] This Pokemon cannot evolve right now!",
                ephemeral=True
            )
            return

        # Get evolution target
        if method == 'multiple':
            # Multiple evolution options (e.g., Eevee)
            await interaction.response.send_message(
                "[!] This Pokemon has multiple evolution options! Use an evolution stone to choose.",
                ephemeral=True
            )
            return

        evolve_into = evolution_data.get('into')
        if not evolve_into:
            await interaction.response.send_message("[X] Evolution data error!", ephemeral=True)
            return

        # Get new species data
        new_species_id = evolve_into
        new_species = self.bot.species_db.get_species_by_name(new_species_id)
        if not new_species:
            await interaction.response.send_message("[X] Evolution species not found!", ephemeral=True)
            return

        old_name = self.species['name']
        new_name = new_species['name']

        # Evolution animation sequence
        await interaction.response.send_message(
            f"✨ What? **{old_name}** is evolving!",
            ephemeral=True
        )
        await asyncio.sleep(2)

        # Perform evolution
        success = self.bot.item_usage_manager._trigger_evolution(
            interaction.user.id,
            self.pokemon,
            evolve_into
        )

        if success:
            await interaction.followup.send(
                f"✨✨✨\n"
                f"Congratulations! Your **{old_name}** evolved into **{new_name}**!\n"
                f"✨✨✨",
                ephemeral=True
            )

            # Refresh the Pokemon view
            updated_pokemon = self.bot.player_manager.get_pokemon(self.pokemon['pokemon_id'])
            if updated_pokemon:
                move_data_list = []
                for move in updated_pokemon['moves']:
                    move_data = self.bot.moves_db.get_move(move['move_id'])
                    if move_data:
                        move_data_list.append(move_data)

                embed = EmbedBuilder.pokemon_summary(updated_pokemon, new_species, move_data_list)
                new_view = PokemonActionsView(self.bot, updated_pokemon, new_species)
                await interaction.message.edit(embed=embed, view=new_view)
        else:
            await interaction.followup.send("[X] Evolution failed!", ephemeral=True)


class GiveItemView(View):
    """Select an item to give to Pokemon"""
    
    def __init__(self, bot, pokemon: dict, items: list):
        super().__init__(timeout=300)
        self.bot = bot
        self.pokemon = pokemon
        
        options = []
        for item in items:
            item_data = bot.items_db.get_item(item['item_id'])
            if not item_data:
                continue
            
            label = f"{item_data['name']} (x{item['quantity']})"
            description = item_data.get('description', '')[:100]
            
            options.append(
                discord.SelectOption(
                    label=label[:100],
                    value=item['item_id'],
                    description=description
                )
            )
        
        if options:
            select = Select(
                placeholder="Select an item to give...",
                options=options
            )
            select.callback = self.item_selected
            self.add_item(select)
    
    async def item_selected(self, interaction: discord.Interaction):
        """Handle item selection"""
        item_id = interaction.data['values'][0]
        success, message = self.bot.player_manager.give_item(
            interaction.user.id,
            self.pokemon['pokemon_id'],
            item_id
        )
        await interaction.response.send_message(message, ephemeral=True)




    
class NicknameModal(Modal, title="Change Nickname"):
    """Modal for changing Pokemon nickname"""
    
    def __init__(self, bot, pokemon: dict):
        super().__init__()
        self.bot = bot
        self.pokemon = pokemon
    
    nickname = discord.ui.TextInput(
        label="New Nickname",
        placeholder="Enter a nickname (leave blank to reset)...",
        required=False,
        max_length=12
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle nickname submission"""
        new_nickname = self.nickname.value.strip() if self.nickname.value else None
        
        success, message = self.bot.player_manager.set_nickname(
            interaction.user.id,
            self.pokemon['pokemon_id'],
            new_nickname
        )
        
        await interaction.response.send_message(message, ephemeral=True)




class SortMovesView(View):
    """View that lets the user choose how to sort a Pokémon's moves."""

    def __init__(self, bot, pokemon_id: str):
        super().__init__(timeout=120)
        self.bot = bot
        self.pokemon_id = pokemon_id

        options = [
            discord.SelectOption(label="Name (A–Z)", value="name"),
            discord.SelectOption(label="Type", value="type"),
            discord.SelectOption(label="Category", value="category"),
            discord.SelectOption(label="Power (high→low)", value="power"),
            discord.SelectOption(label="Accuracy (high→low)", value="accuracy"),
        ]

        self.add_item(SortMovesSelect(self, options))


class SortMovesSelect(Select):
    """Dropdown for selecting a move sort order."""

    def __init__(self, parent, options):
        super().__init__(
            placeholder="Sort moves by...",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.owner_view = parent

    async def callback(self, interaction: discord.Interaction):
        from ui.embeds import EmbedBuilder

        sort_key = self.values[0]
        descending = sort_key in ("power", "accuracy")

        # Apply sort in the database
        self.owner_view.bot.player_manager.sort_pokemon_moves(
            self.owner_view.pokemon_id,
            key=sort_key,
            descending=descending,
        )

        # Reload Pokemon & rebuild summary
        pokemon = self.owner_view.bot.player_manager.get_pokemon(self.owner_view.pokemon_id)
        if not pokemon:
            await interaction.response.send_message("[X] Pokemon not found!", ephemeral=True)
            return

        species = self.owner_view.bot.species_db.get_species(pokemon['species_dex_number'])
        move_data_list = []
        for move in pokemon.get('moves', []):
            move_data = self.owner_view.bot.moves_db.get_move(move['move_id'])
            if move_data:
                move_data_list.append(move_data)

        embed = EmbedBuilder.pokemon_summary(pokemon, species, move_data_list)
        view = PokemonActionsView(self.owner_view.bot, pokemon, species)
        await interaction.response.edit_message(content=None, embed=embed, view=view)


class EquipMovesView(View):
    """View allowing a user to (re)assign a Pokémon's moves."""

    def __init__(self, bot, pokemon: dict, available_moves: dict):
        super().__init__(timeout=300)
        self.bot = bot
        self.pokemon_id = pokemon['pokemon_id']
        self.owner_id = pokemon['owner_discord_id']

        current_moves = [m['move_id'] for m in pokemon.get('moves', [])]

        # Build up to 25 options (Discord's limit for a single select)
        options = []
        for move_id, move_data in list(available_moves.items())[:25]:
            name = (move_data.get('name') or move_id).title()
            move_type = (move_data.get('type') or "").title()
            category = (move_data.get('category') or "").title()
            power = move_data.get('power')
            accuracy = move_data.get('accuracy')

            power_str = "—" if not power or power == 0 else str(power)
            if isinstance(accuracy, (int, float)):
                acc_str = f"{accuracy}"
            else:
                acc_str = "—"

            description = f"{move_type}/{category} Pwr {power_str} Acc {acc_str}"

            options.append(
                discord.SelectOption(
                    label=name[:100],
                    value=move_id,
                    description=description[:100],
                    default=move_id in current_moves,
                )
            )

        if not options:
            # No options to show – this view should not have been constructed.
            return

        max_values = min(4, len(options))
        self.add_item(EquipMovesSelect(self, options, max_values=max_values))


class EquipMovesSelect(Select):
    """Dropdown used to select which moves a Pokémon should know."""

    def __init__(self, parent, options, max_values: int = 4):
        super().__init__(
            placeholder="Pick 1–4 moves to equip",
            min_values=1,
            max_values=max_values,
            options=options,
        )
        self.owner_view = parent

    async def callback(self, interaction: discord.Interaction):
        from ui.embeds import EmbedBuilder

        selected_ids = list(self.values)

        success, message = self.owner_view.bot.player_manager.equip_pokemon_moves(
            interaction.user.id,
            self.owner_view.pokemon_id,
            selected_ids,
        )

        if not success:
            await interaction.response.send_message(message, ephemeral=True)
            return

        pokemon = self.owner_view.bot.player_manager.get_pokemon(self.owner_view.pokemon_id)
        if not pokemon:
            await interaction.response.send_message("[X] Pokemon not found after updating moves!", ephemeral=True)
            return

        species = self.owner_view.bot.species_db.get_species(pokemon['species_dex_number'])
        move_data_list = []
        for move in pokemon.get('moves', []):
            move_data = self.owner_view.bot.moves_db.get_move(move['move_id'])
            if move_data:
                move_data_list.append(move_data)

        embed = EmbedBuilder.pokemon_summary(pokemon, species, move_data_list)
        view = PokemonActionsView(self.owner_view.bot, pokemon, species)
        await interaction.response.edit_message(content=None, embed=embed, view=view)



class MoveManagementView(View):
    """Sub-view focused specifically on managing a Pokémon's moves."""

    def __init__(self, bot, pokemon_id: str):
        super().__init__(timeout=300)
        self.bot = bot
        self.pokemon_id = pokemon_id

    @discord.ui.button(label="[MOVES] Sort", style=discord.ButtonStyle.secondary, row=0)
    async def sort_moves_button(self, interaction: discord.Interaction, button: Button):
        """Open the sort moves selector for this Pokémon."""
        from ui.embeds import EmbedBuilder

        pokemon = self.bot.player_manager.get_pokemon(self.pokemon_id)
        if not pokemon:
            await interaction.response.send_message("[X] Pokemon not found!", ephemeral=True)
            return

        if not pokemon.get('moves'):
            await interaction.response.send_message(
                "[X] This Pokemon doesn't know any moves yet!",
                ephemeral=True
            )
            return

        view = SortMovesView(self.bot, self.pokemon_id)
        await interaction.response.send_message(
            "Select how you'd like to sort this Pokémon's moves:",
            view=view,
            ephemeral=True
        )

    @discord.ui.button(label="[MOVES] Equip", style=discord.ButtonStyle.primary, row=0)
    async def equip_moves_button(self, interaction: discord.Interaction, button: Button):
        """Open the move equip selector for this Pokémon."""
        from ui.embeds import EmbedBuilder

        available_moves = self.bot.player_manager.get_available_moves_for_pokemon(self.pokemon_id)
        if not available_moves:
            await interaction.response.send_message(
                "ℹ️ No extra moves are available for this Pokémon yet (at its current level).",
                ephemeral=True
            )
            return

        pokemon = self.bot.player_manager.get_pokemon(self.pokemon_id)
        if not pokemon:
            await interaction.response.send_message("[X] Pokemon not found!", ephemeral=True)
            return

        view = EquipMovesView(self.bot, pokemon, available_moves)
        await interaction.response.send_message(
            "Select up to **four** moves for this Pokémon. "
            "Your current choices will replace its existing moves.",
            view=view,
            ephemeral=True
        )

    @discord.ui.button(label="[BACK] Return", style=discord.ButtonStyle.secondary, row=1)
    async def back_button(self, interaction: discord.Interaction, button: Button):
        """Return to the main Pokemon actions view."""
        from ui.embeds import EmbedBuilder

        pokemon = self.bot.player_manager.get_pokemon(self.pokemon_id)
        if not pokemon:
            await interaction.response.send_message("[X] Pokemon not found!", ephemeral=True)
            return

        species = self.bot.species_db.get_species(pokemon['species_dex_number'])
        move_data_list = []
        for move in pokemon.get('moves', []):
            move_data = self.bot.moves_db.get_move(move['move_id'])
            if move_data:
                move_data_list.append(move_data)

        embed = EmbedBuilder.pokemon_summary(pokemon, species, move_data_list)
        view = PokemonActionsView(self.bot, pokemon, species)
        await interaction.response.edit_message(content=None, embed=embed, view=view)


class ConfirmReleaseView(View):
    """Confirmation dialog for releasing Pokemon"""
    
    def __init__(self):
        super().__init__(timeout=60)
        self.value = None
    
    @discord.ui.button(label="[OK] Confirm Release", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction: discord.Interaction, button: Button):
        """Confirm release"""
        self.value = True
        await interaction.response.defer()
        self.stop()
    
    @discord.ui.button(label="[X] Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        """Cancel release"""
        self.value = False
        await interaction.response.defer()
        self.stop()


async def setup(bot):
    """Add cog to bot"""
    await bot.add_cog(PokemonManagementCog(bot))
