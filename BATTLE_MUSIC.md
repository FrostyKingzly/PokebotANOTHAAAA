# Battle Music System

## Overview

The battle music system allows players to have custom music play during their battles. When a battle starts, the bot joins a voice channel and plays themed music throughout the battle, switching to a victory theme when the battle ends.

## Features

### 🎵 Battle Music Flow

1. **Battle Start**: When a battle begins, players are prompted if they want music
2. **Voice Channel**: If yes, they join a voice channel and the bot plays their battle theme
3. **Battle Theme**: Music plays throughout the battle (loops)
4. **Victory Theme**: When battle ends, switches to victory theme
5. **Fade Out**: Victory theme plays for 1 minute before fading out

### 🎮 Battle Type Support

- ✅ **PvP Battles**: Plays challenger's custom theme
- ✅ **NPC Battles**: Randomizes Gen 1-9 trainer themes
- ✅ **Raid Battles**: Plays designated raid themes
- ❌ **Wild Battles**: No music (as intended)

### 🎯 Queue System

- **One Battle at a Time**: Bot can only play music for one battle simultaneously
- **Queue Management**: If music is in use, players can join a queue
- **Queue Display**: Shows current active session and waiting players
- **No Monopolization**: Can't queue if already using music

## Player Commands

### `/battletheme`
Choose your battle theme from Gen 1-9 preset themes.
- Opens a dropdown menu with all available themes
- Preview links for each generation
- Default: Gen 5 - Unova Epic

### `/setcustomtheme <battle_url> <victory_url>`
Set custom YouTube URLs for battle and victory themes.
- Requires valid YouTube URLs
- Battle URL plays during combat
- Victory URL plays after winning

### `/viewtheme`
View your current battle theme settings.
- Shows current theme name
- Provides links to listen
- Displays if using default theme

## Available Preset Themes

| Generation | Theme Name | Description |
|-----------|------------|-------------|
| Gen 1 | Kanto Classic | The original battle theme |
| Gen 2 | Johto Journey | Gold/Silver/Crystal vibes |
| Gen 3 | Hoenn Adventure | Ruby/Sapphire/Emerald |
| Gen 4 | Sinnoh Symphony | Diamond/Pearl/Platinum |
| Gen 5 | Unova Epic | Black/White (Default) |
| Gen 6 | Kalos Elegance | X/Y themes |
| Gen 7 | Alola Vibes | Sun/Moon tropical |
| Gen 8 | Galar Glory | Sword/Shield |
| Gen 9 | Paldea Power | Scarlet/Violet |

## For NPC Battles

NPC battles randomly select from the casual trainer themes (Gen 1-9). Each generation has:
- **Battle Theme**: Plays during combat
- **Victory Theme**: Plays when you win

This creates variety and nostalgia as you battle through different trainer themes!

## Technical Details

### Architecture

```
battle_music_manager.py    - Core music playback and queue management
battle_themes.py            - Theme configuration and selection
battle_music_ui.py          - UI components (opt-in prompts, queue display)
cogs/battle_cog.py          - Integration with battle system
cogs/profile_cog.py         - Theme selection commands
```

### Database Schema

Added to `trainers` table:
- `battle_theme_url` (TEXT): YouTube URL for battle theme
- `victory_theme_url` (TEXT): YouTube URL for victory theme

### Dependencies

Required packages (added to `requirements.txt`):
- `discord.py[voice]>=2.3.0` - Voice support
- `PyNaCl>=1.5.0` - Voice encryption
- `yt-dlp>=2024.0.0` - YouTube audio extraction
- `aiohttp>=3.9.0` - Async HTTP requests

### System Requirements

- **FFmpeg**: Must be installed on the system for audio processing
  ```bash
  # Ubuntu/Debian
  sudo apt-get install ffmpeg

  # macOS
  brew install ffmpeg

  # Windows
  Download from https://ffmpeg.org/download.html
  ```

## Usage Flow

### Player Perspective

1. Player initiates a battle (NPC, PvP, or Raid)
2. If in a voice channel, prompted: "Would you like music?"
3. **Chooses Yes**:
   - If bot available: "Music will start when battle begins! Join [VC Name]"
   - If bot busy: Shows queue status with position
4. **Battle Starts**: Music plays immediately
5. **Battle Ends**: Switches to victory theme for 1 minute
6. **Fade Out**: Music fades over 5 seconds, disconnects

### Developer Integration

To add music opt-in to a new battle type:

```python
# In your battle initiation code
await battle_cog.prompt_and_start_battle_ui(
    interaction,
    battle_id,
    battle_type
)
```

This automatically handles:
- Music opt-in prompt
- Queue management
- Battle UI display
- Music playback

## Configuration

### Adding New Themes

Edit `battle_themes.py`:

```python
# For NPC themes
CASUAL_NPC_THEMES.append((
    "https://youtu.be/BATTLE_ID",
    "https://youtu.be/VICTORY_ID"
))

# For player-selectable themes
AVAILABLE_PLAYER_THEMES["Gen 10 - Region Name"] = (
    "https://youtu.be/BATTLE_ID",
    "https://youtu.be/VICTORY_ID"
)
```

### Adjusting Music Volume

In `battle_music_manager.py`, adjust the volume parameter:

```python
self.FFMPEG_OPTIONS = {
    'options': '-vn -filter:a "volume=0.5"'  # 0.5 = 50% volume
}
```

### Changing Fade Duration

In `battle_music_manager.py`:

```python
async def _fade_and_disconnect(self):
    await asyncio.sleep(60)  # Play duration (seconds)
    # Fade over 5 seconds (adjust steps for different duration)
```

## Troubleshooting

### Music Not Playing

1. **Check Voice Channel**: Player must be in a voice channel
2. **Check Permissions**: Bot needs voice permissions in that channel
3. **Check FFmpeg**: Ensure FFmpeg is installed
4. **Check Dependencies**: Run `pip install -r requirements.txt`

### Queue Issues

- **Can't Join Queue**: May already be in queue or have active session
- **Queue Not Moving**: Previous battle may still be playing victory theme
- **Queue Position Wrong**: Wait 60 seconds after previous battle ends

### Audio Quality

- Audio streams at YouTube's best available quality
- Volume set to 50% by default
- Can be adjusted in `FFMPEG_OPTIONS`

## Future Enhancements

Potential features for future versions:

- [ ] Ranked battle themes (separate from casual)
- [ ] Gym leader/Elite Four specific themes
- [ ] Volume control per-player
- [ ] Spotify integration
- [ ] Battle intensity-based themes
- [ ] Dynamic theme switching based on HP
- [ ] Champion-tier themes for high-rank players

## Credits

All preset themes are official Pokémon battle themes from their respective games.
Music system designed for educational and entertainment purposes.

## Support

For issues or questions about the music system:
1. Check this documentation
2. Verify all dependencies installed
3. Check bot logs for errors
4. Report issues with specific error messages
