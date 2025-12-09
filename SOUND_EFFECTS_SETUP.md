# Battle Sound Effects Setup Guide

This guide explains how to set up Pokemon cries and battle sound effects for your bot.

## Overview

The bot now supports playing Pokemon cries and battle sound effects alongside battle music! Sound effects include:
- **Pokemon cries** when sent out or fainting
- **Pokeball throw sounds**
- **Switch/recall sounds**
- **Faint sounds**

## Requirements

### Software Dependencies

The following Python package is required (already in `requirements.txt`):
```
pydub>=0.25.1
```

Install with:
```bash
pip install -r requirements.txt
```

### Audio Files Required

Create a `cries` folder in your project root directory with the following files:

#### Battle Sound Effects
1. **Ruby_003D.wav** - Pokeball throw sound
2. **In-Battle_Recall_Switch_Alive.mp3.mpeg** - Recall/switch sound
3. **In-Battle_Faint_No_Health_XY.mp3.mpeg** - Faint sound

#### Pokemon Cries

For each Pokemon, you need two cry files:

1. **Normal cry** (used when sent out or switching):
   - Format: `PV-INDEX_###.wav`
   - Example: `PV-INDEX_001.wav` for Bulbasaur (#001)
   - Example: `PV-INDEX_025.wav` for Pikachu (#025)

2. **Sad cry** (used when fainting):
   - Format: `SAD_###.wav`
   - Example: `SAD_001.wav` for Bulbasaur (#001)
   - Example: `SAD_025.wav` for Pikachu (#025)

**Note:** Files are numbered by National Pokedex number with leading zeros (001-1025+).

Supported audio formats: `.wav`, `.mp3`, `.ogg`, `.mpeg`

## Directory Structure

```
PokebotANOTHAAAA/
├── cries/
│   ├── Ruby_003D.wav
│   ├── In-Battle_Recall_Switch_Alive.mp3.mpeg
│   ├── In-Battle_Faint_No_Health_XY.mp3.mpeg
│   ├── PV-INDEX_001.wav
│   ├── SAD_001.wav
│   ├── PV-INDEX_002.wav
│   ├── SAD_002.wav
│   ├── ... (and so on for all Pokemon)
│   └── SAD_1025.wav
├── battle_sound_effects.py
├── battle_music_manager.py
└── ... (other files)
```

## Sound Sequences

The bot plays different sound sequences for different battle actions:

### 1. Send Out (Initial)
**Sequence:** Throw → Switch → Pokemon Cry
- Pokeball throw sound
- 50ms pause
- Switch sound
- 100ms pause
- Pokemon's normal cry

### 2. Switch Pokemon
**Sequence:** Switch → Pause → Throw → Switch → Cry
- Switch sound (recall)
- 200ms pause
- Pokeball throw
- 50ms pause
- Switch sound (send out)
- 100ms pause
- New Pokemon's normal cry

### 3. Pokemon Faints
**Sequence:** Sad Cry → Faint Noise
- Pokemon's sad cry
- 100ms pause
- Faint sound effect

### 4. Switch After Faint
**Sequence:** Throw → Switch → Cry
- Same as Send Out sequence

## Usage in Code

### In Battle Cog

```python
# When a Pokemon is sent out
if self.music_manager.current_session:
    dex_number = pokemon.species_dex_number
    duration = await self.music_manager.play_send_out_sound(dex_number)
    await asyncio.sleep(duration)  # Wait for sound to finish before showing next embed

# When switching Pokemon
if self.music_manager.current_session:
    dex_number = new_pokemon.species_dex_number
    duration = await self.music_manager.play_switch_sound(dex_number)
    await asyncio.sleep(duration)

# When a Pokemon faints
if self.music_manager.current_session:
    dex_number = fainted_pokemon.species_dex_number
    duration = await self.music_manager.play_faint_sound(dex_number)
    await asyncio.sleep(duration)
```

### API Reference

#### BattleMusicManager Methods

- **`play_send_out_sound(dex_number: int) -> float`**
  - Plays send out sequence
  - Returns duration in seconds

- **`play_switch_sound(dex_number: int) -> float`**
  - Plays switch sequence
  - Returns duration in seconds

- **`play_faint_sound(dex_number: int) -> float`**
  - Plays faint sequence
  - Returns duration in seconds

- **`cleanup_sound_effects()`**
  - Cleans up temporary audio files
  - Call when battle ends

## How It Works

1. **Sound Effect Creation:** When a sound is needed, the system combines individual audio files into a single sequence using pydub.

2. **Audio Mixing:** FFmpeg mixes the sound effect with the music stream:
   - Music volume is lowered to 30% during sound effect
   - Sound effect plays at 100% volume
   - Both audio sources play simultaneously
   - Music automatically returns to normal after sound finishes

3. **Temporary Files:** Combined sequences and mixed audio are exported to temporary MP3 files.

4. **Cleanup:** Temporary files are cleaned up when the battle ends.

## Troubleshooting

### "Cries directory not found" warning
- Create the `cries` folder in your project root
- Add at least the 3 required sound effect files

### Sound effects not playing
- Check that FFmpeg is installed (`ffmpeg -version`)
- Verify file naming matches the format exactly
- Check file extensions are supported
- Ensure bot has voice channel permissions

### Missing Pokemon cries
- The bot will skip cries for Pokemon without files
- Check console for warnings about missing files
- Verify dex numbers match Pokemon species

### Music volume during sound effects
- Music is automatically lowered to 30% when sound effects play
- This makes sound effects clearly audible
- Music returns to normal volume after sound finishes

## Performance Notes

- Sound files are cached after first load for better performance
- Temporary mixed files are created on-demand
- Only one sound effect can play at a time
- Sound effects take priority over music

## Finding Pokemon Cry Files

Pokemon cry audio files can be obtained from various sources:
- Ripped from official Pokemon games
- Pokemon cry databases and sound libraries
- Fan-made collections

Make sure you have rights to use any audio files and comply with copyright laws.

## Example Integration

See `cogs/battle_cog.py` for full integration examples showing how sound effects are called during battle flow.

---

**Note:** Sound effects are only available when music is enabled for a battle. The bot must be connected to a voice channel to play sounds.
