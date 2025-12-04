"""
Learnset Database Module
Handles loading and querying Pokemon learnsets
"""

import json
from typing import List, Dict, Optional


class LearnsetDatabase:
    """Manages learnset data for all Pokemon"""
    
    def __init__(self, filepath: str):
        """Load learnsets from JSON file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            # If the learnset data is missing or corrupted, avoid crashing the bot
            # and fall back to an empty dataset instead.
            # This preserves functionality for commands that can operate without
            # learnset data while surfacing the underlying issue for debugging.
            print(f"Failed to load learnsets from {filepath}: {exc}")
            self.data = {}
    
    def get_learnset(self, pokemon_name: str) -> Optional[Dict]:
        """
        Get learnset for a Pokemon by name
        
        Args:
            pokemon_name: Pokemon species name (e.g., "Bulbasaur" or "bulbasaur")
        
        Returns:
            Learnset dictionary or None if not found
        """
        # Convert to lowercase for lookup
        pokemon_id = pokemon_name.lower().replace(' ', '').replace('-', '')
        return self.data.get(pokemon_id)
    
    def get_moves_at_level(self, pokemon_name: str, level: int, gen: int = 9) -> List[str]:
        """
        Get all moves a Pokemon can know at a given level
        
        Args:
            pokemon_name: Pokemon species name
            level: Current level of the Pokemon
            gen: Generation to use (default 9 for latest)
        
        Returns:
            List of move IDs the Pokemon can know at this level
        """
        learnset = self.get_learnset(pokemon_name)
        if not learnset:
            return []
        
        # Get all level-up moves up to and including this level
        available_moves = []
        for move_data in learnset.get('level_up_moves', []):
            if move_data['level'] <= level:
                # Prefer the specified gen, but include all
                if move_data['gen'] <= gen:
                    move_id = move_data['move_id']
                    if move_id not in available_moves:
                        available_moves.append(move_id)
        
        return available_moves
    
    def get_starting_moves(self, pokemon_name: str, level: int = 5, max_moves: int = 4) -> List[str]:
        """
        Get appropriate starting moves for a Pokemon
        Prioritizes most recent level-up moves
        
        Args:
            pokemon_name: Pokemon species name
            level: Starting level (default 5)
            max_moves: Maximum number of moves to return (default 4)
        
        Returns:
            List of move IDs for starting moveset
        """
        learnset = self.get_learnset(pokemon_name)
        if not learnset:
            # Fallback to basic moves
            return ['tackle', 'growl'][:max_moves]
        
        level_up_moves = learnset.get('level_up_moves', [])
        if not level_up_moves:
            return ['tackle', 'growl'][:max_moves]
        
        # Get moves learned up to the current level
        learned_moves = []
        for move_data in level_up_moves:
            if move_data['level'] <= level:
                learned_moves.append(move_data)
        
        if not learned_moves:
            # If no moves learned yet, get level 1 moves
            learned_moves = [m for m in level_up_moves if m['level'] == 1]
        
        # Sort by level (descending) to get most recent moves first
        learned_moves.sort(key=lambda x: (-x['level'], -x['gen']))
        
        # Get the most recent moves (up to max_moves)
        selected_moves = []
        for move_data in learned_moves:
            move_id = move_data['move_id']
            if move_id not in selected_moves:
                selected_moves.append(move_id)
                if len(selected_moves) >= max_moves:
                    break
        
        # If we still don't have enough moves, pad with level 1 moves
        if len(selected_moves) < max_moves:
            level_1_moves = [m['move_id'] for m in level_up_moves if m['level'] == 1]
            for move_id in level_1_moves:
                if move_id not in selected_moves:
                    selected_moves.append(move_id)
                    if len(selected_moves) >= max_moves:
                        break
        
        # Final fallback
        if not selected_moves:
            selected_moves = ['tackle', 'growl'][:max_moves]
        
        return selected_moves[:max_moves]
    
    def get_tm_moves(self, pokemon_name: str) -> List[str]:
        """Get all TM moves a Pokemon can learn"""
        learnset = self.get_learnset(pokemon_name)
        if not learnset:
            return []
        return learnset.get('tm_moves', [])
    
    def get_egg_moves(self, pokemon_name: str) -> List[str]:
        """Get all egg moves a Pokemon can learn"""
        learnset = self.get_learnset(pokemon_name)
        if not learnset:
            return []
        return learnset.get('egg_moves', [])
    
    def get_tutor_moves(self, pokemon_name: str) -> List[str]:
        """Get all tutor moves a Pokemon can learn"""
        learnset = self.get_learnset(pokemon_name)
        if not learnset:
            return []
        return learnset.get('tutor_moves', [])
    
    def can_learn_move(self, pokemon_name: str, move_id: str) -> bool:
        """Check if a Pokemon can learn a specific move by any method"""
        learnset = self.get_learnset(pokemon_name)
        if not learnset:
            return False
        
        # Check level-up moves
        level_up_moves = [m['move_id'] for m in learnset.get('level_up_moves', [])]
        if move_id in level_up_moves:
            return True
        
        # Check TM moves
        if move_id in learnset.get('tm_moves', []):
            return True
        
        # Check egg moves
        if move_id in learnset.get('egg_moves', []):
            return True
        
        # Check tutor moves
        if move_id in learnset.get('tutor_moves', []):
            return True
        
        return False
    
    def get_next_level_moves(self, pokemon_name: str, current_level: int, max_level: int = 100) -> List[Dict]:
        """
        Get upcoming moves that will be learned
        
        Args:
            pokemon_name: Pokemon species name
            current_level: Current level
            max_level: Max level to check up to
        
        Returns:
            List of dicts with 'level' and 'move_id'
        """
        learnset = self.get_learnset(pokemon_name)
        if not learnset:
            return []
        
        upcoming_moves = []
        for move_data in learnset.get('level_up_moves', []):
            if current_level < move_data['level'] <= max_level:
                upcoming_moves.append({
                    'level': move_data['level'],
                    'move_id': move_data['move_id']
                })
        
        # Sort by level
        upcoming_moves.sort(key=lambda x: x['level'])
        
        # Remove duplicates (keep earliest level)
        seen = set()
        unique_moves = []
        for move_data in upcoming_moves:
            if move_data['move_id'] not in seen:
                seen.add(move_data['move_id'])
                unique_moves.append(move_data)
        
        return unique_moves


# Example usage
if __name__ == "__main__":
    # Test the learnset database
    db = LearnsetDatabase('learnsets.json')
    
    # Test Bulbasaur
    print("Testing Bulbasaur:")
    starting_moves = db.get_starting_moves('Bulbasaur', level=5)
    print(f"Starting moves at level 5: {starting_moves}")
    
    next_moves = db.get_next_level_moves('Bulbasaur', 5, 20)
    print(f"Next moves until level 20:")
    for move in next_moves[:5]:
        print(f"  Level {move['level']}: {move['move_id']}")
    
    print(f"\nCan learn Razor Leaf? {db.can_learn_move('Bulbasaur', 'razorleaf')}")
    print(f"Can learn Flamethrower? {db.can_learn_move('Bulbasaur', 'flamethrower')}")
