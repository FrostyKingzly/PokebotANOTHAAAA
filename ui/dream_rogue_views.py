"""
Dream Rogue UI Views

Discord UI components (buttons, modals, selects) for Dream Rogue gamemode
"""

import discord
from discord.ui import Button, View, Select, Modal, TextInput
from typing import Optional, List, Dict, Any, Callable
import asyncio


class DiveStartView(View):
    """View for starting a Dream Rogue dive"""

    def __init__(self, bot, run_id: str, initiator_id: int, callback):
        super().__init__(timeout=300)
        self.bot = bot
        self.run_id = run_id
        self.initiator_id = initiator_id
        self.callback = callback

    @discord.ui.button(label="Join Dive", style=discord.ButtonStyle.primary, emoji="🌀")
    async def join_button(self, interaction: discord.Interaction, button: Button):
        """Join the dive"""
        from dream_rogue_manager import DreamRogueManager

        manager = DreamRogueManager()

        # Try to add participant
        success = manager.add_participant(self.run_id, interaction.user.id)

        if success:
            await interaction.response.send_message(
                f"✅ You've joined the dive into the dream world!",
                ephemeral=True
            )
            # Update main embed to show new participant
            if self.callback:
                await self.callback(interaction)
        else:
            await interaction.response.send_message(
                "❌ You're already in this dive!",
                ephemeral=True
            )

    @discord.ui.button(label="Start Dive", style=discord.ButtonStyle.success, emoji="▶️")
    async def start_button(self, interaction: discord.Interaction, button: Button):
        """Start the dive (initiator only)"""
        if interaction.user.id != self.initiator_id:
            await interaction.response.send_message(
                "❌ Only the dive initiator can start!",
                ephemeral=True
            )
            return

        from dream_rogue_manager import DreamRogueManager

        manager = DreamRogueManager()
        participants = manager.get_participants(self.run_id)

        if len(participants) == 0:
            await interaction.response.send_message(
                "❌ Need at least one participant to start!",
                ephemeral=True
            )
            return

        # Disable this view
        self.stop()

        # Start the dive
        if self.callback:
            await self.callback(interaction, start=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        """Cancel the dive"""
        if interaction.user.id != self.initiator_id:
            await interaction.response.send_message(
                "❌ Only the dive initiator can cancel!",
                ephemeral=True
            )
            return

        from dream_rogue_manager import DreamRogueManager

        manager = DreamRogueManager()
        manager.end_run(self.run_id, extracted=False)

        self.stop()

        await interaction.response.edit_message(
            content="❌ Dive cancelled.",
            embed=None,
            view=None
        )


class FloorNavigationView(View):
    """View for navigating floor instances"""

    def __init__(self, bot, run_id: str, instances: List[Dict], on_select_callback):
        super().__init__(timeout=600)  # 10 minute timeout
        self.bot = bot
        self.run_id = run_id
        self.instances = instances
        self.on_select_callback = on_select_callback
        self.current_index = 0

        # Add instance selection dropdown if multiple instances
        if len(instances) > 1:
            options = []
            for idx, instance in enumerate(instances[:25]):  # Discord limit
                name = instance.get("name", f"Instance {idx + 1}")
                categories = instance.get("categories", [])
                emoji = self._get_instance_emoji(categories)

                description = instance.get("description", "")[:100]  # Limit length

                options.append(discord.SelectOption(
                    label=name,
                    value=str(idx),
                    description=description,
                    emoji=emoji
                ))

            select = Select(
                placeholder="Choose an instance...",
                options=options,
                row=0
            )
            select.callback = self._on_instance_select
            self.add_item(select)

    def _get_instance_emoji(self, categories: List[str]) -> str:
        """Get emoji for instance based on categories"""
        if "battle" in categories or "boss" in categories:
            return "⚔️"
        elif "rest" in categories:
            return "🛌"
        elif "buff" in categories:
            return "✨"
        elif "curse" in categories or "nightmare" in categories:
            return "👁️"
        elif "economy" in categories or "reward" in categories:
            return "💎"
        elif "gambling" in categories:
            return "🎲"
        elif "domain" in categories:
            return "🌌"
        else:
            return "❓"

    async def _on_instance_select(self, interaction: discord.Interaction):
        """Handle instance selection"""
        selected_index = int(interaction.values[0])
        self.current_index = selected_index

        if self.on_select_callback:
            await self.on_select_callback(interaction, self.instances[selected_index])

    @discord.ui.button(label="View Active Effects", style=discord.ButtonStyle.secondary, emoji="✨", row=1)
    async def view_buffs_button(self, interaction: discord.Interaction, button: Button):
        """View active buffs/curses"""
        from dream_rogue_manager import DreamRogueManager
        from ui.dream_rogue_embeds import DreamRogueEmbeds

        manager = DreamRogueManager()
        buffs = manager.get_active_buffs(self.run_id, interaction.user.id)

        embed = DreamRogueEmbeds.active_buffs(buffs, interaction.user.display_name)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Extract", style=discord.ButtonStyle.danger, emoji="🚪", row=1)
    async def extract_button(self, interaction: discord.Interaction, button: Button):
        """Extract from the dream (team vote)"""
        await interaction.response.send_message(
            "⚠️ Extraction requires team agreement. Starting vote...",
            ephemeral=True
        )

        # Create extraction vote
        from dream_rogue_manager import DreamRogueManager

        manager = DreamRogueManager()
        vote_id = manager.create_vote(
            self.run_id,
            "Extract from the dream now?",
            [
                {"name": "Extract Now", "description": "Leave and save progress"},
                {"name": "Continue", "description": "Keep going deeper"}
            ]
        )

        # Show vote
        vote = manager.get_vote(vote_id)
        percentages = manager.get_vote_percentages(vote_id)

        from ui.dream_rogue_embeds import DreamRogueEmbeds
        embed = DreamRogueEmbeds.voting(vote, percentages)

        view = VotingView(self.bot, vote_id, self.run_id, self._on_extraction_vote_complete)

        # Edit main message to show vote
        await interaction.followup.send(embed=embed, view=view)

    async def _on_extraction_vote_complete(self, interaction: discord.Interaction, extract: bool):
        """Handle extraction vote result"""
        if extract:
            # End run and show summary
            from dream_rogue_manager import DreamRogueManager
            from ui.dream_rogue_embeds import DreamRogueEmbeds

            manager = DreamRogueManager()
            run = manager.get_run(self.run_id)
            participants = manager.get_participants(self.run_id)

            total_dreamlites = sum(p["dreamlites"] for p in participants)

            manager.end_run(self.run_id, extracted=True)

            embed = DreamRogueEmbeds.extraction_summary(
                run, participants, run["current_floor"], total_dreamlites
            )

            await interaction.edit_original_response(embed=embed, view=None)
            self.stop()
        else:
            await interaction.followup.send("The team continues onward!", ephemeral=True)


class VotingView(View):
    """View for team voting"""

    def __init__(self, bot, vote_id: str, run_id: str, on_complete_callback=None):
        super().__init__(timeout=120)  # 2 minute timeout for votes
        self.bot = bot
        self.vote_id = vote_id
        self.run_id = run_id
        self.on_complete_callback = on_complete_callback

        from dream_rogue_manager import DreamRogueManager
        manager = DreamRogueManager()
        vote = manager.get_vote(vote_id)

        # Add button for each option
        for idx, option in enumerate(vote["vote_options"][:5]):  # Max 5 options
            button = Button(
                label=option["name"],
                style=discord.ButtonStyle.primary,
                custom_id=f"vote_{idx}",
                row=idx
            )
            button.callback = self._create_vote_callback(idx)
            self.add_item(button)

    def _create_vote_callback(self, option_index: int):
        """Create callback for vote button"""
        async def callback(interaction: discord.Interaction):
            from dream_rogue_manager import DreamRogueManager
            from ui.dream_rogue_embeds import DreamRogueEmbeds

            manager = DreamRogueManager()

            # Cast vote
            manager.cast_vote(self.vote_id, interaction.user.id, option_index)

            # Get updated percentages
            vote = manager.get_vote(self.vote_id)
            percentages = manager.get_vote_percentages(self.vote_id)

            # Update embed
            embed = DreamRogueEmbeds.voting(vote, percentages)

            await interaction.response.edit_message(embed=embed, view=self)

            # Send confirmation
            await interaction.followup.send(
                f"✅ Vote recorded for: **{vote['vote_options'][option_index]['name']}**",
                ephemeral=True
            )

        return callback

    @discord.ui.button(label="Resolve Vote", style=discord.ButtonStyle.success, emoji="✅", row=4)
    async def resolve_button(self, interaction: discord.Interaction, button: Button):
        """Resolve the vote"""
        from dream_rogue_manager import DreamRogueManager
        from ui.dream_rogue_embeds import DreamRogueEmbeds

        manager = DreamRogueManager()

        # Check if all participants voted
        participants = manager.get_participants(self.run_id)
        vote = manager.get_vote(self.vote_id)
        votes = vote["votes"]

        participant_ids = {str(p["discord_user_id"]) for p in participants}
        voted_ids = set(votes.keys())

        if not voted_ids:
            await interaction.response.send_message(
                "❌ No votes cast yet!",
                ephemeral=True
            )
            return

        # Resolve vote
        result_index = manager.resolve_vote(self.vote_id)

        # Show result
        vote = manager.get_vote(self.vote_id)
        embed = DreamRogueEmbeds.vote_result(vote, result_index)

        await interaction.response.edit_message(embed=embed, view=None)

        # Call completion callback
        if self.on_complete_callback:
            # Check if this was an extraction vote
            if "Extract" in vote["vote_options"][result_index]["name"]:
                await self.on_complete_callback(interaction, True)
            else:
                await self.on_complete_callback(interaction, result_index)

        self.stop()


class InstanceActionView(View):
    """View for instance-specific actions"""

    def __init__(self, bot, run_id: str, instance: Dict, on_complete_callback, origin_channel_id: Optional[int] = None):
        super().__init__(timeout=300)
        self.bot = bot
        self.run_id = run_id
        self.instance = instance
        self.on_complete_callback = on_complete_callback
        self.origin_channel_id = origin_channel_id
        self._pending_battles = set()

        categories = instance.get("categories", [])
        effect_data = instance.get("effect_data", {})

        # Add buttons based on instance type
        if "battle" in categories or "boss" in categories:
            self.add_item(Button(
                label="Start Battle",
                style=discord.ButtonStyle.danger,
                emoji="⚔️",
                custom_id="start_battle"
            ))
            self.children[0].callback = self._start_battle

        elif "rest" in categories:
            self.add_item(Button(
                label="Rest",
                style=discord.ButtonStyle.success,
                emoji="🛌",
                custom_id="rest"
            ))
            self.children[0].callback = self._rest

        elif "gambling" in categories or "trial" in categories:
            self.add_item(Button(
                label="Accept Challenge",
                style=discord.ButtonStyle.primary,
                emoji="🎲",
                custom_id="challenge"
            ))
            self.children[0].callback = self._challenge

        elif "reward" in categories or "economy" in categories:
            self.add_item(Button(
                label="Claim Reward",
                style=discord.ButtonStyle.success,
                emoji="🎁",
                custom_id="reward"
            ))
            self.children[0].callback = self._claim_reward
        else:
            # Fallback action for domains/buffs/curses/etc.
            self.add_item(Button(
                label="Proceed",
                style=discord.ButtonStyle.primary,
                emoji="➡️",
                custom_id="proceed",
                row=1
            ))
            self.children[-1].callback = self._proceed

    async def _start_battle(self, interaction: discord.Interaction):
        """Start a battle instance"""
        from dream_rogue_manager import DreamRogueManager
        from database import PlayerDatabase, SpeciesDatabase
        from models import Pokemon
        from battle_engine_v2 import BattleType, BattleFormat
        from ui.buttons import reconstruct_pokemon_from_data
        import random

        manager = DreamRogueManager()
        player_db = PlayerDatabase()
        species_db = getattr(self.bot, "species_db", SpeciesDatabase("data/pokemon_species.json"))

        battle_cog = self.bot.get_cog("BattleCog")
        if not battle_cog:
            await interaction.response.send_message("❌ Battle system unavailable!", ephemeral=True)
            return

        run = manager.get_run(self.run_id)
        floor = run["current_floor"]
        stage_level = run["stage_level"]
        min_lvl, max_lvl = manager.get_floor_level_range(stage_level, floor)

        categories = self.instance.get("categories", [])
        effect_data = self.instance.get("effect_data", {})
        battle_format_raw = effect_data.get("battle_format", "singles")
        num_opponents = max(1, int(effect_data.get("num_opponents", 1)))
        completion_result = "boss_defeated" if "boss" in categories else "battle_complete"

        if battle_format_raw == "doubles":
            battle_format = BattleFormat.DOUBLES
        elif battle_format_raw == "multi":
            battle_format = BattleFormat.MULTI
        else:
            battle_format = BattleFormat.SINGLES

        participants = manager.get_participants(self.run_id)
        if not participants:
            await interaction.response.send_message("❌ No participants found for this battle!", ephemeral=True)
            return

        if interaction.response.is_done():
            await interaction.followup.send("⚔️ Battle instance is starting for all participants...")
        else:
            await interaction.response.send_message("⚔️ Battle instance is starting for all participants...")

        parent_channel = interaction.channel
        if isinstance(parent_channel, discord.Thread) and parent_channel.parent:
            parent_channel = parent_channel.parent

        if not isinstance(parent_channel, discord.TextChannel):
            await interaction.followup.send("❌ Battles can only start in text channels.", ephemeral=True)
            return

        created_threads = []
        self._pending_battles = {p["discord_user_id"] for p in participants}

        def _create_wild_opponents():
            opponents = []
            all_species = species_db.get_all_species()
            non_legendary = [s for s in all_species if not s.get("is_legendary", False)]
            candidates = non_legendary or all_species
            for _ in range(num_opponents):
                species_data = random.choice(candidates)
                level = random.randint(min_lvl, max_lvl)
                if "boss" in categories:
                    level = max_lvl + 10
                opponents.append(Pokemon(
                    species_data=species_data,
                    level=level,
                    owner_discord_id=None
                ))
            return opponents

        for participant in participants:
            user_id = participant["discord_user_id"]
            user = interaction.guild.get_member(user_id)
            if not user:
                self._pending_battles.discard(user_id)
                continue

            if user_id in battle_cog.user_battles:
                self._pending_battles.discard(user_id)
                continue

            party_data = player_db.get_trainer_party(user_id)
            trainer_pokemon = []
            for poke_data in party_data:
                species_data = species_db.get_species(poke_data["species_dex_number"])
                if not species_data:
                    continue
                trainer_pokemon.append(reconstruct_pokemon_from_data(poke_data, species_data))

            if not trainer_pokemon:
                self._pending_battles.discard(user_id)
                continue

            opponent_pokemon = _create_wild_opponents()
            if not opponent_pokemon:
                self._pending_battles.discard(user_id)
                continue

            opponent_name = opponent_pokemon[0].species_name

            battle_id = battle_cog.battle_engine.start_trainer_battle(
                trainer_id=user_id,
                trainer_name=user.display_name,
                trainer_party=trainer_pokemon,
                npc_party=opponent_pokemon,
                npc_name=opponent_name,
                npc_class="dream_rogue",
                prize_money=0,
                battle_format=battle_format
            )

            thread_name = f"Dream Rogue - {user.display_name}"
            thread = await parent_channel.create_thread(
                name=thread_name,
                auto_archive_duration=60,
                reason=f"Dream Rogue battle for {user.display_name}"
            )

            class MockInteraction:
                def __init__(self, thread, user):
                    self.channel = thread
                    self.user = user
                    self.guild = thread.guild
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

            mock_interaction = MockInteraction(thread, user)

            await battle_cog.prompt_and_start_battle_ui(
                interaction=mock_interaction,
                battle_id=battle_id,
                battle_type=BattleType.WILD
            )

            if not hasattr(self.bot, "dream_rogue_battle_callbacks"):
                self.bot.dream_rogue_battle_callbacks = {}

            async def _battle_done_callback(battle, result, battle_interaction, participant_id=user_id):
                self._pending_battles.discard(participant_id)
                if not self._pending_battles and self.on_complete_callback:
                    await self.on_complete_callback(
                        self._create_channel_interaction(parent_channel),
                        completion_result
                    )

            self.bot.dream_rogue_battle_callbacks[battle_id] = _battle_done_callback
            created_threads.append(thread.mention)

        if created_threads:
            await interaction.followup.send(
                "✅ Battle threads created:\n" + "\n".join(created_threads)
            )
        else:
            await interaction.followup.send("❌ No battle threads could be created.")

        if not self._pending_battles and self.on_complete_callback:
            await self.on_complete_callback(
                self._create_channel_interaction(parent_channel),
                completion_result
            )

    def _create_channel_interaction(self, channel: discord.TextChannel):
        class ChannelInteraction:
            def __init__(self, target_channel):
                self.channel = target_channel
                self.guild = target_channel.guild
                self._response_done = True

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

        return ChannelInteraction(channel)

    async def _rest(self, interaction: discord.Interaction):
        """Rest and restore Pokemon"""
        from dream_rogue_manager import DreamRogueManager
        from database import PlayerDatabase

        manager = DreamRogueManager()
        player_db = PlayerDatabase()

        participants = manager.get_participants(self.run_id)

        # Restore all participants' Pokemon
        for p in participants:
            user_id = p["discord_user_id"]
            party = player_db.get_trainer_party(user_id)

            for pokemon in party:
                # Restore HP and PP
                player_db.update_pokemon(
                    pokemon["pokemon_id"],
                    {"current_hp": pokemon["max_hp"], "status_condition": None}
                )

                # Restore PP for all moves
                moves = pokemon.get("moves", [])
                for move in moves:
                    move["pp"] = move["max_pp"]

                player_db.update_pokemon_moves(pokemon["pokemon_id"], moves)

        await interaction.response.send_message(
            "🛌 Your team has rested. All Pokémon are fully restored!",
            ephemeral=False
        )

        if self.on_complete_callback:
            await self.on_complete_callback(interaction, "rested")

    async def _challenge(self, interaction: discord.Interaction):
        """Accept a challenge/trial/gambling instance"""
        # For now, placeholder
        await interaction.response.send_message(
            "🎲 Challenge accepted! (Implementation in progress)",
            ephemeral=False
        )

        if self.on_complete_callback:
            await self.on_complete_callback(interaction, "challenge_accepted")

    async def _claim_reward(self, interaction: discord.Interaction):
        """Claim a reward"""
        from dream_rogue_manager import DreamRogueManager
        import random

        manager = DreamRogueManager()

        # Generate reward
        dreamlites_gained = random.randint(50, 100)

        # Add to all participants
        participants = manager.get_participants(self.run_id)
        for p in participants:
            manager.add_dreamlites(self.run_id, p["discord_user_id"], dreamlites_gained)

        await interaction.response.send_message(
            f"🎁 Reward claimed! Everyone gains 💎 **{dreamlites_gained}** Dreamlites!",
            ephemeral=False
        )

        if self.on_complete_callback:
            await self.on_complete_callback(interaction, "reward_claimed")

    async def _proceed(self, interaction: discord.Interaction):
        """Proceed through non-interactive instances (domain/buff/curse/etc.)"""
        from dream_rogue_manager import DreamRogueManager

        manager = DreamRogueManager()
        categories = self.instance.get("categories", [])
        scope = self.instance.get("scope", "team")
        effect_data = self.instance.get("effect_data", {})
        duration = self.instance.get("duration", "floor")

        applied = None
        if "buff" in categories or "curse" in categories or "nightmare" in categories or "domain" in categories:
            buff_type = "buff"
            if "nightmare" in categories:
                buff_type = "nightmare"
            elif "curse" in categories:
                buff_type = "curse"
            elif "domain" in categories:
                buff_type = "domain"

            target_user_id = interaction.user.id if scope == "individual" else None

            manager.apply_buff(
                run_id=self.run_id,
                buff_type=buff_type,
                buff_name=self.instance.get("name", "Dream Effect"),
                buff_description=self.instance.get("description", "The dream shifts around you."),
                scope=scope,
                effect_data=effect_data,
                duration=duration,
                target_user_id=target_user_id
            )
            applied = self.instance.get("name", "Dream Effect")

        message = "✨ The dream reshapes itself around your party."
        if applied:
            message += f"\nApplied effect: **{applied}**"

        await interaction.response.send_message(message, ephemeral=False)

        if self.on_complete_callback:
            await self.on_complete_callback(interaction, "proceeded")


class StageSelectModal(Modal, title="Choose Dream Rogue Stage"):
    """Modal for selecting stage level"""

    stage_input = TextInput(
        label="Stage Level (10, 20, 30, 40, 50)",
        placeholder="Enter a stage level (e.g., 10 for Level 10 Stage)",
        style=discord.TextStyle.short,
        required=True,
        max_length=2
    )

    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    async def on_submit(self, interaction: discord.Interaction):
        try:
            stage_level = int(self.stage_input.value)

            # Validate stage level (must be multiple of 10, between 10 and 100)
            if stage_level < 10 or stage_level > 100 or stage_level % 10 != 0:
                await interaction.response.send_message(
                    "❌ Stage level must be 10, 20, 30, 40, 50, 60, 70, 80, 90, or 100!",
                    ephemeral=True
                )
                return

            # Call callback with stage level
            if self.callback:
                await self.callback(interaction, stage_level)

        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid number!",
                ephemeral=True
            )


# Keep FloorSelectModal for backwards compatibility but redirect to StageSelectModal
class FloorSelectModal(StageSelectModal):
    """Deprecated: Use StageSelectModal instead"""
    pass


class IndividualInstanceView(View):
    """View for individual instances - shows button to view privately"""

    def __init__(self, bot, run_id: str, instance: Dict, participant_ids: List[int], on_complete_callback):
        super().__init__(timeout=600)
        self.bot = bot
        self.run_id = run_id
        self.instance = instance
        self.participant_ids = participant_ids
        self.on_complete_callback = on_complete_callback
        self.completed_users = set()

    @discord.ui.button(label="View Instance", style=discord.ButtonStyle.primary, emoji="👁️")
    async def view_instance_button(self, interaction: discord.Interaction, button: Button):
        """Show instance details to user ephemerally"""
        # Check if user is a participant
        if interaction.user.id not in self.participant_ids:
            await interaction.response.send_message(
                "❌ You're not a participant in this dive!",
                ephemeral=True
            )
            return

        # Check if already completed
        if interaction.user.id in self.completed_users:
            await interaction.response.send_message(
                "✅ You've already completed this instance!",
                ephemeral=True
            )
            return

        # Show instance details ephemerally
        from ui.dream_rogue_embeds import DreamRogueEmbeds
        from dream_rogue_manager import DreamRogueManager

        manager = DreamRogueManager()
        run = manager.get_run(self.run_id)
        floor = run["current_floor"]

        embed = DreamRogueEmbeds.instance_selection(self.instance, floor)

        # Create instance action view for this user
        instance_view = InstanceActionView(
            self.bot,
            self.run_id,
            self.instance,
            self._create_completion_callback(interaction.user.id),
            origin_channel_id=interaction.channel.id
        )

        await interaction.response.send_message(
            embed=embed,
            view=instance_view,
            ephemeral=True
        )

    def _create_completion_callback(self, user_id: int):
        """Create a completion callback for a specific user"""
        async def callback(interaction: discord.Interaction, result: str):
            # Mark user as completed
            self.completed_users.add(user_id)

            # Check if all participants have completed
            if len(self.completed_users) >= len(self.participant_ids):
                # All done, proceed with callback
                if self.on_complete_callback:
                    await self.on_complete_callback(interaction, result)
            else:
                # Still waiting on others
                await interaction.followup.send(
                    f"✅ Choice recorded! Waiting for {len(self.participant_ids) - len(self.completed_users)} more participants...",
                    ephemeral=True
                )

        return callback
