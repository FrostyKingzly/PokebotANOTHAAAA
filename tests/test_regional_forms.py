from database import SpeciesDatabase
from sprite_helper import PokemonSpriteHelper


def test_alolan_vulpix_loaded_and_uses_correct_sprite_slug():
    species_db = SpeciesDatabase('data/pokemon_species.json')

    alolan_vulpix = species_db.get_species('Alolan Vulpix')
    assert alolan_vulpix is not None
    assert alolan_vulpix['form'] == 'alola'
    assert alolan_vulpix['types'] == ['ice']

    sprite = PokemonSpriteHelper.get_sprite(alolan_vulpix['name'], alolan_vulpix['dex_number'], use_fallback=False)
    assert sprite.endswith('/vulpix-alola.gif')


def test_regional_aliases_resolve_to_same_species():
    species_db = SpeciesDatabase('data/pokemon_species.json')

    by_suffix = species_db.get_species('vulpix-alola')
    by_prefix = species_db.get_species('alola vulpix')

    assert by_suffix is not None
    assert by_prefix is not None
    assert by_suffix['name'] == by_prefix['name']


def test_hisuian_forms_are_accessible():
    species_db = SpeciesDatabase('data/pokemon_species.json')

    hisuian_growlithe = species_db.get_species('growlithe-hisui')
    assert hisuian_growlithe is not None
    assert hisuian_growlithe['types'] == ['fire', 'rock']
