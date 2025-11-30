"""
EXP Display Helpers
Helper functions for displaying EXP progress in embeds
"""

import discord
from typing import Dict, Tuple
from exp_system import ExpSystem


def get_exp_progress(pokemon_data: Dict, species_data: Dict) -> Tuple[int, int, float, int]:
    """
    Get experience progress for a Pokemon
    
    Args:
        pokemon_data: Pokemon dict with 'exp' and 'level' keys
        species_data: Species data with 'growth_rate' key
    
    Returns:
        Tuple of (current_exp_in_level, exp_needed_for_next, percentage, total_exp)
        
    Example:
        >>> current, needed, percent, total = get_exp_progress(pokemon, species)
        >>> print(f"{current}/{needed} ({percent:.1f}%)")
        140/2000 (7.0%)
    """
    level = pokemon_data['level']
    total_exp = pokemon_data.get('exp', 0)
    growth_rate = species_data.get('growth_rate', 'medium_fast')
    
    if level >= 100:
        return (0, 0, 100.0, total_exp)
    
    # Get exp at current level and next level
    exp_at_current_level = ExpSystem.exp_to_level(level, growth_rate)
    exp_at_next_level = ExpSystem.exp_to_level(level + 1, growth_rate)
    
    # Calculate progress within this level
    current_exp_in_level = max(0, total_exp - exp_at_current_level)
    exp_needed_for_next = exp_at_next_level - exp_at_current_level
    
    # Calculate percentage
    if exp_needed_for_next > 0:
        percentage = (current_exp_in_level / exp_needed_for_next) * 100
    else:
        percentage = 100.0
    
    return (current_exp_in_level, exp_needed_for_next, percentage, total_exp)


def create_exp_bar(percentage: float, length: int = 10) -> str:
    """
    Create a visual EXP progress bar
    
    Args:
        percentage: Progress percentage (0-100)
        length: Length of the bar (default 10)
    
    Returns:
        String representation of the bar
        
    Example:
        >>> create_exp_bar(70, length=10)
        '🟦🟦🟦🟦🟦🟦🟦⬜⬜⬜'
    """
    filled = int((percentage / 100) * length)
    filled = max(0, min(filled, length))  # Clamp to valid range
    empty = length - filled
    
    # Use cyan/blue for exp bars
    return "🟦" * filled + "⬜" * empty


def create_exp_text(pokemon_data: Dict, species_data: Dict, 
                    show_bar: bool = True, bar_length: int = 10) -> str:
    """
    Create formatted EXP text for embeds
    
    Args:
        pokemon_data: Pokemon dict with exp and level
        species_data: Species data with growth_rate
        show_bar: Whether to show the progress bar
        bar_length: Length of the progress bar
    
    Returns:
        Formatted string ready for embed fields
        
    Example:
        >>> text = create_exp_text(pokemon, species, show_bar=True)
        >>> print(text)
        🟦🟦🟦⬜⬜⬜⬜⬜⬜⬜
        **EXP:** 140/2000
        **Total:** 5,140 EXP
    """
    level = pokemon_data['level']
    
    if level >= 100:
        return f"**Level 100!**\n**Total:** {pokemon_data.get('exp', 0):,} EXP"
    
    current_in_level, exp_needed, percentage, total_exp = get_exp_progress(
        pokemon_data, species_data
    )
    
    text = ""
    if show_bar:
        exp_bar = create_exp_bar(percentage, length=bar_length)
        text += f"{exp_bar}\n"
    
    text += f"**EXP:** {current_in_level:,}/{exp_needed:,}\n"
    text += f"**Total:** {total_exp:,} EXP"
    
    return text


def create_compact_exp_text(pokemon_data: Dict, species_data: Dict) -> str:
    """
    Create compact EXP text for space-limited displays
    
    Args:
        pokemon_data: Pokemon dict with exp and level
        species_data: Species data with growth_rate
    
    Returns:
        Compact string like "140/2000 EXP (7%)"
    """
    level = pokemon_data['level']
    
    if level >= 100:
        return "Max Level"
    
    current_in_level, exp_needed, percentage, _ = get_exp_progress(
        pokemon_data, species_data
    )
    
    return f"{current_in_level}/{exp_needed} EXP ({percentage:.0f}%)"


# Example usage
if __name__ == "__main__":
    print("=== EXP Display Helper Examples ===\n")
    
    # Example Pokemon
    example_pokemon = {
        'level': 15,
        'exp': 3000
    }
    
    example_species = {
        'growth_rate': 'medium_fast'
    }
    
    # Get progress
    current, needed, percent, total = get_exp_progress(example_pokemon, example_species)
    print(f"Progress: {current}/{needed} ({percent:.1f}%)")
    print(f"Total EXP: {total:,}\n")
    
    # Show bar
    bar = create_exp_bar(percent, length=10)
    print(f"Bar: {bar}\n")
    
    # Full text
    full_text = create_exp_text(example_pokemon, example_species)
    print("Full Text:")
    print(full_text)
    print()
    
    # Compact text
    compact = create_compact_exp_text(example_pokemon, example_species)
    print(f"Compact: {compact}")
