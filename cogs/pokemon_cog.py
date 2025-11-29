"""
Pokemon Management Cog - Coming soon
"""

from discord.ext import commands


class PokemonCog(commands.Cog):
    """Handles Pokemon management (party, boxes, etc)"""
    
    def __init__(self, bot):
        self.bot = bot


async def setup(bot):
    await bot.add_cog(PokemonCog(bot))
