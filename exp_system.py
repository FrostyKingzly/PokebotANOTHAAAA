"""
Experience System for Pokemon Bot - Gen V+ Accurate
Based on official Pokemon formulas from Bulbapedia

This implements the SCALED experience formula used in Gen V, VII, VIII, and IX
where lower-level Pokemon gain significantly more EXP from higher-level opponents.
"""

import math
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class LevelUpResult:
    """Stores what happened when a Pokemon leveled up"""
    old_level: int
    new_level: int
    stat_gains: Dict[str, int]  # stat_name -> amount gained
    new_moves_learned: List[str]  # move_ids that were learned
    moves_available_to_learn: List[Dict]  # Moves that can be learned (if party full)


class ExpSystem:
    """
    Handles all EXP-related calculations and level-ups
    
    Based on Gen V+ Pokemon games mechanics:
    - Scaled EXP formula (lower level Pokemon gain MORE exp from higher level foes)
    - Growth rates (Fast, Medium Fast, Medium Slow, Slow, Erratic, Fluctuating)
    - EXP Share distributes to entire party
    - Accurate level-up calculations
    """
    
    # Experience tables - these are lookup tables to avoid calculation errors
    # Values are total EXP needed to reach each level
    # Source: https://bulbapedia.bulbagarden.net/wiki/Experience
    
    @staticmethod
    def _generate_experience_table(growth_rate: str, max_level: int = 100) -> Dict[int, int]:
        """
        Generate experience table for a growth rate
        Returns dict of {level: total_exp_needed}
        """
        table = {1: 0}
        
        for level in range(2, max_level + 1):
            if growth_rate == 'fast':
                exp = int((4 * (level ** 3)) / 5)
            elif growth_rate == 'medium_fast':
                exp = int(level ** 3)
            elif growth_rate == 'medium_slow':
                exp = int((6/5) * (level ** 3) - 15 * (level ** 2) + 100 * level - 140)
            elif growth_rate == 'slow':
                exp = int((5 * (level ** 3)) / 4)
            elif growth_rate == 'erratic':
                exp = ExpSystem._erratic_formula(level)
            elif growth_rate == 'fluctuating':
                exp = ExpSystem._fluctuating_formula(level)
            else:
                exp = int(level ** 3)  # Default to medium_fast
            
            table[level] = exp
        
        return table
    
    @staticmethod
    def _erratic_formula(level: int) -> int:
        """
        Erratic growth rate formula (piecewise)
        Used by many Bug and Water types
        Total at level 100: 600,000
        """
        if level <= 50:
            return int(((level ** 3) * (100 - level)) / 50)
        elif level <= 68:
            return int(((level ** 3) * (150 - level)) / 100)
        elif level <= 98:
            return int(((level ** 3) * ((1911 - 10 * level) / 3)) / 500)
        else:
            return int(((level ** 3) * (160 - level)) / 100)
    
    @staticmethod
    def _fluctuating_formula(level: int) -> int:
        """
        Fluctuating growth rate formula (piecewise)
        Slowest growth rate
        Total at level 100: 1,640,000
        """
        if level <= 15:
            return int((level ** 3) * ((((level + 1) / 3) + 24) / 50))
        elif level <= 36:
            return int((level ** 3) * ((level + 14) / 50))
        else:
            return int((level ** 3) * (((level / 2) + 32) / 50))
    
    # Cache experience tables
    _exp_tables = {}
    
    @staticmethod
    def exp_to_level(level: int, growth_rate: str = 'medium_fast') -> int:
        """
        Calculate total EXP needed to reach a level
        Uses lookup table for accuracy
        
        Args:
            level: Target level (1-100)
            growth_rate: Growth rate type
        
        Returns:
            Total EXP needed to reach that level
        """
        if level <= 1:
            return 0
        
        # Generate table if not cached
        if growth_rate not in ExpSystem._exp_tables:
            ExpSystem._exp_tables[growth_rate] = ExpSystem._generate_experience_table(growth_rate)
        
        return ExpSystem._exp_tables[growth_rate].get(level, 0)
    
    @staticmethod
    def exp_to_next_level(current_level: int, current_exp: int, growth_rate: str = 'medium_fast') -> int:
        """
        Calculate EXP needed to reach next level
        
        Args:
            current_level: Pokemon's current level
            current_exp: Pokemon's current total EXP
            growth_rate: Growth rate type
        
        Returns:
            EXP needed to reach next level
        """
        if current_level >= 100:
            return 0
        
        exp_for_next = ExpSystem.exp_to_level(current_level + 1, growth_rate)
        return max(0, exp_for_next - current_exp)
    
    @staticmethod
    def calculate_exp_gain(
        defeated_pokemon_level: int,
        defeated_pokemon_base_exp: int,
        participating_pokemon_level: int,
        is_wild: bool = True,
        is_traded: bool = False,
        is_international: bool = False,
        has_lucky_egg: bool = False,
        has_exp_share: bool = True,
        participated_in_battle: bool = True,
        use_scaled_formula: bool = True
    ) -> int:
        """
        Calculate EXP gained from defeating a Pokemon
        
        Gen V+ Scaled Formula:
        EXP = floor(floor(floor((a*b*L)/(5*s)) * (((2*L+10)^2.5)/((L+Lp+10)^2.5))) + 1) * t * e * p
        
        Where:
        a = 1.5 if trainer battle, 1.0 if wild
        b = base experience yield of defeated Pokemon
        L = level of defeated Pokemon
        Lp = level of your Pokemon
        s = 1 if participated, 2 if didn't participate but has Exp Share
        t = 1.0 (owned), 1.5 (traded), 1.7 (international trade)
        e = 1.5 if Lucky Egg, 1.0 otherwise
        p = other multipliers (we'll keep at 1.0 for now)
        
        Args:
            defeated_pokemon_level: Level of the defeated Pokemon
            defeated_pokemon_base_exp: Base EXP yield (from species data)
            participating_pokemon_level: Level of Pokemon receiving EXP
            is_wild: True if wild battle, False if trainer battle
            is_traded: Whether the Pokemon is traded (different OT)
            is_international: Whether it's an international trade (different language)
            has_lucky_egg: Whether Pokemon is holding Lucky Egg
            has_exp_share: Whether Exp Share is active
            participated_in_battle: Whether this Pokemon actually fought
            use_scaled_formula: Use Gen V+ scaled formula (default True)
        
        Returns:
            EXP gained
        """
        # Base values
        a = 1.0 if is_wild else 1.5  # Trainer battles give 1.5x
        b = defeated_pokemon_base_exp
        L = defeated_pokemon_level
        Lp = participating_pokemon_level
        
        # Participation modifier
        if participated_in_battle:
            s = 1
        else:
            if has_exp_share:
                s = 2  # Non-participants get half
            else:
                return 0  # No EXP without participating or Exp Share
        
        # Trade multipliers
        if is_international:
            t = 1.7  # International trade (6963/4096 ≈ 1.7)
        elif is_traded:
            t = 1.5  # Domestic trade
        else:
            t = 1.0  # Original trainer
        
        # Lucky Egg
        e = 1.5 if has_lucky_egg else 1.0
        
        # Other multipliers (O-Powers, Exp Charm, etc.)
        p = 1.0
        
        if use_scaled_formula:
            # Gen V+ Scaled Formula
            # This is the key part that makes lower level Pokemon gain MORE exp!
            
            # Step 1: Base calculation
            base = math.floor((a * b * L) / (5 * s))
            
            # Step 2: Level scaling factor
            # This is what makes the formula "scaled"
            # Lower level Pokemon get a HUGE boost from this
            numerator = (2 * L + 10) ** 2.5
            denominator = (L + Lp + 10) ** 2.5
            scaling = numerator / denominator
            
            # Step 3: Apply scaling and round
            scaled_exp = math.floor(base * scaling)
            
            # Step 4: Add the constant +1
            scaled_exp = scaled_exp + 1
            
            # Step 5: Apply multipliers
            final_exp = math.floor(scaled_exp * t * e * p)
            
        else:
            # Flat formula (Gen I-IV, VI)
            # Simpler but doesn't scale with level difference
            final_exp = math.floor((a * t * b * e * L) / (7 * s))
        
        return max(1, int(final_exp))  # Minimum 1 EXP
    
    @staticmethod
    def distribute_exp_to_party(
        party: List,
        defeated_pokemon,
        active_pokemon_index: int = 0,
        species_db = None,
        is_trainer_battle: bool = False
    ) -> Dict[int, int]:
        """
        Distribute EXP to entire party (Exp Share active)
        
        In Gen VI+, all participating Pokemon get full exp,
        and non-participating Pokemon get half exp if Exp Share is on.
        
        Args:
            party: List of Pokemon objects
            defeated_pokemon: The defeated Pokemon object
            active_pokemon_index: Index of Pokemon that was actively battling
            species_db: SpeciesDatabase to get base exp values
            is_trainer_battle: Whether this is a trainer battle
        
        Returns:
            Dict mapping party index to EXP gained
        """
        if not party:
            return {}
        
        # Get defeated Pokemon's data
        defeated_level = defeated_pokemon.level
        
        # Get base experience from defeated Pokemon
        if hasattr(defeated_pokemon, 'species_data'):
            defeated_base_exp = defeated_pokemon.species_data.get('base_experience', 100)
        elif species_db:
            species = species_db.get_species(defeated_pokemon.species_dex_number)
            defeated_base_exp = species.get('base_experience', 100)
        else:
            defeated_base_exp = 100  # Fallback
        
        exp_distribution = {}
        
        for idx, pokemon in enumerate(party):
            # Skip fainted Pokemon
            if pokemon.current_hp <= 0:
                continue
            
            participated = (idx == active_pokemon_index)
            
            # Check if traded (assumes Pokemon has 'original_trainer' attribute)
            is_traded = False
            is_international = False
            if hasattr(pokemon, 'original_trainer'):
                # Would need player ID comparison here
                pass
            
            exp_gained = ExpSystem.calculate_exp_gain(
                defeated_pokemon_level=defeated_level,
                defeated_pokemon_base_exp=defeated_base_exp,
                participating_pokemon_level=pokemon.level,
                is_wild=not is_trainer_battle,
                is_traded=is_traded,
                is_international=is_international,
                has_lucky_egg=False,  # TODO: Check if holding Lucky Egg
                has_exp_share=True,  # Always on in modern games
                participated_in_battle=participated,
                use_scaled_formula=True  # Use Gen V+ formula
            )
            
            exp_distribution[idx] = exp_gained
        
        return exp_distribution

    @staticmethod
    def apply_partner_bonus(exp_gained: int, pokemon) -> int:
        """Apply the partner EXP bonus if applicable."""
        is_partner = False
        try:
            is_partner = bool(getattr(pokemon, 'is_partner', False))
        except Exception:
            is_partner = False

        if not is_partner and isinstance(pokemon, dict):
            is_partner = bool(pokemon.get('is_partner'))

        if is_partner:
            return int(math.floor(exp_gained * 1.2))
        return exp_gained

    @staticmethod
    def apply_exp_and_check_levelup(
        pokemon,
        exp_gained: int,
        species_db = None,
        learnset_db = None,
        level_cap: Optional[int] = None
    ) -> Optional[LevelUpResult]:
        """
        Apply EXP to a Pokemon and check if it levels up
        
        Args:
            pokemon: Pokemon object
            exp_gained: Amount of EXP to add
            species_db: SpeciesDatabase (for growth rate)
            learnset_db: LearnsetDatabase (for move learning)
        
        Returns:
            LevelUpResult if leveled up, None otherwise
        """
        if pokemon.level >= 100:
            return None

        old_level = pokemon.level

        # Get growth rate
        if hasattr(pokemon, 'species_data'):
            growth_rate = pokemon.species_data.get('growth_rate', 'medium_fast')
        elif species_db:
            species = species_db.get_species(pokemon.species_dex_number)
            growth_rate = species.get('growth_rate', 'medium_fast')
        else:
            growth_rate = 'medium_fast'

        exp_gained = ExpSystem.apply_partner_bonus(exp_gained, pokemon)
        
        # Apply any stored EXP if the cap allows it
        stored_exp = getattr(pokemon, "stored_exp", 0)
        if stored_exp and (level_cap is None or pokemon.level < level_cap):
            exp_gained += stored_exp
            pokemon.stored_exp = 0

        # Determine cap boundary
        cap_level = min(level_cap, 100) if level_cap else 100
        cap_exp = ExpSystem.exp_to_level(cap_level, growth_rate) if cap_level else None

        # If already capped, store EXP
        if level_cap and pokemon.level >= cap_level:
            pokemon.stored_exp += exp_gained
            return None

        # Add EXP up to the cap
        if cap_exp is not None and pokemon.exp + exp_gained > cap_exp:
            overflow = pokemon.exp + exp_gained - cap_exp
            pokemon.exp = cap_exp
            pokemon.stored_exp += overflow
        else:
            pokemon.exp += exp_gained

        # Check for level up (respecting cap)
        new_level = ExpSystem._calculate_level_from_exp(pokemon.exp, growth_rate)
        if cap_level:
            new_level = min(new_level, cap_level)
        
        if new_level > old_level:
            # Level up!
            return ExpSystem._handle_levelup(
                pokemon, old_level, new_level, species_db, learnset_db
            )
        
        return None
    
    @staticmethod
    def _calculate_level_from_exp(total_exp: int, growth_rate: str) -> int:
        """
        Calculate level based on total EXP
        Uses binary search for efficiency
        """
        if total_exp <= 0:
            return 1
        
        # Generate table if not cached
        if growth_rate not in ExpSystem._exp_tables:
            ExpSystem._exp_tables[growth_rate] = ExpSystem._generate_experience_table(growth_rate)
        
        exp_table = ExpSystem._exp_tables[growth_rate]
        
        # Binary search for level
        for level in range(100, 0, -1):
            if total_exp >= exp_table[level]:
                return level
        
        return 1
    
    @staticmethod
    def _handle_levelup(
        pokemon,
        old_level: int,
        new_level: int,
        species_db = None,
        learnset_db = None
    ) -> LevelUpResult:
        """
        Handle a Pokemon leveling up
        
        - Updates level
        - Recalculates stats
        - Checks for new moves
        """
        # Update level
        pokemon.level = new_level
        
        # Store old stats
        old_stats = {
            'hp': pokemon.max_hp,
            'attack': pokemon.attack,
            'defense': pokemon.defense,
            'sp_attack': pokemon.sp_attack,
            'sp_defense': pokemon.sp_defense,
            'speed': pokemon.speed
        }
        
        # Recalculate stats
        pokemon._calculate_stats()
        
        # Calculate stat gains
        stat_gains = {
            'hp': pokemon.max_hp - old_stats['hp'],
            'attack': pokemon.attack - old_stats['attack'],
            'defense': pokemon.defense - old_stats['defense'],
            'sp_attack': pokemon.sp_attack - old_stats['sp_attack'],
            'sp_defense': pokemon.sp_defense - old_stats['sp_defense'],
            'speed': pokemon.speed - old_stats['speed']
        }
        
        # Heal HP to new max (level up healing)
        hp_difference = pokemon.max_hp - old_stats['hp']
        pokemon.current_hp = min(pokemon.max_hp, pokemon.current_hp + hp_difference)
        
        # Check for new moves
        new_moves_learned = []
        moves_available = []
        
        if learnset_db:
            # Get moves learned between old and new level
            learnset = learnset_db.get_learnset(pokemon.species_name)
            if learnset:
                level_up_moves = learnset.get('level_up_moves', [])
                
                for move_data in level_up_moves:
                    if old_level < move_data['level'] <= new_level:
                        move_id = move_data['move_id']
                        
                        # Check if Pokemon already knows this move
                        current_moves = [m['move_id'] for m in pokemon.moves]
                        if move_id not in current_moves:
                            moves_available.append({
                                'level': move_data['level'],
                                'move_id': move_id
                            })
        
        # Auto-learn moves if less than 4 moves
        current_move_ids = [m['move_id'] for m in pokemon.moves]
        for move_data in moves_available[:]:
            if len(pokemon.moves) < 4:
                # Auto-learn
                move_id = move_data['move_id']
                from database import MovesDatabase
                moves_db = MovesDatabase('data/moves.json')
                move_info = moves_db.get_move(move_id)
                
                if move_info:
                    pokemon.moves.append({
                        'move_id': move_id,
                        'pp': move_info['pp'],
                        'max_pp': move_info['pp']
                    })
                    new_moves_learned.append(move_id)
                    moves_available.remove(move_data)
        
        return LevelUpResult(
            old_level=old_level,
            new_level=new_level,
            stat_gains=stat_gains,
            new_moves_learned=new_moves_learned,
            moves_available_to_learn=moves_available
        )


class ExpShareManager:
    """
    Manages EXP Share distribution across party
    
    This class makes it easy to handle battle rewards
    """
    
    @staticmethod
    def award_exp_from_battle(
        party: List,
        defeated_pokemon,
        active_pokemon_index: int = 0,
        species_db = None,
        learnset_db = None,
        is_trainer_battle: bool = False,
        level_cap: Optional[int] = None,
        exp_multiplier: float = 1.0
    ) -> Dict[str, any]:
        """
        Award EXP to party from battle and handle level-ups
        
        Args:
            party: List of Pokemon in party
            defeated_pokemon: Pokemon that was defeated
            active_pokemon_index: Which Pokemon was actively battling
            species_db: SpeciesDatabase instance
            learnset_db: LearnsetDatabase instance
            is_trainer_battle: Whether this was a trainer battle
            exp_multiplier: Multiplier applied to all EXP gains (e.g., raid bonuses)

        Returns:
            Dict with results for each Pokemon that gained EXP
        """
        # Distribute EXP
        exp_distribution = ExpSystem.distribute_exp_to_party(
            party=party,
            defeated_pokemon=defeated_pokemon,
            active_pokemon_index=active_pokemon_index,
            species_db=species_db,
            is_trainer_battle=is_trainer_battle
        )

        if exp_multiplier != 1:
            for idx, exp_gained in list(exp_distribution.items()):
                exp_distribution[idx] = int(math.floor(exp_gained * exp_multiplier))

        results = {
            'exp_gains': {},
            'level_ups': {},
            'total_exp_awarded': sum(exp_distribution.values())
        }
        
        # Apply EXP and check for level-ups
        for idx, exp_gained in exp_distribution.items():
            pokemon = party[idx]
            
            results['exp_gains'][idx] = {
                'pokemon_name': pokemon.nickname or pokemon.species_name,
                'exp_gained': exp_gained,
                'old_exp': pokemon.exp
            }
            
            # Apply EXP
            levelup_result = ExpSystem.apply_exp_and_check_levelup(
                pokemon=pokemon,
                exp_gained=exp_gained,
                species_db=species_db,
                learnset_db=learnset_db,
                level_cap=level_cap
            )
            
            if levelup_result:
                results['level_ups'][idx] = {
                    'pokemon_name': pokemon.nickname or pokemon.species_name,
                    'result': levelup_result
                }
            
            results['exp_gains'][idx]['new_exp'] = pokemon.exp

        return results


# Example usage and testing
if __name__ == "__main__":
    print("=== Pokemon Experience System - Gen V+ Accurate ===\n")
    
    # Example 1: Level 5 Pokemon vs Level 50 Pokemon (HUGE difference with scaled formula!)
    print("Example 1: Scaled Formula Power")
    print("Level 5 Pokemon defeats Level 50 wild Pokemon (base exp 100)")
    
    exp_scaled = ExpSystem.calculate_exp_gain(
        defeated_pokemon_level=50,
        defeated_pokemon_base_exp=100,
        participating_pokemon_level=5,
        is_wild=True,
        use_scaled_formula=True
    )
    
    exp_flat = ExpSystem.calculate_exp_gain(
        defeated_pokemon_level=50,
        defeated_pokemon_base_exp=100,
        participating_pokemon_level=5,
        is_wild=True,
        use_scaled_formula=False
    )
    
    print(f"  With Gen V+ Scaled Formula: {exp_scaled} EXP")
    print(f"  With Old Flat Formula: {exp_flat} EXP")
    print(f"  Difference: {exp_scaled - exp_flat} EXP ({((exp_scaled/exp_flat - 1) * 100):.0f}% more!)")
    
    # Example 2: Same level battle
    print("\nExample 2: Same Level Battle")
    print("Level 25 Pokemon defeats Level 25 wild Pokemon (base exp 100)")
    
    exp_same = ExpSystem.calculate_exp_gain(
        defeated_pokemon_level=25,
        defeated_pokemon_base_exp=100,
        participating_pokemon_level=25,
        is_wild=True,
        use_scaled_formula=True
    )
    print(f"  EXP gained: {exp_same}")
    
    # Example 3: Trainer battle with Lucky Egg
    print("\nExample 3: Trainer Battle Bonuses")
    print("Level 30 traded Pokemon with Lucky Egg defeats Level 35 trainer Pokemon")
    
    exp_bonus = ExpSystem.calculate_exp_gain(
        defeated_pokemon_level=35,
        defeated_pokemon_base_exp=150,
        participating_pokemon_level=30,
        is_wild=False,  # Trainer battle
        is_traded=True,
        has_lucky_egg=True,
        use_scaled_formula=True
    )
    print(f"  EXP gained: {exp_bonus}")
    print(f"  Bonuses: Trainer (1.5x), Traded (1.5x), Lucky Egg (1.5x)")
    
    # Example 4: Experience tables
    print("\n=== Experience Tables ===")
    growth_rates = ['fast', 'medium_fast', 'medium_slow', 'slow', 'erratic', 'fluctuating']
    
    print("\nTotal EXP needed to reach level 100:")
    for rate in growth_rates:
        exp_100 = ExpSystem.exp_to_level(100, rate)
        print(f"  {rate:15s}: {exp_100:,}")
    
    print("\nEXP needed at various levels (Medium Fast):")
    for level in [5, 10, 20, 30, 50, 75, 100]:
        total_exp = ExpSystem.exp_to_level(level, 'medium_fast')
        if level > 1:
            prev_exp = ExpSystem.exp_to_level(level - 1, 'medium_fast')
            level_exp = total_exp - prev_exp
            print(f"  Level {level:2d}: {total_exp:,} total ({level_exp:,} for this level)")
        else:
            print(f"  Level {level:2d}: {total_exp:,} total")
