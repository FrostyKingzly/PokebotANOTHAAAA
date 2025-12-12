"""Lightweight AI-style Pokemon responses for roleplay posts."""

import re
from typing import Dict, List, Optional

import discord
from discord.ext import commands


NATURE_PERSONALITIES: Dict[str, Dict[str, str]] = {
    "timid": {
        "emoji": "😰",
        "intro": "peeks out timidly and whispers back",
        "closing": "...",
    },
    "brave": {
        "emoji": "💪",
        "intro": "stands tall, answering with steady resolve",
        "closing": "!",
    },
    "jolly": {
        "emoji": "😄",
        "intro": "bounces with excitement and chirps back",
        "closing": "!",
    },
    "calm": {
        "emoji": "🌊",
        "intro": "responds with a soothing tone",
        "closing": ".",
    },
    "sassy": {
        "emoji": "😏",
        "intro": "shoots a sly look and replies",
        "closing": ".",
    },
    "modest": {
        "emoji": "📘",
        "intro": "answers with thoughtful restraint",
        "closing": ".",
    },
    "naive": {
        "emoji": "🌟",
        "intro": "tilts its head with carefree energy",
        "closing": "!",
    },
    "docile": {
        "emoji": "✨",
        "intro": "offers a gentle response",
        "closing": ".",
    },
    "default": {
        "emoji": "✨",
        "intro": "responds",
        "closing": ".",
    },
}


class PokemonAICog(commands.Cog):
    """Responds to inline RP cues with short, in-character Pokemon voice lines."""

    AI_TRIGGER = "[[poke-ai]]"

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if self.AI_TRIGGER.lower() not in message.content.lower():
            return

        trainer = self.bot.player_manager.get_player(message.author.id)
        if not trainer:
            await message.channel.send("[X] Register first with `/register` to use Pokemon RP replies.")
            return

        speaker = self._get_speaker(message.author.id)
        if not speaker:
            await message.channel.send("[X] You need a Pokemon in your party before it can reply.")
            return

        rp_text = self._strip_trigger(message.content)
        memories = self.bot.player_manager.get_pokemon_memories(speaker['pokemon_id'], limit=3)

        reply = self._build_response(speaker, rp_text, memories)
        await message.channel.send(reply)

        if rp_text:
            self.bot.player_manager.add_pokemon_memory(
                speaker['pokemon_id'],
                rp_text[:240],
                max_entries=20,
            )

    def _get_speaker(self, discord_user_id: int) -> Optional[Dict]:
        partner = self.bot.player_manager.get_partner_pokemon(discord_user_id)
        if partner:
            return partner

        party = self.bot.player_manager.get_party(discord_user_id)
        if party:
            return party[0]
        return None

    def _strip_trigger(self, content: str) -> str:
        return re.sub(re.escape(self.AI_TRIGGER), "", content, flags=re.IGNORECASE).strip()

    def _build_response(self, pokemon: Dict, rp_text: str, memories: List[Dict]) -> str:
        nature = str(pokemon.get('nature') or 'neutral').lower()
        personality = NATURE_PERSONALITIES.get(nature, NATURE_PERSONALITIES['default'])
        species_data = self.bot.species_db.get_species(pokemon.get('species_dex_number')) or {}
        display_name = pokemon.get('nickname') or species_data.get('name', 'Pokemon')

        scene_note = rp_text.strip()
        if len(scene_note) > 200:
            scene_note = f"{scene_note[:197]}..."

        memory_line = ""
        if memories:
            recalled = memories[0].get('memory', '').strip()
            if recalled:
                if len(recalled) > 120:
                    recalled = f"{recalled[:117]}..."
                memory_line = f" It remembers {recalled}."

        return (
            f"{personality['emoji']} **{display_name}** {personality['intro']} "
            f"{scene_note or 'gives a quick nod'}{personality['closing']}{memory_line}"
        )


async def setup(bot):
    await bot.add_cog(PokemonAICog(bot))
