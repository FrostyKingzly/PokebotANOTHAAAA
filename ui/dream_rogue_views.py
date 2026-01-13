"""
Dream Dive UI Views

Discord UI components (buttons, modals, selects) for Dream Dive gamemode
"""

import discord
from discord.ui import Button, View, Select, Modal, TextInput
from typing import Optional, List, Dict, Any, Callable


class DiveStartView(View):
    """View for starting a Dream Dive dive"""

    def __init__(self, bot, run_id: str, initiator_id: int, callback):
        super().__init__(timeout=900)  # 15 minute timeout (max allowed by Discord)
        self.bot = bot
        self.run_id = run_id
        self.initiator_id = initiator_id
        self.callback = callback

    @discord.ui.button(label="Join Dive", style=discord.ButtonStyle.primary, emoji="🌀")
    async def join_button(self, interaction: discord.Interaction, button: Button):
        """Join the dive"""
        from dream_rogue_manager import DreamRogueManager
        from database import PlayerDatabase

        manager = DreamRogueManager()

        # Try to add participant
        success = manager.add_participant(self.run_id, interaction.user.id)

        if success:
            player_db = PlayerDatabase()
            party = player_db.get_trainer_party(interaction.user.id)
            manager.record_party_snapshot(self.run_id, interaction.user.id, party)
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
        from dream_dive_rewards import restore_dream_dive_party_levels

        manager = DreamRogueManager()
        participants = manager.get_participants(self.run_id)
        for participant in participants:
            restore_dream_dive_party_levels(self.bot, self.run_id, participant["discord_user_id"])
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
        super().__init__(timeout=900)  # 15 minute timeout (max allowed by Discord)
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
        if "mini_boss" in categories:
            return "🟣"
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
        elif "event" in categories:
            return "❓"
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
            from dream_dive_rewards import (
                calculate_dream_dive_exp,
                apply_dream_dive_exp,
                restore_dream_dive_party_levels,
            )

            manager = DreamRogueManager()
            run = manager.get_run(self.run_id)
            participants = manager.get_participants(self.run_id)

            total_dreamlites = sum(p["dreamlites"] for p in participants)

            exp_rewards = {}
            for participant in participants:
                user_id = participant["discord_user_id"]
                restore_dream_dive_party_levels(self.bot, self.run_id, user_id)
                intensity = run.get("intensity", run.get("stage_level", 1))
                exp_amount = calculate_dream_dive_exp(intensity, participant["dreamlites"])
                apply_dream_dive_exp(self.bot, user_id, exp_amount)
                exp_rewards[user_id] = exp_amount

            manager.end_run(self.run_id, extracted=True)

            embed = DreamRogueEmbeds.extraction_summary(
                run,
                participants,
                run["current_floor"],
                total_dreamlites,
                exp_rewards=exp_rewards,
            )

            await interaction.edit_original_response(embed=embed, view=None)
            self.stop()
        else:
            await interaction.followup.send("The team continues onward!", ephemeral=True)


class VotingView(View):
    """View for team voting"""

    def __init__(self, bot, vote_id: str, run_id: str, on_complete_callback=None):
        super().__init__(timeout=900)  # 15 minute timeout (max allowed by Discord)
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

            participants = manager.get_participants(self.run_id)
            participant_ids = {str(p["discord_user_id"]) for p in participants}
            voted_ids = set(vote["votes"].keys())

            if participant_ids and participant_ids.issubset(voted_ids):
                result_index = manager.resolve_vote(self.vote_id)
                vote_result = manager.get_vote(self.vote_id)
                result_embed = DreamRogueEmbeds.vote_result(vote_result, result_index)

                await interaction.followup.send(
                    "🗳️ All votes are in! Resolving now...",
                    ephemeral=True
                )

                await interaction.message.edit(embed=result_embed, view=None)

                if self.on_complete_callback:
                    if "Extract" in vote_result["vote_options"][result_index]["name"]:
                        await self.on_complete_callback(interaction, True)
                    else:
                        await self.on_complete_callback(interaction, result_index)

                self.stop()

        return callback


class InstanceActionView(View):
    """View for instance-specific actions"""

    def __init__(self, bot, run_id: str, instance: Dict, on_complete_callback, origin_channel_id: Optional[int] = None):
        super().__init__(timeout=900)  # 15 minute timeout (max allowed by Discord)
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
        elif "shop" in categories:
            self.add_item(Button(
                label="Open Shop",
                style=discord.ButtonStyle.secondary,
                emoji="🛍️",
                custom_id="shop"
            ))
            self.children[0].callback = self._open_shop

        elif "reward" in categories or "economy" in categories:
            self.add_item(Button(
                label="Claim Reward",
                style=discord.ButtonStyle.success,
                emoji="🎁",
                custom_id="reward"
            ))
            self.children[0].callback = self._claim_reward
        elif "event" in categories:
            self.add_item(Button(
                label="Resolve Event",
                style=discord.ButtonStyle.primary,
                emoji="❓",
                custom_id="event"
            ))
            self.children[0].callback = self._resolve_event
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
        intensity = run.get("intensity", run.get("stage_level", 1))
        min_lvl, max_lvl = manager.get_floor_level_range(intensity, floor)

        categories = self.instance.get("categories", [])
        effect_data = self.instance.get("effect_data", {})
        battle_format_raw = effect_data.get("battle_format", "singles")
        num_opponents = max(1, int(effect_data.get("num_opponents", 1)))
        instance_type = effect_data.get("type")
        if battle_format_raw == "wild":
            battle_format_raw = "singles"
        if instance_type == "gauntlet":
            battle_format_raw = "singles"
            num_opponents = max(1, int(effect_data.get("num_battles", num_opponents)))
        completion_result = "boss_defeated" if "boss" in categories else "battle_complete"

        if battle_format_raw == "doubles":
            battle_format = BattleFormat.DOUBLES
        elif battle_format_raw == "multi":
            battle_format = BattleFormat.MULTI
        elif battle_format_raw == "raid":
            battle_format = BattleFormat.RAID
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

        def _create_wild_opponents(target_count: int):
            opponents = []
            all_species = species_db.get_all_species()
            non_legendary = [s for s in all_species if not s.get("is_legendary", False)]
            candidates = non_legendary or all_species
            for _ in range(target_count):
                species_data = random.choice(candidates)
                level = random.randint(min_lvl, max_lvl)
                if "boss" in categories:
                    level = max_lvl + 10
                elif "mini_boss" in categories:
                    level = max_lvl + 5
                opponents.append(Pokemon(
                    species_data=species_data,
                    level=level,
                    owner_discord_id=None
                ))
            return opponents

        def _build_trainer_party(user_id: int):
            party_data = player_db.get_trainer_party(user_id)
            trainer_pokemon = []
            for poke_data in party_data:
                species_data = species_db.get_species(poke_data["species_dex_number"])
                if not species_data:
                    continue
                trainer_pokemon.append(reconstruct_pokemon_from_data(poke_data, species_data))
            return trainer_pokemon

        def _create_thread_interaction(thread: discord.Thread, user: discord.Member):
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

            return MockInteraction(thread, user)

        if battle_format == BattleFormat.RAID:
            eligible = []
            for participant in participants:
                user_id = participant["discord_user_id"]
                user = interaction.guild.get_member(user_id)
                if not user or user_id in battle_cog.user_battles:
                    continue
                trainer_pokemon = _build_trainer_party(user_id)
                if not trainer_pokemon:
                    continue
                eligible.append((user, trainer_pokemon))

            if not eligible:
                await interaction.followup.send("❌ No eligible participants for this raid battle.")
                return

            raid_boss = _create_wild_opponents(1)[0]
            raid_boss.is_raid_boss = True
            raid_boss.raid_stat_multiplier = float(effect_data.get("raid_stat_multiplier", 2.0))
            raid_boss.raid_hp_multiplier = float(effect_data.get("raid_hp_multiplier", 5.0))
            raid_boss._calculate_stats()
            raid_boss.current_hp = raid_boss.max_hp

            raid_entries = [
                {"user_id": user.id, "trainer_name": user.display_name, "party": party}
                for user, party in eligible
            ]

            battle_id = battle_cog.battle_engine.start_battle(
                trainer_id=raid_entries[0]["user_id"],
                trainer_name=", ".join([entry["trainer_name"] for entry in raid_entries]) or "Raid Team",
                trainer_party=raid_entries[0]["party"],
                opponent_party=[raid_boss],
                battle_type=BattleType.TRAINER,
                opponent_is_ai=True,
                opponent_name=f"Dream Dive {raid_boss.species_name}",
                battle_format=BattleFormat.RAID,
                raid_participants=raid_entries,
            )

            battle = battle_cog.battle_engine.get_battle(battle_id)
            if battle:
                battle.raid_participants = raid_entries

            for entry in raid_entries:
                battle_cog.user_battles[entry["user_id"]] = battle_id

            thread = await parent_channel.create_thread(
                name="Dream Dive - Raid Battle",
                auto_archive_duration=60,
                reason="Dream Dive raid battle"
            )
            created_threads.append(thread.mention)

            mock_interaction = _create_thread_interaction(thread, interaction.user)
            await battle_cog.prompt_and_start_battle_ui(
                interaction=mock_interaction,
                battle_id=battle_id,
                battle_type=BattleType.TRAINER
            )

            if not hasattr(self.bot, "dream_rogue_battle_callbacks"):
                self.bot.dream_rogue_battle_callbacks = {}

            async def _battle_done_callback(battle, result, battle_interaction):
                if self.on_complete_callback:
                    await self.on_complete_callback(
                        self._create_channel_interaction(parent_channel),
                        completion_result
                    )

            self.bot.dream_rogue_battle_callbacks[battle_id] = _battle_done_callback
        elif battle_format == BattleFormat.MULTI:
            eligible = []
            for participant in participants:
                user_id = participant["discord_user_id"]
                user = interaction.guild.get_member(user_id)
                if not user or user_id in battle_cog.user_battles:
                    continue
                trainer_pokemon = _build_trainer_party(user_id)
                if not trainer_pokemon:
                    continue
                eligible.append((user, trainer_pokemon))

            if len(eligible) < 2:
                await interaction.followup.send("❌ Need at least two ready participants for a multi battle.")
                return

            player_pair = random.sample(eligible, 2)
            trainer1, trainer1_party = player_pair[0]
            trainer2, trainer2_party = player_pair[1]

            opponent_pool = _create_wild_opponents(max(2, num_opponents))
            npc1_party = opponent_pool[::2] or opponent_pool[:1]
            npc2_party = opponent_pool[1::2] or opponent_pool[:1]
            npc1_name = npc1_party[0].species_name
            npc2_name = npc2_party[0].species_name

            battle_id = battle_cog.battle_engine.start_multi_battle(
                trainer1_id=trainer1.id,
                trainer1_name=trainer1.display_name,
                trainer1_party=trainer1_party,
                partner1_id=trainer2.id,
                partner1_name=trainer2.display_name,
                partner1_party=trainer2_party,
                partner1_is_ai=False,
                trainer2_id=-10000,
                trainer2_name=npc1_name,
                trainer2_party=npc1_party,
                partner2_id=-10001,
                partner2_name=f"{npc2_name}'s Partner",
                partner2_party=npc2_party,
                partner2_is_ai=True,
                partner1_class=None,
                partner2_class="dream_rogue",
                is_pve=True
            )

            battle_cog.user_battles[trainer1.id] = battle_id
            battle_cog.user_battles[trainer2.id] = battle_id

            thread = await parent_channel.create_thread(
                name=f"Dream Dive - {trainer1.display_name} & {trainer2.display_name}",
                auto_archive_duration=60,
                reason="Dream Dive multi battle"
            )
            created_threads.append(thread.mention)

            mock_interaction = _create_thread_interaction(thread, interaction.user)
            await battle_cog.prompt_and_start_battle_ui(
                interaction=mock_interaction,
                battle_id=battle_id,
                battle_type=BattleType.TRAINER
            )

            if not hasattr(self.bot, "dream_rogue_battle_callbacks"):
                self.bot.dream_rogue_battle_callbacks = {}

            async def _battle_done_callback(battle, result, battle_interaction):
                if self.on_complete_callback:
                    await self.on_complete_callback(
                        self._create_channel_interaction(parent_channel),
                        completion_result
                    )

            self.bot.dream_rogue_battle_callbacks[battle_id] = _battle_done_callback
        else:
            self._pending_battles = {p["discord_user_id"] for p in participants}
            self._battle_results = {}  # Track win/loss for each participant
            for participant in participants:
                user_id = participant["discord_user_id"]
                user = interaction.guild.get_member(user_id)
                if not user:
                    self._pending_battles.discard(user_id)
                    continue

                if user_id in battle_cog.user_battles:
                    self._pending_battles.discard(user_id)
                    continue

                trainer_pokemon = _build_trainer_party(user_id)
                if not trainer_pokemon:
                    self._pending_battles.discard(user_id)
                    continue

                opponent_pokemon = _create_wild_opponents(num_opponents)
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

                thread_name = f"Dream Dive - {user.display_name}"
                thread = await parent_channel.create_thread(
                    name=thread_name,
                    auto_archive_duration=60,
                    reason=f"Dream Dive battle for {user.display_name}"
                )

                mock_interaction = _create_thread_interaction(thread, user)

                await battle_cog.prompt_and_start_battle_ui(
                    interaction=mock_interaction,
                    battle_id=battle_id,
                    battle_type=BattleType.WILD
                )

                if not hasattr(self.bot, "dream_rogue_battle_callbacks"):
                    self.bot.dream_rogue_battle_callbacks = {}

                async def _battle_done_callback(battle, result, battle_interaction, participant_id=user_id):
                    # Track battle result for this participant
                    self._battle_results[participant_id] = result
                    self._pending_battles.discard(participant_id)
                    if not self._pending_battles and self.on_complete_callback:
                        # Pass battle results along with completion
                        interaction_with_results = self._create_channel_interaction(parent_channel)
                        interaction_with_results._battle_results = self._battle_results
                        await self.on_complete_callback(
                            interaction_with_results,
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

        if battle_format not in {BattleFormat.RAID, BattleFormat.MULTI}:
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
        effect_data = self.instance.get("effect_data", {})
        heal_percent = float(effect_data.get("heal_hp_percent", 0.2))

        # Restore all participants' Pokemon
        for p in participants:
            user_id = p["discord_user_id"]
            party = player_db.get_trainer_party(user_id)

            for pokemon in party:
                max_hp = int(pokemon.get("max_hp", 1))
                current_hp = int(pokemon.get("current_hp", max_hp))
                heal_amount = max(1, int(round(max_hp * heal_percent)))
                new_hp = min(max_hp, current_hp + heal_amount)
                player_db.update_pokemon(
                    pokemon["pokemon_id"],
                    {"current_hp": new_hp}
                )

        await interaction.response.send_message(
            "🛌 Your team rests by the campfire. Each Pokémon recovers some HP.",
            ephemeral=False
        )

        if self.on_complete_callback:
            await self.on_complete_callback(interaction, "rested")

    async def _challenge(self, interaction: discord.Interaction):
        """Accept a challenge/trial/gambling instance"""
        from dream_rogue_manager import DreamRogueManager
        from social_stats import (
            SOCIAL_STAT_ORDER,
            POINTS_PER_RANK,
            clamp_points,
            points_to_rank,
            calculate_max_stamina,
        )
        import random

        manager = DreamRogueManager()
        effect_data = self.instance.get("effect_data", {})
        challenge_type = effect_data.get("type")
        participants = manager.get_participants(self.run_id)

        def _weighted_choice(outcomes: List[Dict[str, object]]) -> Optional[Dict[str, object]]:
            if not outcomes:
                return None
            total = sum(float(o.get("weight", 1)) for o in outcomes)
            roll = random.uniform(0, total)
            cumulative = 0.0
            for outcome in outcomes:
                cumulative += float(outcome.get("weight", 1))
                if roll <= cumulative:
                    return outcome
            return outcomes[-1]

        def _pick_template(match_fn) -> Optional[Dict[str, object]]:
            candidates = []
            for category_group, templates in manager.instance_templates.items():
                for template_id, template in templates.items():
                    categories = template.get("categories", [])
                    if match_fn(categories):
                        instance = template.copy()
                        instance["template_id"] = f"{category_group}.{template_id}"
                        candidates.append(instance)
            return random.choice(candidates) if candidates else None

        def _apply_star_delta(user_id: int, stat_key: str, amount: int) -> bool:
            trainer = self.bot.player_manager.get_player(user_id)
            if not trainer:
                return False
            current_points = int(getattr(trainer, f"{stat_key}_points", 0))
            cap = trainer.get_stat_cap(stat_key)
            new_points = clamp_points(current_points + amount * POINTS_PER_RANK, cap)
            new_rank = points_to_rank(new_points, cap)
            updates = {
                f"{stat_key}_points": new_points,
                f"{stat_key}_rank": new_rank,
            }
            if stat_key == "fortitude":
                new_max = calculate_max_stamina(new_rank)
                updates["stamina_max"] = new_max
                updates["stamina_current"] = min(getattr(trainer, "stamina_current", new_max), new_max)
            self.bot.player_manager.update_player(user_id, **updates)
            return True

        if challenge_type == "roulette":
            user_id = interaction.user.id
            bet_options = sorted(effect_data.get("bet_options", []))
            affordable = [b for b in bet_options if manager.can_afford(self.run_id, user_id, b)]
            if not affordable:
                await interaction.response.send_message(
                    "❌ You don't have enough Dreamlites to bet right now.",
                    ephemeral=True
                )
                return

            bet_amount = max(affordable)
            manager.add_dreamlites(self.run_id, user_id, -bet_amount)

            outcome = _weighted_choice(effect_data.get("outcomes", []))
            outcome_name = outcome.get("name", "Outcome")
            outcome_effect = outcome.get("effect")
            result_lines = [f"🎲 **Dream Roulette** — Bet: 💎 {bet_amount}"]

            if outcome_effect == "double_bet":
                winnings = bet_amount * 2
                manager.add_dreamlites(self.run_id, user_id, winnings)
                result_lines.append(f"✅ {outcome_name}: You won 💎 {winnings}!")
            elif outcome_effect == "random_rare_buff":
                template = _pick_template(lambda cats: "buff" in cats and "curse" not in cats and "nightmare" not in cats)
                if template:
                    manager.apply_buff(
                        run_id=self.run_id,
                        buff_type="buff",
                        buff_name=template.get("name", "Dream Blessing"),
                        buff_description=template.get("description", "A gentle boon."),
                        scope="individual",
                        effect_data=template.get("effect_data", {}),
                        duration=template.get("duration", "floor"),
                        target_user_id=user_id,
                    )
                    result_lines.append(f"✨ {outcome_name}: {template.get('name')}")
                else:
                    result_lines.append(f"✨ {outcome_name}: The dream shimmers, but nothing manifests.")
            elif outcome_effect == "random_curse":
                template = _pick_template(lambda cats: "curse" in cats or "nightmare" in cats)
                if template:
                    manager.apply_buff(
                        run_id=self.run_id,
                        buff_type="curse",
                        buff_name=template.get("name", "Dream Curse"),
                        buff_description=template.get("description", "A chilling omen."),
                        scope="individual",
                        effect_data=template.get("effect_data", {}),
                        duration=template.get("duration", "floor"),
                        target_user_id=user_id,
                    )
                    result_lines.append(f"👁️ {outcome_name}: {template.get('name')}")
                else:
                    result_lines.append(f"👁️ {outcome_name}: The dream flickers ominously.")
            elif outcome_effect == "marked":
                manager.apply_buff(
                    run_id=self.run_id,
                    buff_type="curse",
                    buff_name=outcome_name,
                    buff_description=outcome.get("description", "The dream marks you."),
                    scope="individual",
                    effect_data={"type": "marked"},
                    duration="run",
                    target_user_id=user_id,
                )
                result_lines.append(f"⚠️ {outcome_name}: The dream marks you for the run.")
            else:
                result_lines.append(f"➖ {outcome_name}: Nothing happens this time.")

            await interaction.response.send_message("\n".join(result_lines), ephemeral=False)

        elif challenge_type == "coin_flip":
            flip = random.choice(["heads", "tails"])
            if flip == "heads":
                stat_key = random.choice(SOCIAL_STAT_ORDER)
                amount = int(effect_data.get("heads", {}).get("amount", 1))
                for participant in participants:
                    _apply_star_delta(participant["discord_user_id"], stat_key, amount)
                stat_name = stat_key.title()
                await interaction.response.send_message(
                    f"🪙 **Heads!** Everyone gains +{amount} {stat_name} star rank.",
                    ephemeral=False
                )
            else:
                manager.apply_buff(
                    run_id=self.run_id,
                    buff_type="curse",
                    buff_name="Enemy Hidden Passive",
                    buff_description="Enemies gain a hidden passive this floor.",
                    scope="team",
                    effect_data=effect_data.get("tails", {}),
                    duration="floor",
                )
                await interaction.response.send_message(
                    "🪙 **Tails!** Enemies gain a hidden passive this floor.",
                    ephemeral=False
                )

        elif challenge_type == "star_trade":
            user_id = interaction.user.id
            trainer = self.bot.player_manager.get_player(user_id)
            if not trainer:
                await interaction.response.send_message(
                    "❌ Could not load your trainer data.",
                    ephemeral=True
                )
                return

            eligible_stats = [key for key in SOCIAL_STAT_ORDER if trainer.get_stat_rank(key) > 0]
            if not eligible_stats:
                await interaction.response.send_message(
                    "❌ You don't have any star ranks to trade yet.",
                    ephemeral=True
                )
                return

            stat_key = random.choice(eligible_stats)
            _apply_star_delta(user_id, stat_key, -1)

            options = effect_data.get("options", [])
            chosen = random.choice(options) if options else {"name": "Dream Boon", "effect": "unknown"}

            manager.apply_buff(
                run_id=self.run_id,
                buff_type="buff",
                buff_name=chosen.get("name", "Dream Boon"),
                buff_description="A permanent boon from the dealer.",
                scope="individual",
                effect_data={"type": chosen.get("effect"), "value": chosen.get("value")},
                duration="permanent",
                target_user_id=user_id,
            )

            await interaction.response.send_message(
                f"🃏 You traded 1 {stat_key.title()} star rank for **{chosen.get('name')}**.",
                ephemeral=False
            )

        else:
            await interaction.response.send_message(
                "❌ This challenge cannot be resolved yet.",
                ephemeral=True
            )
            return

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

    async def _open_shop(self, interaction: discord.Interaction):
        """Open a Dream Shop for the user."""
        from dream_rogue_manager import DreamRogueManager
        from ui.dream_rogue_embeds import DreamRogueEmbeds

        manager = DreamRogueManager()
        effect_data = self.instance.get("effect_data", {})
        items = effect_data.get("items", [])
        if not items:
            await interaction.response.send_message(
                "❌ The dream merchant has nothing to offer right now.",
                ephemeral=True
            )
            return

        shop_items = []
        for item in items:
            shop_items.append({
                "name": item.get("name", "Dream Item"),
                "description": item.get("description", ""),
                "dreamlite_cost": item.get("cost", 0),
                "effect": item.get("effect"),
                "value": item.get("value"),
            })

        user_dreamlites = manager.get_dreamlites(self.run_id, interaction.user.id)
        embed = DreamRogueEmbeds.shop(shop_items, user_dreamlites)
        view = DreamShopView(self.bot, self.run_id, shop_items)

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _resolve_event(self, interaction: discord.Interaction):
        """Resolve an event choice."""
        from dream_rogue_manager import DreamRogueManager
        from ui.dream_rogue_embeds import DreamRogueEmbeds
        import random

        manager = DreamRogueManager()
        effect_data = self.instance.get("effect_data", {})
        options = effect_data.get("options", [])
        if not options:
            await interaction.response.send_message(
                "❌ This event has no choices to resolve.",
                ephemeral=True
            )
            return

        vote_id = manager.create_vote(
            self.run_id,
            effect_data.get("prompt", self.instance.get("name", "Dream Event")),
            [
                {
                    "name": option.get("name", "Option"),
                    "description": option.get("description", "A path through the dream."),
                }
                for option in options
            ],
        )

        vote = manager.get_vote(vote_id)
        percentages = manager.get_vote_percentages(vote_id)
        embed = DreamRogueEmbeds.voting(vote, percentages)

        async def _on_event_vote_complete(vote_interaction: discord.Interaction, result_index: int):
            chosen = options[result_index]
            participants = manager.get_participants(self.run_id)
            effects = chosen.get("effects", {})

            def _pick_template(match_fn):
                candidates = []
                for category_group, templates in manager.instance_templates.items():
                    for template_id, template in templates.items():
                        categories = template.get("categories", [])
                        if match_fn(categories):
                            instance = template.copy()
                            instance["template_id"] = f"{category_group}.{template_id}"
                            candidates.append(instance)
                return random.choice(candidates) if candidates else None

            dreamlites_gain = int(effects.get("dreamlites_gain", 0))
            dreamlites_loss = int(effects.get("dreamlites_loss", 0))

            if "roll_d20" in effects:
                roll = random.randint(1, 20)
                threshold = int(effects["roll_d20"].get("success_threshold", 11))
                outcome = effects["roll_d20"]["success"] if roll >= threshold else effects["roll_d20"]["failure"]
                dreamlites_gain += int(outcome.get("dreamlites_gain", 0))
                dreamlites_loss += int(outcome.get("dreamlites_loss", 0))

                if outcome.get("random_buff"):
                    template = _pick_template(lambda cats: "buff" in cats and "curse" not in cats and "nightmare" not in cats)
                    if template:
                        manager.apply_buff(
                            run_id=self.run_id,
                            buff_type="buff",
                            buff_name=template.get("name", "Dream Blessing"),
                            buff_description=template.get("description", "A gentle boon."),
                            scope="team",
                            effect_data=template.get("effect_data", {}),
                            duration=template.get("duration", "floor"),
                        )
                if outcome.get("random_curse"):
                    template = _pick_template(lambda cats: "curse" in cats or "nightmare" in cats)
                    if template:
                        manager.apply_buff(
                            run_id=self.run_id,
                            buff_type="curse",
                            buff_name=template.get("name", "Dream Curse"),
                            buff_description=template.get("description", "A chilling omen."),
                            scope="team",
                            effect_data=template.get("effect_data", {}),
                            duration=template.get("duration", "floor"),
                        )

            if dreamlites_gain:
                for participant in participants:
                    manager.add_dreamlites(self.run_id, participant["discord_user_id"], dreamlites_gain)
            if dreamlites_loss:
                for participant in participants:
                    manager.add_dreamlites(self.run_id, participant["discord_user_id"], -dreamlites_loss)

            outcome_lines = []
            if dreamlites_gain:
                outcome_lines.append(f"💎 Everyone gained **{dreamlites_gain}** Dreamlites.")
            if dreamlites_loss:
                outcome_lines.append(f"💎 Everyone lost **{dreamlites_loss}** Dreamlites.")

            if outcome_lines:
                await vote_interaction.followup.send("\n".join(outcome_lines))

            if self.on_complete_callback:
                await self.on_complete_callback(vote_interaction, "event_resolved")

        view = VotingView(self.bot, vote_id, self.run_id, _on_event_vote_complete)

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view)

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


class DreamShopView(View):
    """View for purchasing Dream Shop items."""

    def __init__(self, bot, run_id: str, items: List[Dict[str, object]]):
        super().__init__(timeout=600)
        self.bot = bot
        self.run_id = run_id
        self.items = items

        options = []
        for idx, item in enumerate(items[:25]):
            name = item.get("name", "Dream Item")
            description = item.get("description", "")[:100]
            cost = item.get("dreamlite_cost", 0)
            options.append(discord.SelectOption(
                label=f"{name} ({cost} 💎)",
                value=str(idx),
                description=description
            ))

        select = Select(
            placeholder="Choose an item to purchase...",
            options=options
        )
        select.callback = self._on_purchase
        self.add_item(select)

    async def _on_purchase(self, interaction: discord.Interaction):
        from dream_rogue_manager import DreamRogueManager

        manager = DreamRogueManager()
        item = self.items[int(interaction.values[0])]
        cost = int(item.get("dreamlite_cost", 0))

        if not manager.can_afford(self.run_id, interaction.user.id, cost):
            await interaction.response.send_message(
                "❌ You don't have enough Dreamlites for that item.",
                ephemeral=True
            )
            return

        manager.add_dreamlites(self.run_id, interaction.user.id, -cost)
        manager.apply_buff(
            run_id=self.run_id,
            buff_type="buff",
            buff_name=item.get("name", "Dream Blessing"),
            buff_description=item.get("description", "A boon from the merchant."),
            scope="individual",
            effect_data={
                "type": item.get("effect"),
                "value": item.get("value")
            },
            duration="floor",
            target_user_id=interaction.user.id,
        )

        await interaction.response.send_message(
            f"✅ You purchased **{item.get('name', 'Dream Item')}**.",
            ephemeral=True
        )
        self.stop()


class DiveConfigModal(Modal, title="Choose Dream Dive Layer & Intensity"):
    """Modal for selecting dream layer and intensity."""

    layer_input = TextInput(
        label="Layer (Somnia Prima available)",
        placeholder="Somnia Prima",
        style=discord.TextStyle.short,
        required=True,
        max_length=30
    )
    intensity_input = TextInput(
        label="Intensity (1-10)",
        placeholder="Enter an intensity (e.g., 1)",
        style=discord.TextStyle.short,
        required=True,
        max_length=2
    )

    def __init__(self, callback, allow_test_path: bool = False):
        super().__init__()
        self.callback = callback
        self.allow_test_path = allow_test_path

    def _normalize_layer(self, value: str) -> Optional[str]:
        allowed_layers = {
            "somnia prima": "Somnia Prima",
            "somnia": "Somnia Prima",
        }
        if self.allow_test_path:
            allowed_layers.update({
                "somnia prima test path": "Somnia Prima - Test Path",
                "somnia prima - test path": "Somnia Prima - Test Path",
                "test path": "Somnia Prima - Test Path",
            })
        normalized = value.strip().lower()
        return allowed_layers.get(normalized)

    async def on_submit(self, interaction: discord.Interaction):
        layer_name = self._normalize_layer(self.layer_input.value)
        if not layer_name:
            error_message = "❌ Only **Somnia Prima** is available right now."
            if self.allow_test_path:
                error_message = (
                    "❌ Available layers: **Somnia Prima** or **Somnia Prima - Test Path**."
                )
            await interaction.response.send_message(
                error_message,
                ephemeral=True
            )
            return

        try:
            intensity = int(self.intensity_input.value)
        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid intensity between 1 and 10!",
                ephemeral=True
            )
            return

        if intensity < 1 or intensity > 10:
            await interaction.response.send_message(
                "❌ Intensity must be between 1 and 10!",
                ephemeral=True
            )
            return

        if self.callback:
            await self.callback(interaction, layer_name, intensity)


# New dropdown-based configuration view for Dream Dive
class DiveConfigView(View):
    """View for selecting dream layer, dive type, and intensity."""

    def __init__(self, callback, allow_test_path: bool = False):
        super().__init__(timeout=300)
        self.callback = callback
        self.allow_test_path = allow_test_path
        self.selected_layer: Optional[str] = None
        self.selected_mode: Optional[str] = None
        self.selected_intensity: Optional[int] = None

        self.layer_select = Select(
            placeholder="Select a dream layer...",
            options=[
                discord.SelectOption(
                    label="Somnia Prima",
                    value="Somnia Prima",
                    description="The first dream layer."
                )
            ],
        )
        self.layer_select.callback = self._on_layer_selected

        mode_options = [
            discord.SelectOption(
                label="Exploration",
                value="exploration",
                description="Standard Dream Dive run."
            ),
            discord.SelectOption(
                label="Domain",
                value="domain",
                description="Enter a domain (intensity locked)."
            ),
        ]
        if self.allow_test_path:
            mode_options.append(
                discord.SelectOption(
                    label="Path",
                    value="path",
                    description="Follow the scripted test path."
                )
            )

        self.mode_select = Select(
            placeholder="Select dive type...",
            options=mode_options,
            disabled=True
        )
        self.mode_select.callback = self._on_mode_selected

        self.intensity_select = Select(
            placeholder="Select intensity (1-10)...",
            options=[
                discord.SelectOption(label=str(value), value=str(value))
                for value in range(1, 11)
            ],
            disabled=True
        )
        self.intensity_select.callback = self._on_intensity_selected

        self.start_button = Button(
            label="Start Dive",
            style=discord.ButtonStyle.primary,
            disabled=True
        )
        self.start_button.callback = self._on_start

        self.add_item(self.layer_select)
        self.add_item(self.mode_select)
        self.add_item(self.intensity_select)
        self.add_item(self.start_button)

    def _update_option_defaults(self, select: Select, selected_value: Optional[str]):
        for option in select.options:
            option.default = selected_value == option.value

    def _sync_controls(self):
        self.mode_select.disabled = self.selected_layer is None

        if self.selected_mode == "exploration":
            self.intensity_select.disabled = False
            self.intensity_select.placeholder = "Select intensity (1-10)..."
        else:
            self.intensity_select.disabled = True
            self.intensity_select.placeholder = "Intensity locked to 1"

        can_start = self.selected_layer and self.selected_mode
        if self.selected_mode == "exploration":
            can_start = can_start and self.selected_intensity is not None
        self.start_button.disabled = not can_start

        self._update_option_defaults(self.layer_select, self.selected_layer)
        self._update_option_defaults(self.mode_select, self.selected_mode)
        if self.selected_intensity is not None:
            self._update_option_defaults(self.intensity_select, str(self.selected_intensity))
        else:
            self._update_option_defaults(self.intensity_select, None)

    async def _on_layer_selected(self, interaction: discord.Interaction):
        self.selected_layer = self.layer_select.values[0]
        self.selected_mode = None
        self.selected_intensity = None
        self._sync_controls()
        await interaction.response.edit_message(view=self)

    async def _on_mode_selected(self, interaction: discord.Interaction):
        self.selected_mode = self.mode_select.values[0]
        if self.selected_mode == "exploration":
            self.selected_intensity = None
        else:
            self.selected_intensity = 1
        self._sync_controls()
        await interaction.response.edit_message(view=self)

    async def _on_intensity_selected(self, interaction: discord.Interaction):
        self.selected_intensity = int(self.intensity_select.values[0])
        self._sync_controls()
        await interaction.response.edit_message(view=self)

    async def _on_start(self, interaction: discord.Interaction):
        if not self.callback:
            await interaction.response.send_message(
                "❌ Unable to start the dive right now.",
                ephemeral=True
            )
            return

        if self.selected_mode == "path":
            from dream_rogue_manager import DreamRogueManager
            layer_name = DreamRogueManager.TEST_PATH_LAYER
            intensity = 1
        else:
            layer_name = self.selected_layer
            intensity = self.selected_intensity or 1

        await self.callback(interaction, layer_name, intensity)


# Keep StageSelectModal for backwards compatibility but redirect to DiveConfigModal
class StageSelectModal(DiveConfigModal):
    """Deprecated: Use DiveConfigModal instead."""
    pass


# Keep FloorSelectModal for backwards compatibility but redirect to DiveConfigModal
class FloorSelectModal(DiveConfigModal):
    """Deprecated: Use DiveConfigModal instead."""
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
