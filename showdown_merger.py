"""
Showdown Data Merger
Merges Showdown's TypeScript data with your existing JSON files
Preserves your structure while adding Showdown's effects
"""

import json
import re
from typing import Dict, Any


class ShowdownMerger:
    """Merge Showdown data with existing JSON files"""
    
    @staticmethod
    def parse_move_from_ts(ts_text: str) -> Dict[str, Any]:
        """Extract move data from a TypeScript move definition"""
        data = {}
        
        # Extract basic fields
        data['power'] = ShowdownMerger._extract_value(ts_text, 'basePower', int) or 0
        data['accuracy'] = ShowdownMerger._extract_value(ts_text, 'accuracy')
        data['pp'] = ShowdownMerger._extract_value(ts_text, 'pp', int) or 5
        data['priority'] = ShowdownMerger._extract_value(ts_text, 'priority', int) or 0
        data['category'] = (ShowdownMerger._extract_value(ts_text, 'category', str) or 'status').lower()
        data['type'] = (ShowdownMerger._extract_value(ts_text, 'type', str) or 'normal').lower()
        
        # Extract crit rate
        crit_ratio = ShowdownMerger._extract_value(ts_text, 'critRatio', int)
        if crit_ratio:
            data['crit_rate'] = crit_ratio
        
        # Extract flags
        flags_match = re.search(r'flags:\s*\{([^}]+)\}', ts_text)
        if flags_match:
            flags = {}
            for flag in re.findall(r'(\w+):\s*1', flags_match.group(1)):
                flags[flag] = True
            if flags:
                data['flags'] = flags
        
        # Extract secondary effects
        secondary_match = re.search(r'secondary:\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}', ts_text)
        if secondary_match:
            secondary = {}
            sec_text = secondary_match.group(1)
            
            chance = ShowdownMerger._extract_value(sec_text, 'chance', int)
            if chance:
                secondary['chance'] = chance
            
            status = ShowdownMerger._extract_value(sec_text, 'status', str)
            if status:
                secondary['status'] = status
            
            volatile = ShowdownMerger._extract_value(sec_text, 'volatileStatus', str)
            if volatile:
                secondary['volatileStatus'] = volatile
            
            # Extract boosts
            boosts_match = re.search(r'boosts:\s*\{([^}]+)\}', sec_text)
            if boosts_match:
                boosts = {}
                for stat in ['atk', 'def', 'spa', 'spd', 'spe', 'accuracy', 'evasion']:
                    val = ShowdownMerger._extract_value(boosts_match.group(1), stat, int)
                    if val is not None:
                        boosts[stat] = val
                if boosts:
                    secondary['boosts'] = boosts
            
            if secondary:
                data['secondary'] = secondary
        
        # Extract direct boosts (for status moves)
        boosts_match = re.search(r'^\s*boosts:\s*\{([^}]+)\}', ts_text, re.MULTILINE)
        if boosts_match:
            boosts = {}
            for stat in ['atk', 'def', 'spa', 'spd', 'spe', 'accuracy', 'evasion']:
                val = ShowdownMerger._extract_value(boosts_match.group(1), stat, int)
                if val is not None:
                    boosts[stat] = val
            if boosts:
                data['boosts'] = boosts
        
        # Extract drain, recoil, heal
        for effect_type in ['drain', 'recoil', 'heal']:
            match = re.search(rf'{effect_type}:\s*\[(\d+),\s*(\d+)\]', ts_text)
            if match:
                data[effect_type] = [int(match.group(1)), int(match.group(2))]
        
        # Extract multihit
        if 'multihit:' in ts_text:
            multihit_match = re.search(r'multihit:\s*\[(\d+),\s*(\d+)\]', ts_text)
            if multihit_match:
                data['multihit'] = [int(multihit_match.group(1)), int(multihit_match.group(2))]
            else:
                multihit_match = re.search(r'multihit:\s*(\d+)', ts_text)
                if multihit_match:
                    data['multihit'] = int(multihit_match.group(1))
        
        # Other flags
        if 'selfdestruct:' in ts_text:
            data['selfdestruct'] = True
        
        return {k: v for k, v in data.items() if v is not None and v != {} and v != []}
    
    @staticmethod
    def _extract_value(text: str, key: str, value_type=None):
        """Extract a value from text"""
        # String in quotes
        pattern = rf'{key}:\s*["\']([^"\']+)["\']'
        match = re.search(pattern, text)
        if match:
            val = match.group(1)
            if value_type == int:
                try:
                    return int(val)
                except:
                    return None
            return val
        
        # Number
        pattern = rf'{key}:\s*(\d+)'
        match = re.search(pattern, text)
        if match:
            if value_type == str:
                return match.group(1)
            return int(match.group(1))
        
        # Boolean
        pattern = rf'{key}:\s*(true|false)'
        match = re.search(pattern, text)
        if match:
            if value_type == int:
                return None
            return match.group(1) == 'true'
        
        return None
    
    @staticmethod
    def merge_moves(existing_json_path: str, showdown_txt_path: str, output_path: str):
        """
        Merge Showdown move data with existing moves.json
        
        Args:
            existing_json_path: Path to your current moves.json
            showdown_txt_path: Path to Showdown's moves.txt
            output_path: Where to save the merged JSON
        """
        # Load existing JSON
        with open(existing_json_path, 'r', encoding='utf-8') as f:
            existing_moves = json.load(f)
        
        # Load Showdown TypeScript
        with open(showdown_txt_path, 'r', encoding='utf-8') as f:
            showdown_content = f.read()
        
        # Parse Showdown moves
        # Split by move entries
        lines = showdown_content.split('\n')
        current_move = None
        current_data = []
        brace_count = 0
        
        showdown_effects = {}
        
        for line in lines:
            # Check for new move
            match = re.match(r'\s*([a-zA-Z0-9]+):\s*\{', line)
            if match and brace_count == 0:
                # Save previous move
                if current_move:
                    move_text = ' '.join(current_data)
                    effects = ShowdownMerger.parse_move_from_ts(move_text)
                    if effects:
                        showdown_effects[current_move] = effects
                
                # Start new move
                current_move = match.group(1)
                current_data = [line]
                brace_count = line.count('{') - line.count('}')
            else:
                # Continue current move
                if current_move:
                    current_data.append(line)
                    brace_count += line.count('{') - line.count('}')
                    
                    if brace_count == 0 and '},' in line:
                        move_text = ' '.join(current_data)
                        effects = ShowdownMerger.parse_move_from_ts(move_text)
                        if effects:
                            showdown_effects[current_move] = effects
                        current_move = None
                        current_data = []
        
        # Merge data
        merged_count = 0
        for move_id, move_data in existing_moves.items():
            # Try to find matching Showdown data
            showdown_id = move_id.lower().replace('_', '').replace('-', '')
            
            if showdown_id in showdown_effects:
                # Merge Showdown effects into existing move
                effects = showdown_effects[showdown_id]
                
                for key, value in effects.items():
                    # Don't overwrite basic fields if they already exist
                    if key in ['power', 'accuracy', 'pp', 'type', 'category']:
                        if key not in move_data or move_data[key] == 0:
                            move_data[key] = value
                    else:
                        # Always add effect fields
                        move_data[key] = value
                
                merged_count += 1
        
        # Save merged JSON
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(existing_moves, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Merged {merged_count} moves")
        print(f"   Input: {existing_json_path}")
        print(f"   Showdown: {showdown_txt_path}")
        print(f"   Output: {output_path}")
        
        return merged_count


def main():
    """Example usage"""
    import sys
    
    if len(sys.argv) < 4:
        print("Usage: python showdown_merger.py <existing_moves.json> <showdown_moves.txt> <output.json>")
        print()
        print("Example:")
        print("  python showdown_merger.py moves.json showdown_moves.txt moves_enhanced.json")
        return
    
    existing_json = sys.argv[1]
    showdown_txt = sys.argv[2]
    output_json = sys.argv[3]
    
    print("Showdown Data Merger")
    print("=" * 60)
    print()
    
    ShowdownMerger.merge_moves(existing_json, showdown_txt, output_json)
    
    print()
    print("Done! Your moves now have Showdown effects.")
    print()
    print("What was added:")
    print("  - secondary effects (status, stat changes)")
    print("  - drain, recoil, heal effects")
    print("  - multi-hit data")
    print("  - flags (contact, protect, etc.)")
    print("  - priority values")
    print()
    print("Next steps:")
    print("  1. Review the output file")
    print("  2. Replace your old moves.json")
    print("  3. Test in your battle system")


if __name__ == '__main__':
    main()
