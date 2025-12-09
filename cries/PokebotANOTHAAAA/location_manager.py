"""
Location Manager - Handles location data and channel mapping
"""

import json
import random
from pathlib import Path
from typing import Optional, Dict, List
from models import Pokemon


class LocationManager:
    """Manages location data and encounter tables"""

    def __init__(self, json_path: str = "data/locations.json", channel_map_path: str = "config/channel_locations.json"):
        self.json_path = json_path
        self.channel_map_path = Path(channel_map_path)
        self.locations = {}
        self.channel_to_location = {}  # Map channel IDs to location IDs
        self.load_locations()
        self._load_channel_mappings()

    def load_locations(self):
        """Load locations from JSON"""
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                self.locations = json.load(f)

            # Build channel mapping from any legacy channel_id entries
            self.channel_to_location = {}
            for location_id, location_data in self.locations.items():
                for channel_id in location_data.get('channel_ids', []):
                    try:
                        chan_int = int(channel_id)
                    except (TypeError, ValueError):
                        continue
                    self.channel_to_location[chan_int] = location_id

            print(f"✅ Loaded {len(self.locations)} locations")
        except FileNotFoundError:
            print(f"⚠️ Locations file not found at {self.json_path}")
            self.locations = {}

    def _load_channel_mappings(self):
        """Load per-channel location locks from persistent storage."""
        self.channel_map_path.parent.mkdir(parents=True, exist_ok=True)
        mapping_exists = self.channel_map_path.exists()
        if mapping_exists:
            try:
                with open(self.channel_map_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for channel_id, location_id in data.items():
                    try:
                        chan_int = int(channel_id)
                    except (TypeError, ValueError):
                        continue
                    if location_id in self.locations:
                        self.channel_to_location[chan_int] = location_id
            except (json.JSONDecodeError, OSError):
                print("⚠️ Failed to load channel mapping file, continuing with in-memory data")
        self._sync_channel_lists()
        if not mapping_exists:
            self._save_channel_mappings()

    def _save_channel_mappings(self):
        data = {str(channel_id): location_id for channel_id, location_id in self.channel_to_location.items()}
        self.channel_map_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.channel_map_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    def _sync_channel_lists(self):
        for location_id, location_data in self.locations.items():
            ids = [cid for cid, loc in self.channel_to_location.items() if loc == location_id]
            location_data['channel_ids'] = sorted(ids)
    
    def get_location(self, location_id: str) -> Optional[Dict]:
        """Get location data by ID"""
        return self.locations.get(location_id)

    def location_has_amenity(self, location_id: str, amenity: str) -> bool:
        """Return True if the given location advertises the requested amenity."""
        if not location_id or not amenity:
            return False

        location = self.get_location(location_id)
        if not location:
            return False

        amenities = location.get('amenities')
        if isinstance(amenities, list):
            normalized = str(amenity).lower()
            return any(str(entry).lower() == normalized for entry in amenities)

        legacy_flag = location.get(f'has_{amenity}') or location.get(amenity)
        return bool(legacy_flag)

    def has_pokemon_center(self, location_id: str) -> bool:
        """Helper to check whether a location includes a Pokémon Center."""
        return self.location_has_amenity(location_id, 'pokemon_center')

    def get_location_by_channel(self, channel_id: int) -> Optional[str]:
        """Get location ID for a channel"""
        return self.channel_to_location.get(channel_id)
    
    def get_all_locations(self) -> Dict[str, Dict]:
        """Get all locations"""
        return self.locations
    
    def roll_encounter(self, location_id: str, species_db) -> Optional[Pokemon]:
        """
        Roll a single wild Pokemon encounter from a location
        
        Args:
            location_id: ID of the location to roll from
            species_db: SpeciesDatabase instance
        
        Returns:
            Pokemon object or None if location not found
        """
        location = self.get_location(location_id)
        if not location:
            return None
        
        encounters = location.get('encounters', [])
        if not encounters:
            return None
        
        # Calculate total weight
        total_weight = sum(enc['weight'] for enc in encounters)
        
        # Roll for encounter
        roll = random.uniform(0, total_weight)
        current_weight = 0
        
        for encounter in encounters:
            current_weight += encounter['weight']
            if roll <= current_weight:
                # Generate this Pokemon
                species_data = species_db.get_species(encounter['species_dex_number'])
                if not species_data:
                    continue

                # Random level within range
                level = random.randint(
                    encounter['min_level'],
                    encounter['max_level']
                )

                # Get form from encounter data (if specified)
                form = encounter.get('form', None)

                # Create Pokemon
                pokemon = Pokemon(
                    species_data=species_data,
                    level=level,
                    owner_discord_id=None,  # Wild Pokemon
                    form=form
                )

                return pokemon
        
        return None
    
    def roll_multiple_encounters(self, location_id: str, count: int, species_db) -> List[Pokemon]:
        """
        Roll multiple wild Pokemon encounters from a location
        
        Args:
            location_id: ID of the location to roll from
            count: Number of encounters to roll
            species_db: SpeciesDatabase instance
        
        Returns:
            List of Pokemon objects
        """
        encounters = []
        for _ in range(count):
            pokemon = self.roll_encounter(location_id, species_db)
            if pokemon:
                encounters.append(pokemon)
        
        return encounters
    
    def add_channel_to_location(self, channel_id: int, location_id: str) -> bool:
        """
        Map a Discord channel to a location
        
        Args:
            channel_id: Discord channel ID
            location_id: Location ID to map to
        
        Returns:
            True if successful, False if location doesn't exist
        """
        if location_id not in self.locations:
            return False

        existing = self.channel_to_location.get(channel_id)
        if existing and existing != location_id:
            self.remove_channel_from_location(channel_id)

        self.channel_to_location[int(channel_id)] = location_id
        self._sync_channel_lists()
        self._save_channel_mappings()
        self.save_locations()
        return True
    
    def remove_channel_from_location(self, channel_id: int) -> bool:
        """
        Remove a channel from its location mapping
        
        Args:
            channel_id: Discord channel ID
        
        Returns:
            True if removed, False if not found
        """
        location_id = self.channel_to_location.get(channel_id)
        if not location_id:
            return False

        del self.channel_to_location[channel_id]
        self._sync_channel_lists()
        self._save_channel_mappings()
        self.save_locations()
        return True
    
    def save_locations(self):
        """Save locations to JSON file"""
        try:
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(self.locations, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"❌ Error saving locations: {e}")
            return False
    
    def get_location_name(self, location_id: str) -> str:
        """Get formatted location name"""
        location = self.get_location(location_id)
        if location:
            return location.get('name', location_id.replace('_', ' ').title())
        return location_id.replace('_', ' ').title()
