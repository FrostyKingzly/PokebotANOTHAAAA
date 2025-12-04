"""
Pokemon Management Cog - Commands for managing party and boxes
"""

import asyncio
import discord
from discord import Forbidden, NotFound
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, Select, Modal
from typing import Optional
from ui.embeds import EmbedBuilder
from sprite_helper import PokemonSpriteHelper


def _get_pokemon_display_name(pokemon: dict, species: dict) -> str:
    return pokemon.get('nickname') or species.get('name')


def _build_pokemon_summary(bot, pokemon: dict):
    """Helper to rebuild the Pokemon summary embed and actions view."""
    if not pokemon:
        return None, None

    species = bot.species_db.get_species(pokemon['species_dex_number'])
    move_data_list = []
    for move in pokemon.get('moves', []):
        move_data = bot.moves_db.get_move(move.get('move_id')) if isinstance(move, dict) else None
        if move_data:
            move_data_list.append(move_data)

    embed = EmbedBuilder.pokemon_summary(pokemon, species, move_data_list)
    view = PokemonActionsView(bot, pokemon, species)
    return embed, view


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
                "Your party is empty.",
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
        
        embed, view = _build_pokemon_summary(self.bot, pokemon)

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
        
        embed, view = _build_pokemon_summary(self.bot, pokemon)

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
        
        # Add navigation controls (disabled automatically at bounds)
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
        self.trainer = self.bot.player_manager.get_player(pokemon.get('owner_discord_id'))

        # Check if Pokemon can evolve and add button dynamically
        if hasattr(bot, 'item_usage_manager'):
            can_evolve, method, evolution_data = bot.item_usage_manager.can_evolve(pokemon)
            if can_evolve:
                self.add_evolution_button()

        self._set_item_button_label()

        if hasattr(self, 'partner_up_button') and self.partner_up_button in self.children:
            if not self._should_show_partner_button():
                self.remove_item(self.partner_up_button)

    def _should_show_partner_button(self) -> bool:
        if self.pokemon.get('is_partner'):
            return False
        if self.trainer and getattr(self.trainer, 'partner_pokemon_id', None):
            return False
        return True
    
    @discord.ui.button(label="⭐️ Partner Up", style=discord.ButtonStyle.success, row=0)
    async def partner_up_button(self, interaction: discord.Interaction, button: Button):
        """Begin the partner confirmation flow."""
        trainer = self.trainer or self.bot.player_manager.get_player(interaction.user.id)

        if interaction.user.id != self.pokemon.get('owner_discord_id'):
            await interaction.response.send_message("[X] This isn't your Pokemon!", ephemeral=True)
            return

        if trainer and getattr(trainer, 'partner_pokemon_id', None):
            await interaction.response.send_message(
                "[X] You've already chosen a partner Pokemon.",
                ephemeral=True,
            )
            return

        if self.pokemon.get('is_partner'):
            await interaction.response.send_message(
                "[X] This Pokemon is already set as a partner.",
                ephemeral=True,
            )
            return

        name = _get_pokemon_display_name(self.pokemon, self.species)
        intro_embed = discord.Embed(
            title=f"Partner up with {name}?",
            description=(
                "Partnering with this Pokémon will make them your best friend and constant companion. "
                "This is your eternal vow to push each other forward and reach for your dreams as one. "
                "Together, anything is possible."
            ),
            color=discord.Color.gold(),
        )

        await interaction.response.edit_message(
            embed=intro_embed,
            view=PartnerIntroView(self.bot, self.pokemon, self.species),
        )

    @discord.ui.button(label="✏️ Nickname", style=discord.ButtonStyle.primary, row=0)
    async def nickname_button(self, interaction: discord.Interaction, button: Button):
        """Change Pokemon nickname"""
        modal = NicknameModal(self.bot, self.pokemon)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Give Item", style=discord.ButtonStyle.primary, row=0)
    async def item_button(self, interaction: discord.Interaction, button: Button):
        """Give or take a held item depending on current state."""
        if self.pokemon.get('held_item'):
            await self._handle_take_item(interaction)
            return

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
    
    

    @discord.ui.button(label="🎯 Moves", style=discord.ButtonStyle.success, row=0)
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

    @discord.ui.button(label="📦 Deposit", style=discord.ButtonStyle.secondary, row=1)
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
    
    @discord.ui.button(label="👋 Release", style=discord.ButtonStyle.danger, row=2)
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
    
    @discord.ui.button(label="↪️ Refresh", style=discord.ButtonStyle.secondary, row=2)
    async def refresh_button(self, interaction: discord.Interaction, button: Button):
        """Refresh Pokemon display"""
        embed = self._build_summary_embed()

        if not embed:
            await interaction.response.send_message("[X] Pokemon not found!", ephemeral=True)
            return

        self._set_item_button_label()
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
        new_species = self.bot.species_db.get_species(new_species_id)
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
                try:
                    if interaction.message:
                        await interaction.message.edit(embed=embed, view=new_view)
                    else:
                        await interaction.followup.send(embed=embed, view=new_view, ephemeral=True)
                except (NotFound, Forbidden):
                    # Original message expired, was deleted, or cannot be accessed; fall back to a fresh update
                    await interaction.followup.send(embed=embed, view=new_view, ephemeral=True)
        else:
            await interaction.followup.send("[X] Evolution failed!", ephemeral=True)

    async def _handle_take_item(self, interaction: discord.Interaction):
        """Remove the held item and refresh the display."""
        await interaction.response.defer(ephemeral=True)

        success, message = self.bot.player_manager.take_item(
            interaction.user.id,
            self.pokemon['pokemon_id']
        )

        if success:
            refreshed = self._reload_pokemon()
            if refreshed:
                self._set_item_button_label()
                embed = self._build_summary_embed()
                if embed:
                    try:
                        await interaction.message.edit(embed=embed, view=self)
                    except Exception:
                        pass

        await interaction.followup.send(message, ephemeral=True)

    def _reload_pokemon(self) -> bool:
        """Reload Pokemon and species data from storage."""
        pokemon = self.bot.player_manager.get_pokemon(self.pokemon['pokemon_id'])
        if not pokemon:
            return False

        self.pokemon = pokemon
        self.species = self.bot.species_db.get_species(pokemon['species_dex_number'])
        return True

    def _build_summary_embed(self):
        """Construct the summary embed with the latest Pokemon data."""
        refreshed = self._reload_pokemon()
        if not refreshed:
            return None

        from ui.embeds import EmbedBuilder

        move_data_list = []
        for move in self.pokemon.get('moves', []):
            move_data = self.bot.moves_db.get_move(move['move_id'])
            if move_data:
                move_data_list.append(move_data)

        return EmbedBuilder.pokemon_summary(self.pokemon, self.species, move_data_list)

    def _set_item_button_label(self):
        """Update the item button label based on held item state."""
        if hasattr(self, 'item_button'):
            self.item_button.label = "Take Item" if self.pokemon.get('held_item') else "Give Item"


class PartnerIntroView(View):
    """First step of the partner confirmation flow."""

    def __init__(self, bot, pokemon: dict, species: dict):
        super().__init__(timeout=300)
        self.bot = bot
        self.pokemon = pokemon
        self.species = species

    async def _return_to_actions(self, interaction: discord.Interaction):
        refreshed = self.bot.player_manager.get_pokemon(self.pokemon['pokemon_id'])
        embed, view = _build_pokemon_summary(self.bot, refreshed)
        if embed and view:
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.response.send_message("[X] Pokemon not found.", ephemeral=True)

    @discord.ui.button(label="Let's do it!", style=discord.ButtonStyle.success)
    async def continue_button(self, interaction: discord.Interaction, button: Button):
        name = _get_pokemon_display_name(self.pokemon, self.species)
        confirm_embed = discord.Embed(
            title="This decision cannot be undone.",
            description=f"Are you sure you wish to partner with {name}?",
            color=discord.Color.orange(),
        )
        await interaction.response.edit_message(
            embed=confirm_embed,
            view=PartnerFinalConfirmView(self.bot, self.pokemon, self.species),
        )

    @discord.ui.button(label="Let me think…", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        await self._return_to_actions(interaction)


class PartnerFinalConfirmView(View):
    """Final confirmation for locking in a partner."""

    def __init__(self, bot, pokemon: dict, species: dict):
        super().__init__(timeout=300)
        self.bot = bot
        self.pokemon = pokemon
        self.species = species

    async def _return_to_actions(self, interaction: discord.Interaction):
        refreshed = self.bot.player_manager.get_pokemon(self.pokemon['pokemon_id'])
        embed, view = _build_pokemon_summary(self.bot, refreshed)
        if embed and view:
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.response.send_message("[X] Pokemon not found.", ephemeral=True)

    async def _send_congrats_embed(self, interaction: discord.Interaction, trainer, pokemon: dict):
        species = self.species or self.bot.species_db.get_species(pokemon['species_dex_number'])
        name = _get_pokemon_display_name(pokemon, species)

        congrats_embed = discord.Embed(
            title="A New Partnership!",
            description=(
                f"{trainer.trainer_name} and {name} have become partners. "
                "May their dreams come true together in Reverie."
            ),
            color=discord.Color.gold(),
        )

        if getattr(trainer, 'avatar_url', None):
            congrats_embed.set_thumbnail(url=trainer.avatar_url)

        sprite_url = PokemonSpriteHelper.get_sprite(
            species.get('name'),
            species.get('dex_number'),
            shiny=bool(pokemon.get('is_shiny')),
            form=pokemon.get('form'),
            gender=pokemon.get('gender'),
        )

        if isinstance(sprite_url, list):
            sprite_url = sprite_url[0]

        if sprite_url:
            congrats_embed.set_image(url=sprite_url)

        await interaction.followup.send(embed=congrats_embed)

    @discord.ui.button(label="Yes, together!", style=discord.ButtonStyle.success)
    async def finalize_button(self, interaction: discord.Interaction, button: Button):
        trainer = self.bot.player_manager.get_player(interaction.user.id)
        if not trainer:
            await interaction.response.send_message("[X] Trainer profile not found.", ephemeral=True)
            return

        already_partnered = getattr(trainer, 'partner_pokemon_id', None) == self.pokemon.get('pokemon_id')

        if getattr(trainer, 'partner_pokemon_id', None) and not already_partnered:
            await interaction.response.send_message("[X] You've already chosen a partner Pokemon.", ephemeral=True)
            return

        success, message = self.bot.player_manager.set_partner_pokemon(
            interaction.user.id,
            self.pokemon['pokemon_id'],
        )

        refreshed = self.bot.player_manager.get_pokemon(self.pokemon['pokemon_id'])
        embed, view = _build_pokemon_summary(self.bot, refreshed)

        if embed and view:
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.response.send_message("[X] Pokemon not found.", ephemeral=True)
            return

        if not success:
            await interaction.followup.send(message, ephemeral=True)
            return

        if already_partnered:
            await interaction.followup.send(message, ephemeral=True)
            return

        await self._send_congrats_embed(interaction, trainer, refreshed)

    @discord.ui.button(label="No, not yet…", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        await self._return_to_actions(interaction)


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

    @discord.ui.button(label="↕️ [MOVES] Sort", style=discord.ButtonStyle.secondary, row=0)
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

    @discord.ui.button(label="☑️ [MOVES] Equip", style=discord.ButtonStyle.primary, row=0)
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

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.secondary, row=1)
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
