import pytest

from sprite_helper import PokemonSpriteHelper


def test_showdown_slug_normalization_handles_punctuation():
    url = PokemonSpriteHelper.get_sprite("Mr. Mime", 122, style="showdown", use_fallback=False)
    assert url.endswith("/mrmime.png")


def test_showdown_slug_normalization_strips_accents():
    url = PokemonSpriteHelper.get_sprite("Flabébé", 669, style="showdown", use_fallback=False)
    assert url.endswith("/flabebe.png")


def test_modern_species_default_to_reliable_showdown_static():
    urls = PokemonSpriteHelper.get_sprite("Armarouge", 936)
    assert isinstance(urls, list)
    assert urls[0] == PokemonSpriteHelper.SHOWDOWN_STATIC.format(name="armarouge")
    assert urls[-1] == PokemonSpriteHelper.OFFICIAL_ART.format(id="936")


def test_gen_one_species_keep_gen5_animation_chain():
    urls = PokemonSpriteHelper.get_sprite("Charizard", 6)
    assert urls[0].endswith("gen5ani/charizard.gif")
    assert PokemonSpriteHelper.SHOWDOWN_STATIC.format(name="charizard") in urls
