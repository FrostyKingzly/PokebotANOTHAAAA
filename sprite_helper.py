"""
Pokemon Sprite Helper
Easy integration of Pokemon images into Discord embeds
"""

from typing import Optional


class PokemonSpriteHelper:
    """Helper class to get Pokemon sprite URLs"""

    # Sprite sources
    GEN5_ANIMATED = "https://play.pokemonshowdown.com/sprites/gen5ani/{name}.gif"
    GEN5_ANIMATED_SHINY = "https://play.pokemonshowdown.com/sprites/gen5ani-shiny/{name}.gif"
    GEN5_STATIC = "https://play.pokemonshowdown.com/sprites/gen5/{name}.png"
    GEN5_STATIC_SHINY = "https://play.pokemonshowdown.com/sprites/gen5-shiny/{name}.png"
    SHOWDOWN_STATIC = "https://play.pokemonshowdown.com/sprites/pokemon/{name}.png"
    SHOWDOWN_STATIC_SHINY = "https://play.pokemonshowdown.com/sprites/pokemon/shiny/{name}.png"
    POKEAPI_FRONT = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{id}.png"
    POKEAPI_FRONT_FEMALE = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/female/{id}.png"
    POKEAPI_SHINY = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/shiny/{id}.png"
    POKEAPI_SHINY_FEMALE = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/shiny/female/{id}.png"
    OFFICIAL_ART = "https://assets.pokemon.com/assets/cms2/img/pokedex/full/{id}.png"
    
    @staticmethod
    def _gendered_name(name: str, gender: Optional[str]) -> str:
        """Return the gender-adjusted sprite slug for Showdown sprites."""
        if gender and gender.lower() == "female":
            return f"{name}-f"
        return name

    @staticmethod
    def get_sprite(pokemon_name: str, dex_number: Optional[int] = None,
                   style: str = 'animated', shiny: bool = False, use_fallback: bool = True,
                   form: str = None, gender: Optional[str] = None) -> str:
        """
        Get Pokemon sprite URL

        Args:
            pokemon_name: Pokemon species name (e.g., "pikachu", "charizard")
            dex_number: National Dex number (required for 'static' and 'official' styles)
            style: 'animated', 'gen5static', 'static', 'official', 'showdown'
            shiny: Whether to get shiny sprite (animated/gen5static/showdown use Showdown shinies)
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
        raw_name = pokemon_name.lower().replace(' ', '').replace("'", "").replace(".", "")

        # Infer form or gender from the provided name if they aren't explicitly supplied
        segments = raw_name.split('-')
        inferred_gender = gender
        inferred_form = form

        if len(segments) > 1:
            last_segment = segments[-1]
            if inferred_gender is None and last_segment in {"f", "female", "m", "male"}:
                inferred_gender = "female" if last_segment.startswith('f') else "male"
                base_segments = segments[:-1]
            elif inferred_form is None:
                inferred_form = '-'.join(segments[1:])
                base_segments = [segments[0]]
            else:
                base_segments = segments
        else:
            base_segments = segments

        # Reconstruct the base name without hyphens so we can append forms/gender cleanly
        name = ''.join(base_segments)

        # Add form suffix if specified (e.g., "sandshrew-alola")
        if inferred_form:
            name = f"{name}-{inferred_form.lower()}"

        gender = inferred_gender

        if style == 'animated':
            gendered_name = PokemonSpriteHelper._gendered_name(name, gender)
            static_fallback = (
                PokemonSpriteHelper.GEN5_STATIC_SHINY.format(name=gendered_name)
                if shiny
                else PokemonSpriteHelper.GEN5_STATIC.format(name=gendered_name)
            )

            # Gen5 animated sprites don't exist for Pokemon from gen 8+ (dex 810+)
            if dex_number and dex_number >= 810:
                # Always use the static version for these species
                return static_fallback

            animated_url = (
                PokemonSpriteHelper.GEN5_ANIMATED_SHINY.format(name=gendered_name)
                if shiny
                else PokemonSpriteHelper.GEN5_ANIMATED.format(name=gendered_name)
            )

            if use_fallback:
                return [animated_url, static_fallback]

            return animated_url

        elif style == 'gen5static':
            # Gen 5 static sprites
            gendered_name = PokemonSpriteHelper._gendered_name(name, gender)
            if shiny:
                return PokemonSpriteHelper.GEN5_STATIC_SHINY.format(name=gendered_name)
            return PokemonSpriteHelper.GEN5_STATIC.format(name=gendered_name)

        elif style == 'showdown':
            gendered_name = PokemonSpriteHelper._gendered_name(name, gender)
            if shiny:
                return PokemonSpriteHelper.SHOWDOWN_STATIC_SHINY.format(name=gendered_name)
            return PokemonSpriteHelper.SHOWDOWN_STATIC.format(name=gendered_name)

        elif style == 'static':
            if dex_number is None:
                raise ValueError("dex_number required for static sprites")
            if gender and gender.lower() == "female":
                if shiny:
                    return PokemonSpriteHelper.POKEAPI_SHINY_FEMALE.format(id=dex_number)
                return PokemonSpriteHelper.POKEAPI_FRONT_FEMALE.format(id=dex_number)
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
