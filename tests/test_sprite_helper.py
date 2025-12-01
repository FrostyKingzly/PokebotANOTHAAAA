import pytest

from sprite_helper import PokemonSpriteHelper


def test_showdown_slug_normalization_handles_punctuation():
    url = PokemonSpriteHelper.get_sprite("Mr. Mime", 122, style="showdown", use_fallback=False)
    assert url.endswith("/mrmime.png")


def test_showdown_slug_normalization_strips_accents():
    url = PokemonSpriteHelper.get_sprite("Flabébé", 669, style="showdown", use_fallback=False)
    assert url.endswith("/flabebe.png")


def test_modern_species_use_gen5_chain_even_when_outside_gen5_dex():
    urls = PokemonSpriteHelper.get_sprite("Armarouge", 936)
    assert isinstance(urls, list)
    assert urls[0].endswith("gen5/armarouge.png")
    assert urls[1].endswith("gen5ani/armarouge.gif")
    assert PokemonSpriteHelper.OFFICIAL_ART.format(id="936") not in urls


def test_modern_species_without_fallback_use_static_gen5():
    url = PokemonSpriteHelper.get_sprite(
        "Baxcalibur", 998, style="animated", use_fallback=False
    )
    assert url.endswith("gen5/baxcalibur.png")


def test_regional_forms_prefer_static_when_no_animation_available():
    urls = PokemonSpriteHelper.get_sprite("growlithe-hisui", 58)
    assert urls[0].endswith("gen5/growlithe-hisui.png")
    assert urls[1].endswith("gen5ani/growlithe-hisui.gif")


def test_gen_one_species_keep_gen5_animation_chain():
    urls = PokemonSpriteHelper.get_sprite("Charizard", 6)
    assert urls[0].endswith("gen5ani/charizard.gif")
    assert PokemonSpriteHelper.SHOWDOWN_STATIC.format(name="charizard") in urls


def test_female_sprites_only_use_variant_when_available():
    url = PokemonSpriteHelper.get_sprite("Frosmoth", 873, style="showdown", gender="female", use_fallback=False)
    assert url.endswith("/frosmoth.png")


def test_known_female_variant_keeps_gendered_slug():
    url = PokemonSpriteHelper.get_sprite("Meowstic", 678, style="showdown", gender="female", use_fallback=False)
    assert url.endswith("/meowstic-f.png")
