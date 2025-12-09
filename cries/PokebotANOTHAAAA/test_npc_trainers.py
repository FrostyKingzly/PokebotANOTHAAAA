"""
Test NPC Trainers for Doubles Battles

This module provides pre-configured NPC trainers with specific strategies
for testing doubles battle mechanics.
"""

from models import Pokemon
from typing import List


def create_trick_room_doubles_team(species_db, moves_db) -> List[Pokemon]:
    """
    Create a Trick Room-focused doubles team.

    Team:
    1. Dusclops - Trick Room setter, slow bulky support
    2. Rhyperior - Slow physical attacker with spread moves
    3. Conkeldurr - Slow physical attacker
    4. Torkoal - Slow special attacker with spread moves
    """

    team = []

    # Dusclops - Trick Room setter
    dusclops_species = species_db.get_species("dusclops")
    if dusclops_species:
        dusclops = Pokemon(
            species_dex_number=dusclops_species['dex_number'],
            species_name=dusclops_species['name'],
            species_data=dusclops_species,
            level=50,
            gender='genderless',
            nature='relaxed',  # +Def, -Speed (wants to be slow for Trick Room)
            ability='pressure',
            moves=[
                {'move_id': 'trick_room', 'name': 'Trick Room', 'pp': 5, 'max_pp': 5},
                {'move_id': 'helping_hand', 'name': 'Helping Hand', 'pp': 32, 'max_pp': 32},
                {'move_id': 'pain_split', 'name': 'Pain Split', 'pp': 32, 'max_pp': 32},
                {'move_id': 'night_shade', 'name': 'Night Shade', 'pp': 24, 'max_pp': 24},
            ],
            ivs={'hp': 31, 'attack': 0, 'defense': 31, 'sp_attack': 31, 'sp_defense': 31, 'speed': 0},
            evs={'hp': 252, 'attack': 0, 'defense': 252, 'sp_attack': 0, 'sp_defense': 4, 'speed': 0}
        )
        dusclops.calculate_stats()
        team.append(dusclops)

    # Rhyperior - Slow physical attacker with Earthquake (spread move)
    rhyperior_species = species_db.get_species("rhyperior")
    if rhyperior_species:
        rhyperior = Pokemon(
            species_dex_number=rhyperior_species['dex_number'],
            species_name=rhyperior_species['name'],
            species_data=rhyperior_species,
            level=50,
            gender='male',
            nature='brave',  # +Attack, -Speed
            ability='solid_rock',
            moves=[
                {'move_id': 'earthquake', 'name': 'Earthquake', 'pp': 16, 'max_pp': 16},
                {'move_id': 'rock_slide', 'name': 'Rock Slide', 'pp': 16, 'max_pp': 16},
                {'move_id': 'stone_edge', 'name': 'Stone Edge', 'pp': 8, 'max_pp': 8},
                {'move_id': 'megahorn', 'name': 'Megahorn', 'pp': 16, 'max_pp': 16},
            ],
            ivs={'hp': 31, 'attack': 31, 'defense': 31, 'sp_attack': 31, 'sp_defense': 31, 'speed': 0},
            evs={'hp': 252, 'attack': 252, 'defense': 0, 'sp_attack': 0, 'sp_defense': 4, 'speed': 0}
        )
        rhyperior.calculate_stats()
        team.append(rhyperior)

    # Conkeldurr - Slow physical attacker
    conkeldurr_species = species_db.get_species("conkeldurr")
    if conkeldurr_species:
        conkeldurr = Pokemon(
            species_dex_number=conkeldurr_species['dex_number'],
            species_name=conkeldurr_species['name'],
            species_data=conkeldurr_species,
            level=50,
            gender='male',
            nature='brave',  # +Attack, -Speed
            ability='guts',
            moves=[
                {'move_id': 'drain_punch', 'name': 'Drain Punch', 'pp': 16, 'max_pp': 16},
                {'move_id': 'mach_punch', 'name': 'Mach Punch', 'pp': 48, 'max_pp': 48},
                {'move_id': 'ice_punch', 'name': 'Ice Punch', 'pp': 24, 'max_pp': 24},
                {'move_id': 'knock_off', 'name': 'Knock Off', 'pp': 32, 'max_pp': 32},
            ],
            ivs={'hp': 31, 'attack': 31, 'defense': 31, 'sp_attack': 31, 'sp_defense': 31, 'speed': 0},
            evs={'hp': 252, 'attack': 252, 'defense': 0, 'sp_attack': 0, 'sp_defense': 4, 'speed': 0}
        )
        conkeldurr.calculate_stats()
        team.append(conkeldurr)

    # Torkoal - Slow special attacker with Eruption (spread move)
    torkoal_species = species_db.get_species("torkoal")
    if torkoal_species:
        torkoal = Pokemon(
            species_dex_number=torkoal_species['dex_number'],
            species_name=torkoal_species['name'],
            species_data=torkoal_species,
            level=50,
            gender='male',
            nature='quiet',  # +SpAtk, -Speed
            ability='drought',
            moves=[
                {'move_id': 'eruption', 'name': 'Eruption', 'pp': 8, 'max_pp': 8},
                {'move_id': 'heat_wave', 'name': 'Heat Wave', 'pp': 16, 'max_pp': 16},
                {'move_id': 'earth_power', 'name': 'Earth Power', 'pp': 16, 'max_pp': 16},
                {'move_id': 'protect', 'name': 'Protect', 'pp': 16, 'max_pp': 16},
            ],
            ivs={'hp': 31, 'attack': 0, 'defense': 31, 'sp_attack': 31, 'sp_defense': 31, 'speed': 0},
            evs={'hp': 252, 'attack': 0, 'defense': 0, 'sp_attack': 252, 'sp_defense': 4, 'speed': 0}
        )
        torkoal.calculate_stats()
        team.append(torkoal)

    return team


def get_test_doubles_trainer(species_db, moves_db, trainer_id: int = -9999):
    """
    Get a test doubles trainer with a Trick Room team.

    Returns:
        dict with 'trainer_id', 'trainer_name', 'party', 'trainer_class'
    """
    party = create_trick_room_doubles_team(species_db, moves_db)

    return {
        'trainer_id': trainer_id,
        'trainer_name': 'Trick Room Master Trent',
        'trainer_class': 'Ace Trainer',
        'party': party,
        'prize_money': 5000
    }
