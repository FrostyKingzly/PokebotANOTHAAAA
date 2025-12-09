import discord
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
    create_music_starting_embed, create_victory_music_embed
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

        # Optionally send a victory music notification
        if interaction:
            victory_embed = create_victory_music_embed(winner_name)
            try:
                await interaction.followup.send(embed=victory_embed, ephemeral=True)
            except:
                pass

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
            battle_begin_embed = await self._send_raid_intro(interaction, raid_mon)

            sprite_embed = self._create_raid_sprite_embed(raid_mon)
            status_embed = self._create_raid_status_embed(battle)
            party_embed = self._create_raid_party_embed(battle)
            view = self._create_battle_view(battle)

            if sprite_embed:
                await interaction.followup.send(embed=sprite_embed)

            await self._send_raid_sendouts(interaction, battle)

            field_embed = self._create_field_effects_embed(battle)

            if battle_begin_embed:
                await interaction.followup.send(embed=battle_begin_embed)

            if field_embed:
                await interaction.followup.send(embed=field_embed)

            await interaction.followup.send(embed=status_embed)
            await interaction.followup.send(embed=party_embed, view=view)
            return

        # 1) Opening embed: differentiate wild encounters vs trainer battles
        if battle_mode == BattleType.WILD:
            enc_title = f"{SWORD} Encounter!"
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

        # If there are entry messages or field effects, send them in a final embed
        field_embed = self._create_field_effects_embed(battle, entry_messages)
        if field_embed:
            await interaction.followup.send(embed=field_embed)

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
        name = getattr(pokemon, "nickname", None) or getattr(pokemon, "species_name", "Pokémon")
        if getattr(pokemon, "is_raid_boss", False):
            name = f"Rogue {name}"
        level = getattr(pokemon, "level", None)
        if include_level and level is not None:
            return f"{name} Lv{level}"
        return name

    def _build_raid_hp_bars(self, mon) -> str:
        total_segments = min(3, max(1, math.ceil(getattr(mon, "level", 1) / 100)))
        hp_ratio = max(0.0, getattr(mon, "current_hp", 0) / max(1, getattr(mon, "max_hp", 1)))
        segment_size = 1 / total_segments

        bars: list[str] = []
        for idx in range(total_segments):
            filled_ratio = min(segment_size, max(0.0, hp_ratio - (idx * segment_size))) / segment_size
            bars.append(EmbedBuilder._create_hp_bar(filled_ratio * 100, length=30))

        return "\n".join(bars)

    def _create_raid_status_embed(self, battle) -> discord.Embed:
        raid_mon = (battle.opponent.get_active_pokemon() or [None])[0]
        if not raid_mon:
            return discord.Embed(title="Raid Battle", description="Prepare for battle!", color=discord.Color.dark_red())

        hp_bars = self._build_raid_hp_bars(raid_mon)
        type_list = getattr(raid_mon, "species_data", {}).get("types", [])
        type_emojis = " / ".join([EmbedBuilder._type_to_emoji(t) for t in type_list])

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

    def _create_raid_party_embed(self, battle) -> discord.Embed:
        embed = discord.Embed(
            title="Raid Party",
            description="Trainers, choose your actions!",
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

        # Add weather and terrain information
        field_conditions = []
        if getattr(battle, "weather", None):
            weather_turns = getattr(battle, "weather_turns", 0)
            # Only show turn count for player-set weather (5-8 turns), not permanent rogue weather (99+ turns)
            turns_text = f" ({weather_turns} turns left)" if weather_turns > 0 and weather_turns < 99 else ""
            field_conditions.append(f"Weather: **{battle.weather.title()}**{turns_text}")
        if getattr(battle, "terrain", None):
            terrain_turns = getattr(battle, "terrain_turns", 0)
            turns_text = f" ({terrain_turns} turns left)" if terrain_turns > 0 else ""
            field_conditions.append(f"Terrain: **{battle.terrain.title()}**{turns_text}")

        if field_conditions:
            embed.add_field(name="🌤️ Field Effects", value="\n".join(field_conditions), inline=False)

        return embed

    def _create_raid_sprite_embed(self, raid_mon) -> Optional[discord.Embed]:
        if not raid_mon:
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

    async def _send_raid_intro(self, interaction: discord.Interaction, raid_mon) -> Optional[discord.Embed]:
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
                embeds.append(self._build_action_embed(faint_msgs, title="Pokémon Fainted", color=discord.Color.red()))
            return [emb for emb in embeds if emb]

        for event in events:
            raw_messages = event.get("messages") or []
            action_msgs, faint_msgs = self._split_faint_messages(raw_messages)

            if action_msgs:
                if event.get("type") == "end_of_turn":
                    title = "End of Turn"
                    color = discord.Color.orange()
                else:
                    actor = event.get("actor")
                    actor_name = self._format_pokemon_name(actor, include_level=False) if actor else "Action"
                    title = f"{actor_name}'s Action" if actor else "Action"
                    color = discord.Color.orange()

                embed = self._build_action_embed(action_msgs, title=title, color=color)
                if embed:
                    embeds.append(embed)

            if faint_msgs:
                faint_embed = self._build_action_embed(faint_msgs, title="Pokémon Fainted", color=discord.Color.red())
                if faint_embed:
                    embeds.append(faint_embed)

        if not embeds:
            messages = turn_result.get("messages") or []
            action_msgs, faint_msgs = self._split_faint_messages(messages)
            fallback = self._build_action_embed(action_msgs, title="Turn Result")
            if fallback:
                embeds.append(fallback)
            if faint_msgs:
                faint_fallback = self._build_action_embed(faint_msgs, title="Pokémon Fainted", color=discord.Color.red())
                if faint_fallback:
                    embeds.append(faint_fallback)

        return embeds

    def _build_action_embed(self, messages: list[str], title: str, color: Optional[discord.Color] = None) -> Optional[discord.Embed]:
        if not messages:
            return None
        spaced = []
        for msg in messages:
            if msg is None:
                continue
            spaced.append(str(msg))
            spaced.append("")
        if spaced and spaced[-1] == "":
            spaced.pop()
        desc = "\n".join(spaced) if spaced else "The turn resolves."
        return discord.Embed(title=title, description=desc, color=color or discord.Color.orange())

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
        action_embeds = self._build_turn_embeds(turn_result)
        for embed in action_embeds:
            await self._safe_followup_send(interaction, embed=embed)

        switch_events = turn_result.get("switch_events")
        if switch_events is None:
            switch_msgs = [msg for msg in (turn_result.get('switch_messages') or []) if msg]
            switch_events = ([{"messages": switch_msgs}] if switch_msgs else [])

        for event in switch_events or []:
            embed = self._build_switch_embed(event.get("messages") or [], pokemon=event.get("pokemon"))
            if embed:
                await self._safe_followup_send(interaction, embed=embed)

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

        # Check if this is a U-turn/Volt Switch or a fainted Pokemon
        # First check the new pending_switches dict
        is_volt_switch = False
        if battler_id in battle.pending_switches:
            switch_info = battle.pending_switches[battler_id]
            is_volt_switch = switch_info.get('switch_type') == 'VOLT'
        else:
            # Fall back to old logic
            is_volt_switch = battle.phase == 'VOLT_SWITCH'

        if is_volt_switch:
            # U-turn/Volt Switch case
            active_mon = battler.get_active_pokemon()[0] if battler.get_active_pokemon() else None
            if active_mon:
                desc = (
                    f"**{self._format_pokemon_name(active_mon, include_level=False)}** will switch out!\n\n"
                    "Select another Pokémon to switch in."
                )
            else:
                desc = "Select a Pokémon to switch in."
            embed = discord.Embed(title="Switch Required!", description=desc, color=discord.Color.blue())
        else:
            # Fainted Pokemon case
            fainted = battler.get_active_pokemon()[0] if battler.get_active_pokemon() else None
            if fainted:
                desc = (
                    f"**{self._format_pokemon_name(fainted, include_level=False)}** can no longer fight!\n\n"
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
            desc = "🏆 Battle Over\n\nIt's a draw!"
            await self._safe_followup_send(
                interaction,
                embed=discord.Embed(title='Battle Over', description=desc, color=discord.Color.gold())
            )
            self.battle_engine.end_battle(battle.battle_id)
            self._unregister_battle(battle)
            return

        try:
            from database import PlayerDatabase
            pdb = PlayerDatabase('data/players.db')
            party_rows = pdb.get_trainer_party(battle.trainer.battler_id)
            rows_by_pos = {row.get('party_position', i): row for i, row in enumerate(party_rows)}
            for i, mon in enumerate(battle.trainer.party):
                row = rows_by_pos.get(i) or rows_by_pos.get(getattr(mon, 'party_position', i))
                if row and 'pokemon_id' in row:
                    pdb.update_pokemon(row['pokemon_id'], {'current_hp': max(0, int(getattr(mon, 'current_hp', 0)))})
        except Exception:
            pass

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
                title = 'Battle Over'
                color = discord.Color.red()
        else:
            desc = f"🏆 Battle Over\n\nAll of {loser_name}'s Pokémon have fainted! {winner_name} wins!"
            title = 'Battle Over'
            color = discord.Color.gold() if result == 'trainer' else discord.Color.red()

        # Play victory music if enabled
        if result in ['trainer', 'opponent']:
            actual_winner_name = winner_name if hasattr(battle, 'winner') else 'Winner'
            await self._play_victory_music(battle.battle_id, actual_winner_name, interaction)

        await self._safe_followup_send(
            interaction,
            embed=discord.Embed(title=title, description=desc, color=color)
        )

        exp_embed = None
        if result == 'trainer':
            exp_embed = await self._create_exp_embed(battle, interaction)
        if exp_embed:
            # Send exp embed as ephemeral to reduce clutter
            try:
                await interaction.followup.send(embed=exp_embed, ephemeral=True)
            except Exception:
                # Fallback to channel send if ephemeral fails
                await self._safe_followup_send(interaction, embed=exp_embed)

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
        # Note: Don't cleanup music here - let it play victory theme for 1 minute

        if getattr(battle, 'battle_type', None) == BattleType.WILD:
            await self.send_return_to_encounter_prompt(interaction, battle.trainer.battler_id)

    async def _create_exp_embed(self, battle, interaction: Optional[discord.Interaction] = None) -> Optional[discord.Embed]:
        if not self.exp_handler:
            return None

        trainer = getattr(battle, 'trainer', None)
        opponent = getattr(battle, 'opponent', None)
        if not trainer or not getattr(trainer, 'party', None):
            return None

        active_index = 0
        if getattr(trainer, 'active_positions', None):
            try:
                active_index = int(trainer.active_positions[0])
            except (TypeError, ValueError, IndexError):
                active_index = 0

        defeated_pokemon = None
        opponent_party = getattr(opponent, 'party', None) if opponent else None
        if opponent_party:
            active_positions = getattr(opponent, 'active_positions', None) or []
            if active_positions:
                try:
                    opp_active_index = int(active_positions[0])
                except (TypeError, ValueError, IndexError):
                    opp_active_index = 0
            else:
                opp_active_index = 0

            if 0 <= opp_active_index < len(opponent_party):
                defeated_pokemon = opponent_party[opp_active_index]

            if defeated_pokemon is None:
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

        return self.exp_handler.create_exp_embed(results, trainer.party, defeated_pokemon)

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

        if battle.battle_type == BattleType.WILD and getattr(battle, "wild_dazed", False) and not battle.is_over:
            await self._send_dazed_prompt(interaction, battle)
            return

        if battle.is_over:
            await self._finish_battle(interaction, battle)
            return

        # Check for forced switches (either from KO or from U-turn/Volt Switch)
        # First check the new pending_switches dict, fall back to old fields for compatibility
        if battle.pending_switches:
            # Get the first player (non-AI) that needs to switch
            for battler_id, switch_info in battle.pending_switches.items():
                battler = _get_battler_by_id(battle, battler_id)
                if battler and not getattr(battler, 'is_ai', False):
                    await self._prompt_forced_switch(interaction, battle, battler_id)
                    return
        elif battle.phase in ['FORCED_SWITCH', 'VOLT_SWITCH'] and battle.forced_switch_battler_id:
            await self._prompt_forced_switch(interaction, battle, battle.forced_switch_battler_id)
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

class BattleActionView(discord.ui.View):
    def __init__(self, battle_id: str, battler_id: int, engine: BattleEngine, battle, battle_cog: 'BattleCog'):
        super().__init__(timeout=None)
        self.battle_id = battle_id
        self.battler_id = battler_id
        self.engine = engine
        self.battle = battle
        self.cog = battle_cog

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
                f"Select move for **{first_mon.species_name}** (Slot 1):",
                view=DoublesMoveSelectView(battle, battler_id, self.engine, 0, collector),
                ephemeral=True,
            )
        else:
            # Singles battle
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
                ),
                ephemeral=True,
            )
            return
        action = BattleAction(action_type='move', battler_id=self.battler_id, move_id=self.move_id, target_position=0)
        res = self.engine.register_action(self.battle_id, self.battler_id, action)
        cog = interaction.client.get_cog("BattleCog")

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
        options = []
        battler = _get_battler_by_id(battle, battler_id) or battle.trainer
        party = battler.party
        active_index = battler.active_positions[0]  # Get actual active position
        for idx, mon in enumerate(party):
            name = getattr(mon, "species_name", f"Slot {idx+1}")
            current_hp = getattr(mon, 'current_hp', 0)
            max_hp = getattr(mon, 'max_hp', 1)
            hp = "(Fainted)" if current_hp <= 0 else f"{current_hp}/{max_hp}"
            # Skip disabled options (active or fainted Pokemon)
            if idx == active_index or current_hp <= 0:
                continue
            options.append(discord.SelectOption(label=name, description=f"HP {hp}", value=str(idx), default=False))
        placeholder = "Choose a Pokémon to send out" if forced else "Choose a Pokémon to switch in"
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
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
            if cog:
                send_embed = cog._build_switch_embed(messages, title="Send-out", pokemon=result.get("pokemon"))
                if send_embed:
                    await cog._safe_followup_send(interaction, embed=send_embed)
                battle = parent_view.engine.get_battle(parent_view.battle_id)
                if battle:
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

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="The wild Pokemon ran away!",
                description="It came to its senses and fled.",
                color=discord.Color.dark_grey(),
            ),
            view=None,
        )

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
            content=f"Select move for **{pokemon.species_name}** (Slot {self.pokemon_position + 1}):",
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
            party_index=party_index,
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
                f"Choose action for **{next_mon.species_name}** (Slot {next_pos + 1}):",
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
            content=f"Choose action for **{pokemon.species_name}** (Slot {self.pokemon_position + 1}):",
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

    def has_all_actions(self) -> bool:
        """Check if we have actions for all active Pokemon."""
        battler = _get_battler_by_id(self.battle, self.battler_id)
        num_active = len(battler.get_active_pokemon())
        return len(self.actions) >= num_active

    def add_action(self, position: int, action: BattleAction):
        """Add an action for a specific position."""
        self.actions[position] = action

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
    ):
        super().__init__(timeout=None)
        self.battle = battle
        self.battle_id = battle.battle_id
        self.battler_id = battler_id
        self.engine = engine
        self.pokemon_position = pokemon_position
        self.collector = collector
        self.option_map = option_map

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
                f"Choose action for **{next_mon.species_name}** (Slot {next_pos+1}):",
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
                 engine: BattleEngine, collector: DoublesActionCollector | None = None):
        super().__init__(timeout=None)
        self.battle = battle
        self.battle_id = battle.battle_id
        self.battler_id = battler_id
        self.move_id = move_id
        self.pokemon_position = pokemon_position
        self.engine = engine
        self.collector = collector

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
        name = getattr(pokemon, "nickname", None) or getattr(pokemon, "species_name", "Pokémon")
        if getattr(pokemon, "is_raid_boss", False):
            name = f"Rogue {name}"
        return name

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
            pokemon_position=self.pokemon_position
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
                    f"Choose action for **{next_mon.species_name}** (Slot {next_pos+1}):",
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

            # Process turn
            cog = interaction.client.get_cog("BattleCog")
            if res.get("ready_to_resolve") and cog:
                turn = await self.engine.process_turn(self.battle_id)
                await cog._send_turn_resolution(interaction, turn)
                await cog._handle_post_turn(interaction, self.battle_id)
        else:
            # Singles battle path
            res = self.engine.register_action(self.battle_id, self.battler_id, action)
            cog = interaction.client.get_cog("BattleCog")

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
                    ),
                    embed=None,
                )
            else:
                await interaction.response.edit_message(
                    content=f"Select target for this move:",
                    view=TargetSelectView(
                        self.battle, self.battler_id, move_id,
                        self.pokemon_position, self.engine, self.collector
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
            battler = _get_battler_by_id(self.battle, self.battler_id)
            prev_mon = battler.get_active_pokemon()[prev_pos]
            await interaction.response.edit_message(
                content=f"Select move for **{prev_mon.species_name}** (Slot {prev_pos+1}):",
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
            engine.held_item_manager = HeldItemManager(bot.items_db)
    await bot.add_cog(BattleCog(bot, engine))