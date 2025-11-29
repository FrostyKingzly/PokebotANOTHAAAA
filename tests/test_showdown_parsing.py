import unittest
from types import SimpleNamespace

from cogs.admin_cog import AdminCog
from database import SpeciesDatabase


class DummyBot(SimpleNamespace):
    pass


class ShowdownParsingTests(unittest.TestCase):
    def setUp(self):
        self.cog = AdminCog(bot=DummyBot())

    def test_moves_and_items_normalize_to_database_ids(self):
        showdown_text = """
Porygon-Z @ Choice Scarf
Ability: Download
Level: 50
EVs: 252 SpA / 4 SpD / 252 Spe
Modest Nature
IVs: 31 HP / 31 SpA / 31 Spe
- Tri Attack
- U-turn
- Hidden Power Ice
- Nasty Plot
"""
        parsed = self.cog.parse_showdown_format(showdown_text)

        self.assertEqual(parsed['species'], 'Porygon-Z')
        self.assertEqual(parsed['held_item'], 'choice_scarf')
        self.assertEqual(parsed['ability'], 'download')
        self.assertIn('tri_attack', parsed['moves'])
        self.assertIn('u_turn', parsed['moves'])
        self.assertIn('hidden_power_ice', parsed['moves'])
        self.assertIn('nasty_plot', parsed['moves'])

    def test_species_lookup_handles_showdown_variants(self):
        species_db = SpeciesDatabase('data/pokemon_species.json')

        self.assertEqual(species_db.get_species('mr_mime')['dex_number'], 122)
        self.assertEqual(species_db.get_species('Nidoran-F')['dex_number'], 29)
        self.assertEqual(species_db.get_species('porygon-z')['dex_number'], 474)


if __name__ == '__main__':
    unittest.main()
