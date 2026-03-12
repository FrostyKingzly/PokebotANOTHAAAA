"""
Embed Builders - Creates Discord embeds for various UI elements
"""

import discord
import time
from typing import List, Dict, Optional
from ui.emoji import POKEBALL_EMOJIS, DEFAULT_POKEBALL_ID
from models import Trainer
from exp_display_helpers import create_exp_text
from rank_manager import get_rank_tier_definition
from sprite_helper import PokemonSpriteHelper
from database import NaturesDatabase
from social_stats import SOCIAL_STAT_DEFINITIONS, SOCIAL_STAT_ORDER


class _RotomFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


class EmbedBuilder:
    """Builds Discord embeds for the bot"""

    ROTOM_EMOJI = "<:rotomphone:1445206692936683662>"

    # Color scheme
    PRIMARY_COLOR = discord.Color.blue()
    SUCCESS_COLOR = discord.Color.green()
    ERROR_COLOR = discord.Color.red()
    WARNING_COLOR = discord.Color.orange()
    INFO_COLOR = discord.Color.blurple()

    # Custom emoji maps for types and move categories
    TYPE_EMOJIS = {
        "water":   "<:water:1439925544316833842>",
        "steel":   "<:steel:1439925520044130415>",
        "rock":    "<:rock:1439925494911995998>",
        "psychic": "<:psychic:1439925467221065798>",
        "poison":  "<:poison:1439925408819712191>",
        "normal":  "<:normal:1439925381003214898>",
        "ice":     "<:ice:1439925353035468800>",
        "ground":  "<:ground:1439925294436974704>",
        "grass":   "<:grass:1439925265382899733>",
        "ghost":   "<:ghost:1439925238275113010>",
        "flying":  "<:flying:1439925185825476720>",
        "fire":    "<:fire:1439925160160264233>",
        "fighting": "<:fighting:1439925134306836522>",
        "fairy":   "<:fairy:1439925034901700782>",
        "electric": "<:electric:1439925007928262756>",
        "dragon": "<:dragon:1439924981231259688>",
        "dark":   "<:dark:1439924928920162346>",
        "bug":    "<:bug:1439922930221060117>",
    }

    CATEGORY_EMOJIS = {
        "physical": "<:physical:1441199338662527036>",
        "special":  "<:special:1441199429934649485>",
        # If you add a :status: emoji later, put it here:
        # "status": "<:status:ID>",
    }

    # Rotom quotes
    ROTOM_QUOTES_GENERAL = [
        "Bzzt! Rotom-Drone online! Please don't drop me this time!",
        "Processing… processing… just kidding, I'm always fast!",
        "Did someone say Adven-Tour?!",
        "If you catch something cool today, promise you'll let me take a picture!",
        "Rotom Tip: Staying hydrated!",
        "Let's go do something productive!",
        "I ran a system scan and found… absolutely nothing. Clean as a Whimsicott!",
        "Reminder: I believe in you! Also reminder: Charge your phone.",
    ]

    ROTOM_QUOTES_CONTEXTUAL = {
        "time:morning": [
            "Bzzt… morning detected! Let’s boot up nice and slow, okay?",
            "Systems online! Hope you slept better than I did…",
        ],
        "time:day": [
            "It’s a great day to get things done!",
        ],
        "time:evening": [
            "Looks like sun’s going down… kinda pretty, huh?",
            "Evenings feel quieter… like the world’s catching its breath.",
            "It’s getting late… but there’s still time for another adventure!",
        ],
        "time:night": [
            "It’s getting late… but I’ll stay awake as long as you do.",
            "Hey… you still awake? Don’t forget to rest up when you can.",
        ],
        "weather:sunshine": [
            "Sun’s out, circuits warm—perfect weather for a photo op!",
            "Bzzt! Plenty of sunlight today. Let’s make the most of it!",
        ],
        "weather:rain": [
            "Rain detected. I’m waterproof, but you still might want an umbrella.",
            "Pitter-patter… I’ll keep the map clear while you stay dry.",
        ],
        "weather:snowing": [
            "Snow’s falling! Hope you brought a scarf.",
            "Brrr… even I can feel that chill. Stay warm out there!",
        ],
        "weather:thunder_storm": [
            "Storm alert! Let’s keep our distance from tall trees, okay?",
            "Zzzt! Static in the air… that’s some serious lightning.",
        ],
        "weather:cloudy": [
            "Cloud cover detected—soft light, great for photos.",
            "Overcast skies. Perfect weather for a quiet walk.",
        ],
        "weather:gentle_skies": [
            "Gentle skies… feels like a good day to explore.",
            "The breeze is nice. Let’s take a long route!",
        ],
        "weather:heatwave": [
            "Heatwave warning. Hydration check!",
            "It’s blazing out there—let’s take it easy.",
        ],
        "weather:sandstorm": [
            "Sandstorm detected. I’ll keep the grit out of the ports.",
            "Visibility’s low—stay close, okay?",
        ],
        "weather:blizzard": [
            "Blizzard conditions! Stay warm and stick to safe paths.",
            "Whiteout alert… I’ll keep the route marked.",
        ],
        "stamina:full": [
            "You’re running at peak power right now! Don’t waste it!",
            "I can feel the spark! You’re ready for anything!",
        ],
        "stamina:medium": [
            "Still doing good! Just… don’t forget to pace yourself.",
            "You’ve still got energy left. Just be smart with it, okay?",
        ],
        "stamina:low": [
            "Hey… your energy’s running low. Maybe it’s time to rest for a bit?",
            "It’s okay to stop for now. You don’t have to do everything today.",
        ],
        "promotion:scheduled": [
            "Bzzt! A promotion match has been set! We’d better prepare!",
            "This upcoming promotion match could change everything. No pressure!",
            "Alright! You’re up against {OPPONENT_NAME} in a {BATTLE_FORMAT} match! Data says this won’t be easy!",
            "Looks like your opponent will be {OPPONENT_NAME} in a {BATTLE_FORMAT} match! Maybe we should learn more about them before the battle.",
        ],
        "ticket:held": [
            "Challenger Ticket obtained! Now we just need to wait for your promotion match to be scheduled.",
            "You have a Challanger Ticket! Way to go!",
            "That’s a Challenger Ticket!! You earned it!",
            "Now that you’ve got a Challenger Ticket, I wonder who your next opponent will be…",
            "Nice job snagging yourself a ticket! We should use this downtime to prepare for the big match.",
        ],
        "rank:recent": [
            "Bzzt! Promotion confirmed! Welcome to {RANK_NAME}!!",
            "You did it! You’ve officially ranked up to {RANK_NAME}!",
            "Rank up successful! I knew you had it in you!",
            "Rank up!! From here on out, things are only getting tougher, but I know you’re ready.",
        ],
        "promotion:won": [
            "You did it! That match is officially over… great work!",
            "Bzzt! Victory confirmed! Now we just have to wait for your new rank to unlock.",
            "You’ve earned this moment. The next rank will unlock soon!",
            "Nicely done! You really showed what you’re capable of out there.",
        ],
        "promotion:lost": [
            "That one didn’t go our way. But that’s okay. We’ll work our way back up!",
            "A tough match… We’ll just have to come back stronger next time!",
            "Your Challenger Points dropped back a bit… but you’re still in this.",
            "Every strong trainer stumbles sometimes. What matters is getting back up.",
            "You’ve come too far to stop now. Let’s keep going together.",
        ],
    }

    WEATHER_DISPLAY = {
        "sunshine": {"icon": "☀️", "label": "Sunshine"},
        "rain": {"icon": "🌧️", "label": "Raining"},
        "snowing": {"icon": "🌨️", "label": "Snowing"},
        "thunder_storm": {"icon": "⛈️", "label": "Thunder Storm"},
        "cloudy": {"icon": "☁️", "label": "Cloudy"},
        "gentle_skies": {"icon": "🌤️", "label": "Gentle Skies"},
    }

    @staticmethod
    def _type_to_emoji(type_name: str) -> str:
        return EmbedBuilder.TYPE_EMOJIS.get(type_name.lower(), type_name.title())

    @staticmethod
    def _category_to_emoji(category: str) -> str:
        return EmbedBuilder.CATEGORY_EMOJIS.get(category.lower(), category.title())

    @staticmethod
    def _pokeball_emoji(pokemon: Dict) -> str:
        ball_id = (pokemon.get('pokeball') or DEFAULT_POKEBALL_ID).lower()
        return POKEBALL_EMOJIS.get(ball_id, POKEBALL_EMOJIS.get(DEFAULT_POKEBALL_ID, "🔴"))

    @staticmethod
    def _time_of_day(hour: int) -> str:
        if 5 <= hour < 12:
            return "morning"
        if 12 <= hour < 17:
            return "day"
        if 17 <= hour < 21:
            return "evening"
        return "night"

    @staticmethod
    def _rotom_context_tags(
        trainer: Trainer,
        weather_info: Optional[Dict],
        rank_manager,
        now: float,
    ) -> tuple[List[str], Dict[str, str]]:
        """Collect contextual tags so we can expand quotes later."""

        timestamp = time.localtime(now)
        tags = [f"time:{EmbedBuilder._time_of_day(timestamp.tm_hour)}"]
        context: Dict[str, str] = {
            "RANK_NAME": getattr(trainer, "rank_tier_name", "Unknown Rank"),
        }

        weather = None
        if weather_info:
            weather = weather_info.get("current_weather")
            if weather:
                tags.append(f"weather:{weather}")

        stamina_ratio = 1.0
        if getattr(trainer, "stamina_max", 0):
            stamina_ratio = max(0, trainer.stamina_current) / max(1, trainer.stamina_max)

        if stamina_ratio <= 0.25:
            tags.append("stamina:low")
        elif stamina_ratio >= 0.9:
            tags.append("stamina:full")
        else:
            tags.append("stamina:medium")

        ladder_points = getattr(trainer, "ladder_points", 0)
        if ladder_points >= 50:
            tags.append("rank:climbing")

        match_context = None
        if rank_manager and hasattr(rank_manager, "get_promotion_match_context"):
            match_context = rank_manager.get_promotion_match_context(trainer.discord_user_id)
            if match_context:
                tags.append("promotion:scheduled")
                context.update(match_context)

        if getattr(trainer, "has_promotion_ticket", False) and not match_context:
            tags.append("ticket:held")

        if getattr(trainer, "last_promotion_result", None) == "win" and getattr(trainer, "rank_pending_tier", None):
            tags.append("promotion:won")
        elif getattr(trainer, "last_promotion_result", None) == "loss":
            tags.append("promotion:lost")

        last_rank_up_at = getattr(trainer, "last_rank_up_at", None)
        if last_rank_up_at and (now - last_rank_up_at) <= 86400:
            tags.append("rank:recent")

        # Additional tags can be added later without changing selection logic
        return tags, context

    @staticmethod
    def _select_rotom_quote(
        trainer: Trainer,
        weather_info: Optional[Dict],
        rank_manager,
        *,
        now: Optional[float] = None,
    ) -> str:
        """Pick a deterministic Rotom quote for the current hour/context."""

        now = now or time.time()
        tags, context = EmbedBuilder._rotom_context_tags(trainer, weather_info, rank_manager, now)

        candidates: List[str] = list(EmbedBuilder.ROTOM_QUOTES_GENERAL)
        for tag in tags:
            if tag in EmbedBuilder.ROTOM_QUOTES_CONTEXTUAL:
                candidates.extend(EmbedBuilder.ROTOM_QUOTES_CONTEXTUAL[tag])

        if not candidates:
            return ""

        hour_bucket = int(now // 3600)
        selection_key = f"{hour_bucket}|{'|'.join(tags)}"
        index = abs(hash(selection_key)) % len(candidates)
        selected = candidates[index]
        try:
            return selected.format_map(_RotomFormatDict(context))
        except (KeyError, ValueError):
            return selected

    @staticmethod
    def _calculate_display_stats(pokemon: Dict, species_data: Dict) -> Dict[str, int]:
        """Calculate actual stats for display using stored IVs/EVs and nature."""
        natures_db = NaturesDatabase('data/natures.json')
        nature_data = natures_db.get_nature(pokemon.get('nature')) or {}

        base_stats = species_data.get('base_stats', {})
        ivs = {
            'hp': pokemon.get('iv_hp', 31),
            'attack': pokemon.get('iv_attack', 31),
            'defense': pokemon.get('iv_defense', 31),
            'sp_attack': pokemon.get('iv_sp_attack', 31),
            'sp_defense': pokemon.get('iv_sp_defense', 31),
            'speed': pokemon.get('iv_speed', 31),
        }
        evs = {
            'hp': pokemon.get('ev_hp', 0),
            'attack': pokemon.get('ev_attack', 0),
            'defense': pokemon.get('ev_defense', 0),
            'sp_attack': pokemon.get('ev_sp_attack', 0),
            'sp_defense': pokemon.get('ev_sp_defense', 0),
            'speed': pokemon.get('ev_speed', 0),
        }

        level = pokemon.get('level', 1)
        stats = {
            'hp': int(
                ((2 * base_stats.get('hp', 0) + ivs['hp'] + (evs['hp'] // 4))
                 * level // 100) + level + 10
            )
        }

        for stat in ['attack', 'defense', 'sp_attack', 'sp_defense', 'speed']:
            base = base_stats.get(stat, 0)
            value = int(((2 * base + ivs[stat] + (evs[stat] // 4)) * level // 100) + 5)

            if nature_data.get('increased_stat') == stat:
                value = int(value * 1.1)
            elif nature_data.get('decreased_stat') == stat:
                value = int(value * 0.9)

            stats[stat] = value

        return stats


    @staticmethod
    def format_rank_progress(trainer: Trainer, segments: int = 10) -> str:
        """Return a simple progress bar for Challenger points toward a ticket.

        Uses ladder_points out of 100 for the visual, and notes if a ticket
        has already been earned.
        """
        if getattr(trainer, "rank_pending_tier", None):
            return "Awaiting Promotion"
        tier = trainer.rank_tier_number or 1
        definition = get_rank_tier_definition(tier)
        ticket_threshold = definition.get('ticket_threshold')
        point_cap = definition.get('point_cap')
        if ticket_threshold and ticket_threshold > 0:
            max_points = ticket_threshold
        elif point_cap and point_cap > 0:
            max_points = point_cap
        else:
            max_points = 0
        raw_points = getattr(trainer, "ladder_points", 0) or 0
        points = max(0, int(raw_points))
        clamped = min(points, max_points)

        if max_points <= 0:
            return f"{points} pts (No cap)"

        filled_segments = int(round((clamped / max_points) * segments))
        filled_segments = max(0, min(segments, filled_segments))
        bar = '█' * filled_segments + '░' * (segments - filled_segments)

        suffix = f"{points}/{max_points}"
        if getattr(trainer, "has_promotion_ticket", False):
            suffix += " – 🎟️ Ticket earned"

        return f"{bar} ({suffix})"
    
    @staticmethod
    def _format_location_name(location_id: str, location_manager=None) -> str:
        """Return a formatted location name, preferring data from the manager."""
        if not location_id:
            return "Unknown Location"

        if location_manager:
            try:
                return location_manager.get_location_name(location_id)
            except Exception:
                pass

        return location_id.replace('_', ' ').title()

    @staticmethod
    def main_menu(
        trainer: Trainer,
        rank_manager=None,
        location_manager=None,
        *,
        wild_area_manager=None,
        wild_area_state: Optional[Dict] = None,
        weather_manager=None,
        dreamlites: Optional[int] = None,
    ) -> discord.Embed:
        """Create the main menu embed."""
        embed = discord.Embed(
            title=f"{trainer.trainer_name}'s Phone",
            color=EmbedBuilder.PRIMARY_COLOR
        )

        weather_info: Optional[Dict] = None

        # Money
        embed.add_field(
            name=f"₱{trainer.money:,}",
            value="\u200b",
            inline=True
        )

        if dreamlites is not None:
            embed.add_field(
                name="💎 Dreamlites",
                value=f"{dreamlites:,}",
                inline=True
            )

        # Location
        location_value = EmbedBuilder._format_location_name(
            trainer.current_location_id,
            location_manager
        )

        if wild_area_state:
            area_id = wild_area_state.get('area_id')
            zone_id = wild_area_state.get('current_zone_id')
            area_name = area_id
            zone_name = zone_id

            if wild_area_manager:
                try:
                    area_data = wild_area_manager.get_wild_area(area_id)
                    area_name = area_data.get('name', area_id) if area_data else area_id
                    zone_data = wild_area_manager.get_zone(zone_id) if zone_id else None
                    zone_name = zone_data.get('name', zone_id) if zone_data else zone_id
                except Exception:
                    pass

            if area_name and zone_name:
                location_value = f"{area_name} – {zone_name}"
            elif area_name:
                location_value = area_name

        if weather_manager:
            weather_info = weather_manager.get_weather_for_context(
                trainer.current_location_id,
                wild_area_state,
                now=time.time(),
            )
            weather_line = EmbedBuilder._format_weather_line(weather_info) if weather_info else None
            if weather_line:
                location_value = f"{location_value}\n{weather_line}"

        rotom_quote = EmbedBuilder._select_rotom_quote(
            trainer,
            weather_info,
            rank_manager,
            now=time.time(),
        )
        if rotom_quote:
            embed.description = f"{EmbedBuilder.ROTOM_EMOJI} “{rotom_quote}”\n\u200b"

        embed.add_field(
            name="📍 Location",
            value=location_value,
            inline=True
        )

        # Stamina
        embed.add_field(
            name="⚡️ Stamina",
            value=trainer.get_stamina_display(),
            inline=False
        )

        # Rank
        rank_lines = []
        show_progress = True
        if rank_manager and hasattr(rank_manager, "is_twilight_participant"):
            is_participant = rank_manager.is_twilight_participant(trainer.discord_user_id)
            if is_participant:
                rank_lines.append(trainer.get_rank_display())
            else:
                rank_lines.append("Unranked")
                show_progress = False

            if is_participant and hasattr(rank_manager, "twilight_started") and not rank_manager.twilight_started():
                rank_lines.append("Ranked battles are locked until the Summit begins.")
        else:
            rank_lines.append(trainer.get_rank_display())

        if show_progress:
            rank_lines.append(EmbedBuilder.format_rank_progress(trainer))

        embed.add_field(
            name="🏅 Rank",
            value="\n".join(rank_lines),
            inline=False
        )

        # Ranked promotion state
        status_text = None
        if rank_manager is not None and getattr(trainer, "rank_pending_tier", None):
            status_text = (
                "⏳ **Awaiting Promotion**\n"
                "Your promotion is secured. Ranked battles are locked until the league unlocks the next tier."
            )
        elif rank_manager is not None and getattr(trainer, "has_promotion_ticket", False):
            try:
                match = rank_manager.get_pending_match_for_player(trainer.discord_user_id)
            except Exception:
                match = None

            if match is None:
                status_text = (
                    "🎟️ **Rank-Up Match Pending**\n"
                    "You hold a Challenger Ticket. League staff need to schedule "
                    "your promotion match before you can take on ranked battles."
                )
            else:
                fmt_name = getattr(match, "format", "ranked").title()
                status_text = (
                    "⚔️ **Rank-Up Match Ready**\n"
                    f"Tier {match.tier} · Format: **{fmt_name}**\n"
                    "Complete your promotion match to continue climbing the ladder."
                )

        if status_text:
            embed.add_field(
                name="📣 Ranked Status",
                value=status_text,
                inline=False
            )

        if trainer.avatar_url:
            embed.set_thumbnail(url=trainer.avatar_url)

        embed.set_footer(text="Use the buttons below to navigate")

        return embed

    @staticmethod
    def promotion_match_ready(
        match,
        opponent_label: str,
        opponent_details: Optional[str] = None,
    ) -> discord.Embed:
        """Build an embed that highlights a scheduled promotion match."""
        tier_name = get_rank_tier_definition(match.tier)["name"]
        format_name = getattr(match, "format", "ranked").title()

        embed = discord.Embed(
            title="🏆 Promotion Match Ready",
            description="Your next rank-up match is ready to begin.",
            color=discord.Color.gold(),
        )

        embed.add_field(
            name="Tier",
            value=f"{tier_name} (Tier {match.tier})",
            inline=True,
        )
        embed.add_field(
            name="Format",
            value=format_name,
            inline=True,
        )
        embed.add_field(
            name="Match ID",
            value=match.match_id,
            inline=True,
        )
        embed.add_field(
            name="Opponent",
            value=opponent_label,
            inline=False,
        )
        if opponent_details:
            embed.add_field(
                name="Match Details",
                value=opponent_details,
                inline=False,
            )
        if getattr(match, "notes", None):
            embed.add_field(
                name="Staff Notes",
                value=match.notes,
                inline=False,
            )

        embed.set_footer(text="Use the buttons below to view your opponent or start the match.")
        return embed

    @staticmethod
    def _format_weather_line(weather_info: Optional[Dict]) -> Optional[str]:
        """Return a friendly weather status line."""

        if not weather_info:
            return None

        weather = weather_info.get('current_weather')
        if not weather:
            return None

        normalized = weather.lower().strip()
        display = EmbedBuilder.WEATHER_DISPLAY.get(normalized)
        emoji = display.get("icon") if display else "🌦️"
        label = display.get("label") if display else weather.replace('_', ' ').title()
        return f"{emoji} {label}"

    @staticmethod
    def alerts_overview(alerts: List[Dict[str, str]]) -> discord.Embed:
        embed = discord.Embed(
            title="🔔 Notifications",
            color=EmbedBuilder.INFO_COLOR,
        )

        if not alerts:
            embed.description = "You're all caught up! No alerts right now."
            return embed

        lines = []
        for alert in alerts:
            status = alert.get("status")
            prefix = "✅" if status == "joined" else "⚠️"
            summary = alert.get("summary") or ""
            lines.append(f"{prefix} **{alert.get('title', 'Alert')}** — {summary}")

        embed.description = "\n".join(lines)
        embed.set_footer(text="Select an alert from the dropdown to read more.")
        return embed

    @staticmethod
    def alert_detail(alert: Dict[str, str]) -> discord.Embed:
        embed = discord.Embed(
            title=f"🔔 {alert.get('title', 'Alert')}",
            description=alert.get("details", "No details provided."),
            color=EmbedBuilder.INFO_COLOR,
        )

        if alert.get("image"):
            embed.set_thumbnail(url=alert["image"])

        status = alert.get("status")
        if status == "joined":
            embed.add_field(name="Status", value="✅ You're signed up.", inline=False)
        elif status:
            embed.add_field(name="Status", value=status.title(), inline=False)

        return embed

    @staticmethod
    def pokedex_entry(
        species: Dict,
        *,
        seen: bool,
        caught: bool,
        entry_index: int,
        filtered_total: int,
        total_species: int,
        seen_total: int,
        caught_total: int,
        spawn_locations: List[str],
    ) -> discord.Embed:
        """Build a Pokédex entry embed for a single species."""

        if not species:
            return discord.Embed(
                title="📘 Pokédex",
                description="No entries match this view yet.",
                color=EmbedBuilder.WARNING_COLOR,
            )

        status_text = "✅ Captured" if caught else "👀 Seen" if seen else "❔ Unseen"
        color = (
            EmbedBuilder.SUCCESS_COLOR if caught else EmbedBuilder.INFO_COLOR if seen else EmbedBuilder.WARNING_COLOR
        )

        description = species.get("description") or "No Pokédex notes recorded yet."
        if not seen and not caught:
            description = (
                "You haven't encountered this Pokémon yet. Once you spot it in the wild or add it to your team, "
                "its entry will be fully verified.\n\n"
            ) + description

        type_list = species.get("types", []) or []
        type_line = " / ".join(EmbedBuilder._type_to_emoji(t) for t in type_list) or "Unknown"

        abilities = species.get("abilities", {}) or {}
        ability_parts: List[str] = []
        if abilities.get("primary"):
            ability_parts.append(f"1️⃣ {abilities['primary'].replace('_', ' ').title()}")
        if abilities.get("secondary"):
            ability_parts.append(f"2️⃣ {abilities['secondary'].replace('_', ' ').title()}")
        if abilities.get("hidden"):
            ability_parts.append(f"✨ {abilities['hidden'].replace('_', ' ').title()}")
        ability_text = "\n".join(ability_parts) if ability_parts else "No ability data recorded."

        stats = species.get("base_stats", {}) or {}
        stat_line_one = (
            f"HP {stats.get('hp', '?')} | Atk {stats.get('attack', '?')} | Def {stats.get('defense', '?')}"
        )
        stat_line_two = (
            f"SpA {stats.get('sp_attack', '?')} | SpD {stats.get('sp_defense', '?')} | Spe {stats.get('speed', '?')}"
        )
        stats_text = f"{stat_line_one}\n{stat_line_two}"

        spawn_text = "No wild encounter data recorded."
        if spawn_locations:
            shown = spawn_locations[:8]
            spawn_text = "\n".join(f"• {loc}" for loc in shown)
            remaining = len(spawn_locations) - len(shown)
            if remaining > 0:
                spawn_text += f"\n…and {remaining} more areas"
        elif not (seen or caught):
            spawn_text = "Sight a wild specimen to unlock location data."

        dex_number = species.get("dex_number")
        name = species.get("name", "Unknown Pokémon")

        embed = discord.Embed(
            title=f"📘 #{dex_number:03d} {name}",
            description=description,
            color=color,
        )

        sprite = PokemonSpriteHelper.get_sprite(name, dex_number, style="official", use_fallback=False)
        if sprite:
            embed.set_thumbnail(url=sprite)

        embed.add_field(name="Status", value=status_text, inline=True)
        embed.add_field(name="Typing", value=type_line, inline=True)

        embed.add_field(name="Abilities", value=ability_text, inline=False)
        embed.add_field(name="Base Stats", value=stats_text, inline=False)
        embed.add_field(name="Wild Locations", value=spawn_text, inline=False)

        embed.set_footer(
            text=(
                f"Entry {entry_index + 1}/{filtered_total} • Seen {seen_total}/{total_species} "
                f"• Caught {caught_total}/{total_species}"
            )
        )

        return embed

    @staticmethod
    def trainer_card(trainer: Trainer, party_count: int = 0,
                    total_pokemon: int = 0, pokedex_caught: int = 0,
                    location_manager=None) -> discord.Embed:
        """Create trainer card embed"""
        embed = discord.Embed(
            title=f"Trainer Card",
            color=EmbedBuilder.INFO_COLOR
        )
        
        # Trainer info
        info_text = f"**Name:** {trainer.trainer_name}\n"

        if getattr(trainer, "pronouns", None):
            info_text += f"**Pronouns:** {trainer.pronouns}\n"

        if getattr(trainer, "age", None):
            info_text += f"**Age:** {trainer.age}\n"

        if getattr(trainer, "birthday", None):
            info_text += f"**Birthday:** {trainer.birthday}\n"

        if getattr(trainer, "home_region", None):
            info_text += f"**Home Region:** {trainer.home_region.title()}\n"

        info_text += (
            f"**Location:** "
            f"{EmbedBuilder._format_location_name(trainer.current_location_id, location_manager)}\n"
        )
        info_text += f"**Rank:** {trainer.get_rank_display()}\n"
        info_text += EmbedBuilder.format_rank_progress(trainer) + "\n"
        info_text += f"**Money:** ₱{trainer.money:,}"

        embed.add_field(
            name="👤 Profile",
            value=info_text,
            inline=False
        )

        if getattr(trainer, "bio", None):
            embed.add_field(
                name="📝 About",
                value=trainer.bio,
                inline=False,
            )
        
        # Star traits
        stats = trainer.get_social_stats_dict()
        stat_lines = []
        for name, info in stats.items():
            rank = info['rank']
            if rank > 0:
                stars = "⭐" * rank
                line = f"**{name}:** {stars}"
            else:
                # No star shown when rank is 0
                line = f"**{name}:** —"
            stat_lines.append(line)
        stats_text = "\n".join(stat_lines) if stat_lines else "No star traits yet."

        embed.add_field(
            name="📊 Star Traits",
            value=stats_text,
            inline=True
        )

                # Pokemon collection
        collection_text = f"**Party:** {party_count}/6\n"
        collection_text += f"**Total:** {total_pokemon}\n"
        collection_text += f"**Pokédex:** {pokedex_caught}"
        
        embed.add_field(
            name="📦 Collection",
            value=collection_text,
            inline=True
        )
        
        if trainer.avatar_url:
            embed.set_thumbnail(url=trainer.avatar_url)
        
        return embed
    
    @staticmethod
    def party_view(party: List[Dict], species_db, trainer_name: str = None) -> discord.Embed:
        """Create party view embed"""
        title = f"{trainer_name}'s Party" if trainer_name else "Your Party"
        embed = discord.Embed(
            title=title,
            description="Your current party Pokémon",
            color=EmbedBuilder.PRIMARY_COLOR
        )

        if not party:
            embed.description = "Your party is empty! Catch some Pokémon!"
            return embed

        for i, pokemon in enumerate(party, 1):
            species = species_db.get_species(pokemon['species_dex_number'])
            name = pokemon.get('nickname') or species['name']

            pokeball = EmbedBuilder._pokeball_emoji(pokemon)
            types = species.get('types', []) if species else []
            type_emojis = " ".join(EmbedBuilder._type_to_emoji(t) for t in types) or "Unknown type"
            hp_text = f"HP: {pokemon['current_hp']}/{pokemon['max_hp']}"

            embed.add_field(
                name=f"{i}. {pokeball} {name} Lv. {pokemon['level']}",
                value=f"{type_emojis} {hp_text}",
                inline=True
            )

        return embed
    
    @staticmethod
    def registration_welcome() -> discord.Embed:
        """Create welcome embed for registration"""
        embed = discord.Embed(
            title="😄 Welcome to the Pokémon World!",
            description=(
                "Welcome, new trainer! You're about to begin your journey.\n\n"
                "Let's get you set up with your trainer profile."
            ),
            color=EmbedBuilder.SUCCESS_COLOR
        )
        
        embed.add_field(
            name="✨ What You'll Choose",
            value=(
                "• Your trainer name\n"
                "• Your avatar (optional)\n"
                "• Your starter Pokémon\n"
                "• Your social stat strengths"
            ),
            inline=False
        )
        
        embed.set_footer(text="Click 'Begin Registration' to start!")
        
        return embed
    
    @staticmethod
    def registration_summary(trainer_name: str, starter_species: str,
                           boon_stat: str, bane_stat: str,
                           avatar_url: str = None) -> discord.Embed:
        """Create registration summary for confirmation"""
        embed = discord.Embed(
            title="📋 Registration Summary",
            description="Please review your choices before confirming:",
            color=EmbedBuilder.INFO_COLOR
        )
        
        embed.add_field(
            name="🏷️ Trainer Name",
            value=trainer_name,
            inline=False
        )
        
        embed.add_field(
            name="⭐ Starter Pokémon",
            value=starter_species,
            inline=False
        )
        
        # Star traits preview
        stats_preview_lines = []
        for stat_key in SOCIAL_STAT_ORDER:
            display_name = SOCIAL_STAT_DEFINITIONS[stat_key].display_name
            rank = 1
            marker = ""
            if stat_key == boon_stat:
                rank = 2
                marker = " ⬆️"
            elif stat_key == bane_stat:
                rank = 0
                marker = " ⬇️"
            stats_preview_lines.append(f"• **{display_name}:** Rank {rank}{marker}")
        stats_preview = "\n".join(stats_preview_lines)

        embed.add_field(
            name="📊 Star Traits",
            value=stats_preview,
            inline=False
        )
        
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)
        
        embed.set_footer(text="Click ✅ to confirm or ❌ to cancel")
        
        return embed
    
    @staticmethod
    def error(title: str, description: str) -> discord.Embed:
        """Create error embed"""
        embed = discord.Embed(
            title=f"❌ {title}",
            description=description,
            color=EmbedBuilder.ERROR_COLOR
        )
        return embed
    
    @staticmethod
    def success(title: str, description: str) -> discord.Embed:
        """Create success embed"""
        embed = discord.Embed(
            title=f"✅ {title}",
            description=description,
            color=EmbedBuilder.SUCCESS_COLOR
        )
        return embed
    
    @staticmethod
    def info(title: str, description: str) -> discord.Embed:
        """Create info embed"""
        embed = discord.Embed(
            title=f"ℹ️ {title}",
            description=description,
            color=EmbedBuilder.INFO_COLOR
        )
        return embed
    
    @staticmethod
    def pokemon_summary(pokemon: Dict, species_data: Dict, move_data_list: List[Dict] = None) -> discord.Embed:
        """Create detailed Pokemon summary embed"""
        # Get display name
        display_name = pokemon.get('nickname') or species_data['name']
        
        # Determine embed color based on first type
        type_colors = {
            'normal': discord.Color.light_gray(),
            'fire': discord.Color.red(),
            'water': discord.Color.blue(),
            'electric': discord.Color.gold(),
            'grass': discord.Color.green(),
            'ice': discord.Color.from_rgb(150, 217, 214),
            'fighting': discord.Color.from_rgb(194, 46, 40),
            'poison': discord.Color.purple(),
            'ground': discord.Color.from_rgb(226, 191, 101),
            'flying': discord.Color.from_rgb(169, 143, 243),
            'psychic': discord.Color.from_rgb(249, 85, 135),
            'bug': discord.Color.from_rgb(166, 185, 26),
            'rock': discord.Color.from_rgb(182, 161, 54),
            'ghost': discord.Color.from_rgb(115, 87, 151),
            'dragon': discord.Color.from_rgb(111, 53, 252),
            'dark': discord.Color.from_rgb(112, 87, 70),
            'steel': discord.Color.from_rgb(183, 183, 206),
            'fairy': discord.Color.from_rgb(214, 133, 173)
        }
        
        primary_type = species_data['types'][0]
        color = type_colors.get(primary_type, discord.Color.blurple())
        
        # Create embed
        shiny_indicator = "✨ " if pokemon.get('is_shiny') else ""
        gender_symbol = "♂" if pokemon.get("gender") == "male" else "♀" if pokemon.get("gender") == "female" else ""
        
        embed = discord.Embed(
            title=f"{shiny_indicator}{display_name} {gender_symbol}",
            description=f"**{species_data['name']}** • Lv. {pokemon['level']}",
            color=color
        )

        # Add Pokemon sprite
        sprite_url = PokemonSpriteHelper.get_sprite(
            species_data['name'],
            pokemon['species_dex_number'],
            style='animated',
            shiny=pokemon.get('is_shiny', False),
            gender=pokemon.get('gender'),
            use_fallback=False
        )
        embed.set_thumbnail(url=sprite_url)

        # Basic Info
        # Use server emoji for types via server custom icons
        type_list = species_data.get("types", [])
        type_emojis = " / ".join([EmbedBuilder._type_to_emoji(t) for t in type_list])
        ability_str = pokemon['ability'].replace('_', ' ').title()
        nature_str = pokemon['nature'].title()

        basic_info = f"**Type:** {type_emojis}\n"
        basic_info += f"**Ability:** {ability_str}\n"
        basic_info += f"**Nature:** {nature_str}"
        if pokemon.get('held_item'):
            item_name = pokemon['held_item'].replace('_', ' ').title()
            basic_info += f"\n**Held Item:** {item_name}"

        # Use invisible field name so no 'Info' header is shown
        embed.add_field(name="\u200b", value=basic_info, inline=True)

# HP & Status
        hp_percentage = (pokemon['current_hp'] / pokemon['max_hp']) * 100
        hp_bar = EmbedBuilder._create_hp_bar(hp_percentage)

        hp_status = f"{hp_bar}\n"
        hp_status += f"**HP:** {pokemon['current_hp']}/{pokemon['max_hp']}"

        embed.add_field(name="❤️ Health", value=hp_status, inline=True)

        # Stats (calculate actual stats from IVs/EVs)
        display_stats = EmbedBuilder._calculate_display_stats(pokemon, species_data)
        stats_text = f"**HP:** {display_stats['hp']}\n"

        for stat_name in ['attack', 'defense', 'sp_attack', 'sp_defense', 'speed']:
            iv = pokemon.get(f'iv_{stat_name}', 31)

            # IV judge-style rating (like in-game) with 5-star scale
            if iv == 0:
                judge = "No Good"
                stars = "☆☆☆☆☆"
            elif 1 <= iv <= 15:
                judge = "Decent"
                stars = "★☆☆☆☆"
            elif 16 <= iv <= 20:
                judge = "Pretty Good"
                stars = "★★☆☆☆"
            elif 21 <= iv <= 29:
                judge = "Very Good"
                stars = "★★★☆☆"
            elif iv == 30:
                judge = "Fantastic"
                stars = "★★★★☆"
            else:  # 31
                judge = "Best"
                stars = "★★★★★"

            display_name_map = {
                'attack': 'Atk',
                'defense': 'Def',
                'sp_attack': 'SpA',
                'sp_defense': 'SpD',
                'speed': 'Spe'
            }

            stats_text += (
                f"**{display_name_map[stat_name]}:** "
                f"{display_stats[stat_name]} {stars} ({judge})\n"
            )

        embed.add_field(name="📊 Stats", value=stats_text, inline=True)
        
        # Moves
        moves_text = ""
        if pokemon['moves']:
            for i, move in enumerate(pokemon['moves'][:4], 1):
                move_name = move['move_id'].replace('_', ' ').title()
                pp = move['pp']
                max_pp = move['max_pp']

                summary = ""
                if move_data_list and len(move_data_list) >= i:
                    move_info = move_data_list[i-1]
                    move_type_raw = (move_info.get('type') or "").lower()
                    category_raw = (move_info.get('category') or "").lower()
                    power = move_info.get('power')
                    accuracy = move_info.get('accuracy')

                    power_str = "—" if not power or power == 0 else str(power)
                    if isinstance(accuracy, (int, float)):
                        acc_str = f"{accuracy}"
                    else:
                        acc_str = "—"

                    # Use emoji for move type and category using server emojis
                    type_emoji = EmbedBuilder._type_to_emoji(move_type_raw) if move_type_raw else ""
                    category_emoji = EmbedBuilder._category_to_emoji(category_raw) if category_raw else ""

                    emoji_parts = [p for p in (type_emoji, category_emoji) if p]
                    if emoji_parts:
                        emoji_label = " ".join(emoji_parts)
                        summary = f" ({emoji_label}) Pwr {power_str} Acc {acc_str}"
                    else:
                        summary = f" Pwr {power_str} Acc {acc_str}"

                moves_text += f"{i}. **{move_name}**{summary} - {pp}/{max_pp} PP\n"

        if not moves_text:
            moves_text = "No moves learned yet."

        embed.add_field(name="🎯 Moves", value=moves_text, inline=False)

        # Bond & Friendship
        bond_text = f"**Friendship:** {pokemon.get('friendship', 20)}/255\n"
        bond_text += f"**Bond Level:** {pokemon.get('bond_level', 0)}"
        
        embed.add_field(name="🤝 Bond", value=bond_text, inline=True)
        
        # Experience
        if pokemon['level'] < 100:
            exp_text = create_exp_text(pokemon, species_data, show_bar=True, bar_length=10)
        else:
            exp_text = f"**Level 100!**\n**Total:** {pokemon.get('exp', 0):,} EXP"

        embed.add_field(name="⭐ Progress", value=exp_text, inline=True)
        
        # IVs (for advanced players)
        iv_text = f"HP: {pokemon.get('iv_hp', 31)} | "
        iv_text += f"Atk: {pokemon.get('iv_attack', 31)} | "
        iv_text += f"Def: {pokemon.get('iv_defense', 31)}\n"
        iv_text += f"SpA: {pokemon.get('iv_sp_attack', 31)} | "
        iv_text += f"SpD: {pokemon.get('iv_sp_defense', 31)} | "
        iv_text += f"Spe: {pokemon.get('iv_speed', 31)}"
        
        embed.add_field(name="🧬 IVs", value=iv_text, inline=False)
        
        # EVs with arrows for increased/decreased stats from nature
        ev_text = ""
        nature_str = pokemon['nature'].lower()
        
        # Nature modifiers (which stats are boosted/hindered)
        nature_modifiers = {
            'lonely': ('attack', 'defense'), 'brave': ('attack', 'speed'),
            'adamant': ('attack', 'sp_attack'), 'naughty': ('attack', 'sp_defense'),
            'bold': ('defense', 'attack'), 'relaxed': ('defense', 'speed'),
            'impish': ('defense', 'sp_attack'), 'lax': ('defense', 'sp_defense'),
            'timid': ('speed', 'attack'), 'hasty': ('speed', 'defense'),
            'jolly': ('speed', 'sp_attack'), 'naive': ('speed', 'sp_defense'),
            'modest': ('sp_attack', 'attack'), 'mild': ('sp_attack', 'defense'),
            'quiet': ('sp_attack', 'speed'), 'rash': ('sp_attack', 'sp_defense'),
            'calm': ('sp_defense', 'attack'), 'gentle': ('sp_defense', 'defense'),
            'sassy': ('sp_defense', 'speed'), 'careful': ('sp_defense', 'sp_attack'),
            'hardy': (None, None), 'docile': (None, None), 'serious': (None, None),
            'bashful': (None, None), 'quirky': (None, None)
        }
        
        boosted, hindered = nature_modifiers.get(nature_str, (None, None))
        
        stat_names = ['hp', 'attack', 'defense', 'sp_attack', 'sp_defense', 'speed']
        stat_display = {'hp': 'HP', 'attack': 'Atk', 'defense': 'Def', 
                       'sp_attack': 'SpA', 'sp_defense': 'SpD', 'speed': 'Spe'}
        
        for stat in stat_names:
            ev_value = pokemon.get(f'ev_{stat}', 0)
            arrow = ""
            if stat == boosted:
                arrow = " ⬆️"
            elif stat == hindered:
                arrow = " ⬇️"
            
            if stat == 'hp' or stat == 'attack' or stat == 'defense':
                ev_text += f"**{stat_display[stat]}:** {ev_value}{arrow}"
                if stat != 'defense':
                    ev_text += " | "
                else:
                    ev_text += "\n"
            else:
                ev_text += f"**{stat_display[stat]}:** {ev_value}{arrow}"
                if stat != 'speed':
                    ev_text += " | "
        
        embed.add_field(name="📈 EVs", value=ev_text, inline=False)
        
        # Footer
        dex_num = f"#{pokemon['species_dex_number']:03d}"
        embed.set_footer(text=f"Pokédex {dex_num} | Caught: {pokemon.get('caught_at', 'Unknown')[:10]}")
        
        return embed
    
    @staticmethod
    def _create_hp_bar(percentage: float, length: int = 10) -> str:
        """Create a visual HP bar"""
        filled = int((percentage / 100) * length)
        empty = length - filled
        
        if percentage > 50:
            bar_char = "🟩"
        elif percentage > 20:
            bar_char = "🟧"
        else:
            bar_char = "🟥"

        return bar_char * filled + "⬜" * empty
    
    @staticmethod
    def box_view(boxes: List[Dict], species_db, page: int = 0, total_pages: int = 1) -> discord.Embed:
        """Create box storage view embed"""
        embed = discord.Embed(
            title="Storage Boxes",
            description=f"Page {page + 1}/{total_pages} • {len(boxes)} Pokémon in storage",
            color=EmbedBuilder.PRIMARY_COLOR
        )
        
        if not boxes:
            embed.description = "Your boxes are empty!"
            return embed
        
        # Show 30 Pokemon per page
        start_idx = page * 30
        end_idx = start_idx + 30
        page_boxes = boxes[start_idx:end_idx]
        
        # Group into rows of 6
        for row in range(0, len(page_boxes), 6):
            row_pokemon = page_boxes[row:row+6]
            row_text = ""
            
            for i, pokemon in enumerate(row_pokemon):
                species = species_db.get_species(pokemon['species_dex_number'])
                name = pokemon.get('nickname') or species['name']
                
                # Truncate name if too long
                if len(name) > 10:
                    name = name[:9] + "…"
                
                shiny = "✨" if pokemon.get('is_shiny') else ""
                row_text += f"`{name[:10]:10}` Lv.{pokemon['level']:2} {shiny}\n"
            
            embed.add_field(
                name=f"Slot {start_idx + row + 1}-{start_idx + row + len(row_pokemon)}",
                value=row_text,
                inline=True
            )
        
        embed.set_footer(text="Use the buttons below to navigate or select a Pokémon")
        
        return embed
    
    @staticmethod
    def bag_view(inventory: List[Dict], items_db) -> discord.Embed:
        """Create bag/inventory view embed"""
        embed = discord.Embed(
            title="Bag",
            description="Your items organized by category. Use **Select Item** to pick a category and item.",
            color=EmbedBuilder.PRIMARY_COLOR
        )
        
        if not inventory:
            embed.description = "Your bag is empty! Visit the shop to buy items."
            return embed
        
        # Organize items by category
        categories = {
            'medicine':    {'items': [], 'emoji': '💊', 'name': 'Medicine'},
            'pokeball':    {'items': [], 'emoji': '⚪', 'name': 'Poké Balls'},
            'battle_item': {'items': [], 'emoji': '⚔️', 'name': 'Battle'},
            'berries':     {'items': [], 'emoji': '🍓', 'name': 'Berries'},
            'tms':         {'items': [], 'emoji': '📘', 'name': 'TMs'},
            'omni':        {'items': [], 'emoji': '✨', 'name': 'Omni Items'},
            'key_item':    {'items': [], 'emoji': '🔑', 'name': 'Key Items'},
            'other':       {'items': [], 'emoji': '📦', 'name': 'Other'},
        }

        # Sort items into categories
        for item in inventory:
            if item['quantity'] <= 0:
                continue

            item_data = items_db.get_item(item['item_id'])
            if not item_data:
                continue

            category = item_data.get('bag_category') or item_data.get('category', 'other')
            if category not in categories:
                category = 'other'

            categories[category]['items'].append({
                'id': item['item_id'],
                'name': item_data['name'],
                'quantity': item['quantity'],
                'description': item_data.get('description', '')
            })

        
        # Add fields for each category with items
        for category_key, category_data in categories.items():
            if not category_data['items']:
                continue
            
            items_text = ""
            for item in sorted(category_data['items'], key=lambda x: x['name'])[:10]:  # Max 10 per category
                items_text += f"**{item['name']}** x{item['quantity']}\n"
            
            if len(category_data['items']) > 10:
                items_text += f"_...and {len(category_data['items']) - 10} more_"
            
            embed.add_field(
                name=f"{category_data['emoji']} {category_data['name']}",
                value=items_text,
                inline=True
            )
        
        total_items = sum(item['quantity'] for item in inventory)
        embed.set_footer(text=f"Total items: {total_items}")
        
        return embed
    
    @staticmethod
    def item_use_view(item_data: Dict, inventory_qty: int) -> discord.Embed:
        """Create item detail view for using"""
        embed = discord.Embed(
            title=f"🧪 {item_data['name']}",
            description=item_data.get('description', 'No description available.'),
            color=EmbedBuilder.INFO_COLOR
        )
        
        # Item details
        details = f"**Category:** {item_data.get('category', 'Unknown').replace('_', ' ').title()}\n"
        details += f"**In Bag:** {inventory_qty}\n"
        
        # Effect description
        if item_data.get('effect'):
            details += f"\n**Effect:** {item_data['effect']}"
        
        embed.add_field(name="📦 Details", value=details, inline=False)
        
        # Usage instructions
        category = item_data.get('category', '')
        if category == 'medicine':
            embed.add_field(
                name="⚙️ Usage",
                value="Select a Pokémon from your party to use this item on.",
                inline=False
            )
        elif category == 'evolution':
            embed.add_field(
                name="⚙️ Usage",
                value="Select a Pokémon that can evolve with this item.",
                inline=False
            )
        elif category == 'held_items':
            embed.add_field(
                name="⚙️ Usage",
                value="Select a Pokémon to give this item to hold.",
                inline=False
            )
        
        return embed
    
    @staticmethod
    def travel_menu(current_location_id: str, all_locations: dict, location_manager) -> discord.Embed:
        """
        Create travel menu embed
        
        Args:
            current_location_id: Player's current location
            all_locations: Dictionary of all available locations
            location_manager: LocationManager instance
        """
        current_location = all_locations.get(current_location_id, {})
        current_name = location_manager.get_location_name(current_location_id)
        
        embed = discord.Embed(
            title="Ã°Å¸—ÂºÃ¯Â¸Â Travel Menu",
            description=f"**Current Location:** {current_name}\n\n"
                       f"{current_location.get('description', 'No description available.')}\n\n"
                       f"Select a location from the dropdown below to travel.",
            color=discord.Color.blue()
        )
        
        # Add available locations
        location_list = []
        for location_id, location_data in all_locations.items():
            name = location_data.get('name', location_id.replace('_', ' ').title())
            if location_id == current_location_id:
                name = f"Ã°Å¸“Â **{name}** (Current)"
            else:
                name = f"• {name}"
            location_list.append(name)
        
        if location_list:
            # Insert a spacer between the description and the list for readability
            embed.add_field(name="\u200b", value="\u200b", inline=False)
            embed.add_field(
                name="Available Locations",
                value="\n".join(location_list),
                inline=False
            )
        
        embed.set_footer(text="Choose a location to begin your journey!")
        
        return embed
    
    @staticmethod
    def encounter_roll(encounters: list, location: dict) -> discord.Embed:
        """
        Create encounter roll display embed
        
        Args:
            encounters: List of Pokemon objects
            location: Location data dictionary
        """
        location_name = location.get('name', 'Unknown Location')
        
        embed = discord.Embed(
            title=f"Wild Encounters - {location_name}",
            description=f"You found {len(encounters)} wild Pokémon! Choose one to battle, or reroll for different encounters.",
            color=discord.Color.green()
        )
        
        # Group encounters by species for display
        encounter_list = []
        for i, pokemon in enumerate(encounters, 1):
            types = "/".join([t.title() for t in pokemon.species_data['types']])
            
            # Build display string
            display = f"`#{i:02d}` "
            
            # Add shiny indicator
            if getattr(pokemon, "is_shiny", False):
                display += "✨ "
            
            display += f"**{pokemon.species_name}** - Lv. {pokemon.level}"
            display += f" ({types})"
            
            # Add gender
            gender = getattr(pokemon, "gender", None)
            if gender:
                gender_symbol = "♂" if gender == "male" else "♀" if gender == "female" else ""
                display += f" {gender_symbol}"
            
            encounter_list.append(display)
        
        # Show all encounters in one list
        embed.add_field(
            name="Available Encounters",
            value="\n".join(encounter_list),
            inline=False
        )
        
        embed.set_footer(text="Use the dropdown to select a Pokémon, or click Reroll for new encounters!")

        return embed

    @staticmethod
    def raid_alert(raid_summary: dict, location_name: str) -> discord.Embed:
        """Build a warning embed that sits under the wild encounter roll."""

        embed = discord.Embed(
            title="⚠️ Raid Detected!",
            description=(
                f"A powerful **{raid_summary.get('species_name', 'Unknown')}** is stirring in {location_name}.\n"
                "Coordinate with trainers, invite allies, and ready up to begin the fight."
            ),
            color=discord.Color.orange(),
        )

        embed.add_field(
            name="Level",
            value=raid_summary.get("level", "?"),
            inline=True,
        )
        embed.add_field(
            name="Move Slots",
            value=len(raid_summary.get("move_ids", []) or []),
            inline=True,
        )
        embed.add_field(
            name="Ready",
            value=(
                f"{raid_summary.get('ready_count', 0)}/"
                f"{max(1, raid_summary.get('participant_count', 1))}"
            ),
            inline=True,
        )

        sprite_url = PokemonSpriteHelper.get_sprite(
            raid_summary.get("species_name"),
            raid_summary.get("species_dex_number"),
            style="animated",
            shiny=False,
            use_fallback=False,
        )
        if sprite_url:
            embed.set_thumbnail(url=sprite_url)

        embed.set_footer(text="Press Fight to join the lobby, ready up, and launch the raid battle.")
        return embed
    
    @staticmethod
    def travel_select(all_locations: dict, current_location_id: str) -> discord.Embed:
        """
        Create travel location selection embed
        
        Args:
            all_locations: Dictionary of all locations
            current_location_id: Player's current location ID
        """
        embed = discord.Embed(
            title="🧭 Travel to Location",
            description="Choose a destination within the Lights District to instantly move between the Central Plaza and the Art Studio.",
            color=discord.Color.blue()
        )

        # List all locations
        preferred_order = [
            'lights_district_central_plaza',
            'lights_district_art_studio'
        ]
        ordered_ids = [loc_id for loc_id in preferred_order if loc_id in all_locations]
        ordered_ids.extend(
            loc_id for loc_id in all_locations
            if loc_id not in preferred_order
        )

        location_list = []
        for location_id in ordered_ids:
            location_data = all_locations[location_id]
            location_name = location_data.get('name', location_id.replace('_', ' ').title())

            # Mark current location
            if location_id == current_location_id:
                location_list.append(f"📍 **{location_name}** (Current)")
            else:
                location_list.append(f"• {location_name}")
        
        embed.add_field(
            name="Available Locations",
            value="\n".join(location_list),
            inline=False
        )
        
        # Get current location info
        current_location = all_locations.get(current_location_id)
        if current_location:
            current_name = current_location.get('name', current_location_id.replace('_', ' ').title())
            current_desc = current_location.get('description', 'No description available.')
            
            embed.add_field(
                name=f"{current_name} (Current)",
                value=current_desc,
                inline=False
            )
        
        embed.set_footer(text="Select a location from the dropdown below!")
        
        return embed
    
    @staticmethod
    def battle_menu(location: dict, available_pvp: Optional[int] = None) -> discord.Embed:
        """Create battle menu embed"""
        location_name = location.get('name', 'Unknown Location')
        embed = discord.Embed(
            title="⚔️ Battle Menu",
            description=f"Choose your battle type at **{location_name}**!",
            color=discord.Color.red()
        )

        # Casual battle summary (players + casual NPCs)
        casual_npcs = location.get('npc_trainers', [])
        casual_npc_count = len(casual_npcs)

        total_casual_targets = None
        if available_pvp is not None:
            # Combine available players and NPCs if we know player count
            total_casual_targets = available_pvp + casual_npc_count

        if total_casual_targets is None:
            if casual_npc_count:
                casual_status = (
                    f"Challenge other nearby trainers or {casual_npc_count} local NPC(s) for a casual spar."
                )
            else:
                casual_status = "Challenge other nearby trainers for a casual spar."
        elif total_casual_targets <= 0:
            casual_status = "No other casual trainers are here right now."
        else:
            plural = "trainer" if total_casual_targets == 1 else "trainers"
            casual_status = f"Challenge {total_casual_targets} nearby {plural} for a casual battle!"

        embed.add_field(
            name="🎮 Casual Battles",
            value=casual_status,
            inline=False
        )

        # Ranked battle summary (players + NPCs)
        ranked_npcs = location.get('ranked_npc_trainers', [])
        npc_count = len(ranked_npcs)
        if available_pvp is None:
            ranked_player_text = "Take on local trainers for Challenger points."
        elif available_pvp <= 0:
            ranked_player_text = "No other players are currently eligible for ranked battles."
        else:
            plural = "trainer" if available_pvp == 1 else "trainers"
            ranked_player_text = f"{available_pvp} player {plural} available for ranked battles."

        if npc_count:
            npc_text = f"{npc_count} League official(s) ready for ranked challenges."
        else:
            npc_text = "No ranked NPC challengers at this location."

        embed.add_field(
            name="🏆 Ranked Battles",
            value=f"{ranked_player_text}\n{npc_text}\nEarn Challenger points when you win!",
            inline=False
        )

        embed.set_footer(text="Select a battle type from the buttons below!")
        return embed

    @staticmethod
    def pvp_challenge_menu(location_name: str, opponents: list, ranked: bool = False) -> discord.Embed:
        """Show available opponents for PvP battles."""
        if ranked:
            title = "🏆 Ranked Player Battles"
            description = (
                f"Challenge another trainer currently exploring **{location_name}** for ranked play.\n"
                "Use the dropdown below to pick your opponent and customize the rules."
            )
            color = discord.Color.gold()
        else:
            title = "🔥 Player Battles"
            description = (
                f"Challenge another trainer currently exploring **{location_name}**.\n"
                "Use the dropdown below to pick your opponent and customize the rules."
            )
            color = discord.Color.orange()

        embed = discord.Embed(
            title=title,
            description=description,
            color=color
        )

        if opponents:
            preview_lines = []
            for trainer in opponents[:10]:
                trainer_name = getattr(trainer, 'trainer_name', 'Trainer')
                preview_lines.append(f"• **{trainer_name}**")
            if len(opponents) > 10:
                preview_lines.append(f"…and {len(opponents) - 10} more")
            embed.add_field(
                name="Nearby Trainers",
                value="\n".join(preview_lines),
                inline=False
            )
        else:
            embed.add_field(
                name="Nearby Trainers",
                value="No other registered trainers are at this location.",
                inline=False
            )

        footer = "Ranked wins grant Challenger points!" if ranked else "Pick a trainer, then choose singles or doubles and the team size!"
        embed.set_footer(text=footer)
        return embed

    @staticmethod
    def npc_trainer_list(npc_trainers: list, location: dict, ranked: bool = False) -> discord.Embed:
        """Create NPC trainer selection embed"""
        location_name = location.get('name', 'Unknown Location')
        if ranked:
            title = f"🏆 Ranked Officials at {location_name}"
            description = "Select a League-sanctioned opponent for a ranked match."
            color = discord.Color.gold()
        else:
            title = f"⚔️ Trainers at {location_name}"
            description = "Choose a trainer to battle!"
            color = discord.Color.orange()

        embed = discord.Embed(
            title=title,
            description=description,
            color=color
        )

        # List trainers
        for i, npc in enumerate(npc_trainers, 1):
            npc_name = npc.get('name', 'Unknown Trainer')
            npc_class = npc.get('class', 'Trainer')
            party_size = len(npc.get('party', []))
            prize_money = npc.get('prize_money', 0)
            battle_format = npc.get('battle_format', 'singles')

            # Display battle format
            format_display = battle_format.capitalize() if battle_format else 'Singles'

            levels = [
                poke.get("level", 1)
                for poke in (npc.get("party") or npc.get("team", []))
                if poke.get("level") is not None
            ]
            avg_level = round(sum(levels) / len(levels)) if levels else 1

            trainer_info = f"**{npc_class}**\n"
            trainer_info += f"Battle Type: {format_display} | Av. Lvl {avg_level}"
            if ranked:
                npc_rank = npc.get("rank_tier_number") or npc.get("rank") or 1
                rank_name = get_rank_tier_definition(npc_rank)["name"]
                trainer_info = f"**{rank_name} (Lv. {avg_level})**\nBattle Type: {format_display}"

            embed.add_field(
                name=f"{i}. {npc_name}",
                value=trainer_info,
                inline=False
            )
        
        embed.set_footer(text="Select a trainer from the dropdown below!")
        return embed

    @staticmethod
    def party_menu(wild_area_state: Dict, available_parties: List[Dict]) -> discord.Embed:
        """Create party creation/join menu embed"""
        embed = discord.Embed(
            title="🤝 Team Up",
            description="Create a new team or join an existing one!",
            color=EmbedBuilder.SUCCESS_COLOR
        )

        embed.add_field(
            name="📍 Current Zone",
            value=wild_area_state['current_zone_id'],
            inline=False
        )

        embed.add_field(
            name="⚡ Stamina",
            value=f"{wild_area_state['current_stamina']}/{wild_area_state['entry_stamina']}",
            inline=True
        )

        if available_parties:
            parties_text = "\n".join([
                f"**{p['party_name']}** (Leader: <@{p['leader_discord_id']}>)"
                for p in available_parties
            ])
            embed.add_field(
                name=f"Available Teams ({len(available_parties)})",
                value=parties_text,
                inline=False
            )
        else:
            embed.add_field(
                name="Available Teams",
                value="No teams in this area. Create one!",
                inline=False
            )

        return embed

    @staticmethod
    def party_info(party: Dict, member_ids: List[int], player_manager) -> discord.Embed:
        """Create party info embed"""
        embed = discord.Embed(
            title=f"🤝 {party['party_name']}",
            description=f"Leader: <@{party['leader_discord_id']}>",
            color=EmbedBuilder.SUCCESS_COLOR
        )

        embed.add_field(
            name="📍 Current Zone",
            value=party['current_zone_id'],
            inline=True
        )

        embed.add_field(
            name="👥 Members",
            value=f"{len(member_ids)} trainers",
            inline=True
        )

        # List members
        members_text = []
        for member_id in member_ids:
            trainer = player_manager.get_player(member_id)
            name = trainer.trainer_name if trainer else f"User {member_id}"
            members_text.append(f"• {name}")

        embed.add_field(
            name="Team Roster",
            value="\n".join(members_text) if members_text else "No members",
            inline=False
        )

        return embed

    @staticmethod
    def wild_area_info(area: Dict, zone: Dict, stamina: int, max_stamina: int) -> discord.Embed:
        """Create wild area info embed"""
        embed = discord.Embed(
            title=f"🗺️ {area['name']}",
            description=area.get('description', 'A mysterious wild area...'),
            color=EmbedBuilder.INFO_COLOR
        )

        embed.add_field(
            name="📍 Current Zone",
            value=f"**{zone['name']}**\n{zone.get('description', '')}",
            inline=False
        )

        embed.add_field(
            name="⚡ Stamina",
            value=f"{stamina}/{max_stamina}",
            inline=True
        )

        if zone.get('has_pokemon_station'):
            embed.add_field(
                name="🏥 Station",
                value="Pokémon Station available!",
                inline=True
            )

        return embed
