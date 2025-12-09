"""
Anime Battle Engine - Phase-based natural language battles with AI narration
Uses OpenAI GPT-4o-mini for generating battle narration

ENHANCED with full move effects, status conditions, and stat stages!
"""

import re
import random
import json
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from ability_handler import AbilityHandler


# Import enhanced battle systems
try:
    from enhanced_calculator import EnhancedDamageCalculator
    from status_conditions import StatusConditionManager
    ENHANCED_SYSTEMS_AVAILABLE = True
except ImportError:
    ENHANCED_SYSTEMS_AVAILABLE = False
    print("⚠️ Enhanced battle systems not found. Using basic damage calculation.")
    print("   To enable: Copy status_conditions.py, effect_handler.py, and enhanced_calculator.py to this directory.")

# Try to import openai - handle both old and new versions
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("⚠️ OpenAI not installed. AI narration will use fallback templates.")
    print("   To install: pip install openai")


@dataclass
class PokemonProxy:
    """Lightweight proxy for Pokemon data to avoid circular imports"""
    species_name: str
    level: int
    current_hp: int
    max_hp: int
    attack: int
    defense: int
    sp_attack: int
    sp_defense: int
    speed: int
    moves: List
    species_data: Dict


@dataclass
class BattleAction:
    """Represents a single battle action"""
    action_type: str  # 'move', 'dodge', 'block', 'switch', 'item', 'flee', 'take_hit'
    move_id: Optional[str] = None
    target_position: Optional[int] = None
    item_id: Optional[str] = None
    switch_to_position: Optional[int] = None


@dataclass
class BattleState:
    """Tracks the current state of a battle"""
    battle_id: str
    trainer_id: int
    trainer_pokemon: List  # Active party (up to 6) - any Pokemon-like objects
    wild_pokemon: Optional[object]  # For wild battles - any Pokemon-like object
    trainer_active_position: int  # Which slot is currently active (0-5)
    wild_active: bool  # Whether wild Pokemon is active
    turn_number: int
    battle_log: List[str]  # History of battle events
    is_over: bool = False
    winner: Optional[str] = None  # 'trainer', 'wild', 'fled'
    
    # Phase system
    phase: str = 'WAITING_ACTION'  # WAITING_ACTION, WAITING_REACTION, RESOLVING
    initiative_holder: str = None  # 'trainer' or 'wild'
    pending_action: Optional[BattleAction] = None
    pending_actor: Optional[object] = None
    
    # Dodge tracking
    dodge_penalties: Dict = field(default_factory=dict)  # pokemon_id -> penalty_percent
    player_message: Optional[str] = None
    
    # NEW FIELDS FOR ABILITIES:
    weather: Optional[str] = None  # 'sandstorm', 'rain', 'sun', 'snow', 'hail'
    weather_turns: int = 0
    terrain: Optional[str] = None  # 'electric', 'grassy', 'psychic', 'misty'
    terrain_turns: int = 0


class CommandParser:
    """Parses natural language battle commands"""
    
    # Common move command patterns
    MOVE_PATTERNS = [
        r'(?:use|attack with|hit (?:them |it )?with)\s+([a-z\s-]+)',
        r'([a-z\s-]+)(?:\s+attack|\s+move)?!*$',
        r'^([a-z\s-]+)!*$'
    ]
    
    # Dodge patterns
    DODGE_PATTERNS = [
        r'dodge',
        r'evade',
        r'avoid (?:it|the attack|that)',
        r'get out of the way'
    ]
    
    # Block patterns
    BLOCK_PATTERNS = [
        r'block',
        r'defend',
        r'guard',
        r'brace'
    ]
    
    def __init__(self, moves_database):
        """Initialize with moves database for fuzzy matching"""
        self.moves_db = moves_database
    
    def parse_command(self, text: str, pokemon, require_quotes: bool = True) -> Optional[BattleAction]:
        """
        Parse a natural language command into a BattleAction
        Supports RP-style posts with dialogue!
        
        Args:
            text: The user's text input (can be a full RP post)
            pokemon: The active Pokemon (to validate moves) - any object with .moves
            require_quotes: If True, command must be in quotes (single or double)
            
        Returns:
            BattleAction or None if couldn't parse
        """
        original_text = text
        
        # RP MODE: Extract dialogue from quotes (single or double, including curly quotes from mobile)
        if require_quotes:
            # Try to find dialogue in quotes (prioritize single quotes for RP)
            # Patterns: 'Growlithe, Tackle!' or "Growlithe, use Tackle!"
            # ALSO HANDLES CURLY QUOTES from mobile keyboards: " " ' '
            dialogue_patterns = [
                r"'([^']+)'",  # Single quotes (RP dialogue)
                r'"([^"]+)"',  # Double quotes (straight)
                r'[\u201c\u201d]([^\u201c\u201d]+)[\u201c\u201d]',  # Curly double quotes (mobile/smart keyboards)
                r'[\u2018\u2019]([^\u2018\u2019]+)[\u2018\u2019]',  # Curly single quotes (mobile/smart keyboards)
            ]
            
            dialogue_text = None
            for pattern in dialogue_patterns:
                match = re.search(pattern, text)
                if match:
                    dialogue_text = match.group(1)
                    break
            
            if not dialogue_text:
                return None
            
            text = dialogue_text
        
        text_lower = text.lower().strip()
        
        # PRIORITY 1: Check for bold move names (**Tackle**)
        bold_pattern = r'\*\*([^*]+)\*\*'
        bold_match = re.search(bold_pattern, text, re.IGNORECASE)
        if bold_match:
            move_name = bold_match.group(1).strip()
            matched_move = self._fuzzy_match_move(move_name, pokemon.moves)
            if matched_move:
                return BattleAction(
                    action_type='move',
                    move_id=matched_move['move_id']
                )
        
        # PRIORITY 2: RP-style commands (Pokemon name + move)
        # Patterns: "Growlithe, Tackle!", "Pikachu, use Thunderbolt!", "Use Tackle!"
        rp_move_patterns = [
            r'(?:use|attack with)\s+([a-z\s-]+?)(?:!+)?$',  # "use Tackle!"
            r',\s*([a-z\s-]+?)(?:!+)?$',  # "Growlithe, Tackle!"
            r'(?:use|go)\s+([a-z\s-]+?)(?:!+)?$',  # "go Tackle!"
        ]
        
        for pattern in rp_move_patterns:
            match = re.search(pattern, text_lower)
            if match:
                move_name = match.group(1).strip()
                matched_move = self._fuzzy_match_move(move_name, pokemon.moves)
                if matched_move:
                    return BattleAction(
                        action_type='move',
                        move_id=matched_move['move_id']
                    )
        
        # PRIORITY 3: Check for dodge
        for pattern in self.DODGE_PATTERNS:
            if re.search(pattern, text_lower):
                return BattleAction(action_type='dodge')
        
        # PRIORITY 4: Check for block
        for pattern in self.BLOCK_PATTERNS:
            if re.search(pattern, text_lower):
                return BattleAction(action_type='block')
        
        # PRIORITY 5: Search for any of the Pokemon's move names directly in the text
        # This handles cases like: "Alright, now we've gottem. Garchomp, Dragon Tail!!"
        # Even with surrounding RP text, it will find "Dragon Tail" or "Dragon-Tail"
        for move in pokemon.moves:
            move_data = self.moves_db.get_move(move['move_id'])
            if move_data:
                move_name = move_data['name'].lower()
                # Try both with spaces and hyphens
                move_patterns = [
                    move_name,
                    move_name.replace(' ', '-'),
                    move_name.replace('-', ' '),
                    move_name.replace(' ', ''),  # squished together
                ]
                
                for pattern in move_patterns:
                    if pattern in text_lower:
                        return BattleAction(
                            action_type='move',
                            move_id=move['move_id']
                        )
        
        
        # PRIORITY 6: Try generic extraction patterns as fallback
        for pattern in self.MOVE_PATTERNS:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                move_name = match.group(1).strip()
                
                # Try to find matching move in Pokemon's moveset
                matched_move = self._fuzzy_match_move(move_name, pokemon.moves)
                
                if matched_move:
                    return BattleAction(
                        action_type='move',
                        move_id=matched_move['move_id']
                    )
        
        return None
    
    def _fuzzy_match_move(self, text: str, pokemon_moves: List) -> Optional:
        """
        Fuzzy match a move name against Pokemon's moveset
        
        Handles:
        - Exact matches
        - Case-insensitive matches
        - Partial matches
        - Common misspellings
        """
        text = text.lower().replace('-', ' ').replace('_', ' ')
        
        # Try exact match first
        for move in pokemon_moves:
            move_data = self.moves_db.get_move(move['move_id'])
            move_name = move_data['name'].lower().replace('-', ' ')
            
            if text == move_name:
                return move
        
        # Try partial match (text is contained in move name or vice versa)
        for move in pokemon_moves:
            move_data = self.moves_db.get_move(move['move_id'])
            move_name = move_data['name'].lower().replace('-', ' ')
            
            if text in move_name or move_name in text:
                return move
        
        # Try word-by-word match (for moves like "extreme speed" vs "extremespeed")
        text_words = set(text.split())
        for move in pokemon_moves:
            move_data = self.moves_db.get_move(move['move_id'])
            move_name = move_data['name'].lower().replace('-', ' ')
            move_words = set(move_name.split())
            
            if text_words == move_words:
                return move
        
        return None


class DamageCalculator:
    """Calculates Pokemon damage using Gen 8+ formula"""
    
    def __init__(self, type_chart, moves_db):
        self.type_chart = type_chart
        self.moves_db = moves_db
    
    def calculate_damage(
        self,
        attacker,  # Any Pokemon-like object
        defender,  # Any Pokemon-like object
        move_id: str,
        is_blocked: bool = False,
        weather: Optional[str] = None,
        terrain: Optional[str] = None
    ) -> Tuple[int, bool, float]:
        """
        Calculate damage dealt by a move
        
        Args:
            is_blocked: If True, damage is reduced by 50%
        
        Returns:
            (damage, is_critical, effectiveness)
        """
        move_data = self.moves_db.get_move(move_id)
        
        # Status moves don't deal damage
        if move_data['category'] == 'status':
            return 0, False, 1.0
        
        # Get attack and defense stats
        if move_data['category'] == 'physical':
            attack = attacker.attack
            defense = defender.defense
        else:  # special
            attack = attacker.sp_attack
            defense = defender.sp_defense
        
        # Base damage formula
        level = attacker.level
        power = move_data['power']
        
        # Critical hit check
        crit_stage = move_data.get('crit_rate', 1)
        crit_chance = [1/24, 1/8, 1/2, 1/1][min(crit_stage - 1, 3)]
        is_critical = random.random() < crit_chance
        
        if is_critical:
            # Crits ignore defense boosts and attack drops
            damage = ((2 * level / 5 + 2) * power * attack / defense / 50 + 2) * 1.5
        else:
            damage = (2 * level / 5 + 2) * power * attack / defense / 50 + 2
        
        # STAB (Same Type Attack Bonus)
        move_type = move_data['type']
        attacker_types = attacker.species_data['types']
        if move_type in attacker_types:
            damage *= 1.5
        
        # Type effectiveness
        effectiveness = self._get_type_effectiveness(move_type, defender.species_data['types'])
        damage *= effectiveness
        
        # Random factor (0.85 to 1.0)
        damage *= random.uniform(0.85, 1.0)
        
        # Block reduces damage by 50%
        if is_blocked:
            damage *= 0.5
        
        # Convert to int
        damage = max(1, int(damage))
        
        return damage, is_critical, effectiveness
    
    def _get_type_effectiveness(self, attack_type: str, defender_types: List[str]) -> float:
        """Calculate type effectiveness multiplier"""
        multiplier = 1.0
        
        for def_type in defender_types:
            # Get effectiveness from type chart
            if attack_type in self.type_chart and def_type in self.type_chart[attack_type]:
                multiplier *= self.type_chart[attack_type][def_type]
        
        return multiplier


class DodgeSystem:
    """Handles dodge/evasion mechanics with penalties and recovery"""
    
    def __init__(self):
        self.consecutive_dodges = {}  # pokemon_id -> number of consecutive dodges
    
    def can_dodge(self, pokemon, battle_state: BattleState) -> Tuple[bool, str, bool]:
        """
        Check if a Pokemon can successfully dodge
        
        Returns:
            (success, reason_message, gained_initiative)
        """
        pokemon_id = id(pokemon)
        consecutive = self.consecutive_dodges.get(pokemon_id, 0)
        
        # Base dodge chance based on Speed stat
        base_chance = min(0.7, 0.3 + (pokemon.speed - 50) / 200)
        
        # Apply penalty: -20% per consecutive dodge
        penalty = consecutive * 0.20
        final_chance = max(0.1, base_chance - penalty)  # Minimum 10% chance
        
        success = random.random() < final_chance
        gained_initiative = False
        
        if success:
            self.consecutive_dodges[pokemon_id] = consecutive + 1
            gained_initiative = True  # Successful dodge grants initiative next turn!
            
            if consecutive > 0:
                return True, f"{pokemon.species_name} dodged again, but it's getting harder!", gained_initiative
            else:
                return True, f"{pokemon.species_name}'s speed allowed it to dodge!", gained_initiative
        else:
            self.consecutive_dodges[pokemon_id] = 0
            
            if consecutive > 0:
                return False, f"{pokemon.species_name} couldn't dodge again!", gained_initiative
            else:
                return False, f"{pokemon.species_name} wasn't fast enough to dodge!", gained_initiative
    
    def recover_penalty(self, pokemon):
        """Recover dodge penalty by 10% (called each turn Pokemon doesn't dodge)"""
        pokemon_id = id(pokemon)
        if pokemon_id in self.consecutive_dodges and self.consecutive_dodges[pokemon_id] > 0:
            self.consecutive_dodges[pokemon_id] = max(0, self.consecutive_dodges[pokemon_id] - 0.5)  # -10% recovery
    
    def reset_consecutive(self, pokemon):
        """Reset consecutive dodge counter (after using an attack)"""
        pokemon_id = id(pokemon)
        self.consecutive_dodges[pokemon_id] = 0


class AIBattleNarrator:
    """Generates dramatic battle narration using OpenAI"""
    
    def __init__(self, api_key: str):
        """Initialize with OpenAI API key"""
        self.api_key = api_key
        openai.api_key = api_key
        self.model = "gpt-4o-mini"  # Cheapest option
    
    async def narrate_action_start(
        self,
        actor,
        move_id: str,
        target,
        moves_db,
        player_message: Optional[str] = None
    ) -> str:
        """
        Generate narration for an action STARTING (no resolution yet)
        
        Returns:
            A 1-2 sentence description of the action beginning
        """
        if not OPENAI_AVAILABLE or not self.api_key:
            move_data = moves_db.get_move(move_id)
            return f"{actor.species_name} is preparing to use {move_data['name']}!"
        
        move_data = moves_db.get_move(move_id)
        
        # Determine narration length based on player's message
        base_length = 20  # Default short
        max_tokens = 40
        
        if player_message:
            clean_message = player_message.replace('**', '').replace('"', '')
            word_count = len(clean_message.split())
            
            # Scale response to match player's effort
            if word_count > 50:  # Long RP post (5+ sentences)
                base_length = 50
                max_tokens = 100
            elif word_count > 25:  # Medium RP post (3-4 sentences)
                base_length = 35
                max_tokens = 70
            # else: keep short (1-2 sentences)
            
            player_context = f"\nTrainer's message ({word_count} words): \"{clean_message}\""
        else:
            player_context = ""
        
        prompt = f"""You are a Pokemon battle narrator. Describe the START of this attack.

Context:
- {actor.species_name} is using {move_data['name']}
- Target: {target.species_name}{player_context}

LENGTH REQUIREMENT: Write approximately {base_length} words.
- If trainer wrote a short command: 1-2 sentences (~20 words)
- If trainer wrote a medium RP post: 2-3 sentences (~35 words)
- If trainer wrote a long RP post: 3-4 sentences (~50 words)

CRITICAL RULES: 
- MATCH the length to the trainer's effort
- Use {actor.species_name}'s name, not "the Pokemon"
- Show the WINDUP only, not the result
- BANNED PHRASES (NEVER USE THESE):
  * "muscles coiling" or "muscles coiled"
  * "like a spring" or "like springs"
  * "fierce determination" or "fierce resolve"
  * "unwavering determination"
  * "power surged" or "power surge"
  * "determination burning" or "determination ignited"
  * "tightly wound"
  * Any phrase with "coiling" or "coiled"
  * Any spring/coil comparisons
- Be CREATIVE and VARIED - use completely different descriptions each time!

Good examples:
- Short: "{actor.species_name}'s eyes flashed with intensity!"
- Medium: "{actor.species_name} shifted its stance, energy rippling across its body. The air grew tense!"
- Long: "{actor.species_name} focused intently on its target. Its body thrummed with barely contained energy as it prepared to strike. The battlefield fell silent, anticipating the clash!"

Write the narration NOW (remember: NO banned phrases):"""
        
        try:
            response = await self._call_openai(prompt, max_tokens=max_tokens)
            return response
        except Exception as e:
            print(f"⚠️ OpenAI API error: {e}")
            return f"{actor.species_name} is preparing to use {move_data['name']}!"
    
    async def narrate_resolution(
        self,
        attacker,
        defender,
        attack_action: BattleAction,
        defend_action: BattleAction,
        attack_damage: int,
        is_critical: bool,
        effectiveness: float,
        dodged: bool,
        blocked: bool,
        missed: bool,
        defender_fainted: bool,
        moves_db
    ) -> str:
        """
        Generate narration for the RESOLUTION of both actions
        
        Returns:
            A 2-3 sentence description of what happened
        """
        if not OPENAI_AVAILABLE or not self.api_key:
            return self._fallback_resolution(attacker, defender, attack_action, defend_action, 
                                            attack_damage, dodged, blocked, missed, defender_fainted, moves_db)
        
        attack_move = moves_db.get_move(attack_action.move_id)
        
        # Build context
        outcome = "missed completely" if missed else (
            "was dodged" if dodged else (
                "was blocked but still dealt damage" if blocked else "connected"
            )
        )
        
        defend_text = ""
        if defend_action.action_type == 'dodge':
            defend_text = f"\n- {defender.species_name} attempted to dodge"
        elif defend_action.action_type == 'block':
            defend_text = f"\n- {defender.species_name} tried to block"
        elif defend_action.action_type == 'move':
            defend_move = moves_db.get_move(defend_action.move_id)
            defend_text = f"\n- {defender.species_name} countered with {defend_move['name']}"
        
        faint_context = ""
        if defender_fainted:
            faint_context = f"\n- {defender.species_name} FAINTED from this hit!"
        
        # Determine target length
        if defender_fainted:
            target_words = "30-40"  # Slightly longer for dramatic faint
            max_tokens = 60
        elif dodged or missed:
            target_words = "20-25"  # Shorter for dodge/miss
            max_tokens = 40
        else:
            target_words = "25-30"  # Normal hit
            max_tokens = 50
        
        prompt = f"""Pokemon battle narrator. Describe the RESULT of this attack.

What happened:
- {attacker.species_name}'s {attack_move['name']} {outcome}
- Damage: {attack_damage} HP
- {"CRITICAL HIT!" if is_critical else ""}
- {self._get_effectiveness_text(effectiveness)}{faint_context}
- Defender HP remaining: {defender.current_hp}/{defender.max_hp}

CRITICAL RULES:
1. Write approximately {target_words} words
2. ALWAYS use Pokemon NAMES ("{attacker.species_name}", "{defender.species_name}")
3. {"ONLY IF defender_fainted is TRUE: Show them fainting/collapsing/defeated" if defender_fainted else "IMPORTANT: Defender is STILL CONSCIOUS! Do NOT say they fainted, collapsed, defeated, or gave up!"}
4. BANNED PHRASES (never use these):
   - "muscles coiling"
   - "like a spring"
   - "fierce determination" 
   - "unwavering determination"
   - "power surged"
   - "determination burning"
   - "determination ignited"
   - Any phrase with "coiling"
   - Any phrase comparing to springs/coils
5. Be creative and VARIED - use completely different descriptions each time

{"Good examples (defender still fighting):" if not defender_fainted else "Good examples (defender fainted):"}
{
  "- The attack connected! " + defender.species_name + " staggered but stayed on its feet!" if not defender_fainted else 
  "- The blow landed with crushing finality! " + defender.species_name + " collapsed, unable to battle!"
}
{
  "- " + attacker.species_name + "'s strike hit its mark! " + defender.species_name + " reeled from the impact!" if not defender_fainted else
  "- The attack was too much! " + defender.species_name + " fell, defeated!"
}

Write the narration now:"""
        
        try:
            response = await self._call_openai(prompt, max_tokens=max_tokens)
            return response
        except Exception as e:
            print(f"⚠️ OpenAI API error: {e}")
            return self._fallback_resolution(attacker, defender, attack_action, defend_action,
                                            attack_damage, dodged, blocked, missed, moves_db)
    
    async def _call_openai(self, prompt: str, max_tokens: int) -> str:
        """Call OpenAI API with error handling"""
        try:
            response = openai.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a Pokemon battle narrator. Be dramatic, concise, and EXTREMELY VARIED. NEVER reuse phrases like 'muscles coiling' or 'like a spring'. Every narration must be completely unique and creative."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=1.4,  # Higher for more creativity
                presence_penalty=0.6  # Discourage repetition
            )
            return response.choices[0].message.content.strip()
        except AttributeError:
            # Fall back to old API
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a Pokemon battle narrator. Be dramatic, concise, and EXTREMELY VARIED. NEVER reuse phrases."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=1.4,
                presence_penalty=0.6
            )
            return response.choices[0].message['content'].strip()
    
    def _get_effectiveness_text(self, effectiveness: float) -> str:
        """Convert effectiveness multiplier to text"""
        if effectiveness == 0:
            return "It had no effect..."
        elif effectiveness < 0.5:
            return "It's not very effective..."
        elif effectiveness < 1:
            return "It's not very effective..."
        elif effectiveness == 1:
            return ""
        elif effectiveness < 2:
            return "It's super effective!"
        else:
            return "It's super effective!"
    
    def _fallback_resolution(self, attacker, defender, attack_action, defend_action,
                            damage, dodged, blocked, missed, defender_fainted, moves_db) -> str:
        """Fallback narration if API fails"""
        attack_move = moves_db.get_move(attack_action.move_id)
        
        if missed:
            return f"{attacker.species_name}'s {attack_move['name']} missed!"
        elif dodged:
            return f"{defender.species_name} dodged {attacker.species_name}'s {attack_move['name']}!"
        elif blocked:
            return f"{defender.species_name} blocked some of the damage from {attack_move['name']}!"
        elif defender_fainted:
            return f"{attacker.species_name}'s {attack_move['name']} hit {defender.species_name} for {damage} damage! {defender.species_name} fainted!"
        else:
            return f"{attacker.species_name}'s {attack_move['name']} hit {defender.species_name} for {damage} damage!"


class AnimeBattleEngine:
    """Main battle engine for phase-based anime-style battles"""
    
    def __init__(self, type_chart, moves_db, api_key: str):
        """
        Initialize the battle engine
        
        Args:
            type_chart: Type effectiveness data
            moves_db: MovesDatabase instance
            api_key: OpenAI API key
        """
        self.parser = CommandParser(moves_db)
        
        # Use enhanced calculator if available, otherwise fallback to basic
        if ENHANCED_SYSTEMS_AVAILABLE:
            self.calculator = EnhancedDamageCalculator(moves_db, type_chart)
            self.enhanced_mode = True
            print("✨ Enhanced battle systems enabled! (Status, effects, stat stages)")
        else:
            self.calculator = DamageCalculator(type_chart, moves_db)
            self.enhanced_mode = False
        
        self.dodge_system = DodgeSystem()
        self.narrator = AIBattleNarrator(api_key)
        self.moves_db = moves_db
        
        self.ability_handler = AbilityHandler()
        print("✨ Ability system enabled!")  
        
        self.active_battles = {}  # battle_id -> BattleState
    
    def start_wild_battle(self, trainer_id: int, trainer_pokemon: List, wild_pokemon) -> str:
        """
        Start a new wild Pokemon battle
        
        Args:
            trainer_id: Discord user ID
            trainer_pokemon: List of Pokemon objects (any type with required attributes)
            wild_pokemon: Wild Pokemon object (any type with required attributes)
        
        Returns:
            battle_id
        """
        import uuid
        battle_id = str(uuid.uuid4())
        
        # Determine who has initiative (based on speed)
        trainer_active = trainer_pokemon[0]
        initiative_holder = 'trainer' if trainer_active.speed >= wild_pokemon.speed else 'wild'
        
        battle_state = BattleState(
            battle_id=battle_id,
            trainer_id=trainer_id,
            trainer_pokemon=trainer_pokemon,
            wild_pokemon=wild_pokemon,
            trainer_active_position=0,  # First Pokemon is active
            wild_active=True,
            turn_number=1,
            battle_log=[],
            phase='WAITING_ACTION',
            initiative_holder=initiative_holder,
            weather=None,  # NEW
            weather_turns=0,  # NEW
            terrain=None,  # NEW
            terrain_turns=0  # NEW
        )
        
        # NEW: Trigger entry abilities
        entry_messages = []
        
        # Trainer's Pokemon enters first
        trainer_abilities = self.ability_handler.trigger_on_entry(trainer_active, battle_state)
        entry_messages.extend(trainer_abilities)
        
        # Wild Pokemon enters second
        wild_abilities = self.ability_handler.trigger_on_entry(wild_pokemon, battle_state)
        entry_messages.extend(wild_abilities)
        
        # Add to battle log
        battle_state.battle_log.extend(entry_messages)
        
        self.active_battles[battle_id] = battle_state
        
        # Return both battle_id and entry messages for display
        return battle_id
    
    def get_initiative_info(self, battle_id: str) -> Dict:
        """Get info about who has initiative"""
        battle = self.active_battles.get(battle_id)
        if not battle:
            return {"error": "Battle not found"}
        
        trainer_pokemon = battle.trainer_pokemon[battle.trainer_active_position]
        wild_pokemon = battle.wild_pokemon
        
        return {
            "initiative_holder": battle.initiative_holder,
            "trainer_speed": trainer_pokemon.speed,
            "wild_speed": wild_pokemon.speed,
            "phase": battle.phase
        }
    
    async def process_action(self, battle_id: str, trainer_command: str) -> Dict:
        """
        Process a player action (either initiative or reaction)
        
        Args:
            battle_id: The battle to process
            trainer_command: Natural language command from trainer (must be in quotes)
            
        Returns:
            Dict with action results
        """
        battle = self.active_battles.get(battle_id)
        if not battle or battle.is_over:
            return {"error": "Battle not found or already over"}
        
        trainer_pokemon = battle.trainer_pokemon[battle.trainer_active_position]
        wild_pokemon = battle.wild_pokemon
        
        # Parse trainer command (requires quotes)
        trainer_action = self.parser.parse_command(trainer_command, trainer_pokemon, require_quotes=False)
        
        if not trainer_action:
            available_moves = [self.moves_db.get_move(m['move_id'])['name'] for m in trainer_pokemon.moves[:4]]
            return {
                "error": "⚠️ Put your command in quotes!",
                "hint": f'RP Examples: "Growlithe, use {available_moves[0]}!" or "Dodge!" (Curly quotes " " work too!)'
            }
        
        # Store player message for narration
        battle.player_message = trainer_command
        
        # Handle based on current phase
        if battle.phase == 'WAITING_ACTION':
            # This is the initiative action
            if battle.initiative_holder == 'trainer':
                # Player acts first, store action and wait for wild response
                return await self._handle_trainer_initiative(battle, trainer_action)
            else:
                # Wild acts first, player is reacting
                # This shouldn't happen - wild should act automatically
                return {"error": "Waiting for wild Pokemon to act first..."}
        
        elif battle.phase == 'WAITING_REACTION':
            # Player is reacting to wild Pokemon's action
            return await self._handle_trainer_reaction(battle, trainer_action)
        
        else:
            return {"error": "Battle is processing, please wait..."}
    
    async def _handle_trainer_initiative(self, battle: BattleState, trainer_action: BattleAction) -> Dict:
        """
        Handle when trainer has initiative and acts first
        
        Flow:
        1. Show trainer action starting (no result)
        2. Wild Pokemon reacts (AI decides)
        3. Resolve both actions
        """
        trainer_pokemon = battle.trainer_pokemon[battle.trainer_active_position]
        wild_pokemon = battle.wild_pokemon
        
        # Generate narration for action starting
        if trainer_action.action_type == 'move':
            action_narration = await self.narrator.narrate_action_start(
                actor=trainer_pokemon,
                move_id=trainer_action.move_id,
                target=wild_pokemon,
                moves_db=self.moves_db,
                player_message=battle.player_message
            )
        else:
            action_narration = f"{trainer_pokemon.species_name} is preparing to {trainer_action.action_type}!"
        
        # Wild Pokemon reacts (AI decision)
        wild_action = self._wild_pokemon_ai_react(wild_pokemon, trainer_action)
        
        # Now resolve both actions
        resolution = await self._resolve_turn(battle, trainer_pokemon, trainer_action, wild_pokemon, wild_action)
        
        return {
            "phase": "initiative",
            "action_narration": action_narration,
            "resolution": resolution,
            "battle_over": battle.is_over,
            "winner": battle.winner
        }
    
    async def _handle_trainer_reaction(self, battle: BattleState, trainer_action: BattleAction) -> Dict:
        """
        Handle when trainer is reacting to wild Pokemon's action
        
        Flow:
        1. Wild action was already shown
        2. Trainer reacts
        3. Resolve both actions
        """
        trainer_pokemon = battle.trainer_pokemon[battle.trainer_active_position]
        wild_pokemon = battle.wild_pokemon
        wild_action = battle.pending_action
        
        # Resolve both actions
        resolution = await self._resolve_turn(battle, wild_pokemon, wild_action, trainer_pokemon, trainer_action)
        
        return {
            "phase": "reaction",
            "resolution": resolution,
            "battle_over": battle.is_over,
            "winner": battle.winner
        }
    
    async def process_wild_initiative(self, battle_id: str) -> Dict:
        """
        Process wild Pokemon's initiative action
        
        Called when wild Pokemon has initiative
        Returns action narration and waits for trainer reaction
        """
        battle = self.active_battles.get(battle_id)
        if not battle or battle.is_over:
            return {"error": "Battle not found or already over"}
        
        trainer_pokemon = battle.trainer_pokemon[battle.trainer_active_position]
        wild_pokemon = battle.wild_pokemon
        
        # Wild Pokemon decides action
        wild_action = self._wild_pokemon_ai(wild_pokemon)
        
        # Store pending action
        battle.pending_action = wild_action
        battle.pending_actor = wild_pokemon
        battle.phase = 'WAITING_REACTION'
        
        # Generate narration for action starting
        if wild_action.action_type == 'move':
            action_narration = await self.narrator.narrate_action_start(
                actor=wild_pokemon,
                move_id=wild_action.move_id,
                target=trainer_pokemon,
                moves_db=self.moves_db,
                player_message=None  # No player message for wild Pokemon
            )
            
            move_data = self.moves_db.get_move(wild_action.move_id)
            move_name = move_data['name']
        else:
            action_narration = f"The wild {wild_pokemon.species_name} is preparing to {wild_action.action_type}!"
            move_name = wild_action.action_type
        
        return {
            "phase": "wild_initiative",
            "action_narration": action_narration,
            "move_name": move_name,
            "waiting_for": "trainer_reaction"
        }
    
    async def _resolve_turn(
        self,
        battle: BattleState,
        first_actor,
        first_action: BattleAction,
        second_actor,
        second_action: BattleAction
    ) -> Dict:
        """
        Resolve both actions and determine outcome
        
        Order:
        1. First actor's action
        2. Second actor's reaction
        3. Apply results
        """
        results = []
        
        # Process first action against second actor's reaction
        if first_action.action_type == 'move':
            result = await self._resolve_move(first_actor, first_action, second_actor, second_action, battle)
            results.append(result)
        
        # If second actor is still standing and used an attack, resolve it
        if second_actor.current_hp > 0 and second_action.action_type == 'move':
            # Second actor can only attack back if they didn't dodge/block
            if second_action.action_type == 'move':
                # Create empty first action for counter
                counter_result = await self._resolve_move(
                    second_actor, second_action, first_actor, 
                    BattleAction(action_type='take_hit'), battle
                )
                results.append(counter_result)
        
        # Check battle end
        battle.turn_number += 1
        
        # NEW: Apply end-of-turn effects (status damage, etc.)
        end_of_turn_messages = []
        if self.enhanced_mode:
            # Apply to trainer's active Pokemon
            trainer_pokemon = battle.trainer_pokemon[battle.trainer_active_position]
            trainer_eot = self.calculator.apply_end_of_turn(trainer_pokemon)
            if trainer_eot:
                end_of_turn_messages.extend([f"[Trainer] {msg}" for msg in trainer_eot])
            
            # Apply to wild Pokemon
            if battle.wild_pokemon.current_hp > 0:
                wild_eot = self.calculator.apply_end_of_turn(battle.wild_pokemon)
                if wild_eot:
                    end_of_turn_messages.extend([f"[Wild] {msg}" for msg in wild_eot])
        
        # NEW: Apply weather effects
        if hasattr(battle, 'weather') and battle.weather:
            # Weather damage
            trainer_weather_msg = self.ability_handler.apply_weather_damage(
                battle.trainer_pokemon[battle.trainer_active_position],
                battle.weather
            )
            if trainer_weather_msg:
                end_of_turn_messages.append(f"[Trainer] {trainer_weather_msg}")
            
            wild_weather_msg = self.ability_handler.apply_weather_damage(
                battle.wild_pokemon,
                battle.weather
            )
            if wild_weather_msg:
                end_of_turn_messages.append(f"[Wild] {wild_weather_msg}")
            
            # Weather healing (Rain Dish, Ice Body, etc.)
            trainer_heal_msg = self.ability_handler.apply_weather_healing(
                battle.trainer_pokemon[battle.trainer_active_position],
                battle.weather
            )
            if trainer_heal_msg:
                end_of_turn_messages.append(f"[Trainer] {trainer_heal_msg}")
            
            wild_heal_msg = self.ability_handler.apply_weather_healing(
                battle.wild_pokemon,
                battle.weather
            )
            if wild_heal_msg:
                end_of_turn_messages.append(f"[Wild] {wild_heal_msg}")
            
            # Decrement weather turns
            battle.weather_turns -= 1
            if battle.weather_turns <= 0:
                end_of_turn_messages.append(f"The {battle.weather} subsided!")
                battle.weather = None
                battle.weather_turns = 0
        
        battle.phase = 'WAITING_ACTION'
        self._check_battle_end(battle)
        
        # Determine next turn's initiative
        if not battle.is_over:
            self._determine_next_initiative(battle, results)
        
        return {
            "turn_number": battle.turn_number - 1,
            "results": results,
            "trainer_hp": f"{battle.trainer_pokemon[battle.trainer_active_position].current_hp}/"
                         f"{battle.trainer_pokemon[battle.trainer_active_position].max_hp}",
            "wild_hp": f"{battle.wild_pokemon.current_hp}/{battle.wild_pokemon.max_hp}",
            "end_of_turn_messages": end_of_turn_messages  # NEW: Status damage at turn end
        }
    
    async def _resolve_move(
        self,
        attacker,
        attack_action: BattleAction,
        defender,
        defend_action: BattleAction,
        battle: BattleState
    ) -> Dict:
        """
        Resolve a single move with defender's reaction
        
        Returns dict with narration and results
        """
        move_data = self.moves_db.get_move(attack_action.move_id)
        
        # Check if this is a status move and defender is blocking
        if move_data['category'] == 'status' and defend_action.action_type == 'block':
            # Can't block status moves
            defend_action = BattleAction(action_type='take_hit')
        
        dodged = False
        blocked = False
        missed = False
        damage = 0
        is_critical = False
        effectiveness = 1.0
        gained_initiative = False
        
        # First check: Did defender try to dodge?
        if defend_action.action_type == 'dodge':
            success, message, gained_initiative = self.dodge_system.can_dodge(defender, battle)
            if success:
                dodged = True
                self.dodge_system.reset_consecutive(attacker)  # Attacker's consecutive dodge resets
            else:
                # Dodge failed, still check accuracy
                pass
        
        # Second check: If not dodged, roll for accuracy
        if not dodged:
            accuracy = move_data.get('accuracy')
            
            # Handle different accuracy values
            # - None or True means always hits (status moves, Swift, etc.)
            # - 'true' string also means always hits
            # - Numbers are the accuracy percentage
            if accuracy is None or accuracy is True or accuracy == 'true':
                # Move always hits, skip accuracy check
                pass
            else:
                # Convert to int and check accuracy
                try:
                    accuracy_int = int(accuracy)
                    if random.randint(1, 100) > accuracy_int:
                        missed = True
                except (ValueError, TypeError):
                    # If we can't convert, assume it hits (default 100%)
                    pass
        
        # Calculate damage if hit
        effect_messages = []
        if not dodged and not missed:
            is_blocked = defend_action.action_type == 'block'
            
            # Use enhanced calculator if available
            if self.enhanced_mode:
                damage, is_critical, effectiveness, effect_messages = self.calculator.calculate_damage_with_effects(
                    attacker=attacker,
                    defender=defender,
                    move_id=attack_action.move_id,
                    is_blocked=is_blocked
                )
            else:
                # Fallback to basic calculation
                damage, is_critical, effectiveness = self.calculator.calculate_damage(
                    attacker=attacker,
                    defender=defender,
                    move_id=attack_action.move_id,
                    is_blocked=is_blocked
                )
            
            if is_blocked:
                blocked = True
            
            # Apply damage
            defender.current_hp = max(0, defender.current_hp - damage)
            
            # Reset attacker's consecutive dodges when attacking
            self.dodge_system.reset_consecutive(attacker)
        
        # Check if defender fainted
        defender_fainted = (defender.current_hp <= 0)
        
        # Generate resolution narration
        narration = await self.narrator.narrate_resolution(
            attacker=attacker,
            defender=defender,
            attack_action=attack_action,
            defend_action=defend_action,
            attack_damage=damage,
            is_critical=is_critical,
            effectiveness=effectiveness,
            dodged=dodged,
            blocked=blocked,
            missed=missed,
            defender_fainted=defender_fainted,
            moves_db=self.moves_db
        )
        
        return {
            "attacker": attacker.species_name,
            "defender": defender.species_name,
            "move_name": move_data['name'],
            "narration": narration,
            "damage": damage,
            "is_critical": is_critical,
            "effectiveness": effectiveness,
            "dodged": dodged,
            "blocked": blocked,
            "missed": missed,
            "gained_initiative": gained_initiative,
            "defender_hp": f"{defender.current_hp}/{defender.max_hp}",
            "effect_messages": effect_messages  # NEW: Status effects, stat changes, etc.
        }
    
    def _determine_next_initiative(self, battle: BattleState, results: List[Dict]):
        """
        Determine who has initiative next turn
        
        - If someone successfully dodged, they get initiative
        - Otherwise, compare speeds (with priority moves)
        """
        # Check if anyone gained initiative from dodging
        for result in results:
            if result.get('gained_initiative'):
                # The defender gained initiative
                defender_name = result['defender']
                trainer_pokemon = battle.trainer_pokemon[battle.trainer_active_position]
                
                if defender_name == trainer_pokemon.species_name:
                    battle.initiative_holder = 'trainer'
                else:
                    battle.initiative_holder = 'wild'
                return
        
        # No special initiative change, stays the same or goes by speed
        # (In future, check priority moves here)
        trainer_pokemon = battle.trainer_pokemon[battle.trainer_active_position]
        wild_pokemon = battle.wild_pokemon
        
        if trainer_pokemon.speed >= wild_pokemon.speed:
            battle.initiative_holder = 'trainer'
        else:
            battle.initiative_holder = 'wild'
    
    def _wild_pokemon_ai(self, pokemon) -> BattleAction:
        """Simple AI for wild Pokemon - pick a random attacking move"""
        attacking_moves = [
            move for move in pokemon.moves
            if self.moves_db.get_move(move['move_id'])['category'] in ['physical', 'special']
        ]
        
        if attacking_moves:
            chosen_move = random.choice(attacking_moves)
            return BattleAction(action_type='move', move_id=chosen_move['move_id'])
        else:
            # If no attacking moves, use first move
            return BattleAction(action_type='move', move_id=pokemon.moves[0]['move_id'])
    
    def _wild_pokemon_ai_react(self, pokemon, opponent_action: BattleAction) -> BattleAction:
        """
        AI decides how to react to opponent's action
        
        Simple strategy:
        - 30% chance to dodge
        - 20% chance to block
        - 50% chance to attack
        """
        roll = random.random()
        
        if roll < 0.3:
            return BattleAction(action_type='dodge')
        elif roll < 0.5:
            return BattleAction(action_type='block')
        else:
            return self._wild_pokemon_ai(pokemon)
    
    def _check_battle_end(self, battle: BattleState):
        """Check if battle is over and set winner"""
        trainer_pokemon = battle.trainer_pokemon[battle.trainer_active_position]
        wild_pokemon = battle.wild_pokemon
        
        if trainer_pokemon.current_hp <= 0:
            battle.is_over = True
            battle.winner = 'wild'
        elif wild_pokemon.current_hp <= 0:
            battle.is_over = True
            battle.winner = 'trainer'
    
    def get_battle(self, battle_id: str) -> Optional[BattleState]:
        """Get battle state by ID"""
        return self.active_battles.get(battle_id)
    
    def end_battle(self, battle_id: str):
        """Clean up a finished battle"""
        if battle_id in self.active_battles:
            del self.active_battles[battle_id]
