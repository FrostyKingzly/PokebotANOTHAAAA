# Battle Music System

## Overview

The battle music system plays random themed music during NPC trainer battles. When you start an NPC battle, you'll be prompted if you want music. If you say yes and join a voice channel, the bot will play a random Gen 1-9 battle theme during the fight, then switch to the victory theme when you win!

## Features

### 🎵 How It Works

1. **Start NPC Battle**: Choose an NPC trainer to fight
2. **Music Prompt**: A prompt appears asking "Would you like music?"
3. **Join Voice Channel**: If yes, join the voice channel shown
4. **Battle Theme Plays**: Random Gen 1-9 theme plays during battle (loops)
5. **Victory Theme**: When you win, switches to the matching victory theme
6. **Fade Out**: Victory music plays for 1 minute then fades out

### 🎯 Battle Types

- ✅ **NPC Battles (Casual)**: Random Gen 1-9 themes
- ✅ **NPC Battles (Ranked)**: Will use ranked themes when added
- ✅ **Raid Battles**: Will use raid themes when added
- ❌ **Wild Battles**: No music
- ❌ **PvP Battles**: No music (for now)

### 🎮 Queue System

- **One Battle at a Time**: Bot can only play music for one battle simultaneously
- **Queue Display**: If music is in use, you'll see who's currently using it
- **Join Queue**: Wait in line and music will start when it's your turn
- **No Monopolization**: Can't join queue if you're already using music

## Random Themes

Each NPC battle randomly picks from these official Pokémon game themes:

| Generation | Game | Themes |
|-----------|------|--------|
| Gen 1 | Red/Blue/Yellow | Kanto Classic |
| Gen 2 | Gold/Silver/Crystal | Johto Journey |
| Gen 3 | Ruby/Sapphire/Emerald | Hoenn Adventure |
| Gen 4 | Diamond/Pearl/Platinum | Sinnoh Symphony |
| Gen 5 | Black/White | Unova Epic |
| Gen 6 | X/Y | Kalos Elegance |
| Gen 7 | Sun/Moon | Alola Vibes |
| Gen 8 | Sword/Shield | Galar Glory |
| Gen 9 | Scarlet/Violet | Paldea Power |

Each generation has a battle theme (plays during combat) and victory theme (plays when you win).

## Technical Details

### Architecture

```
battle_music_manager.py    - Music playback and queue management
battle_themes.py            - Random theme selection from Gen 1-9
battle_music_ui.py          - Music opt-in prompt
cogs/battle_cog.py          - Integration with NPC battles
```

### System Requirements

**Required:**
- **FFmpeg**: Audio processing
  ```bash
  # Ubuntu/Debian
  sudo apt-get install ffmpeg

  # macOS
  brew install ffmpeg

  # Windows
  Download from https://ffmpeg.org/download.html
  ```

**Dependencies (auto-installed):**
- `discord.py[voice]>=2.3.0` - Voice support
- `PyNaCl>=1.5.0` - Voice encryption
- `yt-dlp>=2024.0.0` - YouTube audio extraction
- `aiohttp>=3.9.0` - Async HTTP requests

### Installation

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Install FFmpeg** (see above)

3. **Bot Permissions**: Ensure bot has:
   - Connect to voice channels
   - Speak in voice channels

## Usage Example

```
Player: "I want to battle the Ace Trainer!"
Bot: "🎵 Would you like music for your battle?"
      [Yes, play music!] [No, battle silently]

Player: *clicks Yes*
Bot: "Music will start when battle begins! Join #battle-music"

Player: *joins voice channel*
Player: *clicks Start Battle*
Bot: *Plays random Gen 5 Battle Theme*

*Battle proceeds...*

Bot: "You win!"
Bot: *Switches to Gen 5 Victory Theme*
     *Plays for 1 minute, then fades out*
```

## Configuration

### Adding Ranked Themes

When you're ready to add ranked battle themes, edit `battle_themes.py`:

```python
RANKED_NPC_THEMES = [
    ("https://youtu.be/BATTLE_URL", "https://youtu.be/VICTORY_URL"),
    ("https://youtu.be/BATTLE_URL_2", "https://youtu.be/VICTORY_URL_2"),
    # Add more ranked themes...
]
```

### Adding Raid Themes

For raid-specific themes, edit `battle_themes.py`:

```python
RAID_THEMES = [
    ("https://youtu.be/RAID_BATTLE", "https://youtu.be/RAID_VICTORY"),
    # Add more raid themes...
]
```

### Adjusting Music Volume

In `battle_music_manager.py`, line ~25:

```python
self.FFMPEG_OPTIONS = {
    'options': '-vn -filter:a "volume=0.5"'  # 0.5 = 50% volume
}
```

### Changing Victory Duration

In `battle_music_manager.py`, `_fade_and_disconnect()` method:

```python
await asyncio.sleep(60)  # Play for 60 seconds (1 minute)
```

## Troubleshooting

### Music Not Playing

1. **Check Voice Channel**: You must be in a voice channel before saying yes
2. **Check Permissions**: Bot needs Connect and Speak permissions
3. **Check FFmpeg**: Run `ffmpeg -version` to verify installation
4. **Check Dependencies**: Run `pip install -r requirements.txt`

### Queue Issues

- **Can't Join Queue**: You may already be in queue or using music
- **Queue Not Moving**: Previous battle's victory theme may still be playing (wait 60 seconds)

### Audio Quality

- Streams at YouTube's best available quality
- Default volume is 50% (adjustable)
- No lag if good internet connection

## How Music System Integrates

The music system automatically integrates when you start NPC battles:

1. Player selects NPC trainer from encounter list
2. `battle_cog.prompt_and_start_battle_ui()` is called
3. Music opt-in prompt appears (only for NPC battles)
4. If yes:
   - Checks if bot is available
   - If available: Marks battle for music
   - If busy: Shows queue, adds to queue
5. Battle UI starts
6. Music begins playing random Gen 1-9 theme
7. Battle proceeds normally
8. On victory: Switches to victory theme
9. After 60 seconds: Fades out, disconnects

## No Commands Needed!

This system requires **zero commands**. Everything happens automatically:
- Music opt-in prompts appear when starting NPC battles
- Themes are randomly selected
- Queue is managed automatically
- Victory themes play automatically

Just battle and enjoy the music! 🎵

## Future Enhancements

Possible features for later:

- [ ] Ranked battle themes
- [ ] Raid battle themes
- [ ] PvP battle music support
- [ ] Volume control per-player
- [ ] Player-selectable themes
- [ ] Spotify integration

## Credits

All themes are official Pokémon battle themes from their respective games.
Music system designed for educational and entertainment purposes.
