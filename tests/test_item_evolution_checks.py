from item_usage_manager import ItemUsageManager


class _SpeciesDB:
    def get_species(self, _):
        return None


class _Bot:
    items_db = None
    moves_db = None
    species_db = _SpeciesDB()


def _manager_with_data(data: dict) -> ItemUsageManager:
    manager = ItemUsageManager(_Bot())
    manager.evolution_data = data
    return manager


def test_stone_evolution_detected_when_holding_matching_item():
    manager = _manager_with_data(
        {"pikachu": {"method": "stone", "stone": "thunder_stone", "into": "raichu"}}
    )
    can_evolve, method, evo_data = manager.can_evolve(
        {"species_name": "Pikachu", "level": 6, "held_item": "thunder_stone"}
    )

    assert can_evolve is True
    assert method == "stone"
    assert evo_data["into"] == "raichu"


def test_stone_evolution_matches_item_name_with_spaces():
    manager = _manager_with_data(
        {"pikachu": {"method": "stone", "stone": "thunder_stone", "into": "raichu"}}
    )
    can_evolve, method, _ = manager.can_evolve(
        {"species_name": "Pikachu", "held_item": "Thunder Stone"}
    )

    assert can_evolve is True
    assert method == "stone"


def test_multiple_stone_evolution_detected_with_held_item():
    manager = _manager_with_data(
        {
            "eevee": {
                "method": "multiple",
                "evolutions": [
                    {"method": "stone", "stone": "water_stone", "into": "vaporeon"},
                    {"method": "stone", "stone": "thunder_stone", "into": "jolteon"},
                ],
            }
        }
    )
    can_evolve, method, evo_data = manager.can_evolve(
        {"species_name": "Eevee", "held_item": "Thunder Stone"}
    )

    assert can_evolve is True
    assert method == "multiple"
    assert evo_data["into"] == "jolteon"


def test_multiple_stone_evolution_resolves_fire_stone_to_flareon():
    manager = _manager_with_data(
        {
            "eevee": {
                "method": "multiple",
                "evolutions": [
                    {"method": "stone", "stone": "water_stone", "into": "vaporeon"},
                    {"method": "stone", "stone": "thunder_stone", "into": "jolteon"},
                    {"method": "stone", "stone": "fire_stone", "into": "flareon"},
                ],
            }
        }
    )
    can_evolve, method, evo_data = manager.can_evolve(
        {"species_name": "Eevee", "held_item": "Fire Stone"}
    )

    assert can_evolve is True
    assert method == "multiple"
    assert evo_data["into"] == "flareon"
