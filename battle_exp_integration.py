"""
Battle EXP Integration - SIMPLIFIED (No Progress Bars)
Clean, simple EXP display without visual bars
"""

from exp_system import ExpShareManager, ExpSystem
from typing import Dict, List, Optional
import discord
import json


class BattleExpHandler:
    """Handles EXP rewards at the end of battles - simplified version"""
    
    def __init__(self, species_db, learnset_db, player_manager, item_usage_manager=None):
        """
        Initialize the handler
        
        Args:
            species_db: SpeciesDatabase instance
            learnset_db: LearnsetDatabase instance
            player_manager: PlayerManager instance
        """
        self.species_db = species_db
        self.learnset_db = learnset_db
        self.player_manager = player_manager
        self.item_usage_manager = item_usage_manager
        self.evolution_data = getattr(item_usage_manager, 'evolution_data', {}) if item_usage_manager else {}
    
    async def award_battle_exp(
        self,
        trainer_id: int,
        party: List,
        defeated_pokemon,
        active_pokemon_index: int = 0,
        is_trainer_battle: bool = False,
        exp_multiplier: float = 1.0
    ) -> Dict:
        """
        Award EXP to party after battle victory
        
        Args:
            trainer_id: Discord user ID
            party: List of Pokemon objects
            defeated_pokemon: Pokemon that was defeated
            active_pokemon_index: Index of Pokemon that was battling
            is_trainer_battle: Whether this was a trainer battle
            exp_multiplier: Multiplier for EXP gains (e.g., raid bonus)

        Returns:
            Results dictionary with EXP gains and level-ups
        """
        # Award EXP and handle level-ups
        level_cap = None
        if self.player_manager:
            trainer = self.player_manager.get_player(trainer_id)
            if trainer:
                level_cap = self.player_manager.get_level_cap_for_trainer(trainer)

        results = ExpShareManager.award_exp_from_battle(
            party=party,
            defeated_pokemon=defeated_pokemon,
            active_pokemon_index=active_pokemon_index,
            species_db=self.species_db,
            learnset_db=self.learnset_db,
            is_trainer_battle=is_trainer_battle,
            level_cap=level_cap,
            exp_multiplier=exp_multiplier
        )
        
        # Check for evolution readiness
        results['evolution_ready'] = {}
        for idx in results['level_ups'].keys():
            pokemon = party[idx]
            if self._can_evolve(pokemon):
                results['evolution_ready'][idx] = {
                    'pokemon_name': pokemon.nickname or pokemon.species_name,
                    'species_name': pokemon.species_name,
                    'level': pokemon.level
                }
        
        # Update all Pokemon in database
        print(f"[DEBUG] Updating {len(results['exp_gains'])} Pokemon in database...")
        
        for idx in results['exp_gains'].keys():
            pokemon = party[idx]
            
            # Check if Pokemon has a pokemon_id attribute
            if hasattr(pokemon, 'pokemon_id'):
                pokemon_id = pokemon.pokemon_id
            else:
                # Fallback: Find by party position
                all_pokemon = self.player_manager.get_all_pokemon(trainer_id)
                pokemon_id = None
                
                for db_pokemon in all_pokemon:
                    if (db_pokemon.get('in_party') and 
                        db_pokemon.get('party_position') == idx):
                        pokemon_id = db_pokemon['pokemon_id']
                        break
            
            if not pokemon_id:
                print(f"[ERROR] Could not find Pokemon at position {idx}")
                continue
            
            # IMPORTANT: Update ALL fields that changed
            updates = {
                'exp': pokemon.exp,
                'level': pokemon.level,
                'current_hp': pokemon.current_hp,
                'max_hp': pokemon.max_hp,
                'moves': json.dumps(pokemon.moves),
                'stored_exp': getattr(pokemon, 'stored_exp', 0)
            }
            
            print(f"[DEBUG] Updating {pokemon.species_name}: Level {pokemon.level}, EXP {pokemon.exp}, HP {pokemon.current_hp}/{pokemon.max_hp}")
            
            # Update directly via database
            success = self.player_manager.db.update_pokemon(pokemon_id, updates)
            
            if success:
                print(f"[SUCCESS] Updated {pokemon.species_name} in database")
            else:
                print(f"[ERROR] Failed to update {pokemon.species_name}")
        
        return results
    
    def _can_evolve(self, pokemon) -> bool:
        """
        Check if a Pokemon is ready to evolve
        
        Args:
            pokemon: Pokemon object to check
        
        Returns:
            True if can evolve, False otherwise
        """
        # Prefer comprehensive evolution data from ItemUsageManager
        evolution = self.evolution_data.get(getattr(pokemon, 'species_name', '').lower())
        if evolution:
            if evolution.get('method') != 'level':
                return False

            required_level = evolution.get('level')
            if required_level is None or pokemon.level < required_level:
                return False

            required_move = evolution.get('move')
            if required_move:
                moves = getattr(pokemon, 'moves', []) or []
                move_ids = []
                for move in moves:
                    if isinstance(move, dict):
                        move_ids.append(move.get('move_id'))
                    else:
                        move_ids.append(getattr(move, 'move_id', None))

                if required_move not in move_ids:
                    return False

            return True

        # Fallback legacy mappings for older datasets
        level_evolutions = {
            'bulbasaur': 16, 'ivysaur': 32,
            'charmander': 16, 'charmeleon': 36,
            'squirtle': 16, 'wartortle': 36,
            'pidgey': 18, 'pidgeotto': 36,
            'rattata': 20,
            'caterpie': 7, 'metapod': 10,
            'weedle': 7, 'kakuna': 10,
            'spearow': 20,
            'ekans': 22,
            'sandshrew': 22,
        }

        species_name_lower = pokemon.species_name.lower()
        required_level = level_evolutions.get(species_name_lower)

        return bool(required_level and pokemon.level >= required_level)
    
    def create_exp_embed(
        self,
        results: Dict,
        party: List,
        defeated_pokemon
    ) -> discord.Embed:
        """
        Create a Discord embed showing EXP gains and level-ups (NO PROGRESS BARS)
        
        Args:
            results: Results from award_battle_exp()
            party: List of Pokemon objects
            defeated_pokemon: The defeated Pokemon
        
        Returns:
            Discord Embed (simple, clean format)
        """
        embed = discord.Embed(
            title="⭐ Battle Victory!",
            description=f"Defeated {defeated_pokemon.species_name} (Lv. {defeated_pokemon.level})!",
            color=discord.Color.gold()
        )
        
        # Show EXP gains - SIMPLE FORMAT, NO BARS
        exp_text = ""
        for idx, exp_data in results['exp_gains'].items():
            pokemon_name = exp_data['pokemon_name']
            exp_gained = exp_data['exp_gained']
            exp_text += f"**{pokemon_name}** gained **{exp_gained} EXP**!\n"
        
        if exp_text:
            embed.add_field(name="💫 Experience Gained", value=exp_text, inline=False)
        
        # Show level-ups
        if results['level_ups']:
            for idx, levelup_data in results['level_ups'].items():
                pokemon_name = levelup_data['pokemon_name']
                result = levelup_data['result']
                
                # Simple level up message
                levelup_text = f"**Level {result.old_level} → {result.new_level}!**\n\n"
                
                # Show stat gains
                levelup_text += "**Stat Gains:**\n"
                levelup_text += f"• HP: +{result.stat_gains['hp']}\n"
                levelup_text += f"• Attack: +{result.stat_gains['attack']}\n"
                levelup_text += f"• Defense: +{result.stat_gains['defense']}\n"
                levelup_text += f"• Sp. Atk: +{result.stat_gains['sp_attack']}\n"
                levelup_text += f"• Sp. Def: +{result.stat_gains['sp_defense']}\n"
                levelup_text += f"• Speed: +{result.stat_gains['speed']}\n"
                
                # Show moves learned (deduplicated)
                if result.new_moves_learned:
                    levelup_text += "\n**Moves Learned:**\n"
                    unique_moves = []
                    for move_id in result.new_moves_learned:
                        if move_id not in unique_moves:
                            unique_moves.append(move_id)
                    for move_id in unique_moves:
                        move_name = move_id.replace('_', ' ').title()
                        levelup_text += f"⚔️ **{move_name}**\n"

                # Show moves available to learn (already knows 4 moves)
                if result.moves_available_to_learn:
                    levelup_text += "\n**Wants to learn:**\n"
                    for move_data in result.moves_available_to_learn:
                        move_name = move_data['move_id'].replace('_', ' ').title()
                        levelup_text += f"• {move_name}\n"
                    levelup_text += "\n*Already knows 4 moves!*\n"
                embed.add_field(
                    name=f"📈 {pokemon_name} leveled up!",
                    value=levelup_text,
                    inline=False
                )
        
        # Show evolution readiness
        if results.get('evolution_ready'):
            evo_text = ""
            for idx, evo_data in results['evolution_ready'].items():
                pokemon_name = evo_data['pokemon_name']
                evo_text += f"✨ **{pokemon_name}** can now evolve!\n"
            
            if evo_text:
                evo_text += "\n*Use the Evolution menu to evolve your Pokémon!*"
                embed.add_field(
                    name="🌟 Evolution Ready!",
                    value=evo_text,
                    inline=False
                )
        
        return embed


# Quick test
if __name__ == "__main__":
    print("✅ Battle EXP Integration loaded! (SIMPLIFIED - No Progress Bars)")
    print("\nFeatures:")
    print("✨ Clean EXP gain display")
    print("⚔️ Move learning notifications")
    print("🌟 Evolution readiness alerts")
    print("📊 Detailed level-up stats")
    print("💾 Proper database saving")