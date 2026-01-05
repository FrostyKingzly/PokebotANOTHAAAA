"""
Session Cog - Admin-led group session commands
Allows admins to create sessions where players join and are controlled as a group
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List
import re

from models import Pokemon
from sprite_helper import PokemonSpriteHelper
from ui.embeds import EmbedBuilder

def is_admin(interaction: discord.Interaction) -> bool:
    """Return True when the invoking user has administrator permissions."""
    return interaction.user.guild_permissions.administrator


class JoinSessionView(discord.ui.View):
    """View with Join Session button"""

    def __init__(self, bot, session_id: str):
        super().__init__(timeout=None)  # No timeout for join button
        self.bot = bot
        self.session_id = session_id

    @discord.ui.button(label="Join Session", style=discord.ButtonStyle.primary, emoji="✋")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle join session button click"""
        user_id = interaction.user.id

        # Check if player is registered
        if not self.bot.player_manager.player_exists(user_id):
            await interaction.response.send_message(
                "❌ You need to register first with `/register`!",
                ephemeral=True
            )
            return

        # Check if already in a session
        if self.bot.session_manager.is_in_session(user_id):
            current_session = self.bot.session_manager.get_player_session(user_id)
            if current_session and current_session['session_id'] == self.session_id:
                await interaction.response.send_message(
                    "ℹ️ You're already in this session!",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ You're already in another session! Leave that session first.",
                    ephemeral=True
                )
            return

        # Add to session
        success = self.bot.session_manager.add_participant(self.session_id, user_id)

        if success:
            session = self.bot.session_manager.get_session(self.session_id)
            await interaction.response.send_message(
                f"✅ You've joined the session **{session['session_name']}**! You're now in session state and will move with the group.",
                ephemeral=True
            )

            # Update the join embed to show current participants
            await self._update_join_embed(interaction)
        else:
            await interaction.response.send_message(
                "❌ Failed to join session. Please try again.",
                ephemeral=True
            )

    async def _update_join_embed(self, interaction: discord.Interaction):
        """Update the join message embed with current participant list"""
        session = self.bot.session_manager.get_session(self.session_id)

        if not session or not session.get('join_message_id'):
            return

        try:
            # Get the original message
            channel = interaction.guild.get_channel(session['join_message_channel_id'])
            if not channel:
                return

            message = await channel.fetch_message(session['join_message_id'])

            # Get current participants
            participants = self.bot.session_manager.get_session_participants(self.session_id)
            participant_list = "\n".join([f"• <@{uid}>" for uid in participants])

            # Get location info
            admin_location = session.get('current_location_id')
            location_name = None
            if admin_location:
                location_name = self.bot.location_manager.get_location_name(admin_location)

            # Recreate embed with updated participant count
            embed = discord.Embed(
                title=f"📢 Session Started: {session['session_name']}",
                description=(
                    f"**Session Leader:** <@{session['admin_id']}>\n\n"
                    f"A new session has started! Click the button below to join.\n\n"
                    f"**What happens when you join:**\n"
                    f"• You'll enter session state\n"
                    f"• You can't travel or battle on your own\n"
                    f"• Your location moves with the session group\n"
                    f"• The admin controls encounters, rewards, and movement"
                ),
                color=discord.Color.blue()
            )

            if admin_location:
                embed.add_field(
                    name="Current Location",
                    value=location_name or admin_location,
                    inline=False
                )

            # Add participants field
            embed.add_field(
                name=f"Participants ({len(participants)})",
                value=participant_list if participants else "No participants yet",
                inline=False
            )

            await message.edit(embed=embed)
        except Exception as e:
            # Silently fail if we can't update the message
            print(f"Failed to update join embed: {e}")


class MoveLocationSelect(discord.ui.Select):
    """Select menu for choosing a location to move to"""

    def __init__(self, bot, session_id: str):
        self.bot = bot
        self.session_id = session_id

        # Get all locations
        locations = self.bot.location_manager.locations

        # Create options (max 25 for Discord)
        options = []
        for loc_id, loc_data in list(locations.items())[:25]:
            label = loc_data.get('name', loc_id.replace('_', ' ').title())[:100]
            description = loc_data.get('description', '')[:100]
            options.append(
                discord.SelectOption(
                    label=label,
                    value=loc_id,
                    description=description
                )
            )

        super().__init__(
            placeholder="Choose a location to travel to...",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle location selection"""
        location_id = self.values[0]
        location_data = self.bot.location_manager.get_location(location_id)

        if not location_data:
            await interaction.response.send_message(
                "❌ Invalid location selected.",
                ephemeral=True
            )
            return

        # Get stamina cost (default to 1 if location doesn't specify)
        stamina_cost = location_data.get('travel_cost', 1)
        location_name = location_data.get('name', location_id.replace('_', ' ').title())

        # Move session
        success, message = self.bot.session_manager.move_session_to_location(
            self.session_id, location_id, stamina_cost
        )

        if success:
            # Get participants for announcement
            participants = self.bot.session_manager.get_session_participants(self.session_id)
            participant_mentions = " ".join([f"<@{uid}>" for uid in participants])

            await interaction.response.send_message(
                f"✅ Session moved to **{location_name}**!\n{message}\n\n{participant_mentions}",
                allowed_mentions=discord.AllowedMentions(users=True)
            )
        else:
            await interaction.response.send_message(
                f"❌ {message}",
                ephemeral=True
            )


class MoveLocationView(discord.ui.View):
    """View for moving the session to a new location"""

    def __init__(self, bot, session_id: str):
        super().__init__(timeout=180)
        self.add_item(MoveLocationSelect(bot, session_id))


class StaminaControlModal(discord.ui.Modal, title="Adjust Stamina"):
    """Modal for adjusting participant stamina"""

    amount = discord.ui.TextInput(
        label="Amount",
        placeholder="Enter stamina amount (positive to add, negative to remove)",
        required=True
    )

    def __init__(self, bot, session_id: str, target_user_id: Optional[int] = None, restore_to_max: bool = False):
        super().__init__()
        self.bot = bot
        self.session_id = session_id
        self.target_user_id = target_user_id
        self.restore_to_max = restore_to_max

    async def on_submit(self, interaction: discord.Interaction):
        """Handle stamina adjustment"""
        try:
            amount = int(self.amount.value)
        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid number!",
                ephemeral=True
            )
            return

        participants = self.bot.session_manager.get_session_participants(self.session_id)

        if self.target_user_id:
            # Single target
            if self.target_user_id not in participants:
                await interaction.response.send_message(
                    "❌ That user is not in the session!",
                    ephemeral=True
                )
                return

            success, new_stamina = self.bot.session_manager.adjust_participant_stamina(
                self.target_user_id, amount
            )

            if success:
                await interaction.response.send_message(
                    f"✅ Adjusted <@{self.target_user_id}>'s stamina by {amount:+d}. New stamina: {new_stamina}",
                    allowed_mentions=discord.AllowedMentions.none()
                )
            else:
                await interaction.response.send_message(
                    "❌ Failed to adjust stamina.",
                    ephemeral=True
                )
        else:
            # All participants
            results = []
            for user_id in participants:
                success, new_stamina = self.bot.session_manager.adjust_participant_stamina(
                    user_id, amount
                )
                if success:
                    results.append(f"<@{user_id}>: {new_stamina}")

            if results:
                await interaction.response.send_message(
                    f"✅ Adjusted stamina by {amount:+d} for all participants:\n" + "\n".join(results),
                    allowed_mentions=discord.AllowedMentions.none()
                )
            else:
                await interaction.response.send_message(
                    "❌ Failed to adjust stamina.",
                    ephemeral=True
                )


class StaminaControlView(discord.ui.View):
    """View for stamina control options"""

    def __init__(self, bot, session_id: str):
        super().__init__(timeout=180)
        self.bot = bot
        self.session_id = session_id

    @discord.ui.button(label="Adjust All", style=discord.ButtonStyle.primary)
    async def adjust_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Adjust stamina for all participants"""
        await interaction.response.send_modal(
            StaminaControlModal(self.bot, self.session_id, target_user_id=None)
        )

    @discord.ui.button(label="Restore All to Max", style=discord.ButtonStyle.success)
    async def restore_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Restore all participants to max stamina"""
        participants = self.bot.session_manager.get_session_participants(self.session_id)

        results = []
        for user_id in participants:
            success, new_stamina = self.bot.session_manager.restore_participant_stamina(user_id)
            if success:
                results.append(f"<@{user_id}>: {new_stamina}")

        if results:
            await interaction.response.send_message(
                "✅ Restored all participants to max stamina:\n" + "\n".join(results),
                allowed_mentions=discord.AllowedMentions.none()
            )
        else:
            await interaction.response.send_message(
                "❌ Failed to restore stamina.",
                ephemeral=True
            )


class EncounterConfigModal(discord.ui.Modal, title="Create Encounter"):
    """Modal for configuring a custom encounter"""

    showdown_text = discord.ui.TextInput(
        label="Pokemon (Showdown Format)",
        placeholder="e.g., Pikachu @ Light Ball\nLevel: 50\n- Thunderbolt\n- Quick Attack",
        style=discord.TextStyle.paragraph,
        required=True
    )

    num_enemies = discord.ui.TextInput(
        label="Number of Enemies",
        placeholder="1",
        default="1",
        required=True
    )

    def __init__(self, bot, session_id: str):
        super().__init__()
        self.bot = bot
        self.session_id = session_id

    async def on_submit(self, interaction: discord.Interaction):
        """Handle encounter creation"""
        await interaction.response.defer(ephemeral=True)

        try:
            num_enemies = int(self.num_enemies.value)
            if num_enemies < 1:
                raise ValueError("Must have at least 1 enemy")
        except ValueError as e:
            await interaction.followup.send(
                f"❌ Invalid number of enemies: {e}",
                ephemeral=True
            )
            return

        # Store the encounter config in the bot for the next step (participant selection)
        if not hasattr(self.bot, '_pending_encounters'):
            self.bot._pending_encounters = {}

        self.bot._pending_encounters[interaction.user.id] = {
            'session_id': self.session_id,
            'showdown_text': self.showdown_text.value,
            'num_enemies': num_enemies
        }

        # Show participant selection view
        participants = self.bot.session_manager.get_session_participants(self.session_id)
        view = EncounterParticipantView(self.bot, self.session_id, participants)

        await interaction.followup.send(
            "✅ Encounter configured! Now select who will face this encounter:",
            view=view,
            ephemeral=True
        )


class BattleFormatSelect(discord.ui.Select):
    """Select menu for battle format"""

    def __init__(self):
        options = [
            discord.SelectOption(label="Singles", value="singles", emoji="1️⃣"),
            discord.SelectOption(label="Doubles", value="doubles", emoji="2️⃣"),
            discord.SelectOption(label="Multi", value="multi", emoji="👥"),
        ]

        super().__init__(
            placeholder="Choose battle format...",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle format selection"""
        # Store selection in the view
        self.view.selected_format = self.values[0]
        await interaction.response.send_message(
            f"✅ Selected format: **{self.values[0].title()}**",
            ephemeral=True
        )


class ParticipantSelect(discord.ui.UserSelect):
    """Select menu for choosing individual participants"""

    def __init__(self):
        super().__init__(
            placeholder="Select individual participants...",
            min_values=1,
            max_values=25,  # Discord's max
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle participant selection"""
        # Store selected users in the view
        self.view.selected_participants = [user.id for user in self.values]
        await interaction.response.send_message(
            f"✅ Selected {len(self.values)} participant(s)! Click 'Start Selected' to create their encounters.",
            ephemeral=True
        )


class EncounterParticipantView(discord.ui.View):
    """View for selecting participants for an encounter"""

    def __init__(self, bot, session_id: str, participants: List[int]):
        super().__init__(timeout=180)
        self.bot = bot
        self.session_id = session_id
        self.participants = participants
        self.selected_format = "singles"
        self.selected_participants = []

        # Add format selector
        self.add_item(BattleFormatSelect())

        # Add participant selector
        self.add_item(ParticipantSelect())

    @discord.ui.button(label="Everyone", style=discord.ButtonStyle.primary, row=2)
    async def everyone_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Give encounter to everyone"""
        await self._create_encounters(interaction, self.participants)

    @discord.ui.button(label="Start Selected", style=discord.ButtonStyle.success, row=2)
    async def selected_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Give encounter to selected participants"""
        if not self.selected_participants:
            await interaction.response.send_message(
                "❌ Please select participants first using the dropdown menu!",
                ephemeral=True
            )
            return

        # Filter to only participants actually in the session
        valid_participants = [uid for uid in self.selected_participants if uid in self.participants]

        if not valid_participants:
            await interaction.response.send_message(
                "❌ None of the selected users are in this session!",
                ephemeral=True
            )
            return

        await self._create_encounters(interaction, valid_participants)

    async def _start_session_battle(
        self,
        thread: discord.Thread,
        user_id: int,
        pokemon_entries: List[dict],
        num_enemies: int,
        battle_format: str
    ):
        """Start a battle for a session participant"""
        from battle_engine_v2 import BattleType, BattleFormat
        from models import Pokemon

        # Get battle cog
        battle_cog = self.bot.get_cog('BattleCog')
        if not battle_cog:
            raise Exception("Battle system not loaded")

        # Check if user is already in battle
        if user_id in battle_cog.user_battles:
            raise Exception("Already in a battle")

        # Get player's party
        party_data = self.bot.player_manager.db.get_trainer_party(user_id)
        if not party_data:
            raise Exception("No Pokemon in party")

        trainer_pokemon = []
        for poke_data in party_data:
            species_data = self.bot.species_db.get_species(poke_data['species_dex_number'])
            if not species_data:
                continue

            # Reconstruct Pokemon from data
            from ui.buttons import reconstruct_pokemon_from_data
            pokemon = reconstruct_pokemon_from_data(poke_data, species_data)
            trainer_pokemon.append(pokemon)

        if not trainer_pokemon:
            raise Exception("No valid Pokemon in party")

        # Create opponent Pokemon (exactly like admin_cog does)
        opponent_pokemon = []
        for pokemon_data in pokemon_entries:
            # Get species data
            species_name = pokemon_data.get('species', 'Pikachu')
            species_data = self.bot.species_db.get_species(species_name)
            if not species_data:
                continue

            # Create Pokemon with exact same signature as admin_cog
            pokemon = Pokemon(
                species_data=species_data,
                level=pokemon_data.get('level', 5),
                owner_discord_id=None,  # Wild Pokemon have no owner
                nature=pokemon_data.get('nature', 'hardy'),
                ability=pokemon_data.get('ability'),
                moves=pokemon_data.get('moves'),
                ivs=pokemon_data.get('ivs'),
                is_shiny=pokemon_data.get('shiny', False),
                gender=pokemon_data.get('gender'),
                pokeball=pokemon_data.get('pokeball', 'poke_ball')
            )

            # Set EVs after creation (like admin_cog does)
            if pokemon_data.get('evs'):
                pokemon.evs = pokemon_data['evs']

            # Set held item after creation
            if pokemon_data.get('held_item'):
                pokemon.held_item = pokemon_data['held_item']

            # Recalculate stats with EVs (CRITICAL - matches admin_cog)
            pokemon._calculate_stats()
            pokemon.current_hp = pokemon.max_hp

            opponent_pokemon.append(pokemon)

        if not opponent_pokemon:
            raise Exception("Failed to create opponent Pokemon")

        # Determine battle format
        if battle_format.lower() == "doubles":
            format_enum = BattleFormat.DOUBLES
        elif battle_format.lower() == "multi":
            format_enum = BattleFormat.MULTI
        else:
            format_enum = BattleFormat.SINGLES

        # Get user object
        user = thread.guild.get_member(user_id)
        if not user:
            raise Exception("User not found")

        # Create opponent name based on Pokemon
        if len(opponent_pokemon) == 1:
            opponent_name = f"{opponent_pokemon[0].species_name}"
        else:
            opponent_name = f"{opponent_pokemon[0].species_name}"  # Show first Pokemon name

        # Start trainer battle with wild-style setup
        battle_id = battle_cog.battle_engine.start_trainer_battle(
            trainer_id=user_id,
            trainer_name=user.display_name,
            trainer_party=trainer_pokemon,
            npc_party=opponent_pokemon,
            npc_name=opponent_name,  # Just the Pokemon name, not "Session Encounter"
            npc_class="wild_pokemon",
            prize_money=0,
            battle_format=format_enum
        )

        # Create a mock interaction for the thread
        class MockInteraction:
            def __init__(self, thread, user, guild):
                self.channel = thread
                self.user = user
                self.guild = guild
                self._response_done = False

            @property
            def response(self):
                class Response:
                    def __init__(self, parent):
                        self.parent = parent

                    async def defer(self):
                        self.parent._response_done = True

                    def is_done(self):
                        return self.parent._response_done

                return Response(self)

            @property
            def followup(self):
                class Followup:
                    def __init__(self, parent):
                        self.parent = parent

                    async def send(self, *args, **kwargs):
                        return await self.parent.channel.send(*args, **kwargs)

                return Followup(self)

        mock_interaction = MockInteraction(thread, user, thread.guild)

        # Send initial message (skip "ready/prepare" - let wild encounter message handle it)

        # Start battle UI in the thread - use WILD type for wild-style encounter
        await battle_cog.prompt_and_start_battle_ui(
            interaction=mock_interaction,
            battle_id=battle_id,
            battle_type=BattleType.WILD  # Changed to WILD for wild-style encounter
        )

    async def _create_encounters(self, interaction: discord.Interaction, target_users: List[int]):
        """Create encounters for the specified users"""
        if interaction.user.id not in self.bot._pending_encounters:
            await interaction.response.send_message(
                "❌ Encounter configuration not found. Please start over.",
                ephemeral=True
            )
            return

        config = self.bot._pending_encounters[interaction.user.id]
        showdown_text = config['showdown_text']
        num_enemies = config['num_enemies']

        await interaction.response.defer()

        # Parse showdown format (reuse parsing logic from admin_cog)
        from cogs.admin_cog import AdminCog
        admin_cog = self.bot.get_cog('AdminCog')

        if not admin_cog:
            await interaction.followup.send(
                "❌ Admin cog not found. Cannot parse Pokemon.",
                ephemeral=True
            )
            return

        try:
            pokemon_entries = admin_cog.parse_showdown_import(showdown_text)
        except Exception as e:
            await interaction.followup.send(
                f"❌ Failed to parse Pokemon: {e}",
                ephemeral=True
            )
            return

        # Create threads for each participant
        session = self.bot.session_manager.get_session(self.session_id)
        channel = interaction.guild.get_channel(session['channel_id'])

        if not channel or not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(
                "❌ Session channel not found or invalid.",
                ephemeral=True
            )
            return

        # Group participants for multi battles if needed
        if self.selected_format == "multi":
            # For multi battles, pair up participants
            # For simplicity, we'll create individual threads but note it's a multi battle
            pass

        created_threads = []

        for user_id in target_users:
            user = interaction.guild.get_member(user_id)
            if not user:
                continue

            # Create thread for this participant
            thread_name = f"Encounter - {user.display_name}"
            thread = await channel.create_thread(
                name=thread_name,
                auto_archive_duration=60,
                reason=f"Session encounter created by {interaction.user.display_name}"
            )

            # Start the battle automatically
            try:
                await self._start_session_battle(
                    thread=thread,
                    user_id=user_id,
                    pokemon_entries=pokemon_entries,
                    num_enemies=num_enemies,
                    battle_format=self.selected_format
                )
                created_threads.append(thread.mention)
            except Exception as e:
                # If battle start fails, send error message
                await thread.send(
                    f"<@{user_id}> ❌ Failed to start battle: {e}",
                    allowed_mentions=discord.AllowedMentions(users=True)
                )
                print(f"Failed to start session battle: {e}")

        # Clean up pending encounter
        del self.bot._pending_encounters[interaction.user.id]

        if created_threads:
            await interaction.followup.send(
                f"✅ Created {len(created_threads)} encounter thread(s):\n" + "\n".join(created_threads)
            )
        else:
            await interaction.followup.send(
                "❌ No encounters created. Check that participants are valid.",
                ephemeral=True
            )


class RewardModal(discord.ui.Modal, title="Give Rewards"):
    """Modal for giving rewards to participants"""

    money = discord.ui.TextInput(
        label="Money",
        placeholder="Amount of money to give (optional)",
        required=False
    )

    items = discord.ui.TextInput(
        label="Items",
        placeholder="item_id:quantity, item_id:quantity (optional)",
        style=discord.TextStyle.paragraph,
        required=False
    )

    def __init__(self, bot, session_id: str, target_users: Optional[List[int]] = None):
        super().__init__()
        self.bot = bot
        self.session_id = session_id
        self.target_users = target_users

    async def on_submit(self, interaction: discord.Interaction):
        """Handle reward distribution"""
        await interaction.response.defer()

        participants = self.target_users or self.bot.session_manager.get_session_participants(self.session_id)

        results = []

        # Parse money
        money_amount = 0
        if self.money.value:
            try:
                money_amount = int(self.money.value)
            except ValueError:
                await interaction.followup.send(
                    "❌ Invalid money amount!",
                    ephemeral=True
                )
                return

        # Parse items
        items_to_give = []
        if self.items.value:
            try:
                for item_str in self.items.value.split(','):
                    item_str = item_str.strip()
                    if ':' in item_str:
                        item_id, quantity = item_str.split(':', 1)
                        items_to_give.append((item_id.strip(), int(quantity.strip())))
                    else:
                        items_to_give.append((item_str, 1))
            except Exception as e:
                await interaction.followup.send(
                    f"❌ Invalid item format: {e}",
                    ephemeral=True
                )
                return

        # Give rewards
        for user_id in participants:
            user_results = []

            # Give money
            if money_amount > 0:
                trainer = self.bot.player_manager.get_player(user_id)
                if trainer:
                    new_money = trainer.money + money_amount
                    self.bot.player_manager.db.update_trainer(user_id, money=new_money)
                    user_results.append(f"+${money_amount}")

            # Give items
            for item_id, quantity in items_to_give:
                self.bot.player_manager.db.add_item_to_inventory(user_id, item_id, quantity)
                user_results.append(f"+{quantity}x {item_id}")

            if user_results:
                results.append(f"<@{user_id}>: {', '.join(user_results)}")

        if results:
            await interaction.followup.send(
                "✅ Rewards distributed:\n" + "\n".join(results),
                allowed_mentions=discord.AllowedMentions.none()
            )
        else:
            await interaction.followup.send(
                "ℹ️ No rewards given (nothing was specified).",
                ephemeral=True
            )


class RewardTargetView(discord.ui.View):
    """View for selecting reward targets"""

    def __init__(self, bot, session_id: str):
        super().__init__(timeout=180)
        self.bot = bot
        self.session_id = session_id

    @discord.ui.button(label="Everyone", style=discord.ButtonStyle.primary)
    async def everyone_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Give rewards to everyone"""
        await interaction.response.send_modal(
            RewardModal(self.bot, self.session_id, target_users=None)
        )


class SessionControlsView(discord.ui.View):
    """Main session controls view with all management buttons"""

    def __init__(self, bot, session_id: str):
        super().__init__(timeout=300)
        self.bot = bot
        self.session_id = session_id

    @discord.ui.button(label="Move", style=discord.ButtonStyle.primary, emoji="🗺️", row=0)
    async def move_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open move location menu"""
        view = MoveLocationView(self.bot, self.session_id)
        await interaction.response.send_message(
            "Select a location to move the session to:",
            view=view,
            ephemeral=True
        )

    @discord.ui.button(label="Stamina", style=discord.ButtonStyle.primary, emoji="⚡", row=0)
    async def stamina_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open stamina control menu"""
        view = StaminaControlView(self.bot, self.session_id)
        await interaction.response.send_message(
            "Select stamina control option:",
            view=view,
            ephemeral=True
        )

    @discord.ui.button(label="Encounter", style=discord.ButtonStyle.primary, emoji="⚔️", row=0)
    async def encounter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open encounter creation modal"""
        await interaction.response.send_modal(
            EncounterConfigModal(self.bot, self.session_id)
        )

    @discord.ui.button(label="Reward", style=discord.ButtonStyle.success, emoji="🎁", row=1)
    async def reward_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open reward menu"""
        view = RewardTargetView(self.bot, self.session_id)
        await interaction.response.send_message(
            "Who should receive rewards?",
            view=view,
            ephemeral=True
        )

    @discord.ui.button(label="Dive", style=discord.ButtonStyle.primary, emoji="🌀", row=0)
    async def dive_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Start Dream Rogue dive"""
        from ui.dream_rogue_views import FloorSelectModal

        # Show floor selection modal
        modal = FloorSelectModal(self._on_floor_selected)
        modal.interaction = interaction  # Store for callback
        await interaction.response.send_modal(modal)

    async def _on_floor_selected(self, interaction: discord.Interaction, floor: int):
        """Handle floor selection and start dive"""
        dream_cog = self.bot.get_cog("DreamRogueCog")

        if not dream_cog:
            await interaction.response.send_message(
                "❌ Dream Rogue system not available!",
                ephemeral=True
            )
            return

        # Start dive from session
        await dream_cog.start_dive_from_session(interaction, floor)

    @discord.ui.button(label="End Session", style=discord.ButtonStyle.danger, emoji="🛑", row=1)
    async def end_session_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """End the session"""
        session = self.bot.session_manager.get_session(self.session_id)
        participants = self.bot.session_manager.get_session_participants(self.session_id)

        success = self.bot.session_manager.end_session(self.session_id)

        if success:
            participant_mentions = " ".join([f"<@{uid}>" for uid in participants])

            await interaction.response.send_message(
                f"✅ Session **{session['session_name']}** has ended!\n\n"
                f"{participant_mentions} You're no longer in session state.",
                allowed_mentions=discord.AllowedMentions(users=True)
            )

            # Disable all buttons
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(view=self)
        else:
            await interaction.response.send_message(
                "❌ Failed to end session.",
                ephemeral=True
            )


class SessionCog(commands.Cog):
    """Admin-led group session commands"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="start_session", description="[ADMIN] Start a new group session")
    @app_commands.describe(
        session_name="Name for this session"
    )
    @app_commands.check(is_admin)
    async def start_session(
        self,
        interaction: discord.Interaction,
        session_name: str
    ):
        """Start a new session"""

        # Check if there's already an active session in this guild
        existing_session = self.bot.session_manager.get_active_session_by_guild(interaction.guild_id)

        if existing_session:
            await interaction.response.send_message(
                f"❌ There's already an active session in this server: **{existing_session['session_name']}**\n"
                f"End that session first with `/session_controls`.",
                ephemeral=True
            )
            return

        # Get current location from admin's player data
        admin_location = None
        if self.bot.player_manager.player_exists(interaction.user.id):
            admin = self.bot.player_manager.get_player(interaction.user.id)
            admin_location = admin.current_location_id

        # Create session
        session_id = self.bot.session_manager.create_session(
            guild_id=interaction.guild_id,
            admin_id=interaction.user.id,
            session_name=session_name,
            channel_id=interaction.channel_id,
            current_location_id=admin_location
        )

        if not session_id:
            await interaction.response.send_message(
                "❌ Failed to create session. Please try again.",
                ephemeral=True
            )
            return

        # Create join embed
        embed = discord.Embed(
            title=f"📢 Session Started: {session_name}",
            description=(
                f"**Session Leader:** {interaction.user.mention}\n\n"
                f"A new session has started! Click the button below to join.\n\n"
                f"**What happens when you join:**\n"
                f"• You'll enter session state\n"
                f"• You can't travel or battle on your own\n"
                f"• Your location moves with the session group\n"
                f"• The admin controls encounters, rewards, and movement"
            ),
            color=discord.Color.blue()
        )

        if admin_location:
            location_name = self.bot.location_manager.get_location_name(admin_location)
            embed.add_field(
                name="Current Location",
                value=location_name or admin_location,
                inline=False
            )

        # Create join view
        view = JoinSessionView(self.bot, session_id)

        await interaction.response.send_message(
            embed=embed,
            view=view
        )

        # Store the message ID for later updates
        message = await interaction.original_response()
        self.bot.session_manager.set_join_message(session_id, message.id, interaction.channel_id)

        # Send controls to admin
        await interaction.followup.send(
            f"✅ Session created! Use `/session_controls` to manage the session.",
            ephemeral=True
        )

    @app_commands.command(name="session_controls", description="[ADMIN] Open session control panel")
    @app_commands.check(is_admin)
    async def session_controls(self, interaction: discord.Interaction):
        """Open session controls"""

        # Get active session for this guild
        session = self.bot.session_manager.get_active_session_by_guild(interaction.guild_id)

        if not session:
            await interaction.response.send_message(
                "❌ No active session found in this server. Start one with `/start_session`.",
                ephemeral=True
            )
            return

        # Get session info
        participants = self.bot.session_manager.get_session_participants(session['session_id'])
        location_name = "Unknown"
        if session['current_location_id']:
            location_name = self.bot.location_manager.get_location_name(session['current_location_id']) or session['current_location_id']

        # Create control panel embed
        embed = discord.Embed(
            title=f"🎮 Session Controls: {session['session_name']}",
            description=(
                f"**Participants:** {len(participants)}\n"
                f"**Current Location:** {location_name}\n\n"
                f"Use the buttons below to control the session:"
            ),
            color=discord.Color.gold()
        )

        embed.add_field(
            name="🗺️ Move",
            value="Travel the group to a new location",
            inline=True
        )

        embed.add_field(
            name="⚡ Stamina",
            value="Adjust participant stamina",
            inline=True
        )

        embed.add_field(
            name="⚔️ Encounter",
            value="Create custom encounters",
            inline=True
        )

        embed.add_field(
            name="🎁 Reward",
            value="Give rewards to participants",
            inline=True
        )

        embed.add_field(
            name="🛑 End Session",
            value="End the session and release participants",
            inline=True
        )

        # Create controls view
        view = SessionControlsView(self.bot, session['session_id'])

        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True
        )

    @app_commands.command(name="leave_session", description="Leave the current session")
    async def leave_session(self, interaction: discord.Interaction):
        """Leave current session"""

        if not self.bot.session_manager.is_in_session(interaction.user.id):
            await interaction.response.send_message(
                "❌ You're not in a session!",
                ephemeral=True
            )
            return

        session = self.bot.session_manager.get_player_session(interaction.user.id)

        success = self.bot.session_manager.remove_participant(interaction.user.id)

        if success:
            await interaction.response.send_message(
                f"✅ You've left the session **{session['session_name']}**.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Failed to leave session.",
                ephemeral=True
            )


async def setup(bot):
    """Setup function for loading the cog"""
    await bot.add_cog(SessionCog(bot))
