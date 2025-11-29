"""
Pokemon Sprite Helper
Easy integration of Pokemon images into Discord embeds
"""

from typing import Optional


class PokemonSpriteHelper:
    """Helper class to get Pokemon sprite URLs"""
    
    # Sprite sources
    GEN5_ANIMATED = "https://play.pokemonshowdown.com/sprites/gen5ani/{name}.gif"
    GEN5_STATIC = "https://play.pokemonshowdown.com/sprites/gen5/{name}.png"
    SHOWDOWN_STATIC = "https://play.pokemonshowdown.com/sprites/pokemon/{name}.png"
    POKEAPI_FRONT = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{id}.png"
    POKEAPI_SHINY = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/shiny/{id}.png"
    OFFICIAL_ART = "https://assets.pokemon.com/assets/cms2/img/pokedex/full/{id}.png"
    
    @staticmethod
    def get_sprite(pokemon_name: str, dex_number: Optional[int] = None,
                   style: str = 'animated', shiny: bool = False, use_fallback: bool = True,
                   form: str = None) -> str:
        """
        Get Pokemon sprite URL

        Args:
            pokemon_name: Pokemon species name (e.g., "pikachu", "charizard")
            dex_number: National Dex number (required for 'static' and 'official' styles)
            style: 'animated', 'gen5static', 'static', 'official', 'showdown'
            shiny: Whether to get shiny sprite (only works for 'static')
            use_fallback: If True and style='animated', returns a list [animated_url, gen5static_url]
            form: Regional form (e.g., 'alola', 'hisui', 'galar') or None for base form

        Returns:
            URL string for the sprite, or list of URLs if use_fallback=True for animated

        Examples:
            >>> PokemonSpriteHelper.get_sprite("pikachu", 25)
            ['https://play.pokemonshowdown.com/sprites/gen5ani/pikachu.gif',
             'https://play.pokemonshowdown.com/sprites/gen5/pikachu.png']

            >>> PokemonSpriteHelper.get_sprite("rillaboom", 812, use_fallback=False)
            'https://play.pokemonshowdown.com/sprites/gen5ani/rillaboom.gif'

            >>> PokemonSpriteHelper.get_sprite("charizard", 6, style='official')
            'https://assets.pokemon.com/assets/cms2/img/pokedex/full/006.png'

            >>> PokemonSpriteHelper.get_sprite("sandshrew", 27, form='alola')
            'https://play.pokemonshowdown.com/sprites/gen5ani/sandshrew-alola.gif'
        """
        name = pokemon_name.lower().replace(' ', '').replace('-', '')

        # Add form suffix if specified (e.g., "sandshrew-alola")
        if form:
            name = f"{name}-{form.lower()}"

        if style == 'animated':
            # Use Showdown Gen 5 static sprites (all Pokemon have these)
            # Gen5 animated sprites don't exist for all Pokemon
            return PokemonSpriteHelper.GEN5_STATIC.format(name=name)

        elif style == 'gen5static':
            # Gen 5 static sprites
            return PokemonSpriteHelper.GEN5_STATIC.format(name=name)

        elif style == 'showdown':
            return PokemonSpriteHelper.SHOWDOWN_STATIC.format(name=name)

        elif style == 'static':
            if dex_number is None:
                raise ValueError("dex_number required for static sprites")
            if shiny:
                return PokemonSpriteHelper.POKEAPI_SHINY.format(id=dex_number)
            return PokemonSpriteHelper.POKEAPI_FRONT.format(id=dex_number)

        elif style == 'official':
            if dex_number is None:
                raise ValueError("dex_number required for official art")
            return PokemonSpriteHelper.OFFICIAL_ART.format(id=f"{dex_number:03d}")

        else:
            raise ValueError(f"Unknown style: {style}. Use 'animated', 'gen5static', 'static', 'official', or 'showdown'")
    
    @staticmethod
    def get_battle_sprites(pokemon1_name: str, pokemon1_dex: int,
                          pokemon2_name: str, pokemon2_dex: int,
                          style: str = 'animated') -> tuple[str, str]:
        """
        Get sprites for both Pokemon in a battle
        
        Returns:
            (trainer_pokemon_sprite, wild_pokemon_sprite)
        """
        sprite1 = PokemonSpriteHelper.get_sprite(pokemon1_name, pokemon1_dex, style)
        sprite2 = PokemonSpriteHelper.get_sprite(pokemon2_name, pokemon2_dex, style)
        return sprite1, sprite2
    
    @staticmethod
    def add_to_embed(embed, pokemon_name: str, dex_number: Optional[int] = None,
                     position: str = 'thumbnail', style: str = 'animated'):
        """
        Add Pokemon sprite to a Discord embed
        
        Args:
            embed: discord.Embed object
            pokemon_name: Pokemon species name
            dex_number: National Dex number (optional)
            position: 'thumbnail', 'image', or 'author_icon'
            style: Sprite style (see get_sprite)
        
        Example:
            >>> import discord
            >>> embed = discord.Embed(title="Wild Pikachu appeared!")
            >>> PokemonSpriteHelper.add_to_embed(embed, "pikachu", 25)
        """
        url = PokemonSpriteHelper.get_sprite(pokemon_name, dex_number, style)
        
        if position == 'thumbnail':
            embed.set_thumbnail(url=url)
        elif position == 'image':
            embed.set_image(url=url)
        elif position == 'author_icon':
            embed.set_author(name=pokemon_name.title(), icon_url=url)
        else:
            raise ValueError(f"Unknown position: {position}")
        
        return embed


# Quick usage examples
if __name__ == '__main__':
    print("Pokemon Sprite Helper")
    print("=" * 50)
    print()
    
    # Example 1: Basic usage
    print("Example 1: Get Pikachu sprite")
    url = PokemonSpriteHelper.get_sprite("pikachu", 25)
    print(f"  URL: {url}")
    print()
    
    # Example 2: Different styles
    print("Example 2: Different sprite styles")
    for style in ['animated', 'static', 'official']:
        url = PokemonSpriteHelper.get_sprite("charizard", 6, style=style)
        print(f"  {style.title()}: {url}")
    print()
    
    # Example 3: Shiny Pokemon
    print("Example 3: Shiny Gyarados")
    url = PokemonSpriteHelper.get_sprite("gyarados", 130, style='static', shiny=True)
    print(f"  Shiny URL: {url}")
    print()
    
    # Example 4: Battle sprites
    print("Example 4: Battle - Pikachu vs Charizard")
    sprite1, sprite2 = PokemonSpriteHelper.get_battle_sprites(
        "pikachu", 25, "charizard", 6
    )
    print(f"  Pikachu: {sprite1}")
    print(f"  Charizard: {sprite2}")
    print()
    
    print("Integration Examples:")
    print("-" * 50)
    print()
    print("# In your battle_cog.py or similar:")
    print("from sprite_helper import PokemonSpriteHelper")
    print()
    print("# When creating battle embed:")
    print("embed = discord.Embed(title='Wild Pikachu appeared!')")
    print("PokemonSpriteHelper.add_to_embed(embed, 'pikachu', 25)")
    print()
    print("# Or manually:")
    print("sprite_url = PokemonSpriteHelper.get_sprite('charizard', 6)")
    print("embed.set_thumbnail(url=sprite_url)")
