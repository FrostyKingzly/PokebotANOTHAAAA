#!/usr/bin/env python3
"""
Script to apply status effect patches to moves.json
Run this from your project root directory
"""

import json
import sys
from pathlib import Path

def apply_status_patch():
    """Apply the status effect patches to moves.json"""
    
    # Load moves.json
    moves_path = Path('data/moves.json')
    if not moves_path.exists():
        moves_path = Path('moves.json')
    
    if not moves_path.exists():
        print("Error: Could not find moves.json")
        sys.exit(1)
    
    with open(moves_path, 'r', encoding='utf-8') as f:
        moves = json.load(f)
    
    # Load patch
    patch_path = Path('moves_status_patch.json')
    if not patch_path.exists():
        print("Error: Could not find moves_status_patch.json")
        sys.exit(1)
    
    with open(patch_path, 'r', encoding='utf-8') as f:
        patch = json.load(f)
    
    # Apply patches
    patched_count = 0
    for move_id, status_data in patch.items():
        if move_id == "comment":
            continue
        
        if move_id not in moves:
            print(f"Warning: Move '{move_id}' not found in moves.json")
            continue
        
        # Add status field
        if 'status' in status_data:
            moves[move_id]['status'] = status_data['status']
            patched_count += 1
            print(f"✓ Added status '{status_data['status']}' to {move_id}")
        
        # Add volatileStatus field
        if 'volatileStatus' in status_data:
            moves[move_id]['volatileStatus'] = status_data['volatileStatus']
            patched_count += 1
            print(f"✓ Added volatileStatus '{status_data['volatileStatus']}' to {move_id}")
    
    # Backup original
    backup_path = moves_path.with_suffix('.json.backup')
    print(f"\nCreating backup at {backup_path}")
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(moves, f, indent=2)
    
    # Save patched version
    print(f"Saving patched moves.json")
    with open(moves_path, 'w', encoding='utf-8') as f:
        json.dump(moves, f, indent=2)
    
    print(f"\n✅ Successfully patched {patched_count} moves!")
    print(f"Backup saved to: {backup_path}")

if __name__ == '__main__':
    apply_status_patch()
