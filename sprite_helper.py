"""
Pokemon Sprite Helper
Easy integration of Pokemon images into Discord embeds
"""

import functools
import re
import unicodedata
import urllib.error
import urllib.request
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

    KNOWN_FORM_SUFFIXES = {
        "alola", "galar", "hisui", "paldea", "gmax", "mega", "primal",
        "dawn", "dusk", "midday", "midnight", "school", "totem", "therian",
        "incarnate", "origin", "sky", "ash", "zen", "frost", "heat", "mow",
        "wash", "fan", "sunny", "rainy", "snowy", "attack", "defense", "speed",
        "plant", "sandy", "trash", "black", "white", "shadow", "busted",
        "disguised", "pau", "pom-pom", "sensu", "baile", "blade", "shield",
        "crowned", "low-key", "amped", "resolute", "pirouette", "unbound",
        "eternamax", "starter", "dada", "rapid-strike", "single-strike",
        "dawn-wings", "dusk-mane", "male", "female", "hero", "zero",
    }

    @staticmethod
    def _strip_accents(text: str) -> str:
        """Return text with diacritic marks removed."""
        normalized = unicodedata.normalize("NFKD", text)
        return "".join(ch for ch in normalized if not unicodedata.combining(ch))

    @staticmethod
    def _sanitize_component(text: str, allow_hyphens: bool = False) -> str:
        """Normalize a name/form component for Showdown sprite slugs."""
        text = PokemonSpriteHelper._strip_accents(text.lower())
        if allow_hyphens:
            return re.sub(r"[^a-z0-9-]", "", text)
        return re.sub(r"[^a-z0-9]", "", text)
    
    FEMALE_SPRITE_SPECIES = {
        # Species with distinct female Showdown sprite slugs
        "basculegion", "frillish", "hippopotas", "hippowdon", "indeedee",
        "jellicent", "meowstic", "oinkologne", "pyroar", "unfezant",
    }

    @staticmethod
    def _gendered_name(name: str, gender: Optional[str]) -> str:
        """Return the gender-adjusted sprite slug for Showdown sprites.

        Only a handful of species have dedicated "-f" sprites on Showdown. For
        everything else we stick to the base slug so we don't request missing
        assets (which Discord then shows as a broken image).
        """
        if gender and gender.lower() == "female":
            base_species = name.split("-", 1)[0]
            if base_species in PokemonSpriteHelper.FEMALE_SPRITE_SPECIES:
                return f"{name}-f"
        return name

    @staticmethod
    @functools.lru_cache(maxsize=2048)
    def _url_exists(url: str) -> bool:
        """Return True if the remote sprite URL responds with a success status.

        A lightweight HEAD request is attempted first; if the host rejects HEAD
        (e.g., 405 Method Not Allowed) we retry with GET. Any network or HTTP
        errors are treated as the URL being unavailable so callers can safely
        fall back to alternative sprite sources.
        """

        try:
            request = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(request, timeout=3) as response:
                return 200 <= response.status < 400
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False

            if exc.code != 405:
                return True

            # Some hosts reject HEAD requests; retry with GET.
            try:
                request = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(request, timeout=3) as response:
                    return 200 <= response.status < 400
            except urllib.error.HTTPError as get_exc:
                return get_exc.code != 404
            except Exception:
                return True
        except Exception:
            # If connectivity is restricted, assume the sprite exists so we still
            # prefer Gen 5 assets over generic Showdown sprites.
            return True

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
            use_fallback: If True and style='animated', returns a prioritized list of URLs
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
        # Convert to lowercase, remove diacritics, and replace spaces with hyphens for parsing
        # Remove apostrophes, periods, and colons so names like "Mr. Mime" or "Type: Null"
        # line up with Showdown's sprite IDs.
        raw_name = (
            PokemonSpriteHelper._strip_accents(pokemon_name.lower())
            .replace(' ', '-')
            .replace("'", "")
            .replace(".", "")
            .replace(":", "")
            .replace("%", "")
        )

        # Infer form or gender from the provided name if they aren't explicitly supplied
        segments = raw_name.split('-')
        inferred_gender = gender
        inferred_form = form

        if len(segments) > 1:
            last_segment = segments[-1]
            if inferred_gender is None and last_segment in {"f", "female", "m", "male"}:
                inferred_gender = "female" if last_segment.startswith('f') else "male"
                base_segments = segments[:-1]
            elif inferred_form is None and last_segment in PokemonSpriteHelper.KNOWN_FORM_SUFFIXES:
                inferred_form = '-'.join(segments[1:])
                base_segments = [segments[0]]
            else:
                base_segments = segments
        else:
            base_segments = segments

        # Reconstruct the base name without hyphens so we can append forms/gender cleanly
        base_name = ''.join(base_segments)
        base_name = PokemonSpriteHelper._sanitize_component(base_name)

        # Normalize certain forms to match Showdown sprite naming
        if inferred_form:
            form_key = (base_name, inferred_form.lower())
            if form_key == ("lycanroc", "midday"):
                inferred_form = None  # Midday uses the base lycanroc sprite
            elif form_key == ("urshifu", "single-strike"):
                inferred_form = None  # Single Strike is the default Urshifu sprite
            elif form_key == ("urshifu", "rapid-strike"):
                inferred_form = "rapidstrike"

        # Add form suffix if specified (e.g., "sandshrew-alola")
        if inferred_form:
            form_slug = PokemonSpriteHelper._sanitize_component(inferred_form, allow_hyphens=True)
            name = f"{base_name}-{form_slug}"
        else:
            name = base_name

        gender = inferred_gender

        if style == 'animated':
            gendered_name = PokemonSpriteHelper._gendered_name(name, gender)

            animated_url = (
                PokemonSpriteHelper.GEN5_ANIMATED_SHINY.format(name=gendered_name)
                if shiny
                else PokemonSpriteHelper.GEN5_ANIMATED.format(name=gendered_name)
            )
            static_fallback = (
                PokemonSpriteHelper.GEN5_STATIC_SHINY.format(name=gendered_name)
                if shiny
                else PokemonSpriteHelper.GEN5_STATIC.format(name=gendered_name)
            )

            showdown_static = (
                PokemonSpriteHelper.SHOWDOWN_STATIC_SHINY.format(name=gendered_name)
                if shiny
                else PokemonSpriteHelper.SHOWDOWN_STATIC.format(name=gendered_name)
            )

            sprite_urls = [animated_url, static_fallback, showdown_static]
            available_urls = [url for url in sprite_urls if PokemonSpriteHelper._url_exists(url)]

            if available_urls:
                prioritized_urls = available_urls + [
                    url for url in sprite_urls if url not in available_urls
                ]
            else:
                prioritized_urls = sprite_urls

            if not use_fallback:
                return prioritized_urls[0]

            return prioritized_urls

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

        if isinstance(url, list):
            url = url[0]

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
