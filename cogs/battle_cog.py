import asyncio
import re
import discord
from discord import app_commands
from discord.ext import commands
from pathlib import Path
from typing import Optional, Any
import math

from battle_engine_v2 import BattleEngine, BattleType, BattleAction, BattleFormat, HeldItemManager
from battle_exp_integration import BattleExpHandler
from battle_music_manager import BattleMusicManager
from battle_themes import get_random_npc_theme, get_ranked_npc_theme, get_raid_theme
from battle_music_ui import (
    MusicOptInView, MusicQueueView,
    create_music_opt_in_embed, create_queue_status_embed,
    create_music_starting_embed
)
from capture import simulate_throw, guaranteed_capture
from learnset_database import LearnsetDatabase
from sprite_helper import PokemonSpriteHelper
from ui.embeds import EmbedBuilder
# Emoji placeholders (fallbacks if ui.emoji is missing)
try:
    from ui.emoji import (
        SWORD,
        FIELD,
        EVENTS,
        YOU,
        FOE,
        TYPE_EMOJIS,
        POKEBALL_EMOJIS,
        DEFAULT_POKEBALL_ID,
        BALL,
    )
except Exception:
    SWORD = "⚔️"; FIELD = "🌦️"; EVENTS = "📋"; YOU = "👉"; FOE = "🎯"; BALL = "🔴"
    TYPE_EMOJIS = {}
    POKEBALL_EMOJIS = {}
    DEFAULT_POKEBALL_ID = "poke_ball"

try:
    from version import BUILD_TAG
except Exception:
    BUILD_TAG = "dev"

class BattleCog(commands.Cog):
    """Handles battle UI and flow."""
    def __init__(self, bot: commands.Bot, battle_engine: BattleEngine):
        self.bot = bot
        self.battle_engine = battle_engine
        # Tracks active battle per user id (int -> str battle_id)
        self.user_battles = {}
        self.exp_handler = self._init_exp_handler()
        # Battle music manager
        self.music_manager = BattleMusicManager(bot)
        # Track which battles have music enabled (battle_id -> bool)
        self.battles_with_music = {}

    def _init_exp_handler(self) -> Optional[BattleExpHandler]:
        species_db = getattr(self.bot, "species_db", None)
        player_manager = getattr(self.bot, "player_manager", None)
        if not species_db or not player_manager:
            return None

        learnset_db = None
        learnset_path = Path("data/learnsets.json")
        if learnset_path.exists():
            try:
                learnset_db = LearnsetDatabase(str(learnset_path))
            except Exception:
                learnset_db = None

        try:
            return BattleExpHandler(
                species_db,
                learnset_db,
                player_manager,
                getattr(self.bot, "item_usage_manager", None)
            )
        except Exception:
            return None

    def _unregister_battle(self, battle):
        """Remove all user tracking entries for a finished battle."""
        if not battle:
            return
        self.user_battles.pop(getattr(battle.trainer, 'battler_id', None), None)
        if getattr(battle, 'battle_format', None) == BattleFormat.MULTI:
            self.user_battles.pop(getattr(battle.trainer_partner, 'battler_id', None), None)
            self.user_battles.pop(getattr(battle.opponent_partner, 'battler_id', None), None)
        if getattr(battle, 'battle_type', None) == BattleType.PVP:
            self.user_battles.pop(getattr(battle.opponent, 'battler_id', None), None)
        if getattr(battle, 'battle_format', None) == BattleFormat.RAID:
            for ally in getattr(battle, 'raid_allies', []) or []:
                self.user_battles.pop(getattr(ally, 'battler_id', None), None)

    async def _prompt_for_music(
        self,
        interaction: discord.Interaction,
        battle_id: str,
        battle_type: BattleType,
        user_voice_channel: Optional[discord.VoiceChannel] = None
    ) -> bool:
        """
        Prompt user if they want music for their battle.
        Returns True if music will be used, False otherwise.

        This should be called before starting the battle UI.
        """
        # Support NPC and PvP battles (not wild, not raids)
        if battle_type == BattleType.WILD:
            return False

        # Check if this is a raid battle by getting the battle format
        battle = self.battle_engine.get_battle(battle_id)
        if battle and battle.battle_format == BattleFormat.RAID:
            return False

        # Check if user is in a voice channel
        if not user_voice_channel:
            # Try to get it from interaction user
            if hasattr(interaction.user, 'voice') and interaction.user.voice:
                user_voice_channel = interaction.user.voice.channel

        # If not in VC, can't use music
        if not user_voice_channel:
            return False

        if getattr(self.music_manager, "session_override_active", False):
            message = "⚠️ Session music override is active, so battle music is currently disabled."
            if not interaction.response.is_done():
                await interaction.response.send_message(message, ephemeral=True)
            else:
                await interaction.followup.send(message, ephemeral=True)
            return False

        session_manager = getattr(self.bot, "session_manager", None)
        if session_manager:
            session = session_manager.get_active_session_by_guild(interaction.guild_id)
            if session and interaction.user.id != session["admin_id"]:
                message = "❌ Music can only be started by the session admin while a session is active."
                if not interaction.response.is_done():
                    await interaction.response.send_message(message, ephemeral=True)
                else:
                    await interaction.followup.send(message, ephemeral=True)
                return False

        # Create opt-in prompt
        opt_in_embed = create_music_opt_in_embed()

        music_chosen = False
        use_custom = False

        async def on_yes(button_interaction: discord.Interaction):
            nonlocal music_chosen, use_custom
            music_chosen = True
            use_custom = False

            # Request music from manager
            username = button_interaction.user.display_name
            battle_type_str = "npc" if battle_type == BattleType.TRAINER else "pvp"

            can_start, message, position = await self.music_manager.request_music(
                battle_id,
                button_interaction.user.id,
                username,
                user_voice_channel.id,
                battle_type_str
            )

            if can_start:
                self.battles_with_music[battle_id] = False  # False = random NPC theme
                await button_interaction.response.send_message(
                    f"Music will start when battle begins! Join **{user_voice_channel.name}**",
                    ephemeral=True
                )
            else:
                # Show queue status
                queue_data = self.music_manager.get_queue_display()
                queue_embed = create_queue_status_embed(queue_data, user_voice_channel.name)
                await button_interaction.response.send_message(
                    embed=queue_embed,
                    ephemeral=True
                )

        async def on_my_theme(button_interaction: discord.Interaction):
            nonlocal music_chosen, use_custom
            music_chosen = True
            use_custom = True

            # Request music from manager
            username = button_interaction.user.display_name
            battle_type_str = "npc" if battle_type == BattleType.TRAINER else "pvp"

            can_start, message, position = await self.music_manager.request_music(
                battle_id,
                button_interaction.user.id,
                username,
                user_voice_channel.id,
                battle_type_str
            )

            if can_start:
                self.battles_with_music[battle_id] = True  # True = custom theme
                await button_interaction.response.send_message(
                    f"Your custom theme will play! Join **{user_voice_channel.name}**",
                    ephemeral=True
                )
            else:
                # Show queue status
                queue_data = self.music_manager.get_queue_display()
                queue_embed = create_queue_status_embed(queue_data, user_voice_channel.name)
                await button_interaction.response.send_message(
                    embed=queue_embed,
                    ephemeral=True
                )

        async def on_no(button_interaction: discord.Interaction):
            await button_interaction.response.send_message(
                "Battle will proceed without music.",
                ephemeral=True
            )

        view = MusicOptInView(on_yes, on_no, on_my_theme)

        # Send the prompt
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=opt_in_embed, view=view, ephemeral=True)
        else:
            await interaction.followup.send(embed=opt_in_embed, view=view, ephemeral=True)

        # Wait for response
        await view.wait()

        return music_chosen

    async def _start_battle_music(self, battle_id: str, battle_type: BattleType, trainer_id: int):
        """Start playing music for a battle - uses custom or random themes"""
        if battle_id not in self.battles_with_music:
            return

        use_custom_theme = self.battles_with_music[battle_id]

        # Get themes
        if use_custom_theme:
            # Use player's custom theme
            player_manager = getattr(self.bot, 'player_manager', None)
            if player_manager:
                try:
                    trainer = player_manager.get_player(trainer_id)
                    battle_theme_url = getattr(trainer, 'battle_theme_url', None)
                    victory_theme_url = getattr(trainer, 'victory_theme_url', None)

                    # Fall back to random if no custom theme set
                    if not battle_theme_url or not victory_theme_url:
                        print(f"⚠️ No custom theme set, using random NPC theme")
                        battle_theme_url, victory_theme_url = get_random_npc_theme()
                except:
                    print(f"⚠️ Failed to get trainer data, using random NPC theme")
                    battle_theme_url, victory_theme_url = get_random_npc_theme()
            else:
                battle_theme_url, victory_theme_url = get_random_npc_theme()
        else:
            # Use random NPC theme
            battle_theme_url, victory_theme_url = get_random_npc_theme()

        # Start music
        success = await self.music_manager.start_battle_music(battle_theme_url, victory_theme_url)

        if success:
            theme_type = "custom" if use_custom_theme else "random NPC"
            print(f"✅ Battle music started for battle {battle_id} ({theme_type} theme)")
        else:
            print(f"❌ Failed to start battle music for battle {battle_id}")

    async def _play_victory_music(self, battle_id: str, winner_name: str, interaction: Optional[discord.Interaction] = None):
        """Play victory music after battle ends"""
        if battle_id not in self.battles_with_music:
            return

        await self.music_manager.play_victory_music()

    async def _cleanup_battle_music(self, battle_id: str):
        """Clean up music session when battle ends or is cancelled"""
        if battle_id in self.battles_with_music:
            await self.music_manager.cancel_session(battle_id)
            del self.battles_with_music[battle_id]

    def _get_ball_inventory(self, discord_user_id: int):
        """Return a dict of {item_id: (item_data, quantity)} for Poké Balls.

        Uses ItemsDatabase (self.bot.items_db) and the player's inventory rows.
        """
        items_db = getattr(self.bot, "items_db", None)
        if not items_db:
            return {}
        pm = self.bot.player_manager
        inventory_rows = pm.get_inventory(discord_user_id)
        balls = {}
        for row in inventory_rows:
            item_id = row.get("item_id")
            qty = row.get("quantity", 0)
            if qty <= 0:
                continue
            # Look up item data via ItemsDatabase
            item_data = items_db.get_item(item_id)
            if not item_data:
                continue
            if item_data.get("category") == "pokeball":
                balls[item_id] = (item_data, qty)
        return balls

    def _consume_ball(self, discord_user_id: int, item_id: str) -> bool:
        """Remove one ball from inventory if possible."""
        pm = self.bot.player_manager
        return pm.remove_item(discord_user_id, item_id, quantity=1)

    async def _send_dazed_prompt(self, interaction: discord.Interaction, battle):
        """Send 'Will you catch it?' prompt when wild Pokémon is dazed."""
        opponent_mon = battle.opponent.get_active_pokemon()[0]
        embed = discord.Embed(
            title=f"😵 The wild {opponent_mon.species_name} is dazed!",
            description="**Will you catch it?**",
            color=discord.Color.gold()
        )

        # Add sprite
        sprite_url = PokemonSpriteHelper.get_sprite(
            opponent_mon.species_name,
            opponent_mon.species_dex_number,
            style='animated',
            gender=getattr(opponent_mon, 'gender', None),
            shiny=getattr(opponent_mon, 'is_shiny', False),
            use_fallback=False
        )
        embed.set_thumbnail(url=sprite_url)

        view = DazedCatchView(self, battle.battle_id)
        await interaction.followup.send(embed=embed, view=view)

    async def _handle_ball_throw(self, interaction: discord.Interaction, battle_id: str, item_id: str, guaranteed: bool = False):
        """Core capture logic used by the dazed 'Yes' flow, and for in-battle Bag throws."""
        battle = self.battle_engine.get_battle(battle_id)

        async def send_msg(*args, **kwargs):
            """Safe send helper: uses response.send_message first, then followups."""
            if not interaction.response.is_done():
                await interaction.response.send_message(*args, **kwargs)
            else:
                await interaction.followup.send(*args, **kwargs)

        if not battle or battle.battle_type != BattleType.WILD:
            await send_msg("❌ You can only use Poké Balls in wild battles.", ephemeral=True)
            return

        wild_mon = battle.opponent.get_active_pokemon()[0]
        balls = self._get_ball_inventory(interaction.user.id)
        if item_id not in balls:
            await send_msg("❌ You don't have that kind of Poké Ball.", ephemeral=True)
            return

        item_data, _qty = balls[item_id]

        # Consume the ball up front
        if not self._consume_ball(interaction.user.id, item_id):
            await send_msg("❌ You don't have that Poké Ball anymore.", ephemeral=True)
            return

        # Determine ball bonus: use item's catch_rate_modifier as base
        ball_bonus = float(item_data.get("catch_rate_modifier", 1.0))
        # Treat Master Ball-like behaviour as guaranteed
        if ball_bonus >= 255.0:
            guaranteed = True

        if guaranteed:
            result = guaranteed_capture()
            caught = True
            shakes = result["shakes"]
        else:
            # Use modern style formula
            species_rate = int(wild_mon.species_data.get("catch_rate", 45))
            max_hp = int(getattr(wild_mon, "max_hp", 1))
            cur_hp = int(max(0, getattr(wild_mon, "current_hp", 0)))
            status = getattr(wild_mon, "major_status", None)
            result = simulate_throw(max_hp, cur_hp, species_rate, ball_bonus, status=status)
            caught = result["caught"]
            shakes = result["shakes"]

        if caught:
            # Add Pokemon to trainer and end battle
            pm = self.bot.player_manager
            wild_mon.owner_discord_id = interaction.user.id
            wild_mon.pokeball = item_id or 'poke_ball'

            # Decide whether it goes to party or box
            party = pm.get_party(interaction.user.id)
            if len(party) >= 6:
                pm.add_pokemon_to_box(wild_mon)
                location_text = "It was sent to your storage box."
            else:
                pm.add_pokemon_to_party(wild_mon)
                location_text = "It was added to your party."

            # Mark battle over
            battle.is_over = True
            battle.winner = "trainer"

            embed = discord.Embed(
                title=f"🎉 Gotcha! {wild_mon.species_name} was caught!",
                description=f"You used **{item_data.get('name', item_id)}**.\n{location_text}",
                color=discord.Color.green()
            )

            # Add sprite
            sprite_url = PokemonSpriteHelper.get_sprite(
                wild_mon.species_name,
                wild_mon.species_dex_number,
                style='animated',
                gender=getattr(wild_mon, 'gender', None),
                shiny=getattr(wild_mon, 'is_shiny', False),
                use_fallback=False
            )
            embed.set_thumbnail(url=sprite_url)

            await send_msg(embed=embed)
            await self.send_return_to_encounter_prompt(interaction, interaction.user.id)
            return
        else:
            msg = f"The {item_data.get('name', item_id)} shook {shakes} time(s), but the Pokémon broke free!"
            embed = discord.Embed(
                title="...Almost had it!",
                description=msg,
                color=discord.Color.orange()
            )

            # Add sprite
            sprite_url = PokemonSpriteHelper.get_sprite(
                wild_mon.species_name,
                wild_mon.species_dex_number,
                style='animated',
                gender=getattr(wild_mon, 'gender', None),
                shiny=getattr(wild_mon, 'is_shiny', False),
                use_fallback=False
            )
            embed.set_thumbnail(url=sprite_url)

            await send_msg(embed=embed)
            # Note: throwing a ball consumes the turn externally; the turn resolution
            # for the wild Pokémon will still happen via the normal battle engine.

    async def send_return_to_encounter_prompt(self, interaction: discord.Interaction, discord_user_id: int):
        """Send a button that lets the trainer reopen their remaining encounter pool"""
        active_sets = getattr(self.bot, 'active_encounters', None)
        if not active_sets:
            return

        data = active_sets.get(discord_user_id)
        if not data:
            return

        encounters = data.get('encounters') or []
        location_id = data.get('location_id')
        if not encounters or not location_id:
            return

        try:
            from ui.buttons import ReturnToEncounterView
        except Exception:
            return

        message = "↩️ Continue exploring the remaining encounters from your last roll."
        view = ReturnToEncounterView(self.bot, discord_user_id)

        send_kwargs = {
            'content': message,
            'view': view,
            'ephemeral': True
        }

        try:
            if interaction.response.is_done():
                await interaction.followup.send(**send_kwargs)
            else:
                await interaction.response.send_message(**send_kwargs)
        except Exception:
            pass

    async def prompt_and_start_battle_ui(
        self,
        interaction: discord.Interaction,
        battle_id: str,
        battle_type: BattleType
    ):
        """
        Prompt for music opt-in, then start battle UI.
        This is the recommended method to call when starting a battle.
        """
        # Prompt for music (skips if wild battle or not in VC)
        await self._prompt_for_music(interaction, battle_id, battle_type)

        # Now start the battle UI
        await self.start_battle_ui(interaction, battle_id, battle_type)

    async def start_battle_ui(
        self,
        interaction: discord.Interaction,
        battle_id: str,
        battle_type: BattleType
    ):
        """Start the multi-embed battle intro safely from a Select callback."""
        battle = self.battle_engine.get_battle(battle_id)
        if not battle:
            if not interaction.response.is_done():
                await interaction.response.send_message("Battle not found!", ephemeral=True)
            else:
                await interaction.followup.send("Battle not found!", ephemeral=True)
            return

        # Make sure we can send multiple messages from a select interaction
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass

        # Start battle music if enabled
        trainer_id = battle.trainer.battler_id if hasattr(battle.trainer, 'battler_id') else None
        if trainer_id:
            await self._start_battle_music(battle_id, battle_type, trainer_id)

        trainer_active = battle.trainer.get_active_pokemon()
        opponent_active = battle.opponent.get_active_pokemon()

        battle_mode = battle_type or battle.battle_type

        # Raid-specific dramatic intro and UI layout
        if battle.battle_format == BattleFormat.RAID:
            raid_mon = opponent_active[0] if opponent_active else None
            battle_begin_embed = await self._send_raid_intro(interaction, opponent_active)

            sprite_embed = self._create_raid_sprite_embed(raid_mon)
            status_embed = self._create_raid_status_embed(battle)
            party_embed = self._create_raid_party_embed(battle)
            view = self._create_battle_view(battle)

            if sprite_embed:
                await interaction.followup.send(embed=sprite_embed)
                await asyncio.sleep(1)

            await self._send_raid_sendouts(interaction, battle)

            field_embed = self._create_field_effects_embed(battle)

            if battle_begin_embed:
                await interaction.followup.send(embed=battle_begin_embed)
                await asyncio.sleep(1)

            if field_embed:
                await interaction.followup.send(embed=field_embed)
                await asyncio.sleep(1)

            await interaction.followup.send(embed=status_embed)
            await asyncio.sleep(1)
            await interaction.followup.send(embed=party_embed, view=view)
            return

        # 1) Opening embed: differentiate wild encounters vs trainer battles
        if battle_mode == BattleType.WILD:
            enc_title = f"{SWORD} Encounter!"
            # Show all wild pokemon for doubles/multi battles
            if len(opponent_active) > 1:
                pokemon_names = " and ".join([f"**{mon.species_name}**" for mon in opponent_active])
                enc_description = f"You encountered wild {pokemon_names}!"
            else:
                enc_description = f"You encountered a wild **{opponent_active[0].species_name}**!"
        elif battle.battle_format == BattleFormat.MULTI:
            enc_title = f"{SWORD} Multi Battle Start!"
            # Show team composition
            team1_names = f"**{battle.trainer.battler_name}**"
            if battle.trainer_partner:
                team1_names += f" & **{battle.trainer_partner.battler_name}**"
            team2_names = f"**{battle.opponent.battler_name}**"
            if battle.opponent_partner:
                team2_names += f" & **{battle.opponent_partner.battler_name}**"
            enc_description = f"{team1_names} challenge {team2_names} to a multi battle!"
        else:
            enc_title = f"{SWORD} Battle Start!"
            enc_description = (
                f"**{battle.trainer.battler_name}** challenges "
                f"**{battle.opponent.battler_name}** to a battle!"
            )

        enc = discord.Embed(
            title=enc_title,
            description=enc_description,
            color=discord.Color.blue()
        )

        # Add sprite for wild encounters
        if battle_mode == BattleType.WILD and opponent_active:
            sprite_url = PokemonSpriteHelper.get_sprite(
                opponent_active[0].species_name,
                opponent_active[0].species_dex_number,
                style='animated',
                gender=getattr(opponent_active[0], 'gender', None),
                shiny=getattr(opponent_active[0], 'is_shiny', False),
                use_fallback=False
            )
            enc.set_thumbnail(url=sprite_url)

        enc.set_footer(text=f"Build: {BUILD_TAG}")
        await interaction.followup.send(embed=enc)

        # 2) Send-out + entry effects - separate embeds for each Pokemon

        # Gather entry messages to show once after all send-outs
        entry_messages = list(getattr(battle, "entry_messages", []) or [])

        # Send out trainer's Pokemon first (one embed per Pokemon)
        for idx, mon in enumerate(trainer_active):
            position_text = f" (Slot {idx+1})" if len(trainer_active) > 1 else ""
            description = f"**{battle.trainer.battler_name}** sent out **{mon.species_name}**{position_text}!"

            send_embed = discord.Embed(
                title="Send-out",
                description=description,
                color=discord.Color.blurple()
            )

            # Add sprite
            sprite_url = PokemonSpriteHelper.get_sprite(
                mon.species_name,
                mon.species_dex_number,
                style='animated',
                gender=getattr(mon, 'gender', None),
                shiny=getattr(mon, 'is_shiny', False),
                use_fallback=False
            )
            send_embed.set_thumbnail(url=sprite_url)

            await interaction.followup.send(embed=send_embed)
            await asyncio.sleep(1)

        # For multi battles, also send out partner's Pokemon
        if battle.battle_format == BattleFormat.MULTI and battle.trainer_partner:
            partner_active = battle.trainer_partner.get_active_pokemon()
            for idx, mon in enumerate(partner_active):
                position_text = f" (Slot {idx+1})" if len(partner_active) > 1 else ""
                description = f"**{battle.trainer_partner.battler_name}** sent out **{mon.species_name}**{position_text}!"

                send_embed = discord.Embed(
                    title="Send-out",
                    description=description,
                    color=discord.Color.blurple()
                )

                # Add sprite
                sprite_url = PokemonSpriteHelper.get_sprite(
                    mon.species_name,
                    mon.species_dex_number,
                    style='animated',
                    gender=getattr(mon, 'gender', None),
                    shiny=getattr(mon, 'is_shiny', False),
                    use_fallback=False
                )
                send_embed.set_thumbnail(url=sprite_url)

                await interaction.followup.send(embed=send_embed)
                await asyncio.sleep(1)

        # For trainer battles, also send out opponent's Pokemon (one embed per Pokemon)
        if battle_mode != BattleType.WILD:
            for idx, mon in enumerate(opponent_active):
                position_text = f" (Slot {idx+1})" if len(opponent_active) > 1 else ""
                description = f"**{battle.opponent.battler_name}** sent out **{mon.species_name}**{position_text}!"

                send_embed = discord.Embed(
                    title="Send-out",
                    description=description,
                    color=discord.Color.blurple()
                )

                # Add sprite
                sprite_url = PokemonSpriteHelper.get_sprite(
                    mon.species_name,
                    mon.species_dex_number,
                    style='animated',
                    gender=getattr(mon, 'gender', None),
                    shiny=getattr(mon, 'is_shiny', False),
                    use_fallback=False
                )
                send_embed.set_thumbnail(url=sprite_url)

                await interaction.followup.send(embed=send_embed)
                await asyncio.sleep(1)

            # For multi battles, also send out opponent partner's Pokemon
            if battle.battle_format == BattleFormat.MULTI and battle.opponent_partner:
                partner_active = battle.opponent_partner.get_active_pokemon()
                for idx, mon in enumerate(partner_active):
                    position_text = f" (Slot {idx+1})" if len(partner_active) > 1 else ""
                    description = f"**{battle.opponent_partner.battler_name}** sent out **{mon.species_name}**{position_text}!"

                    send_embed = discord.Embed(
                        title="Send-out",
                        description=description,
                        color=discord.Color.blurple()
                    )

                    # Add sprite
                    sprite_url = PokemonSpriteHelper.get_sprite(
                        mon.species_name,
                        mon.species_dex_number,
                        style='animated',
                        gender=getattr(mon, 'gender', None),
                        shiny=getattr(mon, 'is_shiny', False),
                        use_fallback=False
                    )
                    send_embed.set_thumbnail(url=sprite_url)

                    await interaction.followup.send(embed=send_embed)
                    await asyncio.sleep(1)

        # If there are entry messages or field effects, send them in a final embed
        field_embed = self._create_field_effects_embed(battle, entry_messages)
        if field_embed:
            await interaction.followup.send(embed=field_embed)
            await asyncio.sleep(1)

        # 3) Main action embed + view
        main_embed = self._create_battle_embed(battle)
        view = self._create_battle_view(battle)
        await interaction.followup.send(embed=main_embed, view=view)

    # --------------------
    # Helpers
    # --------------------
    def _hp_bar(self, mon) -> str:
        try:
            filled = int(round(10 * max(0, mon.current_hp) / max(1, mon.max_hp)))
        except Exception:
            filled = 0
        return ("🟩" * filled) + ("⬜" * (10 - filled))

    def _create_field_effects_embed(self, battle, entry_messages: Optional[list[str]] = None) -> Optional[discord.Embed]:
        entry_messages = entry_messages or list(getattr(battle, "entry_messages", []) or [])

        if not (entry_messages or getattr(battle, "weather", None) or getattr(battle, "terrain", None)):
            return None

        effects_embed = discord.Embed(
            title=f"{FIELD} Field Effects",
            color=discord.Color.blurple()
        )

        if entry_messages:
            effects_embed.description = "\n".join([f"• {msg}" for msg in entry_messages])

        fields = []
        if getattr(battle, "weather", None):
            wt = getattr(battle, "weather_turns", None)
            # Only show turn count for player-set weather (5-8 turns), not permanent rogue weather (99+ turns)
            turns_text = f" ({wt} turns)" if wt and wt < 99 else ""
            fields.append(f"Weather: **{battle.weather.title()}**{turns_text}")
        if getattr(battle, "terrain", None):
            tt = getattr(battle, "terrain_turns", None)
            fields.append(f"Terrain: **{battle.terrain.title()}**" + (f" ({tt} turns)" if tt else ""))

        if fields:
            effects_embed.add_field(name="Conditions", value="\n".join(fields), inline=False)

        return effects_embed

    def _get_pokeball_id(self, mon) -> str:
        if hasattr(mon, 'pokeball') and getattr(mon, 'pokeball'):
            return getattr(mon, 'pokeball') or DEFAULT_POKEBALL_ID

        if isinstance(mon, dict) and mon.get('pokeball'):
            return mon.get('pokeball') or DEFAULT_POKEBALL_ID

        return DEFAULT_POKEBALL_ID

    def _get_pokeball_emoji(self, mon) -> str:
        ball_id = (self._get_pokeball_id(mon) or DEFAULT_POKEBALL_ID).lower()
        return POKEBALL_EMOJIS.get(ball_id, POKEBALL_EMOJIS.get(DEFAULT_POKEBALL_ID, BALL))

    def _held_item_text(self, mon) -> Optional[str]:
        item_id = getattr(mon, 'held_item', None)
        if not item_id:
            return None
        return item_id.replace('_', ' ').title()

    def _create_battle_embed(self, battle) -> discord.Embed:
        if battle.battle_format == BattleFormat.RAID:
            return self._create_raid_status_embed(battle)

        trainer_active = battle.trainer.get_active_pokemon()
        opponent_active = battle.opponent.get_active_pokemon()

        is_doubles = battle.battle_format == BattleFormat.DOUBLES
        is_multi = battle.battle_format == BattleFormat.MULTI

        # Determine title
        if is_multi:
            title = f"{SWORD} Multi Battle"
        elif is_doubles:
            title = f"{SWORD} Doubles Battle"
        else:
            title = f"{SWORD} Battle"

        e = discord.Embed(
            title=title,
            description=f"**Turn {battle.turn_number}**",
            color=discord.Color.dark_grey()
        )

        # For multi battles, show both opponents
        if is_multi:
            # Show opponent team leader's Pokemon (exclude fainted)
            for idx, opp_mon in enumerate(opponent_active):
                if opp_mon.current_hp <= 0:
                    continue
                opp_value = f"HP: {self._hp_bar(opp_mon)} ({max(0, opp_mon.current_hp)}/{opp_mon.max_hp})"
                foe_name = self._format_pokemon_name(opp_mon)
                foe_ball = self._get_pokeball_emoji(opp_mon)
                e.add_field(
                    name=f"{foe_ball} {battle.opponent.battler_name}'s {foe_name}",
                    value=opp_value,
                    inline=True
                )

            # Show opponent partner's Pokemon (exclude fainted)
            if battle.opponent_partner:
                partner_active = battle.opponent_partner.get_active_pokemon()
                for idx, partner_mon in enumerate(partner_active):
                    if partner_mon.current_hp <= 0:
                        continue
                    partner_value = f"HP: {self._hp_bar(partner_mon)} ({max(0, partner_mon.current_hp)}/{partner_mon.max_hp})"
                    partner_name = self._format_pokemon_name(partner_mon)
                    partner_ball = self._get_pokeball_emoji(partner_mon)
                    e.add_field(
                        name=f"{partner_ball} {battle.opponent_partner.battler_name}'s {partner_name}",
                        value=partner_value,
                        inline=True
                    )

            # Add separator
            e.add_field(name="\u200b", value="\u200b", inline=False)

            # Show player team leader's Pokemon (exclude fainted)
            for idx, trainer_mon in enumerate(trainer_active):
                if trainer_mon.current_hp <= 0:
                    continue
                trainer_value = f"HP: {self._hp_bar(trainer_mon)} ({max(0, trainer_mon.current_hp)}/{trainer_mon.max_hp})"
                trainer_name = self._format_pokemon_name(trainer_mon)
                trainer_ball = self._get_pokeball_emoji(trainer_mon)
                e.add_field(
                    name=f"{trainer_ball} {battle.trainer.battler_name}'s {trainer_name}",
                    value=trainer_value,
                    inline=True
                )

            # Show player partner's Pokemon (exclude fainted)
            if battle.trainer_partner:
                partner_active = battle.trainer_partner.get_active_pokemon()
                for idx, partner_mon in enumerate(partner_active):
                    if partner_mon.current_hp <= 0:
                        continue
                    partner_value = f"HP: {self._hp_bar(partner_mon)} ({max(0, partner_mon.current_hp)}/{partner_mon.max_hp})"
                    partner_name = self._format_pokemon_name(partner_mon)
                    partner_ball = self._get_pokeball_emoji(partner_mon)
                    e.add_field(
                        name=f"{partner_ball} {battle.trainer_partner.battler_name}'s {partner_name}",
                        value=partner_value,
                        inline=True
                    )
        else:
            # Standard singles/doubles display
            # Show all active opponent Pokemon (exclude fainted)
            active_opponent_count = 0
            for idx, opp_mon in enumerate(opponent_active):
                if opp_mon.current_hp <= 0:
                    continue
                opp_value = f"HP: {self._hp_bar(opp_mon)} ({max(0, opp_mon.current_hp)}/{opp_mon.max_hp})"

                position_label = f" (Slot {idx+1})" if is_doubles else ""
                opp_name = self._format_pokemon_name(opp_mon)
                opp_ball = self._get_pokeball_emoji(opp_mon)
                e.add_field(
                    name=f"{opp_ball} {opp_name}{position_label}",
                    value=opp_value,
                    inline=is_doubles
                )
                active_opponent_count += 1

            # Add blank separator for doubles to force player Pokemon to new row
            if is_doubles and active_opponent_count > 0:
                e.add_field(name="\u200b", value="\u200b", inline=False)

            # Show all active trainer Pokemon (exclude fainted)
            for idx, trainer_mon in enumerate(trainer_active):
                if trainer_mon.current_hp <= 0:
                    continue
                trainer_value = f"HP: {self._hp_bar(trainer_mon)} ({max(0, trainer_mon.current_hp)}/{trainer_mon.max_hp})"

                position_label = f" (Slot {idx+1})" if is_doubles else ""
                trainer_name = self._format_pokemon_name(trainer_mon)
                trainer_ball = self._get_pokeball_emoji(trainer_mon)
                e.add_field(
                    name=f"{trainer_ball} {trainer_name}{position_label}",
                    value=trainer_value,
                    inline=is_doubles
                )
        if getattr(battle, "recent_events", None):
            e.add_field(name=f"{EVENTS} Recent Events", value="\n".join(battle.recent_events[-5:]), inline=False)
        if getattr(battle, "weather", None) or getattr(battle, "terrain", None):
            lines = []
            if getattr(battle, "weather", None):
                weather_turns = getattr(battle, "weather_turns", 0)
                # Only show turn count for player-set weather (5-8 turns), not permanent rogue weather (99+ turns)
                turns_text = f" ({weather_turns} turns left)" if weather_turns > 0 and weather_turns < 99 else ""
                lines.append(f"Weather: **{battle.weather.title()}**{turns_text}")
            if getattr(battle, "terrain", None):
                terrain_turns = getattr(battle, "terrain_turns", 0)
                turns_text = f" ({terrain_turns} turns left)" if terrain_turns > 0 else ""
                lines.append(f"Terrain: **{battle.terrain.title()}**{turns_text}")
            e.add_field(name=f"{FIELD} Field Effects", value="\n".join(lines), inline=False)
        e.set_footer(text=f"Build: {BUILD_TAG}")
        return e

    def _create_battle_view(self, battle) -> discord.ui.View:
        return BattleActionView(battle.battle_id, battle.trainer.battler_id, self.battle_engine, battle, self)

    def _format_pokemon_name(self, pokemon, include_level: bool = True) -> str:
        return _format_battle_pokemon_name(pokemon, include_level=include_level)

    def _build_raid_hp_bars(self, mon) -> str:
        if not getattr(mon, "is_raid_boss", False):
            return self._hp_bar(mon)

        total_segments = min(3, max(1, math.ceil(getattr(mon, "level", 1) / 100)))
        hp_ratio = max(0.0, getattr(mon, "current_hp", 0) / max(1, getattr(mon, "max_hp", 1)))
        segment_size = 1 / total_segments

        bars: list[str] = []
        for idx in range(total_segments):
            filled_ratio = min(segment_size, max(0.0, hp_ratio - (idx * segment_size))) / segment_size
            bars.append(EmbedBuilder._create_hp_bar(filled_ratio * 100, length=30))

        return "\n".join(bars)

    def _create_raid_status_embed(self, battle) -> discord.Embed:
        active_raids = [
            mon for mon in (battle.opponent.get_active_pokemon() or [])
            if getattr(mon, "current_hp", 0) > 0
        ]
        if not active_raids:
            return discord.Embed(title="Raid Battle", description="Prepare for battle!", color=discord.Color.dark_red())

        if len(active_raids) == 1:
            raid_mon = active_raids[0]
            hp_bars = self._build_raid_hp_bars(raid_mon)
            type_list = getattr(raid_mon, "species_data", {}).get("types", [])
            type_emojis = " ".join([EmbedBuilder._type_to_emoji(t) for t in type_list])

            embed = discord.Embed(
                title=f"{self._format_pokemon_name(raid_mon)}",
                description=(
                    f"**HP** {type_emojis}\n{hp_bars}\n"
                    f"**{max(0, int(getattr(raid_mon, 'current_hp', 0)))}/{int(getattr(raid_mon, 'max_hp', 1))}**"
                ),
                color=discord.Color.dark_red(),
            )

            sprite_url = PokemonSpriteHelper.get_sprite(
                getattr(raid_mon, "species_name", None),
                getattr(raid_mon, "species_dex_number", None),
                style='animated',
                gender=getattr(raid_mon, 'gender', None),
                shiny=getattr(raid_mon, 'is_shiny', False),
                use_fallback=False
            )
            if sprite_url:
                embed.set_thumbnail(url=sprite_url)

            return embed

        embed = discord.Embed(
            title="Enemies",
            description=f"**Turn {battle.turn_number}**",
            color=discord.Color.dark_red(),
        )

        for idx, raid_mon in enumerate(active_raids):
            hp_bars = self._build_raid_hp_bars(raid_mon)
            type_list = getattr(raid_mon, "species_data", {}).get("types", [])
            type_emojis = " ".join([EmbedBuilder._type_to_emoji(t) for t in type_list])
            embed.add_field(
                name=self._format_pokemon_name(raid_mon),
                value=(
                    f"**HP** {type_emojis}\n{hp_bars}\n"
                    f"**{max(0, int(getattr(raid_mon, 'current_hp', 0)))}/{int(getattr(raid_mon, 'max_hp', 1))}**"
                ),
                inline=True,
            )

            if (idx + 1) % 4 == 0:
                embed.add_field(name="\u200b", value="\u200b", inline=False)

        return embed

    def _create_raid_party_embed(self, battle) -> discord.Embed:
        embed = discord.Embed(
            title="Allies",
            description=f"**Turn {battle.turn_number}**",
            color=discord.Color.blurple(),
        )

        participants = getattr(battle, "raid_participants", [])
        entries: list[tuple[str, Any]] = []
        participant_map = {p.get("user_id"): p.get("trainer_name") for p in participants}

        for battler in battle.get_all_battlers():
            if getattr(battler, "is_ai", False):
                continue

            active_mon = next((m for m in battler.get_active_pokemon() if getattr(m, "current_hp", 0) > 0), None)
            if not active_mon:
                active_mon = next((m for m in battler.party if getattr(m, "current_hp", 0) > 0), None)
            if not active_mon:
                continue

            trainer_name = participant_map.get(battler.battler_id) or getattr(battler, "battler_name", "Trainer")
            entries.append((trainer_name, active_mon))
            if len(entries) >= 8:
                break

        for idx, (trainer_name, mon) in enumerate(entries):
            hp_value = f"HP: {self._hp_bar(mon)} ({max(0, mon.current_hp)}/{mon.max_hp})"
            mon_name = self._format_pokemon_name(mon, include_level=False)
            ball = self._get_pokeball_emoji(mon)
            embed.add_field(
                name=f"{ball} {trainer_name}'s {mon_name}",
                value=hp_value,
                inline=True,
            )

            if (idx + 1) % 4 == 0:
                embed.add_field(name="\u200b", value="\u200b", inline=False)

        return embed

    def _create_raid_sprite_embed(self, raid_mon) -> Optional[discord.Embed]:
        if not raid_mon or not getattr(raid_mon, "is_raid_boss", False):
            return None

        embed = discord.Embed(
            title=f"{self._format_pokemon_name(raid_mon, include_level=False)} looms large!",
            color=discord.Color.dark_red(),
        )
        sprite_url = PokemonSpriteHelper.get_sprite(
            getattr(raid_mon, "species_name", None),
            getattr(raid_mon, "species_dex_number", None),
            style='official',
            gender=getattr(raid_mon, 'gender', None),
            shiny=getattr(raid_mon, 'is_shiny', False),
            use_fallback=False,
        )
        if sprite_url:
            embed.set_image(url=sprite_url)
        return embed

    async def _send_raid_intro(
        self,
        interaction: discord.Interaction,
        opponent_active: list[Any],
    ) -> Optional[discord.Embed]:
        raid_mon = opponent_active[0] if opponent_active else None
        if raid_mon and not getattr(raid_mon, "is_raid_boss", False):
            if len(opponent_active) > 1:
                counts = {}
                for mon in opponent_active:
                    counts[mon.species_name] = counts.get(mon.species_name, 0) + 1
                if len(counts) == 1:
                    species_name = next(iter(counts))
                    count = counts[species_name]
                    enc_description = f"**{count}** wild **{species_name}** appeared!"
                else:
                    pokemon_names = " and ".join([f"**{mon.species_name}**" for mon in opponent_active])
                    enc_description = f"You encountered wild {pokemon_names}!"
            else:
                enc_description = f"You encountered a wild **{raid_mon.species_name}**!"

            embed = discord.Embed(
                title=f"{SWORD} Encounter!",
                description=enc_description,
                color=discord.Color.blue(),
            )
            sprite_target = raid_mon
            if sprite_target:
                sprite_url = PokemonSpriteHelper.get_sprite(
                    getattr(sprite_target, "species_name", None),
                    getattr(sprite_target, "species_dex_number", None),
                    style='official',
                    gender=getattr(sprite_target, 'gender', None),
                    shiny=getattr(sprite_target, 'is_shiny', False),
                    use_fallback=False,
                )
                if sprite_url:
                    embed.set_thumbnail(url=sprite_url)
            await interaction.followup.send(embed=embed)
            return None

        name = getattr(raid_mon, "species_name", "The Pokémon") if raid_mon else "The foe"
        formatted_name = self._format_pokemon_name(raid_mon, include_level=False) if raid_mon else name

        lead_embeds = [
            discord.Embed(
                description="\n".join(
                    [
                        f"The {formatted_name} gathers and absorbs dreamlites…",
                        ". . .",
                    ]
                ),
                color=discord.Color.purple(),
            ),
            discord.Embed(
                description="\n".join(
                    [
                        "***!!!***",
                        f"The {formatted_name} erupts with power!",
                    ]
                ),
                color=discord.Color.dark_red(),
            ),
        ]

        for embed in lead_embeds:
            await interaction.followup.send(embed=embed)
            await asyncio.sleep(1)

        return discord.Embed(
            description="***RAID BATTLE - BEGIN!!!***",
            color=discord.Color.gold(),
        )

    async def _send_raid_sendouts(self, interaction: discord.Interaction, battle):
        participants = getattr(battle, "raid_participants", [])
        if not participants:
            return

        for entry in participants:
            trainer_name = entry.get("trainer_name") or "Trainer"
            party = entry.get("party") or []
            if not party:
                continue

            lead = None
            for mon in party:
                if getattr(mon, "current_hp", 0) > 0:
                    lead = mon
                    break

            if not lead:
                continue

            send_embed = discord.Embed(
                title="Send-out",
                description=f"**{trainer_name}** sent out **{lead.species_name}**!",
                color=discord.Color.blurple(),
            )

            sprite_url = PokemonSpriteHelper.get_sprite(
                lead.species_name,
                lead.species_dex_number,
                style='animated',
                gender=getattr(lead, 'gender', None),
                shiny=getattr(lead, 'is_shiny', False),
                use_fallback=False,
            )
            if sprite_url:
                send_embed.set_thumbnail(url=sprite_url)

            await interaction.followup.send(embed=send_embed)
            await asyncio.sleep(1)

    @staticmethod
    def _split_faint_messages(messages: list[str]) -> tuple[list[str], list[str]]:
        action_msgs: list[str] = []
        faint_msgs: list[str] = []

        for msg in messages:
            if not msg:
                continue

            if "fainted" in msg.lower():
                faint_msgs.append(msg)
            else:
                action_msgs.append(msg)

        return action_msgs, faint_msgs

    async def _safe_followup_send(self, interaction: discord.Interaction, **kwargs):
        """Send a message to the channel without creating reply chains."""
        # Send directly to channel to avoid reply chains
        if interaction.channel:
            try:
                await interaction.channel.send(**kwargs)
            except Exception:
                # Fallback to interaction response if channel send fails
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(**kwargs)
                    else:
                        await interaction.followup.send(**kwargs)
                except Exception:
                    pass  # If all methods fail, silently ignore
        else:
            # No channel available, use interaction followup as fallback
            try:
                await interaction.followup.send(**kwargs)
            except Exception:
                if not interaction.response.is_done():
                    await interaction.response.send_message(**kwargs)

    def _build_turn_embeds(self, turn_result: dict) -> list[discord.Embed]:
        events = turn_result.get("action_events") or []
        embeds: list[discord.Embed] = []

        if not events:
            messages = turn_result.get("messages") or []
            action_msgs, faint_msgs = self._split_faint_messages(messages)
            embeds.append(self._build_action_embed(action_msgs, title="Turn Result"))
            if faint_msgs:
                fainted_species = self._extract_fainted_species(faint_msgs)
                embeds.append(
                    self._build_action_embed(
                        faint_msgs,
                        title="Pokémon Fainted",
                        color=discord.Color.red(),
                        species_name=fainted_species
                    )
                )
            return [emb for emb in embeds if emb]

        for event in events:
            raw_messages = event.get("messages") or []
            action_msgs, faint_msgs = self._split_faint_messages(raw_messages)

            if action_msgs:
                event_type = event.get("type")
                custom_title = event.get("title")
                custom_color = event.get("color")
                description_override = event.get("description_override")

                if custom_title:
                    title = custom_title
                    color = custom_color or discord.Color.orange()
                elif event_type == "end_of_turn":
                    title = "End of Turn"
                    color = discord.Color.orange()
                elif event_type == "omni_ring":
                    title = "Omni Ring"
                    color = discord.Color.gold()
                elif event_type == "mega_evolve":
                    # Use base_name if available to avoid "Mega Mawile Mega Evolved"
                    base_name = event.get("base_name")
                    if not base_name:
                        actor = event.get("actor")
                        actor_name = self._format_pokemon_name(actor, include_level=False) if actor else "Pokémon"
                    else:
                        actor_name = base_name
                    title = f"{actor_name} Mega Evolved!!!"
                    color = discord.Color.purple()
                else:
                    actor = event.get("actor")
                    actor_name = self._format_pokemon_name(actor, include_level=False) if actor else "Action"
                    title = f"{actor_name}'s Turn" if actor else "Turn"
                    color = discord.Color.orange()

                if event_type == "omni_ring":
                    omni_title = action_msgs[0] if action_msgs else title
                    embed = self._build_action_embed(
                        [],
                        title=omni_title,
                        color=color,
                        trainer=event.get("trainer"),
                        description_override="",
                    )
                elif event_type == "mega_evolve":
                    embed = self._build_action_embed(
                        [],
                        title=title,
                        color=color,
                        pokemon=None,
                        description_override="",
                    )
                    mega_art_url = self._get_mega_art_url(event.get("actor"))
                    if embed and mega_art_url:
                        embed.set_image(url=mega_art_url)
                else:
                    embed = self._build_action_embed(
                        action_msgs,
                        title=title,
                        color=color,
                        pokemon=event.get("actor"),
                        description_override=description_override,
                    )
                if embed:
                    embeds.append(embed)

            if faint_msgs:
                fainted_species = self._extract_fainted_species(faint_msgs)
                faint_embed = self._build_action_embed(
                    faint_msgs,
                    title="Pokémon Fainted",
                    color=discord.Color.red(),
                    species_name=fainted_species
                )
                if faint_embed:
                    embeds.append(faint_embed)

        if not embeds:
            messages = turn_result.get("messages") or []
            action_msgs, faint_msgs = self._split_faint_messages(messages)
            fallback = self._build_action_embed(action_msgs, title="Turn Result")
            if fallback:
                embeds.append(fallback)
            if faint_msgs:
                fainted_species = self._extract_fainted_species(faint_msgs)
                faint_fallback = self._build_action_embed(
                    faint_msgs,
                    title="Pokémon Fainted",
                    color=discord.Color.red(),
                    species_name=fainted_species
                )
                if faint_fallback:
                    embeds.append(faint_fallback)

        return embeds

    def _build_action_embed(
        self,
        messages: Optional[list[str]],
        title: str,
        color: Optional[discord.Color] = None,
        pokemon=None,
        trainer=None,
        species_name: Optional[str] = None,
        description_override: Optional[str] = None,
    ) -> Optional[discord.Embed]:
        if not messages and description_override is None:
            return None
        if description_override is not None:
            desc = description_override
        else:
            spaced = []
            for msg in messages or []:
                if msg is None:
                    continue
                spaced.append(str(msg))
                spaced.append("")
            if spaced and spaced[-1] == "":
                spaced.pop()
            desc = "\n".join(spaced) if spaced else "The turn resolves."
        embed = discord.Embed(title=title, description=desc, color=color or discord.Color.orange())
        trainer_avatar = self._resolve_trainer_avatar_url(trainer)
        if trainer_avatar:
            embed.set_thumbnail(url=trainer_avatar)
        else:
            sprite_url = self._get_action_sprite_url(pokemon=pokemon, species_name=species_name)
            if sprite_url:
                embed.set_thumbnail(url=sprite_url)
        return embed

    def _resolve_trainer_avatar_url(self, trainer) -> Optional[str]:
        if not trainer:
            return None
        avatar_url = getattr(trainer, "avatar_url", None)
        if avatar_url:
            return avatar_url
        battler_id = getattr(trainer, "battler_id", None)
        if battler_id is None:
            return None
        player_manager = getattr(self.bot, "player_manager", None)
        if player_manager:
            profile = player_manager.get_player(battler_id)
            avatar_url = getattr(profile, "avatar_url", None) if profile else None
            if avatar_url:
                return avatar_url
        return None

    def _get_action_sprite_url(self, pokemon=None, species_name: Optional[str] = None) -> Optional[str]:
        if pokemon:
            sprite_url = PokemonSpriteHelper.get_sprite(
                getattr(pokemon, "species_name", None),
                getattr(pokemon, "species_dex_number", None),
                style='animated',
                gender=getattr(pokemon, 'gender', None),
                shiny=getattr(pokemon, 'is_shiny', False),
                use_fallback=False
            )
            return sprite_url
        if species_name:
            return PokemonSpriteHelper.get_sprite(
                species_name,
                None,
                style='animated',
                shiny=False,
                use_fallback=False
            )
        return None

    def _get_mega_art_url(self, pokemon) -> Optional[str]:
        if not pokemon:
            return None
        # Use gen5 animated sprites for mega evolution
        sprite_url = PokemonSpriteHelper.get_sprite(
            getattr(pokemon, "species_name", None),
            getattr(pokemon, "species_dex_number", None),
            style='animated',
            gender=getattr(pokemon, 'gender', None),
            shiny=getattr(pokemon, 'is_shiny', False),
            use_fallback=False,
        )
        return sprite_url

    def _extract_fainted_species(self, messages: list[str]) -> Optional[str]:
        for msg in messages:
            if not msg:
                continue
            match = re.search(r"(.+?) fainted!", str(msg), flags=re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                if name.lower().startswith("the wild "):
                    name = name[9:]
                if name.lower() in {"the pokémon", "the pokemon"}:
                    return None
                return name
        return None

    def _build_switch_embed(self, messages: list[str], title: str = "Switch", color: Optional[discord.Color] = None, pokemon=None):
        if not messages:
            return None
        embed_color = color or (discord.Color.blurple() if title == "Send-out" else discord.Color.teal())
        embed = discord.Embed(title=title, description="\n".join(messages), color=embed_color)

        if pokemon:
            sprite_url = PokemonSpriteHelper.get_sprite(
                getattr(pokemon, "species_name", None),
                getattr(pokemon, "species_dex_number", None),
                style='animated',
                gender=getattr(pokemon, 'gender', None),
                shiny=getattr(pokemon, 'is_shiny', False),
                use_fallback=False
            )
            if sprite_url:
                embed.set_thumbnail(url=sprite_url)

        return embed

    async def _send_turn_resolution(self, interaction: discord.Interaction, turn_result: dict):
        switch_events = turn_result.get("switch_events")
        if switch_events is None:
            switch_msgs = [msg for msg in (turn_result.get('switch_messages') or []) if msg]
            switch_events = ([{"messages": switch_msgs}] if switch_msgs else [])

        manual_switch_events = [event for event in (switch_events or []) if event.get("source") == "manual"]
        auto_switch_events = [event for event in (switch_events or []) if event.get("source") != "manual"]

        async def send_switch_events(events: list[dict]):
            for event in events:
                embed = self._build_switch_embed(event.get("messages") or [], pokemon=event.get("pokemon"))

                if embed:
                    await self._safe_followup_send(interaction, embed=embed)
                    await asyncio.sleep(1)

        await send_switch_events(manual_switch_events)

        action_embeds = self._build_turn_embeds(turn_result)
        for embed in action_embeds:
            await self._safe_followup_send(interaction, embed=embed)
            await asyncio.sleep(1)

        await send_switch_events(auto_switch_events)

    async def _show_rp_mode_execution_prompt(self, interaction: discord.Interaction, battle):
        """Show the 'Both players have chosen their actions. Awaiting execution.' embed with Go button."""
        # Only show once - check if we already have an execution message
        if battle.rp_mode_execution_message_id:
            # Message already exists, don't create a new one
            return

        embed = discord.Embed(
            title="🎭 Actions Chosen - Ready to Execute!",
            description="Both trainers have chosen their actions!\n\n"
                       "**Take your time to roleplay the turn!**\n"
                       "When both players are ready to see the results, press the **Go!** button below.\n\n"
                       "⏰ *Tip: Use `/rp_go` command if the button expires*",
            color=discord.Color.gold()
        )

        view = RPModeExecutionView(battle.battle_id, self.battle_engine, self)

        # Send to the channel (not ephemeral, so both players can see it)
        try:
            msg = await interaction.channel.send(embed=embed, view=view)
            battle.rp_mode_execution_message_id = msg.id
        except Exception:
            # Fallback to followup if channel send fails
            msg = await interaction.followup.send(embed=embed, view=view)
            battle.rp_mode_execution_message_id = msg.id

    async def _prompt_forced_switch(self, interaction: discord.Interaction, battle, battler_id: int):
        # Always refresh the battle state to avoid stale active slots or parties
        fresh_battle = self.battle_engine.get_battle(getattr(battle, 'battle_id', None)) or battle
        battle = fresh_battle
        battler = _get_battler_by_id(battle, battler_id)
        if not battler:
            await interaction.followup.send(
                "Waiting for your opponent to choose their next Pokémon...",
                ephemeral=True,
            )
            return

        if getattr(battler, "is_ai", False):
            await interaction.followup.send(
                "Waiting for your opponent to choose their next Pokémon...",
                ephemeral=True,
            )
            return

        # Safety check: Don't prompt eliminated battlers (those with no Pokemon left)
        if getattr(battler, 'is_eliminated', False):
            print(f"[DEBUG] Battler {battler_id} is eliminated, skipping switch prompt")
            # Remove from pending switches since they can't switch
            if battler_id in battle.pending_switches:
                del battle.pending_switches[battler_id]
            await interaction.followup.send(
                "Your Pokémon have been defeated. Waiting for the battle to conclude...",
                ephemeral=True,
            )
            return

        # Check if this is a U-turn/Volt Switch or a fainted Pokemon
        # First check the new pending_switches dict
        is_volt_switch = False
        if battler_id in battle.pending_switches:
            switch_info = battle.pending_switches[battler_id]
            is_volt_switch = switch_info.get('switch_type') == 'VOLT'
        else:
            # Fall back to old logic
            is_volt_switch = battle.phase == 'VOLT_SWITCH'

        switch_info = battle.pending_switches.get(battler_id, {})
        switch_position = switch_info.get("position")
        active_pokemon = battler.get_active_pokemon()
        active_target = None
        if switch_position is not None and switch_position < len(active_pokemon):
            active_target = active_pokemon[switch_position]
        elif active_pokemon:
            active_target = active_pokemon[0]

        if is_volt_switch:
            # U-turn/Volt Switch case
            if active_target:
                desc = (
                    f"**{self._format_pokemon_name(active_target, include_level=False)}** will switch out!\n\n"
                    "Select another Pokémon to switch in."
                )
            else:
                desc = "Select a Pokémon to switch in."
            embed = discord.Embed(title="Switch Required!", description=desc, color=discord.Color.blue())
        else:
            # Fainted Pokemon case
            if active_target:
                desc = (
                    f"**{self._format_pokemon_name(active_target, include_level=False)}** can no longer fight!\n\n"
                    "Select another healthy Pokémon to continue the battle."
                )
            else:
                desc = "Select another healthy Pokémon to continue the battle."
            embed = discord.Embed(title="Pokémon Fainted!", description=desc, color=discord.Color.red())

        # Send public message with player ping, buttons are restricted to the correct player
        await self._safe_followup_send(
            interaction,
            content=f"<@{battler_id}>",
            embed=embed,
            view=PartySelectView(battle, battler_id, self.battle_engine, forced=True)
        )

    async def _finish_battle(self, interaction: discord.Interaction, battle):
        trainer_name = getattr(battle.trainer, 'battler_name', 'Trainer')
        opponent_name = getattr(battle.opponent, 'battler_name', 'Opponent')
        trainer_has_pokemon = battle.trainer.has_usable_pokemon()
        opponent_has_pokemon = battle.opponent.has_usable_pokemon()

        if battle.winner is None:
            if trainer_has_pokemon and not opponent_has_pokemon:
                battle.winner = 'trainer'
            elif opponent_has_pokemon and not trainer_has_pokemon:
                battle.winner = 'opponent'
            elif not trainer_has_pokemon and not opponent_has_pokemon:
                battle.winner = 'draw'

        result = battle.winner
        if result == 'trainer':
            winner_name, loser_name = trainer_name, opponent_name
        elif result == 'opponent':
            winner_name, loser_name = opponent_name, trainer_name
        else:
            desc = "It's a draw!"
            await self._safe_followup_send(
                interaction,
                embed=discord.Embed(title='The Battle Has Been Decided!', description=desc, color=discord.Color.gold())
            )
            self.battle_engine.end_battle(battle.battle_id)
            self._unregister_battle(battle)
            return

        try:
            from database import PlayerDatabase
            pdb = PlayerDatabase('data/players.db')

            def _persist_battler_party_hp(battler):
                if not battler or battler.is_ai:
                    return
                party_rows = pdb.get_trainer_party(battler.battler_id)
                rows_by_pos = {row.get('party_position', i): row for i, row in enumerate(party_rows)}
                for i, mon in enumerate(battler.party):
                    pokemon_id = getattr(mon, 'pokemon_id', None)
                    if pokemon_id:
                        pdb.update_pokemon(
                            pokemon_id,
                            {'current_hp': max(0, int(getattr(mon, 'current_hp', 0)))},
                        )
                        continue
                    row = rows_by_pos.get(i) or rows_by_pos.get(getattr(mon, 'party_position', i))
                    if row and 'pokemon_id' in row:
                        pdb.update_pokemon(
                            row['pokemon_id'],
                            {'current_hp': max(0, int(getattr(mon, 'current_hp', 0)))},
                        )

            if battle.battle_format == BattleFormat.RAID:
                for battler in battle.get_all_battlers():
                    _persist_battler_party_hp(battler)
            else:
                _persist_battler_party_hp(battle.trainer)
        except Exception:
            pass

        player_manager = getattr(self.bot, 'player_manager', None)
        if player_manager and result in ['trainer', 'opponent']:
            if battle.battle_format == BattleFormat.RAID and result == 'trainer':
                winner_battlers = [b for b in battle.get_all_battlers() if not b.is_ai]
            elif result == 'trainer':
                winner_battlers = [battle.trainer]
                if getattr(battle, 'trainer_partner', None):
                    winner_battlers.append(battle.trainer_partner)
            else:
                winner_battlers = [battle.opponent]
                if getattr(battle, 'opponent_partner', None):
                    winner_battlers.append(battle.opponent_partner)

            for battler in winner_battlers:
                if battler and not battler.is_ai:
                    player_manager.adjust_party_friendship(
                        party_pokemon=battler.party,
                        amount=1,
                        only_survivors=True,
                    )
                    player_manager.reset_faint_streaks(party_pokemon=battler.party)

        if battle.battle_format == BattleFormat.RAID:
            raid_mon = (battle.opponent.get_active_pokemon() or [None])[0]
            raid_name = self._format_pokemon_name(raid_mon, include_level=False) if raid_mon else opponent_name
            if result == 'trainer':
                desc = (
                    f"The Dreamlites dissipate…\n\n"
                    f"***The {raid_name} Fainted!!!***\n\n"
                    "***Victory!!!***"
                )
                title = 'Raid Over'
                color = discord.Color.gold()
            else:
                desc = (
                    "All trainers' Pokémon have fainted…\n\n"
                    f"The Dreamlites surge, and the {raid_name} continues to rampage…\n\n"
                    "You Lose."
                )
                title = 'The Battle Has Been Decided!'
                color = discord.Color.red()
        else:
            # Check if this is a Dream Dive battle (dream_rogue NPC class)
            is_dream_rogue = getattr(battle.opponent, 'npc_class', None) == 'dream_rogue'

            if is_dream_rogue and result == 'trainer':
                # Player won against dream dive wild pokemon
                opponent_party = battle.opponent.party
                if len(opponent_party) > 1:
                    desc = "The opposing Pokémon have all vanished into the mist…\n\n**You win!**"
                else:
                    pokemon_name = opponent_party[0].species_name if opponent_party else "Pokémon"
                    desc = f"The opposing **{pokemon_name}** vanishes into the mist…\n\n**You win!**"
                title = 'Victory!'
                color = discord.Color.gold()
            elif is_dream_rogue and result == 'opponent':
                # Player lost against dream dive wild pokemon
                desc = f"Your Pokémon have all fainted…\n\n**Defeat.**"
                title = 'Defeat'
                color = discord.Color.red()
            else:
                # Standard battle message
                desc = f"All of {loser_name}'s Pokémon have fainted! {winner_name} wins!"
                title = 'The Battle Has Been Decided!'
                color = discord.Color.gold() if result == 'trainer' else discord.Color.red()

        # Play victory music if enabled
        if result in ['trainer', 'opponent']:
            actual_winner_name = winner_name if hasattr(battle, 'winner') else 'Winner'
            await self._play_victory_music(battle.battle_id, actual_winner_name, interaction)

        await self._safe_followup_send(
            interaction,
            embed=discord.Embed(title=title, description=desc, color=color)
        )

        # Exp is now awarded after each faint (in _award_exp_for_new_faints), not at battle end
        # This ensures Pokemon get exp even if they faint later in the battle

        ranked_embed = self._build_ranked_result_embed(battle)
        if ranked_embed:
            await self._safe_followup_send(interaction, embed=ranked_embed)

        player_manager = getattr(self.bot, 'player_manager', None)
        if player_manager:
            if getattr(battle, 'battle_type', None) == BattleType.TRAINER and result == 'trainer':
                identifier = getattr(battle.opponent, 'battler_name', 'opponent')
                target_type = 'npc_ranked' if getattr(battle, 'is_ranked', False) else 'npc_casual'
                duration = None if getattr(battle, 'is_ranked', False) else 24 * 60 * 60
                player_manager.set_battle_cooldown(battle.trainer.battler_id, target_type, identifier, duration)
            elif getattr(battle, 'battle_type', None) == BattleType.PVP and getattr(battle, 'is_ranked', False):
                winner_id = battle.trainer.battler_id if result == 'trainer' else battle.opponent.battler_id
                loser_id = battle.opponent.battler_id if result == 'trainer' else battle.trainer.battler_id
                if isinstance(winner_id, int) and isinstance(loser_id, int):
                    player_manager.set_battle_cooldown(winner_id, 'pvp_ranked', str(loser_id), 24 * 60 * 60)

        self.battle_engine.end_battle(battle.battle_id)
        self._unregister_battle(battle)
        # Note: Don't cleanup music here - let it play the victory theme naturally

        dream_callback_registry = getattr(self.bot, "dream_rogue_battle_callbacks", None)
        if dream_callback_registry and battle.battle_id in dream_callback_registry:
            callback = dream_callback_registry.pop(battle.battle_id, None)
            if callback:
                await callback(battle, result, interaction)

        # Check if this is a session encounter (thread name starts with "Encounter -")
        is_session_encounter = (
            isinstance(interaction.channel, discord.Thread) and
            interaction.channel.name.startswith("Encounter -")
        )
        is_dream_rogue_encounter = (
            isinstance(interaction.channel, discord.Thread) and
            interaction.channel.name.startswith("Dream Dive -")
        )

        if is_session_encounter:
            # Handle session encounter completion
            trainer_id = battle.trainer.battler_id

            # If player lost, deduct 1 stamina
            if result == 'opponent':
                session_manager = getattr(self.bot, 'session_manager', None)
                if session_manager and session_manager.is_in_session(trainer_id):
                    session_manager.adjust_participant_stamina(trainer_id, -1)
                    await self._safe_followup_send(
                        interaction,
                        embed=discord.Embed(
                            title="⚡ Stamina Lost",
                            description="You lost 1 stamina point due to defeat.",
                            color=discord.Color.orange()
                        )
                    )

            # Close the thread after a short delay
            await asyncio.sleep(3)
            try:
                await interaction.channel.send("This thread will now be closed.")
                await asyncio.sleep(2)
                await interaction.channel.edit(archived=True, locked=True)
            except Exception as e:
                print(f"Failed to close session encounter thread: {e}")
        elif is_dream_rogue_encounter:
            await asyncio.sleep(3)
            try:
                parent_channel = interaction.channel.parent
                if parent_channel:
                    await interaction.channel.send(
                        f"✅ Battle complete! Return to {parent_channel.mention} to rejoin the team."
                    )
                await asyncio.sleep(2)
                await interaction.channel.edit(archived=True, locked=True)
            except Exception as e:
                print(f"Failed to close Dream Dive encounter thread: {e}")
        elif getattr(battle, 'battle_type', None) == BattleType.WILD:
            await self.send_return_to_encounter_prompt(interaction, battle.trainer.battler_id)

    async def _award_exp_for_new_faints(self, battle, interaction: Optional[discord.Interaction] = None):
        """
        Award experience for any new faints that haven't been processed yet.
        This is called after each turn to ensure Pokemon get exp immediately after defeating an opponent.
        """
        if getattr(battle, "no_exp", False):
            return
        if not self.exp_handler:
            return

        # Skip Dream Dive battles
        if interaction:
            channel = interaction.channel
            if isinstance(channel, discord.Thread) and channel.name.startswith("Dream Dive -"):
                return

        trainer = getattr(battle, 'trainer', None)
        if not trainer or not getattr(trainer, 'party', None):
            return

        # Check for fainted opponents tracked during battle
        fainted_opponents = getattr(battle, 'fainted_opponents', [])
        if not fainted_opponents:
            return

        # Track which faints have been processed
        if not hasattr(battle, 'exp_processed_faint_count'):
            battle.exp_processed_faint_count = 0

        # Get new faints that haven't been processed
        new_faints = fainted_opponents[battle.exp_processed_faint_count:]
        if not new_faints:
            return

        # Award exp for each new faint
        exp_multiplier = 2.0 if battle.battle_format == BattleFormat.RAID else 1.0

        for faint_data in new_faints:
            defeated_pokemon = faint_data['pokemon']
            active_index = faint_data['active_trainer_index']
            trainer_battler_id = faint_data['trainer_battler_id']

            # Find the appropriate trainer battler (for multi-battles/raids)
            current_trainer = trainer
            if trainer_battler_id != trainer.battler_id:
                # Look for this trainer in raid allies or partner
                for ally in getattr(battle, 'raid_allies', []):
                    if ally.battler_id == trainer_battler_id:
                        current_trainer = ally
                        break
                if getattr(battle, 'trainer_partner', None) and battle.trainer_partner.battler_id == trainer_battler_id:
                    current_trainer = battle.trainer_partner

            try:
                results = await self.exp_handler.award_battle_exp(
                    trainer_id=current_trainer.battler_id,
                    party=current_trainer.party,
                    defeated_pokemon=defeated_pokemon,
                    active_pokemon_index=active_index,
                    is_trainer_battle=(battle.battle_type == BattleType.TRAINER),
                    exp_multiplier=exp_multiplier
                )

                # Send exp embed for this faint (mid-battle K.O.)
                if results and results.get('exp_gains'):
                    embed = self.exp_handler.create_exp_embed(results, current_trainer.party, defeated_pokemon, is_final_victory=False)
                    if embed and interaction:
                        await self._safe_followup_send(interaction, embed=embed)

            except Exception as exc:
                print(f"[BattleCog] Failed to award EXP for {defeated_pokemon.species_name}: {exc}")
                continue

        # Update the count of processed faints
        battle.exp_processed_faint_count = len(fainted_opponents)

    async def _create_exp_embed(self, battle, interaction: Optional[discord.Interaction] = None) -> Optional[discord.Embed]:
        if not self.exp_handler or getattr(battle, "no_exp", False):
            return None

        if interaction:
            channel = interaction.channel
            if isinstance(channel, discord.Thread) and channel.name.startswith("Dream Dive -"):
                return None

        trainer = getattr(battle, 'trainer', None)
        if not trainer or not getattr(trainer, 'party', None):
            return None

        # Check for fainted opponents tracked during battle
        fainted_opponents = getattr(battle, 'fainted_opponents', [])

        if not fainted_opponents:
            # Fallback to old behavior if no fainted opponents were tracked
            opponent = getattr(battle, 'opponent', None)
            active_index = 0
            if getattr(trainer, 'active_positions', None):
                try:
                    active_index = int(trainer.active_positions[0])
                except (TypeError, ValueError, IndexError):
                    active_index = 0

            defeated_pokemon = None
            opponent_party = getattr(opponent, 'party', None) if opponent else None
            if opponent_party:
                for mon in reversed(opponent_party):
                    if getattr(mon, 'current_hp', 1) <= 0:
                        defeated_pokemon = mon
                        break
                if defeated_pokemon is None and opponent_party:
                    defeated_pokemon = opponent_party[-1]

            if defeated_pokemon is None:
                return None

            exp_multiplier = 2.0 if battle.battle_format == BattleFormat.RAID else 1.0

            try:
                results = await self.exp_handler.award_battle_exp(
                    trainer_id=trainer.battler_id,
                    party=trainer.party,
                    defeated_pokemon=defeated_pokemon,
                    active_pokemon_index=active_index,
                    is_trainer_battle=(battle.battle_type == BattleType.TRAINER),
                    exp_multiplier=exp_multiplier
                )
            except Exception as exc:
                print(f"[BattleCog] Failed to award EXP: {exc}")
                return None

            return self.exp_handler.create_exp_embed(results, trainer.party, defeated_pokemon, is_final_victory=True)

        # New behavior: Award EXP for each fainted opponent
        exp_multiplier = 2.0 if battle.battle_format == BattleFormat.RAID else 1.0

        # Merged results across all faints
        merged_results = {
            'exp_gains': {},
            'level_ups': {},
            'evolution_ready': {}
        }

        # Process each fainted opponent
        for faint_data in fainted_opponents:
            defeated_pokemon = faint_data['pokemon']
            active_index = faint_data['active_trainer_index']
            trainer_battler_id = faint_data['trainer_battler_id']

            # Find the appropriate trainer battler (for multi-battles/raids)
            current_trainer = trainer
            if trainer_battler_id != trainer.battler_id:
                # Look for this trainer in raid allies or partner
                for ally in getattr(battle, 'raid_allies', []):
                    if ally.battler_id == trainer_battler_id:
                        current_trainer = ally
                        break
                if getattr(battle, 'trainer_partner', None) and battle.trainer_partner.battler_id == trainer_battler_id:
                    current_trainer = battle.trainer_partner

            try:
                results = await self.exp_handler.award_battle_exp(
                    trainer_id=current_trainer.battler_id,
                    party=current_trainer.party,
                    defeated_pokemon=defeated_pokemon,
                    active_pokemon_index=active_index,
                    is_trainer_battle=(battle.battle_type == BattleType.TRAINER),
                    exp_multiplier=exp_multiplier
                )

                # Merge EXP gains (accumulate EXP for each Pokemon)
                for idx, exp_data in results.get('exp_gains', {}).items():
                    if idx not in merged_results['exp_gains']:
                        merged_results['exp_gains'][idx] = exp_data.copy()
                    else:
                        # Accumulate EXP gained
                        merged_results['exp_gains'][idx]['exp_gained'] += exp_data['exp_gained']
                        merged_results['exp_gains'][idx]['new_exp'] = exp_data['new_exp']

                # Merge level-ups (keep track of all level-ups)
                for idx, levelup_data in results.get('level_ups', {}).items():
                    merged_results['level_ups'][idx] = levelup_data

                # Merge evolution readiness
                for idx, evo_data in results.get('evolution_ready', {}).items():
                    merged_results['evolution_ready'][idx] = evo_data

            except Exception as exc:
                print(f"[BattleCog] Failed to award EXP for {defeated_pokemon.species_name}: {exc}")
                continue

        if not merged_results['exp_gains']:
            return None

        # Create embed with merged results
        # Use the last defeated Pokemon for the embed title (or could show "Multiple Pokemon")
        last_defeated = fainted_opponents[-1]['pokemon'] if fainted_opponents else None
        if len(fainted_opponents) > 1:
            # Create a custom embed for multiple defeats
            embed = discord.Embed(
                title="⭐ Battle Victory!",
                description=f"Defeated {len(fainted_opponents)} Pokémon!",
                color=discord.Color.gold()
            )
        else:
            embed = discord.Embed(
                title="⭐ Battle Victory!",
                description=f"Defeated {last_defeated.species_name} (Lv. {last_defeated.level})!",
                color=discord.Color.gold()
            )

        # Show EXP gains
        exp_text = ""
        for idx, exp_data in merged_results['exp_gains'].items():
            pokemon_name = exp_data['pokemon_name']
            exp_gained = exp_data['exp_gained']
            exp_text += f"**{pokemon_name}** gained **{exp_gained} EXP**!\n"

        if exp_text:
            embed.add_field(name="💫 Experience Gained", value=exp_text, inline=False)

        # Show level-ups
        if merged_results['level_ups']:
            for idx, levelup_data in merged_results['level_ups'].items():
                pokemon_name = levelup_data['pokemon_name']
                result = levelup_data['result']

                levelup_text = f"**Level {result.old_level} → {result.new_level}!**\n\n"
                levelup_text += "**Stat Gains:**\n"
                levelup_text += f"• HP: +{result.stat_gains['hp']}\n"
                levelup_text += f"• Attack: +{result.stat_gains['attack']}\n"
                levelup_text += f"• Defense: +{result.stat_gains['defense']}\n"
                levelup_text += f"• Sp. Atk: +{result.stat_gains['sp_attack']}\n"
                levelup_text += f"• Sp. Def: +{result.stat_gains['sp_defense']}\n"
                levelup_text += f"• Speed: +{result.stat_gains['speed']}\n"

                if result.new_moves_learned:
                    levelup_text += "\n**Moves Learned:**\n"
                    unique_moves = list(dict.fromkeys(result.new_moves_learned))
                    for move_id in unique_moves:
                        move_name = move_id.replace('_', ' ').title()
                        levelup_text += f"⚔️ **{move_name}**\n"

                if result.moves_available_to_learn:
                    levelup_text += "\n**Wants to learn:**\n"
                    for move_data in result.moves_available_to_learn:
                        move_name = move_data['move_id'].replace('_', ' ').title()
                        levelup_text += f"• {move_name}\n"
                    levelup_text += "\n*Already knows 4 moves!*\n"

                embed.add_field(
                    name=f"📈 {pokemon_name} leveled up!",
                    value=levelup_text,
                    inline=False
                )

        # Show evolution readiness
        if merged_results.get('evolution_ready'):
            evo_text = ""
            for idx, evo_data in merged_results['evolution_ready'].items():
                pokemon_name = evo_data['pokemon_name']
                evo_text += f"✨ **{pokemon_name}** can now evolve!\n"

            if evo_text:
                evo_text += "\n*Use the Evolution menu to evolve your Pokémon!*"
                embed.add_field(
                    name="🌟 Evolution Ready!",
                    value=evo_text,
                    inline=False
                )

        return embed

    def _build_ranked_result_embed(self, battle) -> Optional[discord.Embed]:
        if not getattr(battle, 'is_ranked', False):
            return None

        player_manager = getattr(self.bot, 'player_manager', None)
        rank_manager = getattr(self.bot, 'rank_manager', None)
        if not player_manager or not rank_manager:
            return None

        result = rank_manager.process_ranked_battle_result(battle, player_manager)
        if not result:
            return None

        embed = discord.Embed(
            title=result.get('title', 'Ranked Result'),
            description=result.get('description', ''),
            color=discord.Color.green()
        )
        for field in result.get('fields', []):
            embed.add_field(
                name=field.get('name', 'Info'),
                value=field.get('value', '—'),
                inline=field.get('inline', False)
            )
        if result.get('footer'):
            embed.set_footer(text=result['footer'])
        return embed

    async def _handle_post_turn(self, interaction: discord.Interaction, battle_id: str):
        battle = self.battle_engine.get_battle(battle_id)
        if not battle:
            return

        print(f"[DEBUG] _handle_post_turn called. pending_switches: {battle.pending_switches}, phase: {battle.phase}")
        all_battlers = battle.get_all_battlers()
        print(f"[DEBUG] All battlers in battle: {[(b.battler_id, b.battler_name, getattr(b, 'is_ai', False)) for b in all_battlers]}")

        if battle.battle_type == BattleType.WILD and getattr(battle, "wild_dazed", False) and not battle.is_over:
            await self._send_dazed_prompt(interaction, battle)
            return

        # Award exp for any new faints that occurred this turn (before battle ends)
        await self._award_exp_for_new_faints(battle, interaction)

        if battle.is_over:
            await self._finish_battle(interaction, battle)
            return

        print(f"[DEBUG] Checking for forced switches. pending_switches keys: {list(battle.pending_switches.keys())}")
        # Check for forced switches (either from KO or from U-turn/Volt Switch)
        # First check the new pending_switches dict, fall back to old fields for compatibility
        prompted_switch = False
        if battle.pending_switches:
            # First pass: clean up eliminated battlers from pending_switches
            eliminated_ids = []
            for battler_id in list(battle.pending_switches.keys()):
                battler = _get_battler_by_id(battle, battler_id)
                if battler and getattr(battler, 'is_eliminated', False):
                    print(f"[DEBUG] Removing eliminated battler {battler_id} from pending_switches")
                    eliminated_ids.append(battler_id)
            for battler_id in eliminated_ids:
                del battle.pending_switches[battler_id]

            # Second pass: get the first player (non-AI) that needs to switch
            for battler_id, switch_info in battle.pending_switches.items():
                battler = _get_battler_by_id(battle, battler_id)
                # Debug: Check what we found
                if not battler:
                    print(f"[DEBUG] Could not find battler for ID {battler_id}")
                    continue
                is_ai = getattr(battler, 'is_ai', False)
                print(f"[DEBUG] Battler {battler_id} ({battler.battler_name}): is_ai={is_ai}")
                if not is_ai:
                    await self._prompt_forced_switch(interaction, battle, battler_id)
                    prompted_switch = True
                    break

        # If we didn't find anyone in pending_switches, try the old fields
        if not prompted_switch and battle.phase in ['FORCED_SWITCH', 'VOLT_SWITCH'] and battle.forced_switch_battler_id:
            print(f"[DEBUG] Using fallback: forced_switch_battler_id={battle.forced_switch_battler_id}")
            await self._prompt_forced_switch(interaction, battle, battle.forced_switch_battler_id)
            prompted_switch = True

        # Recovery mechanism: Scan for any fainted Pokemon that weren't tracked in pending_switches
        # This catches cases where the fainting detection code failed to add the player
        if not prompted_switch:
            print(f"[DEBUG] No pending switches found, scanning for fainted Pokemon...")
            for battler in battle.get_all_battlers():
                if getattr(battler, 'is_ai', False):
                    continue

                # Skip eliminated battlers (those with no Pokemon left)
                if getattr(battler, 'is_eliminated', False):
                    print(f"[DEBUG] Skipping eliminated battler {battler.battler_id} ({battler.battler_name})")
                    continue

                active_pokemon = battler.get_active_pokemon()
                for pos_idx, active_mon in enumerate(active_pokemon):
                    if getattr(active_mon, 'current_hp', 0) <= 0:
                        print(f"[DEBUG] Found fainted Pokemon {active_mon.species_name} for battler {battler.battler_id} ({battler.battler_name}) at position {pos_idx}")
                        # Check if they have usable bench Pokemon
                        if battler.has_usable_bench_pokemon(exclude_pokemon=active_mon):
                            print(f"[DEBUG] Adding missing switch for battler {battler.battler_id} to pending_switches")
                            # Add to pending switches
                            battle.pending_switches[battler.battler_id] = {
                                'position': pos_idx,
                                'switch_type': 'FORCED'
                            }
                            battle.phase = 'FORCED_SWITCH'
                            battle.forced_switch_battler_id = battler.battler_id
                            battle.forced_switch_position = pos_idx
                            # Prompt the switch immediately
                            await self._prompt_forced_switch(interaction, battle, battler.battler_id)
                            prompted_switch = True
                            break
                if prompted_switch:
                    break

        # If we prompted a switch, stop here
        if prompted_switch:
            return

        if battle.battle_format == BattleFormat.RAID:
            await self._safe_followup_send(
                interaction,
                embed=self._create_raid_status_embed(battle),
            )
            await self._safe_followup_send(
                interaction,
                embed=self._create_raid_party_embed(battle),
                view=self._create_battle_view(battle),
            )
            return

        await self._safe_followup_send(
            interaction,
            embed=self._create_battle_embed(battle),
            view=self._create_battle_view(battle)
        )

    @app_commands.command(name="rp_go", description="Execute the turn in RP mode (use if button expires)")
    async def rp_go_command(self, interaction: discord.Interaction):
        """Slash command to execute RP mode turn when the button expires."""
        # Check if user is in a battle
        battle_id = self.user_battles.get(interaction.user.id)
        if not battle_id:
            await interaction.response.send_message("❌ You are not currently in a battle!", ephemeral=True)
            return

        battle = self.battle_engine.get_battle(battle_id)
        if not battle:
            await interaction.response.send_message("❌ Battle not found!", ephemeral=True)
            return

        # Check if RP mode is active
        if not battle.rp_mode_active:
            await interaction.response.send_message("❌ RP mode is not active in this battle!", ephemeral=True)
            return

        # Check if there are pending actions to execute
        if not battle.pending_actions:
            await interaction.response.send_message("❌ No actions have been chosen yet!", ephemeral=True)
            return

        # Add this battler to the ready set
        battle.rp_mode_go_ready.add(interaction.user.id)

        # Check if both players are ready
        required_battler_ids = {battle.trainer.battler_id, battle.opponent.battler_id}
        all_ready = required_battler_ids.issubset(battle.rp_mode_go_ready)

        if not all_ready:
            await interaction.response.send_message(
                "✅ Ready! Waiting for the other player to use `/rp_go`...",
                ephemeral=True
            )
            return

        # Both players are ready - execute the turn!
        await interaction.response.defer()

        # Clear the ready set for the next turn
        battle.rp_mode_go_ready.clear()

        # Process the turn
        turn = await self.battle_engine.process_turn(battle_id)
        await self._send_turn_resolution(interaction, turn)

        # Update the execution message if it exists
        if battle.rp_mode_execution_message_id and interaction.channel:
            try:
                execution_msg = await interaction.channel.fetch_message(battle.rp_mode_execution_message_id)
                executed_embed = discord.Embed(
                    title="⚡ Turn Executed!",
                    description="Both players are ready! The turn has been executed.\n"
                               "Choose your next actions and use `/rp_go` when ready!",
                    color=discord.Color.green()
                )
                await execution_msg.edit(embed=executed_embed, view=None)
            except Exception:
                pass

        battle.rp_mode_execution_message_id = None
        await self._handle_post_turn(interaction, battle_id)

class ForfeitConfirmView(discord.ui.View):
    def __init__(self, action_view: 'BattleActionView'):
        super().__init__(timeout=None)
        self.action_view = action_view

    @discord.ui.button(label="Yes, forfeit", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.action_view._handle_forfeit(interaction)
        try:
            await interaction.edit_original_response(content="Battle forfeited.", view=None, embed=None)
        except Exception:
            pass
        self.stop()

    @discord.ui.button(label="No", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            await interaction.delete_original_response()
        except Exception:
            try:
                await interaction.edit_original_response(content="Forfeit cancelled.", view=None, embed=None)
            except Exception:
                pass
        self.stop()

class RPModeExecutionView(discord.ui.View):
    """View with the 'Go!' button for executing RP mode turns."""
    def __init__(self, battle_id: str, engine: BattleEngine, battle_cog: 'BattleCog'):
        super().__init__(timeout=None)
        self.battle_id = battle_id
        self.engine = engine
        self.battle_cog = battle_cog

    @discord.ui.button(label="⚡ Go!", style=discord.ButtonStyle.success, custom_id="rp_mode_go")
    async def go_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        battle = self.engine.get_battle(self.battle_id)
        if not battle:
            await interaction.response.send_message("Battle not found.", ephemeral=True)
            return

        # Check if the user is a participant
        battler_id = None
        for battler in battle.get_all_battlers():
            if battler.battler_id == interaction.user.id:
                battler_id = battler.battler_id
                break

        if battler_id is None:
            await interaction.response.send_message("❌ You are not a participant in this battle.", ephemeral=True)
            return

        # Add this battler to the ready set
        battle.rp_mode_go_ready.add(battler_id)

        # Check if both players are ready (for PvP, we need both trainer and opponent)
        required_battler_ids = {battle.trainer.battler_id, battle.opponent.battler_id}
        all_ready = required_battler_ids.issubset(battle.rp_mode_go_ready)

        if not all_ready:
            # Not all players ready yet
            await interaction.response.send_message(
                "✅ Ready! Waiting for the other player to press Go...",
                ephemeral=True
            )
            return

        # Both players are ready - execute the turn!
        await interaction.response.defer()

        # Clear the ready set for the next turn
        battle.rp_mode_go_ready.clear()

        # Process the turn
        cog = self.battle_cog or interaction.client.get_cog("BattleCog")
        if cog:
            turn = await self.engine.process_turn(self.battle_id)
            await cog._send_turn_resolution(interaction, turn)

            # Update the execution message to show turn has been executed
            if battle.rp_mode_execution_message_id and interaction.channel:
                try:
                    execution_msg = await interaction.channel.fetch_message(battle.rp_mode_execution_message_id)
                    executed_embed = discord.Embed(
                        title="⚡ Turn Executed!",
                        description="Both players pressed Go! The turn has been executed.\n"
                                   "Choose your next actions and press Go when ready!",
                        color=discord.Color.green()
                    )
                    await execution_msg.edit(embed=executed_embed, view=None)
                except Exception:
                    pass

            battle.rp_mode_execution_message_id = None
            await cog._handle_post_turn(interaction, self.battle_id)


class RPModeRequestView(discord.ui.View):
    def __init__(self, battle_id: str, other_battler_id: int, requester_id: int, engine: BattleEngine, battle_cog: 'BattleCog'):
        super().__init__(timeout=None)
        self.battle_id = battle_id
        self.other_battler_id = other_battler_id  # The player who needs to accept
        self.requester_id = requester_id  # The player who requested RP mode
        self.engine = engine
        self.battle_cog = battle_cog

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Only the other player can accept
        if interaction.user.id != self.other_battler_id:
            await interaction.response.send_message("❌ Only the challenged player can respond to this request!", ephemeral=True)
            return

        battle = self.engine.get_battle(self.battle_id)
        if not battle:
            await interaction.response.send_message("Battle not found.", ephemeral=True)
            return

        # Activate RP mode
        battle.rp_mode_active = True

        # Update the message to show RP mode is active
        embed = discord.Embed(
            title="🎭 RP Mode Activated!",
            description=f"**{interaction.user.display_name}** has accepted the RP Mode request!\n\n"
                       "From now on, both players must press 'Go!' after selecting their actions to execute the turn.\n"
                       "This gives you unlimited time for roleplay between turns!",
            color=discord.Color.green()
        )

        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Only the other player can decline
        if interaction.user.id != self.other_battler_id:
            await interaction.response.send_message("❌ Only the challenged player can respond to this request!", ephemeral=True)
            return

        # Update the message to show RP mode was declined
        embed = discord.Embed(
            title="🎭 RP Mode Declined",
            description=f"**{interaction.user.display_name}** has declined the RP Mode request.\n\n"
                       "The battle will continue normally.",
            color=discord.Color.red()
        )

        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


class BattleActionView(discord.ui.View):
    def __init__(self, battle_id: str, battler_id: int, engine: BattleEngine, battle, battle_cog: 'BattleCog'):
        super().__init__(timeout=None)
        self.battle_id = battle_id
        self.battler_id = battler_id
        self.engine = engine
        self.battle = battle
        self.cog = battle_cog
        if battle and battle.battle_format == BattleFormat.RAID:
            self.remove_item(self.rp_mode_button)

    def _resolve_battler_id(self, interaction: discord.Interaction, battle) -> Optional[int]:
        for battler in battle.get_all_battlers():
            if battler.battler_id == interaction.user.id:
                return battler.battler_id

        cog = self.cog or interaction.client.get_cog("BattleCog")
        if battle.battle_format == BattleFormat.RAID and cog:
            if getattr(cog, "user_battles", {}).get(interaction.user.id) == battle.battle_id:
                return interaction.user.id
        return None

    @discord.ui.button(label="⚔️ Fight", style=discord.ButtonStyle.danger, row=0)
    async def fight_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Always grab the freshest battle state
        battle = self.engine.get_battle(self.battle_id) or self.battle
        if not battle:
            await interaction.response.send_message("Battle not found.", ephemeral=True)
            return

        # Work out which side this user actually controls (battler_id stores Discord IDs for players)
        battler_id = self._resolve_battler_id(interaction, battle)
        if battler_id is None:
            await interaction.response.send_message("You are not a participant in this battle.", ephemeral=True)
            return

        # Check if this battler has been eliminated
        battler = _get_battler_by_id(battle, battler_id)
        if battler and battler.is_eliminated:
            await interaction.response.send_message("❌ All your Pokémon have fainted! You can no longer battle.", ephemeral=True)
            return

        # Check if this is a doubles battle
        if battle.battle_format == BattleFormat.DOUBLES:
            # Use doubles action collector
            collector = DoublesActionCollector(battle, battler_id, self.engine)
            battler = battle.trainer if battler_id == battle.trainer.battler_id else battle.opponent
            first_mon = battler.get_active_pokemon()[0]
            await interaction.response.send_message(
                f"Select move for **{_format_battle_pokemon_name(first_mon)}** (Slot 1):",
                view=DoublesMoveSelectView(battle, battler_id, self.engine, 0, collector),
                ephemeral=True,
            )
        else:
            # Singles battle
            battler = _get_battler_by_id(battle, battler_id)
            active_pokemon = None
            if battler:
                active_list = battler.get_active_pokemon()
                active_pokemon = active_list[0] if active_list else None
            charge_state = getattr(active_pokemon, "_charge_state", None) if active_pokemon else None
            if charge_state and charge_state.get("move_id"):
                action = BattleAction(
                    action_type='move',
                    battler_id=battler_id,
                    move_id=charge_state["move_id"],
                    target_position=0,
                )
                res = self.engine.register_action(self.battle_id, battler_id, action)
                cog = self.cog or interaction.client.get_cog("BattleCog")
                if not res.get("ready_to_resolve"):
                    await interaction.response.send_message(
                        f"{_format_battle_pokemon_name(active_pokemon)} is charging and will strike next!",
                        ephemeral=True,
                    )
                    return
                if res.get("ready_to_resolve") and cog:
                    turn = await self.engine.process_turn(self.battle_id)
                    await cog._send_turn_resolution(interaction, turn)
                await cog._handle_post_turn(interaction, self.battle_id)
                return
            await interaction.response.send_message(
                "Choose a move:",
                view=MoveSelectView(battle, battler_id, self.engine, controller_id=interaction.user.id),
                ephemeral=True,
            )


    @discord.ui.button(label="🔄 Switch", style=discord.ButtonStyle.primary, row=0)
    async def switch_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        battle = self.engine.get_battle(self.battle_id) or self.battle
        if not battle:
            await interaction.response.send_message("Battle not found.", ephemeral=True)
            return

        # Work out which side this user actually controls (battler_id stores Discord IDs for players)
        battler_id = self._resolve_battler_id(interaction, battle)
        if battler_id is None:
            await interaction.response.send_message("You are not a participant in this battle.", ephemeral=True)
            return

        # Check if this battler has been eliminated
        battler = _get_battler_by_id(battle, battler_id)
        if battler and battler.is_eliminated:
            await interaction.response.send_message("❌ All your Pokémon have fainted! You can no longer battle.", ephemeral=True)
            return

        # Handle doubles switch flow with action collector
        if battle.battle_format == BattleFormat.DOUBLES:
            collector = DoublesActionCollector(battle, battler_id, self.engine)
            battler = _get_battler_by_id(battle, battler_id)
            first_mon = battler.get_active_pokemon()[0] if battler else None
            first_name = _format_battle_pokemon_name(first_mon) if first_mon else "your Pokémon"
            await interaction.response.send_message(
                f"Choose a Pokémon to switch into Slot 1 for **{first_name}**:",
                view=DoublesPartySelectView(
                    battle, battler_id, self.engine,
                    0, collector, forced=False
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Choose a Pokémon to switch in:",
            view=PartySelectView(battle, battler_id, self.engine, forced=False),
            ephemeral=True,
        )


    @discord.ui.button(label="🎒 Bag", style=discord.ButtonStyle.secondary, row=0)
    async def bag_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        battle = self.engine.get_battle(self.battle_id) or self.battle
        if not battle:
            await interaction.response.send_message("Battle not found.", ephemeral=True)
            return
        battler_id = self._resolve_battler_id(interaction, battle)
        if battler_id is None:
            await interaction.response.send_message("You are not a participant in this battle.", ephemeral=True)
            return

        # Check if this battler has been eliminated
        battler = _get_battler_by_id(battle, battler_id)
        if battler and battler.is_eliminated:
            await interaction.response.send_message("❌ All your Pokémon have fainted! You can no longer battle.", ephemeral=True)
            return

        cog = self.cog or interaction.client.get_cog("BattleCog")
        if not cog:
            await interaction.response.send_message("Bag system is not available right now.", ephemeral=True)
            return
        await interaction.response.send_message("Items:", view=BagView(cog, battle, interaction.user.id), ephemeral=True)

    @discord.ui.button(label="🏃 Run", style=discord.ButtonStyle.secondary, row=0)
    async def run_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="Forfeit the battle?",
            description="Forfeiting counts as a loss. Are you sure you want to run?",
            color=discord.Color.dark_red()
        )
        battle = self.engine.get_battle(self.battle_id) or self.battle
        battler_id = self._resolve_battler_id(interaction, battle) if battle else None
        if battler_id is None:
            await interaction.response.send_message("You are not a participant in this battle.", ephemeral=True)
            return

        # Check if this battler has been eliminated
        battler = _get_battler_by_id(battle, battler_id)
        if battler and battler.is_eliminated:
            await interaction.response.send_message("❌ All your Pokémon have fainted! You can no longer battle.", ephemeral=True)
            return

        await interaction.response.send_message(embed=embed, view=ForfeitConfirmView(self), ephemeral=True)

    async def _handle_forfeit(self, interaction: discord.Interaction):
        battle = self.engine.get_battle(self.battle_id)
        if not battle:
            await interaction.followup.send("Battle not found.", ephemeral=True)
            return
        if battle.is_over:
            await interaction.followup.send("The battle is already over.", ephemeral=True)
            return
        forfeiting_id = self._resolve_battler_id(interaction, battle)
        trainer_team_ids = {b.battler_id for b in battle.get_team_battlers(battle.trainer.battler_id)}

        if forfeiting_id in trainer_team_ids:
            battle.winner = 'opponent'
        else:
            battle.winner = 'trainer'
        battle.is_over = True
        cog = self.cog or interaction.client.get_cog("BattleCog")
        if cog:
            await cog._finish_battle(interaction, battle)
        else:
            self.engine.end_battle(self.battle_id)

    @discord.ui.button(label="🎭 RP Mode", style=discord.ButtonStyle.secondary, row=1, custom_id="rp_mode_toggle")
    async def rp_mode_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        battle = self.engine.get_battle(self.battle_id) or self.battle
        if not battle:
            await interaction.response.send_message("Battle not found.", ephemeral=True)
            return

        # Only available for PvP battles
        if battle.battle_type != BattleType.PVP:
            await interaction.response.send_message("❌ RP Mode is only available in PvP battles!", ephemeral=True)
            return

        battler_id = self._resolve_battler_id(interaction, battle)
        if battler_id is None:
            await interaction.response.send_message("You are not a participant in this battle.", ephemeral=True)
            return

        # Check if RP mode is already active
        if battle.rp_mode_active:
            await interaction.response.send_message("✅ RP Mode is already active!", ephemeral=True)
            return

        # Get the other player
        other_battler_id = battle.opponent.battler_id if battler_id == battle.trainer.battler_id else battle.trainer.battler_id
        requester_name = interaction.user.display_name

        # Send RP mode request embed to the channel
        embed = discord.Embed(
            title="🎭 RP Mode Request",
            description=f"**{requester_name}** wants to activate **RP Mode** for this battle!\n\n"
                       "**What is RP Mode?**\n"
                       "• Both players choose their actions normally\n"
                       "• Actions pause before execution\n"
                       "• Both players must press 'Go!' to continue\n"
                       "• Gives unlimited time for roleplay posts between turns!\n\n"
                       "Do you accept?",
            color=discord.Color.purple()
        )

        view = RPModeRequestView(self.battle_id, other_battler_id, requester_id=battler_id, engine=self.engine, battle_cog=self.cog)
        await interaction.response.send_message(embed=embed, view=view)


def _build_revival_target_options(battle, battler_id: int) -> tuple[list[discord.SelectOption], dict[str, tuple[int, int]]]:
    """Build select options for Revival Blessing targets."""
    options: list[discord.SelectOption] = []
    option_map: dict[str, tuple[int, int]] = {}

    raid_participants = {p.get("user_id"): p.get("trainer_name") for p in getattr(battle, "raid_participants", [])}

    for battler in battle.get_team_battlers(battler_id):
        owner_label = raid_participants.get(battler.battler_id) or getattr(battler, "battler_name", "Ally")
        for idx, mon in enumerate(battler.party):
            if getattr(mon, "current_hp", 0) > 0:
                continue

            value = f"{battler.battler_id}:{idx}"
            label = f"{mon.species_name} (Party {idx + 1})"
            description = None

            mon_owner = getattr(mon, "owner_discord_id", None)
            if battle.battle_format == BattleFormat.RAID and mon_owner:
                owner_name = raid_participants.get(mon_owner)
                if owner_name:
                    description = f"Trainer: {owner_name}"
            if not description:
                description = owner_label

            options.append(discord.SelectOption(label=label, value=value, description=description[:99]))
            option_map[value] = (battler.battler_id, idx)

    return options, option_map


def _get_battler_by_id(battle, battler_id: int):
    for battler in battle.get_all_battlers():
        if battler.battler_id == battler_id:
            return battler
    return battle.trainer


def _get_battle_status_label(pokemon) -> Optional[str]:
    status_type = None
    status_manager = getattr(pokemon, "status_manager", None)
    if status_manager and getattr(status_manager, "major_status", None):
        status_type = status_manager.major_status.status_type
    if not status_type:
        status_type = getattr(pokemon, "status_condition", None)
    if not status_type:
        return None

    normalized = str(status_type).lower()
    status_map = {
        "brn": "Burn 🔥",
        "burn": "Burn 🔥",
        "par": "Paralysis ⚡️",
        "paralysis": "Paralysis ⚡️",
        "slp": "Sleep 💤",
        "sleep": "Sleep 💤",
        "frz": "Freeze ❄️",
        "freeze": "Freeze ❄️",
        "psn": "Poison ☠️",
        "poison": "Poison ☠️",
        "tox": "Badly Poisoned ☠️",
        "toxic": "Badly Poisoned ☠️",
        "badly_poisoned": "Badly Poisoned ☠️",
    }
    return status_map.get(normalized)


def _format_battle_pokemon_name(pokemon, include_level: bool = False) -> str:
    name = getattr(pokemon, "nickname", None) or getattr(pokemon, "species_name", "Pokémon")
    if getattr(pokemon, "is_mega_evolved", False) and not name.lower().startswith("mega "):
        name = f"Mega {name}"
    if getattr(pokemon, "is_raid_boss", False):
        name = f"Rogue {name}"
    level = getattr(pokemon, "level", None)
    if include_level and level is not None:
        status_label = _get_battle_status_label(pokemon)
        status_suffix = f" ({status_label})" if status_label else ""
        return f"{name} Lv{level}{status_suffix}"
    return name


class MoveSelectView(discord.ui.View):
    def __init__(self, battle, battler_id: int, engine: BattleEngine, controller_id: Optional[int] = None):
        super().__init__(timeout=None)
        self.battle = battle
        self.battle_id = battle.battle_id
        self.battler_id = battler_id
        self.engine = engine
        self.controller_id = controller_id

        # Figure out which active Pokémon belongs to this battler
        battler = _get_battler_by_id(battle, battler_id)
        active_pokemon = None
        active_list = battler.get_active_pokemon() if battler else []
        if battle.battle_format == BattleFormat.RAID and controller_id:
            for mon in active_list:
                if getattr(mon, "owner_discord_id", None) == controller_id:
                    active_pokemon = mon
                    break
        if not active_pokemon and active_list:
            active_pokemon = active_list[0]

        if not active_pokemon:
            return

        self.mega_selected = False
        self.mega_name = None

        # Add up to 4 move buttons for this Pokémon
        for mv in getattr(active_pokemon, "moves", [])[:4]:
            move_id = mv.get("move_id") or mv.get("id")
            if not move_id:
                continue

            move_info = engine.moves_db.get_move(move_id) if hasattr(engine, "moves_db") else None
            move_name = (move_info.get("name") if move_info else None) or mv.get("name") or move_id
            cur_pp = mv.get("pp")
            max_pp = mv.get("max_pp")
            label = f"{move_name} ({cur_pp}/{max_pp})" if (cur_pp is not None and max_pp is not None) else move_name

            self.add_item(
                MoveButton(
                    label=label,
                    move_id=move_id,
                    engine=engine,
                    battle_id=self.battle_id,
                    battler_id=battler_id,
                    pokemon_position=0,
                    disabled=(cur_pp is not None and cur_pp <= 0),
                )
            )

        mega_name = engine.get_mega_evolution_name(battle, battler_id, active_pokemon)
        if mega_name:
            self.mega_name = mega_name
            self.add_item(MegaEvolveButton(mega_name))


class MegaEvolveButton(discord.ui.Button):
    def __init__(self, mega_name: str):
        super().__init__(label="Mega Evolve", style=discord.ButtonStyle.primary, row=1)
        self.mega_name = mega_name

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not view:
            await interaction.response.send_message("This prompt expired.", ephemeral=True)
            return
        view.mega_selected = not getattr(view, "mega_selected", False)
        self.label = "Mega Evolve ✅" if view.mega_selected else "Mega Evolve"
        self.style = discord.ButtonStyle.success if view.mega_selected else discord.ButtonStyle.primary
        await interaction.response.edit_message(view=view)
        if view.mega_selected:
            await interaction.followup.send(
                f"{self.mega_name} is ready to mega evolve this turn!",
                ephemeral=True,
            )

class MoveButton(discord.ui.Button):
    def __init__(self, label, move_id, engine: BattleEngine, battle_id: str, battler_id: int, pokemon_position: int = 0, disabled: bool = False):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=0, disabled=disabled)
        self.move_id = move_id
        self.engine = engine
        self.battle_id = battle_id
        self.battler_id = battler_id
        self.pokemon_position = pokemon_position

    @staticmethod
    def _should_prompt_target(move_data: dict) -> bool:
        target_type = move_data.get("target", "single")
        if target_type in [
            "self",
            "all",
            "all_opponents",
            "all_adjacent",
            "all_allies",
            "entire_field",
            "user_field",
            "enemy_field",
        ]:
            return False
        return True

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        battle = self.engine.get_battle(self.battle_id)
        mega_evolve = getattr(self.view, "mega_selected", False)
        move_data = self.engine.moves_db.get_move(self.move_id) if hasattr(self.engine, "moves_db") else {}
        if self.move_id == "revival_blessing" and battle:
            options, option_map = _build_revival_target_options(battle, self.battler_id)
            if not options:
                await interaction.followup.send(
                    "There are no fainted ally Pokémon to revive.",
                    ephemeral=True,
                )
                return

            await interaction.followup.send(
                "Choose a Pokémon to revive:",
                view=RevivalTargetSelectView(
                    battle=battle,
                    battler_id=self.battler_id,
                    engine=self.engine,
                    pokemon_position=self.pokemon_position,
                    options=options,
                    option_map=option_map,
                    mega_evolve=mega_evolve,
                ),
                ephemeral=True,
            )
            return

        if battle and self._should_prompt_target(move_data):
            await interaction.followup.send(
                "Choose a target for this move:",
                view=TargetSelectView(
                    battle,
                    self.battler_id,
                    self.move_id,
                    self.pokemon_position,
                    self.engine,
                    mega_evolve=mega_evolve,
                ),
                ephemeral=True,
            )
            return
        action = BattleAction(
            action_type='move',
            battler_id=self.battler_id,
            move_id=self.move_id,
            target_position=0,
            mega_evolve=mega_evolve,
        )
        res = self.engine.register_action(self.battle_id, self.battler_id, action)
        cog = interaction.client.get_cog("BattleCog")

        # Check if RP mode is waiting for both players to press "Go"
        if res.get("rp_mode_waiting") and cog:
            await interaction.followup.send(
                "Move selected! Both players have chosen their actions.",
                ephemeral=True,
            )
            # Show the "awaiting execution" embed
            battle = self.engine.get_battle(self.battle_id)
            if battle:
                await cog._show_rp_mode_execution_prompt(interaction, battle)
            return

        # If the other trainer hasn't chosen yet, just notify this user and stop.
        if not res.get("ready_to_resolve"):
            waiting_for = res.get("waiting_for", [])
            trainer_word = "trainers" if len(waiting_for) > 1 else "trainer"
            await interaction.followup.send(
                f"Move selected! Waiting for the other {trainer_word} to choose...",
                ephemeral=True,
            )
            return

        if res.get("ready_to_resolve") and cog:
            turn = await self.engine.process_turn(self.battle_id)
            await cog._send_turn_resolution(interaction, turn)
        battle = self.engine.get_battle(self.battle_id)
        if battle:
            from cogs.battle_cog import BattleCog  # type: ignore
            # naive way to get cog from interaction.client
            cog = interaction.client.get_cog("BattleCog")
            if cog:
                refreshed = cog._create_battle_embed(battle)
                
                # If this is a wild battle and the opponent is dazed, show the catch prompt instead of the battle panel
                if battle.battle_type == BattleType.WILD and getattr(battle, 'wild_dazed', False) and not battle.is_over:
                    await cog._send_dazed_prompt(interaction, battle)
                    return
                
                if turn.get('is_over') or battle.is_over:
                    await cog._finish_battle(interaction, battle)
                else:
                    # Let BattleCog handle post-turn logic: forced switches, KO prompts, etc.
                    await cog._handle_post_turn(interaction, self.battle_id)
        
class PartySelect(discord.ui.Select):
    def __init__(self, battle, battler_id: int, forced: bool = False):
        self.battle = battle
        self.battler_id = battler_id
        self.forced = forced
        battler = _get_battler_by_id(battle, battler_id) or battle.trainer
        party = battler.party
        active_index = battler.active_positions[0]  # Get actual active position

        options = []
        for idx, mon in enumerate(party):
            name = getattr(mon, "species_name", f"Slot {idx+1}")
            current_hp = getattr(mon, 'current_hp', 0)
            max_hp = getattr(mon, 'max_hp', 1)
            hp = "(Fainted)" if current_hp <= 0 else f"{current_hp}/{max_hp}"

            # Skip disabled options (active or fainted Pokemon)
            if idx == active_index or current_hp <= 0:
                continue

            options.append(discord.SelectOption(label=name, description=f"HP {hp}", value=str(idx), default=False))

        # Discord select menus must always have at least one option; provide a disabled fallback
        if not options:
            options = [
                discord.SelectOption(
                    label="No available Pokémon", description="All other party members are unable to battle.", value="none"
                )
            ]

        placeholder = "Choose a Pokémon to send out" if forced else "Choose a Pokémon to switch in"
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

        # Disable the select when no valid switch targets exist
        if options and options[0].value == "none":
            self.disabled = True

    async def callback(self, interaction: discord.Interaction):
        if self.disabled or (self.values and self.values[0] == "none"):
            await interaction.response.send_message(
                "❌ You have no available Pokémon to switch in.", ephemeral=True
            )
            return

        # Verify that the user clicking the button is the correct player
        battler = _get_battler_by_id(self.battle, self.battler_id)
        if battler and battler.battler_id != interaction.user.id:
            await interaction.response.send_message(
                "❌ This isn't your Pokémon! Please wait for your own switch prompt.",
                ephemeral=True
            )
            return

        await interaction.response.defer()
        idx = int(self.values[0])
        cog = interaction.client.get_cog("BattleCog")
        parent_view = getattr(self, 'view', None)
        if not parent_view:
            await interaction.followup.send("That switch prompt expired.", ephemeral=True)
            return

        if self.forced:
            result = parent_view.engine.force_switch(parent_view.battle_id, self.battler_id, idx)
            if result.get("error"):
                await interaction.followup.send(result["error"], ephemeral=True)
                return
            messages = result.get('messages', [])
            if not messages:
                battle = parent_view.engine.get_battle(parent_view.battle_id)
                battler = _get_battler_by_id(battle, self.battler_id) if battle else None
                pokemon = result.get("pokemon")
                if battler and pokemon:
                    messages = [f"{battler.battler_name} sent out {pokemon.species_name}!"]
                else:
                    messages = ["A new Pokémon entered the battle."]
            if cog:
                send_embed = cog._build_switch_embed(messages, title="Send-out", pokemon=result.get("pokemon"))
                if send_embed:
                    await cog._safe_followup_send(interaction, embed=send_embed)
                battle = parent_view.engine.get_battle(parent_view.battle_id)
                if battle:
                    # Check if there are more pending switches (for raid battles with multiple faints)
                    if battle.pending_switches:
                        # Get the next player (non-AI) that needs to switch
                        for next_battler_id, switch_info in battle.pending_switches.items():
                            next_battler = _get_battler_by_id(battle, next_battler_id)
                            if next_battler and not getattr(next_battler, 'is_ai', False):
                                await cog._prompt_forced_switch(interaction, battle, next_battler_id)
                                return

                    if battle.battle_format == BattleFormat.RAID:
                        await cog._safe_followup_send(
                            interaction,
                            embed=cog._create_raid_status_embed(battle),
                        )
                        await cog._safe_followup_send(
                            interaction,
                            embed=cog._create_raid_party_embed(battle),
                            view=cog._create_battle_view(battle),
                        )
                    else:
                        await cog._safe_followup_send(
                            interaction,
                            embed=cog._create_battle_embed(battle),
                            view=cog._create_battle_view(battle),
                        )
            else:
                text = "\n".join(messages) or "A new Pokémon entered the battle."
                try:
                    await interaction.followup.send(text)
                except Exception:
                    if interaction.channel:
                        await interaction.channel.send(text)
            return

        action = BattleAction(action_type='switch', battler_id=self.battler_id, switch_to_position=idx)
        res = parent_view.engine.register_action(parent_view.battle_id, self.battler_id, action)

        # Check if RP mode is waiting for both players to press "Go"
        if res.get("rp_mode_waiting") and cog:
            await interaction.followup.send(
                "Switch selected! Both players have chosen their actions.",
                ephemeral=True,
            )
            battle = parent_view.engine.get_battle(parent_view.battle_id)
            if battle:
                await cog._show_rp_mode_execution_prompt(interaction, battle)
            return

        # Handle volt switch completion specially
        if res.get("volt_switch_complete") and cog:
            # Send switch embed
            switch_msgs = res.get("switch_messages", [])
            if switch_msgs:
                switch_embed = cog._build_switch_embed(switch_msgs, pokemon=None)
                if switch_embed:
                    await cog._safe_followup_send(interaction, embed=switch_embed)

            # Send end-of-turn embed
            eot_msgs = res.get("eot_messages", [])
            if eot_msgs:
                eot_embed = discord.Embed(
                    title="End of Turn",
                    description="\n".join(eot_msgs),
                    color=discord.Color.light_gray()
                )
                await cog._safe_followup_send(interaction, embed=eot_embed)

            # Handle any auto switch events
            auto_switch_events = res.get("auto_switch_events", [])
            for event in auto_switch_events:
                embed = cog._build_switch_embed(event.get("messages", []), pokemon=event.get("pokemon"))
                if embed:
                    await cog._safe_followup_send(interaction, embed=embed)

        # Handle regular forced switch completion
        elif res.get("forced_switch_complete") and cog:
            switch_msgs = res.get("switch_messages", [])
            if switch_msgs:
                switch_embed = cog._build_switch_embed(switch_msgs, pokemon=None)
                if switch_embed:
                    await cog._safe_followup_send(interaction, embed=switch_embed)

        # Handle normal turn resolution
        elif res.get("ready_to_resolve") and cog:
            turn = await parent_view.engine.process_turn(parent_view.battle_id)
            await cog._send_turn_resolution(interaction, turn)

        if cog:
            await cog._handle_post_turn(interaction, parent_view.battle_id)
class PartySelectView(discord.ui.View):
    def __init__(self, battle, battler_id: int, engine: BattleEngine, forced: bool = False):
        super().__init__(timeout=None)
        self.battle_id = battle.battle_id
        self.engine = engine
        self.forced = forced
        self.add_item(PartySelect(battle, battler_id, forced=forced))
class BagView(discord.ui.View):
    """In-battle bag view focusing on Pokeballs so you can attempt captures at any time."""
    def __init__(self, battle_cog: BattleCog, battle, discord_user_id: int):
        super().__init__(timeout=None)
        self.battle_cog = battle_cog
        self.battle_id = battle.battle_id
        self.engine = battle_cog.battle_engine
        self.discord_user_id = discord_user_id

        balls = self.battle_cog._get_ball_inventory(discord_user_id)

        if not balls:
            self.add_item(
                discord.ui.Button(
                    label="(No usable items found)",
                    style=discord.ButtonStyle.secondary,
                    disabled=True
                )
            )
            return

        self.add_item(BagBallSelect(battle_cog, self.battle_id, balls))


class DazedCatchView(discord.ui.View):
    """Prompt that lets trainers confirm whether they will catch a dazed wild Pokemon."""

    def __init__(self, battle_cog: BattleCog, battle_id: str):
        super().__init__(timeout=None)
        self.battle_cog = battle_cog
        self.battle_id = battle_id

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Player chooses to attempt a guaranteed capture on a dazed target."""

        balls = self.battle_cog._get_ball_inventory(interaction.user.id)
        if not balls:
            await interaction.response.edit_message(
                content="❌ You have no Poke Balls available!",
                embed=None,
                view=None,
            )
            return

        options = [
            discord.SelectOption(
                label=f"{item_data.get('name', item_id)} x{qty}"[:100],
                value=item_id,
            )
            for item_id, (item_data, qty) in balls.items()
        ]

        select = discord.ui.Select(
            placeholder="Choose a Poke Ball",
            min_values=1,
            max_values=1,
            options=options,
        )

        async def select_callback(select_interaction: discord.Interaction):
            chosen_id = select_interaction.data["values"][0]
            await self.battle_cog._handle_ball_throw(
                select_interaction,
                self.battle_id,
                chosen_id,
                guaranteed=True,
            )
            try:
                await select_interaction.edit_original_response(view=None)
            except discord.HTTPException:
                pass

        select.callback = select_callback
        new_view = discord.ui.View(timeout=None)
        new_view.add_item(select)

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Select a Poke Ball",
                color=discord.Color.blue(),
            ),
            view=new_view,
        )

    @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Player declines to catch; the wild Pokemon flees and the encounter ends."""

        battle = self.battle_cog.battle_engine.get_battle(self.battle_id)
        if battle:
            battle.is_over = True
            battle.winner = "trainer"

        # First, edit the message to show the Pokemon fled
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="The wild Pokemon ran away!",
                description="It came to its senses and fled.",
                color=discord.Color.dark_grey(),
            ),
            view=None,
        )

        # Then award exp for defeating the wild Pokemon
        if battle:
            exp_embed = await self.battle_cog._create_exp_embed(battle, interaction)
            if exp_embed:
                await interaction.followup.send(embed=exp_embed)

# ============================================
# DOUBLES BATTLE UI COMPONENTS
# ============================================

class DoublesActionMenuView(discord.ui.View):
    """Action menu for individual Pokemon in doubles battles."""
    def __init__(self, battle, battler_id: int, engine: BattleEngine,
                 pokemon_position: int, collector: DoublesActionCollector):
        super().__init__(timeout=None)
        self.battle = battle
        self.battle_id = battle.battle_id
        self.battler_id = battler_id
        self.engine = engine
        self.pokemon_position = pokemon_position
        self.collector = collector

    @discord.ui.button(label="⚔️ Fight", style=discord.ButtonStyle.primary, row=0)
    async def fight_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Select a move for this Pokemon."""
        battler = _get_battler_by_id(self.battle, self.battler_id)
        pokemon = battler.get_active_pokemon()[self.pokemon_position]
        await interaction.response.edit_message(
            content=f"Select move for **{_format_battle_pokemon_name(pokemon)}** (Slot {self.pokemon_position + 1}):",
            view=DoublesMoveSelectView(
                self.battle, self.battler_id, self.engine,
                self.pokemon_position, self.collector
            )
        )

    @discord.ui.button(label="🔄 Switch", style=discord.ButtonStyle.primary, row=0)
    async def switch_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Switch this Pokemon."""
        await interaction.response.edit_message(
            content=f"Choose a Pokémon to switch into Slot {self.pokemon_position + 1}:",
            view=DoublesPartySelectView(
                self.battle, self.battler_id, self.engine,
                self.pokemon_position, self.collector, forced=False
            )
        )

    @discord.ui.button(label="🎒 Bag", style=discord.ButtonStyle.secondary, row=0)
    async def bag_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Use an item (not implemented for doubles yet)."""
        await interaction.response.send_message(
            "⚠️ Items in doubles battles are not yet supported. Please select a different action.",
            ephemeral=True
        )

    @discord.ui.button(label="🏃 Run", style=discord.ButtonStyle.danger, row=0)
    async def run_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Run from battle (forfeits for both Pokemon)."""
        # For doubles, running should forfeit the entire battle
        cog = interaction.client.get_cog("BattleCog")
        if cog:
            await cog._handle_forfeit(interaction, self.battle_id, self.battler_id)

class DoublesPartySelectView(discord.ui.View):
    """Party selection for switching in doubles battles."""
    def __init__(self, battle, battler_id: int, engine: BattleEngine,
                 pokemon_position: int, collector: DoublesActionCollector, forced: bool = False):
        super().__init__(timeout=None)
        self.battle = battle
        self.battle_id = battle.battle_id
        self.battler_id = battler_id
        self.engine = engine
        self.pokemon_position = pokemon_position
        self.collector = collector
        self.forced = forced

        # Get party
        battler = _get_battler_by_id(battle, battler_id)
        party = battler.party if battler else []

        # Create options for non-fainted, non-active Pokemon
        active_pokemon = battler.get_active_pokemon() if battler else []
        active_ids = {id(p) for p in active_pokemon}

        options = []
        for idx, mon in enumerate(party):
            if id(mon) in active_ids:
                continue  # Skip active Pokemon
            if mon.current_hp <= 0:
                continue  # Skip fainted Pokemon

            species_name = getattr(mon, 'species_name', 'Unknown')
            nickname = getattr(mon, 'nickname', None)
            level = getattr(mon, 'level', '?')
            hp = getattr(mon, 'current_hp', 0)
            max_hp = getattr(mon, 'max_hp', 1)

            display_name = nickname if nickname else species_name
            options.append(discord.SelectOption(
                label=f"{display_name} Lv{level} (HP: {hp}/{max_hp})",
                value=str(idx)
            ))

        if not options:
            # No valid Pokemon to switch to
            button = discord.ui.Button(
                label="(No Pokemon available to switch)",
                style=discord.ButtonStyle.secondary,
                disabled=True
            )
            self.add_item(button)
            return

        # Add select menu
        select = discord.ui.Select(
            placeholder="Choose a Pokemon to switch in",
            options=options[:25]  # Discord limit
        )
        select.callback = self._on_select
        self.add_item(select)

        # Add back button if not forced
        if not forced:
            back_btn = discord.ui.Button(label="← Back", style=discord.ButtonStyle.secondary)
            back_btn.callback = self._back_callback
            self.add_item(back_btn)

    async def _on_select(self, interaction: discord.Interaction):
        """Handle Pokemon selection."""
        value = None
        for child in self.children:
            if isinstance(child, discord.ui.Select) and child.values:
                value = child.values[0]
                break

        if value is None:
            await interaction.response.send_message("Invalid selection.", ephemeral=True)
            return

        party_index = int(value)

        # Create switch action
        action = BattleAction(
            action_type='switch',
            battler_id=self.battler_id,
            switch_to_position=party_index,
            pokemon_position=self.pokemon_position
        )

        # Add to collector
        self.collector.add_action(self.pokemon_position, action)

        # Check if we need more actions
        next_pos = self.collector.get_next_position()
        if next_pos is not None:
            battler = _get_battler_by_id(self.battle, self.battler_id)
            next_mon = battler.get_active_pokemon()[next_pos]
            await interaction.response.send_message(
                f"Choose action for **{_format_battle_pokemon_name(next_mon)}** (Slot {next_pos + 1}):",
                view=DoublesActionMenuView(
                    self.battle, self.battler_id, self.engine,
                    next_pos, self.collector
                ),
                ephemeral=True
            )
            return

        # All actions collected, submit them
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        for pos, act in self.collector.actions.items():
            self.engine.register_action(self.battle_id, self.battler_id, act)

        battle = self.engine.get_battle(self.battle_id)
        if not battle:
            await interaction.followup.send("Battle not found.", ephemeral=True)
            return

        # Check if ready to resolve
        if not battle.opponent.is_ai:
            if len(battle.pending_actions) < len(battle.trainer.get_active_pokemon()) + len(battle.opponent.get_active_pokemon()):
                await interaction.followup.send(
                    "Actions submitted! Waiting for opponent...",
                    ephemeral=True
                )
                return

        # Process turn
        cog = interaction.client.get_cog("BattleCog")
        if cog:
            turn = await self.engine.process_turn(self.battle_id)
            await cog._send_turn_resolution(interaction, turn)
            await cog._handle_post_turn(interaction, self.battle_id)

    async def _back_callback(self, interaction: discord.Interaction):
        """Go back to action menu."""
        battler = _get_battler_by_id(self.battle, self.battler_id)
        pokemon = battler.get_active_pokemon()[self.pokemon_position]
        await interaction.response.edit_message(
            content=f"Choose action for **{_format_battle_pokemon_name(pokemon)}** (Slot {self.pokemon_position + 1}):",
            view=DoublesActionMenuView(
                self.battle, self.battler_id, self.engine,
                self.pokemon_position, self.collector
            )
        )

class DoublesActionCollector:
    """Collects actions for both Pokemon in a doubles battle."""
    def __init__(self, battle, battler_id: int, engine: BattleEngine):
        self.battle = battle
        self.battler_id = battler_id
        self.engine = engine
        self.actions = {}  # {position: BattleAction}
        self.current_position = 0
        self.battle_id = battle.battle_id
        self.mega_reserved = False

    def has_all_actions(self) -> bool:
        """Check if we have actions for all active Pokemon."""
        battler = _get_battler_by_id(self.battle, self.battler_id)
        num_active = len(battler.get_active_pokemon())
        return len(self.actions) >= num_active

    def add_action(self, position: int, action: BattleAction):
        """Add an action for a specific position."""
        self.actions[position] = action
        self.refresh_mega_reserved()

    def refresh_mega_reserved(self) -> None:
        self.mega_reserved = any(getattr(action, "mega_evolve", False) for action in self.actions.values())

    def get_next_position(self) -> int | None:
        """Get the next position that needs an action."""
        battler = _get_battler_by_id(self.battle, self.battler_id)
        for pos in range(len(battler.get_active_pokemon())):
            if pos not in self.actions:
                return pos
        return None


class RevivalTargetSelectView(discord.ui.View):
    """Target selection for Revival Blessing (supports raids and doubles)."""

    def __init__(
        self,
        battle,
        battler_id: int,
        engine: BattleEngine,
        pokemon_position: int,
        options: list[discord.SelectOption],
        option_map: dict[str, tuple[int, int]],
        collector: DoublesActionCollector | None = None,
        mega_evolve: bool = False,
    ):
        super().__init__(timeout=None)
        self.battle = battle
        self.battle_id = battle.battle_id
        self.battler_id = battler_id
        self.engine = engine
        self.pokemon_position = pokemon_position
        self.collector = collector
        self.option_map = option_map
        self.mega_evolve = mega_evolve

        select = discord.ui.Select(placeholder="Select a Pokémon to revive", options=options)
        select.callback = self._on_select
        self.add_item(select)

        if collector:
            back_btn = discord.ui.Button(label="← Back", style=discord.ButtonStyle.secondary)
            back_btn.callback = self._back_callback
            self.add_item(back_btn)

    async def _back_callback(self, interaction: discord.Interaction):
        if not self.collector:
            await interaction.response.send_message("Cannot go back.", ephemeral=True)
            return

        await interaction.response.edit_message(
            content=f"Select move for Pokémon {self.pokemon_position + 1}:",
            view=DoublesMoveSelectView(
                self.battle, self.battler_id, self.engine,
                self.pokemon_position, self.collector
            ),
            embed=None
        )

    async def _on_select(self, interaction: discord.Interaction):
        value = None
        for child in self.children:
            if isinstance(child, discord.ui.Select) and child.values:
                value = child.values[0]
                break

        if not value or value not in self.option_map:
            await interaction.response.send_message("Invalid target selected.", ephemeral=True)
            return

        target_battler_id, target_index = self.option_map[value]

        action = BattleAction(
            action_type='move',
            battler_id=self.battler_id,
            move_id='revival_blessing',
            target_position=0,
            pokemon_position=self.pokemon_position,
            revive_target_battler_id=target_battler_id,
            revive_target_party_index=target_index,
            mega_evolve=self.mega_evolve,
        )

        if self.collector:
            await self._handle_collector_submission(interaction, action)
        else:
            await self._handle_single_submission(interaction, action)

    async def _handle_single_submission(self, interaction: discord.Interaction, action: BattleAction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        res = self.engine.register_action(self.battle_id, self.battler_id, action)
        cog = interaction.client.get_cog("BattleCog")

        # Check if RP mode is waiting for both players to press "Go"
        if res.get("rp_mode_waiting") and cog:
            await interaction.followup.send(
                "Move selected! Both players have chosen their actions.",
                ephemeral=True,
            )
            battle = self.engine.get_battle(self.battle_id)
            if battle:
                await cog._show_rp_mode_execution_prompt(interaction, battle)
            return

        if not res.get("ready_to_resolve"):
            waiting_for = res.get("waiting_for", [])
            trainer_word = "trainers" if len(waiting_for) > 1 else "trainer"
            await interaction.followup.send(
                f"Move selected! Waiting for the other {trainer_word} to choose...",
                ephemeral=True,
            )
            return

        if res.get("ready_to_resolve") and cog:
            turn = await self.engine.process_turn(self.battle_id)
            await cog._send_turn_resolution(interaction, turn)
            await cog._handle_post_turn(interaction, self.battle_id)

    async def _handle_collector_submission(self, interaction: discord.Interaction, action: BattleAction):
        if not self.collector:
            return

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        self.collector.add_action(self.pokemon_position, action)
        next_pos = self.collector.get_next_position()

        if next_pos is not None:
            battler = _get_battler_by_id(self.battle, self.battler_id)
            next_mon = battler.get_active_pokemon()[next_pos]
            await interaction.followup.send(
                f"Choose action for **{_format_battle_pokemon_name(next_mon)}** (Slot {next_pos+1}):",
                view=DoublesActionMenuView(
                    self.battle, self.battler_id, self.engine,
                    next_pos, self.collector
                ),
                ephemeral=True
            )
            return

        for _, act in self.collector.actions.items():
            self.engine.register_action(self.battle_id, self.battler_id, act)

        battle = self.engine.get_battle(self.battle_id)
        if not battle:
            await interaction.followup.send("Battle not found.", ephemeral=True)
            return

        if not battle.opponent.is_ai:
            if len(battle.pending_actions) < len(battle.trainer.get_active_pokemon()) + len(battle.opponent.get_active_pokemon()):
                await interaction.followup.send(
                    "Actions submitted! Waiting for opponent...",
                    ephemeral=True
                )
                return

        cog = interaction.client.get_cog("BattleCog")
        if cog:
            turn = await self.engine.process_turn(self.battle_id)
            await cog._send_turn_resolution(interaction, turn)
            await cog._handle_post_turn(interaction, self.battle_id)

class TargetSelectView(discord.ui.View):
    """View for selecting which target to attack in doubles battles."""
    def __init__(self, battle, battler_id: int, move_id: str, pokemon_position: int,
                 engine: BattleEngine, collector: DoublesActionCollector | None = None,
                 mega_evolve: bool = False):
        super().__init__(timeout=None)
        self.battle = battle
        self.battle_id = battle.battle_id
        self.battler_id = battler_id
        self.move_id = move_id
        self.pokemon_position = pokemon_position
        self.engine = engine
        self.collector = collector
        self.mega_evolve = mega_evolve

        move_data = engine.moves_db.get_move(move_id) if hasattr(engine, 'moves_db') else {}
        target_type = move_data.get('target', 'single')
        is_support = move_data.get('category') == 'status'
        self.target_candidates = self._build_candidates(target_type, is_support)

        auto_targets = {'all_adjacent', 'all_opponents', 'all', 'self', 'entire_field', 'user_field', 'enemy_field', 'all_allies'}
        if target_type in auto_targets:
            auto_btn = discord.ui.Button(label="✓ Confirm", style=discord.ButtonStyle.success, custom_id="auto_target")
            auto_btn.callback = self._create_target_callback(0)
            self.add_item(auto_btn)
        elif self.target_candidates:
            for idx, candidate in enumerate(self.target_candidates):
                # Color-code buttons: green for allies, red for enemies
                is_ally = candidate.get("is_ally", False)
                button_style = discord.ButtonStyle.success if is_ally else discord.ButtonStyle.danger

                button = discord.ui.Button(
                    label=self._format_candidate_label(candidate, target_type),
                    style=button_style,
                    custom_id=f"target_{idx}"
                )
                button.callback = self._create_target_callback(idx)
                self.add_item(button)
        else:
            auto_btn = discord.ui.Button(label="✓ Confirm", style=discord.ButtonStyle.success, custom_id="auto_target")
            auto_btn.callback = self._create_target_callback(0)
            self.add_item(auto_btn)

        # Add back button for doubles
        if collector:
            back_btn = discord.ui.Button(label="← Back", style=discord.ButtonStyle.secondary, custom_id="back")
            back_btn.callback = self._back_callback
            self.add_item(back_btn)

    @staticmethod
    def _format_target_name(pokemon) -> str:
        return _format_battle_pokemon_name(pokemon, include_level=False)

    def _format_candidate_label(self, candidate: dict, target_type: str) -> str:
        # For raids with single-target moves, distinguish between ally and opponent
        is_raid = self.battle.battle_format == BattleFormat.RAID
        if is_raid and target_type == 'single':
            prefix = "Ally" if candidate.get("is_ally") else "Target"
        else:
            prefix = "Target" if target_type != 'ally' else "Support"
        name = self._format_target_name(candidate.get("pokemon"))
        return f"{prefix}: {name} (Slot {candidate.get('position', 0) + 1})"

    def _build_candidates(self, target_type: str, is_support: bool) -> list[dict]:
        candidates: list[dict] = []
        attacker_battler = _get_battler_by_id(self.battle, self.battler_id)
        if not attacker_battler:
            return candidates

        acting_mon = None
        active_pokemon = attacker_battler.get_active_pokemon()
        if self.pokemon_position < len(active_pokemon):
            acting_mon = active_pokemon[self.pokemon_position]

        # For raids, include both allies and opponents as targets for single-target moves
        is_raid = self.battle.battle_format == BattleFormat.RAID
        include_allies = target_type == 'ally'
        include_opponents = target_type != 'ally'

        # In raids with single-target moves, allow targeting both allies and opponents
        if is_raid and target_type == 'single':
            include_allies = True
            include_opponents = True

        # Collect ally candidates
        if include_allies:
            ally_pools = self.battle.get_team_battlers(attacker_battler.battler_id)
            for battler in ally_pools:
                # Skip eliminated battlers
                if getattr(battler, "is_eliminated", False):
                    continue
                for idx, mon in enumerate(battler.get_active_pokemon()):
                    if getattr(mon, "current_hp", 0) <= 0:
                        continue
                    if mon is acting_mon:
                        continue
                    candidates.append({
                        "battler_id": battler.battler_id,
                        "position": idx,
                        "pokemon": mon,
                        "is_rogue": getattr(mon, "is_raid_boss", False),
                        "is_ally": True,
                    })

        # Collect opponent candidates
        if include_opponents:
            opponent_pools = self.battle.get_opposing_team_battlers(attacker_battler.battler_id)
            for battler in opponent_pools:
                # Skip eliminated battlers
                if getattr(battler, "is_eliminated", False):
                    continue
                for idx, mon in enumerate(battler.get_active_pokemon()):
                    if getattr(mon, "current_hp", 0) <= 0:
                        continue
                    candidates.append({
                        "battler_id": battler.battler_id,
                        "position": idx,
                        "pokemon": mon,
                        "is_rogue": getattr(mon, "is_raid_boss", False),
                        "is_ally": False,
                    })

        if not candidates:
            return candidates

        # In raids, prioritize raid boss for offensive moves, allies for support moves
        rogue_candidates = [c for c in candidates if c.get("is_rogue")]
        ally_candidates = [c for c in candidates if not c.get("is_rogue") and c.get("is_ally")]
        opponent_candidates = [c for c in candidates if not c.get("is_rogue") and not c.get("is_ally")]

        if rogue_candidates:
            if is_support:
                # Support moves: allies first, then opponents, then rogue
                candidates = ally_candidates + opponent_candidates + rogue_candidates
            else:
                # Offensive moves: rogue first, then opponents, then allies
                candidates = rogue_candidates + opponent_candidates + ally_candidates
        else:
            # No rogue: allies first for support, opponents first for offense
            if is_support:
                candidates = ally_candidates + opponent_candidates
            else:
                candidates = opponent_candidates + ally_candidates

        return candidates

    def _create_target_callback(self, target_idx: int):
        async def callback(interaction: discord.Interaction):
            await self._handle_target_selection(interaction, target_idx)
        return callback

    async def _back_callback(self, interaction: discord.Interaction):
        """Go back to move selection."""
        if self.pokemon_position > 0 and self.collector:
            # Remove the previous action
            self.collector.actions.pop(self.pokemon_position, None)
            self.collector.refresh_mega_reserved()
            await interaction.response.edit_message(
                content=f"Select move for Pokemon {self.pokemon_position} (Slot {self.pokemon_position+1}):",
                view=DoublesMoveSelectView(
                    self.battle, self.battler_id, self.engine,
                    self.pokemon_position, self.collector
                ),
                embed=None
            )
        else:
            await interaction.response.edit_message(
                content="Cannot go back further.",
                view=None,
                embed=None
            )

    async def _handle_target_selection(self, interaction: discord.Interaction, target_idx: int):
        await interaction.response.defer()

        candidate = None
        if getattr(self, "target_candidates", None) and 0 <= target_idx < len(self.target_candidates):
            candidate = self.target_candidates[target_idx]
        target_position = candidate.get("position") if candidate else target_idx
        target_battler_id = candidate.get("battler_id") if candidate else None

        # Create the action
        action = BattleAction(
            action_type='move',
            battler_id=self.battler_id,
            move_id=self.move_id,
            target_position=target_position,
            target_battler_id=target_battler_id,
            pokemon_position=self.pokemon_position,
            mega_evolve=self.mega_evolve,
        )

        # If this is part of a doubles collector, add to collector
        if self.collector:
            self.collector.add_action(self.pokemon_position, action)

            # Check if we need to select for more Pokemon
            next_pos = self.collector.get_next_position()
            if next_pos is not None:
                battler = _get_battler_by_id(self.battle, self.battler_id)
                next_mon = battler.get_active_pokemon()[next_pos]
                await interaction.followup.send(
                    f"Choose action for **{_format_battle_pokemon_name(next_mon)}** (Slot {next_pos+1}):",
                    view=DoublesActionMenuView(
                        self.battle, self.battler_id, self.engine,
                        next_pos, self.collector
                    ),
                    ephemeral=True
                )
                return

            # All actions collected, submit them all
            for pos, act in self.collector.actions.items():
                self.engine.register_action(self.battle_id, self.battler_id, act)

            # Check if ready to resolve
            res = {'ready_to_resolve': True}  # In doubles, need to check if opponent is ready too
            battle = self.engine.get_battle(self.battle_id)
            if not battle:
                await interaction.followup.send("Battle not found.", ephemeral=True)
                return

            # For PvP battles, check if all required actions are registered
            # (AI actions will be generated automatically in process_turn)
            if not battle.opponent.is_ai:
                if len(battle.pending_actions) < len(battle.trainer.get_active_pokemon()) + len(battle.opponent.get_active_pokemon()):
                    await interaction.followup.send(
                        "Actions submitted! Waiting for opponent...",
                        ephemeral=True
                    )
                    return

            # Check for RP mode
            cog = interaction.client.get_cog("BattleCog")
            if battle.rp_mode_active and battle.battle_type == BattleType.PVP and cog:
                await interaction.followup.send(
                    "Actions submitted! Both players have chosen their actions.",
                    ephemeral=True,
                )
                await cog._show_rp_mode_execution_prompt(interaction, battle)
                return

            # Process turn
            if res.get("ready_to_resolve") and cog:
                turn = await self.engine.process_turn(self.battle_id)
                await cog._send_turn_resolution(interaction, turn)
                await cog._handle_post_turn(interaction, self.battle_id)
        else:
            # Singles battle path
            res = self.engine.register_action(self.battle_id, self.battler_id, action)
            cog = interaction.client.get_cog("BattleCog")

            # Check if RP mode is waiting for both players to press "Go"
            if res.get("rp_mode_waiting") and cog:
                await interaction.followup.send(
                    "Move selected! Both players have chosen their actions.",
                    ephemeral=True,
                )
                battle = self.engine.get_battle(self.battle_id)
                if battle:
                    await cog._show_rp_mode_execution_prompt(interaction, battle)
                return

            if not res.get("ready_to_resolve"):
                waiting_for = res.get("waiting_for", [])
                trainer_word = "trainers" if len(waiting_for) > 1 else "trainer"
                await interaction.followup.send(
                    f"Move selected! Waiting for the other {trainer_word}...",
                    ephemeral=True
                )
                return

            if res.get("ready_to_resolve") and cog:
                turn = await self.engine.process_turn(self.battle_id)
                await cog._send_turn_resolution(interaction, turn)
                await cog._handle_post_turn(interaction, self.battle_id)


class DoublesMoveSelectView(discord.ui.View):
    """Move selection view for one Pokemon in a doubles battle."""
    def __init__(self, battle, battler_id: int, engine: BattleEngine,
                 pokemon_position: int, collector: DoublesActionCollector):
        super().__init__(timeout=None)
        self.battle = battle
        self.battle_id = battle.battle_id
        self.battler_id = battler_id
        self.engine = engine
        self.pokemon_position = pokemon_position
        self.collector = collector
        self.mega_selected = False
        self.mega_name = None

        # Get the Pokemon at this position
        battler = battle.trainer if battler_id == battle.trainer.battler_id else battle.opponent
        active_pokemon = battler.get_active_pokemon()[pokemon_position]

        # Add move buttons
        for mv in getattr(active_pokemon, "moves", [])[:4]:
            move_id = mv.get("move_id") or mv.get("id")
            if not move_id:
                continue

            move_info = engine.moves_db.get_move(move_id) if hasattr(engine, "moves_db") else None
            move_name = (move_info.get("name") if move_info else None) or mv.get("name") or move_id
            cur_pp = mv.get("pp")
            max_pp = mv.get("max_pp")
            label = f"{move_name} ({cur_pp}/{max_pp})" if (cur_pp is not None and max_pp is not None) else move_name

            button = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.secondary,
                disabled=(cur_pp is not None and cur_pp <= 0)
            )
            button.callback = self._create_move_callback(move_id)
            self.add_item(button)

        mega_name = engine.get_mega_evolution_name(battle, battler_id, active_pokemon)
        if mega_name and not self.collector.mega_reserved:
            self.mega_name = mega_name
            self.add_item(MegaEvolveButton(mega_name))

        # Add back button if this isn't the first Pokemon
        if pokemon_position > 0:
            back_btn = discord.ui.Button(label="← Back to previous Pokemon", style=discord.ButtonStyle.secondary)
            back_btn.callback = self._back_callback
            self.add_item(back_btn)

    def _create_move_callback(self, move_id: str):
        async def callback(interaction: discord.Interaction):
            battle = self.engine.get_battle(self.battle_id) or self.battle
            if move_id == "revival_blessing":
                options, option_map = _build_revival_target_options(battle, self.battler_id)
                if not options:
                    await interaction.response.edit_message(
                        content="There are no fainted ally Pokémon to revive.",
                        view=None,
                        embed=None,
                    )
                    return

                await interaction.response.edit_message(
                    content="Select a Pokémon to revive:",
                    view=RevivalTargetSelectView(
                        battle=battle,
                        battler_id=self.battler_id,
                        engine=self.engine,
                        pokemon_position=self.pokemon_position,
                        options=options,
                        option_map=option_map,
                        collector=self.collector,
                        mega_evolve=self.mega_selected,
                    ),
                    embed=None,
                )
            else:
                await interaction.response.edit_message(
                    content=f"Select target for this move:",
                    view=TargetSelectView(
                        self.battle, self.battler_id, move_id,
                        self.pokemon_position, self.engine, self.collector,
                        mega_evolve=self.mega_selected
                    ),
                    embed=None
                )
        return callback

    async def _back_callback(self, interaction: discord.Interaction):
        """Go back to previous Pokemon's move selection."""
        prev_pos = self.pokemon_position - 1
        if prev_pos >= 0:
            # Remove previous Pokemon's action
            self.collector.actions.pop(prev_pos, None)
            self.collector.refresh_mega_reserved()
            battler = _get_battler_by_id(self.battle, self.battler_id)
            prev_mon = battler.get_active_pokemon()[prev_pos]
            await interaction.response.edit_message(
                content=f"Select move for **{_format_battle_pokemon_name(prev_mon)}** (Slot {prev_pos+1}):",
                view=DoublesMoveSelectView(
                    self.battle, self.battler_id, self.engine,
                    prev_pos, self.collector
                ),
                embed=None
            )
        else:
            await interaction.response.send_message("Cannot go back further.", ephemeral=True)


# ============================================
# END DOUBLES BATTLE UI COMPONENTS
# ============================================

async def setup(bot):
    """discord.py 2.x extension entrypoint for BattleCog"""
    # Reuse existing engine if present
    engine = getattr(bot, "battle_engine", None)
    if engine is None:
        # Build required DBs from cached bot attributes when possible
        from database import MovesDatabase, TypeChart, SpeciesDatabase, ItemsDatabase

        moves_db = getattr(bot, 'moves_db', None) or MovesDatabase('data/moves.json')
        type_chart = getattr(bot, 'type_chart', None) or TypeChart('data/type_chart.json')
        species_db = getattr(bot, 'species_db', None) or SpeciesDatabase('data/pokemon_species.json')
        items_db = getattr(bot, 'items_db', None) or ItemsDatabase('data/items.json')

        from battle_engine_v2 import BattleEngine
        engine = BattleEngine(moves_db, type_chart, species_db, items_db=items_db)
        bot.battle_engine = engine
    else:
        if getattr(engine, 'held_item_manager', None) is None and getattr(bot, 'items_db', None):
            engine.items_db = bot.items_db
            engine.held_item_manager = HeldItemManager(
                bot.items_db, getattr(engine, 'type_chart', None)
            )
    engine.player_manager = getattr(bot, 'player_manager', None)
    await bot.add_cog(BattleCog(bot, engine))
