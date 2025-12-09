# Pokemon Discord Bot - Phase 1: Registration System

This is Phase 1 of your Pokemon Discord Bot project, implementing the core foundation and player registration system.

## ✅ What's Implemented

### Core Systems
- ✅ **Database Module** - Loads all JSON game data (species, moves, abilities, items, natures, type chart)
- ✅ **Player Database** - SQLite storage for trainer profiles, Pokemon instances, inventory, Pokedex
- ✅ **Data Models** - Pokemon and Trainer classes with full stats calculation
- ✅ **Player Manager** - CRUD operations for trainer profiles and Pokemon

### Commands
- ✅ **/register** - Interactive registration flow with:
  - Trainer name input
  - Optional avatar URL
  - Starter Pokemon selection (any non-legendary)
  - Social stats Boon/Bane selection
  - Confirmation summary
  
- ✅ **/menu** - Main menu hub with buttons for:
  - Party view (working!)
  - Trainer Card (working!)
  - Boxes, Travel, Shop, Pokedex, Battle (placeholders)

### Features
- ✅ Full Pokemon stat calculation (base stats, IVs, EVs, nature modifiers)
- ✅ Gender generation based on species ratios
- ✅ Random IV generation
- ✅ Move learning system (placeholder for now)
- ✅ Social stats system (Heart, Insight, Charisma, Fortitude, Will)
- ✅ Starter filtering (no legendaries, mythicals, ultra beasts, paradox)
- ✅ One profile per Discord user
- ✅ Ranked ladder data structure (ready for implementation)

## 📋 Setup Instructions

### 1. Install Python Requirements

```bash
pip install -r requirements.txt
```

### 2. Create Discord Bot

1. Go to https://discord.com/developers/applications
2. Click "New Application"
3. Go to "Bot" section
4. Click "Add Bot"
5. Enable these intents:
   - Presence Intent
   - Server Members Intent
   - Message Content Intent
6. Copy your bot token

### 3. Configure Bot Token

Create a `.env` file in the root directory:

```
DISCORD_BOT_TOKEN=your_bot_token_here
```

### 4. Invite Bot to Your Server

1. Go to OAuth2 → URL Generator
2. Select scopes: `bot` and `applications.commands`
3. Select bot permissions:
   - Read Messages/View Channels
   - Send Messages
   - Embed Links
   - Attach Files
   - Use Slash Commands
4. Copy the generated URL and open it in your browser

### 5. Run the Bot

```bash
python pokebot.py
```

## 📤 Saving & Sharing Your Changes

When you finish a round of work in this workspace, push it to your shared GitHub repo so everyone sees the updates:

1. **Review local changes**
   ```bash
   git status -sb
   ```
   Confirm the files you expect to change are listed.

2. **Stage the updates**
   ```bash
   git add <file_or_folder>
   # or add everything:
   git add -A
   ```

3. **Commit with a clear message**
   ```bash
   git commit -m "Describe today's work"
   ```

4. **Push to GitHub**
   ```bash
   git push origin work
   ```
   Replace `work` with another branch name if you are using one. Once pushed, GitHub will show the new timestamp and commit hash so teammates can pull the changes.

> 💡 If nothing shows under `git status`, there is nothing new to add yet. Make sure you've saved your files before running `git add`.

## 🎮 Usage

### For Players

1. **Register**: `/register`
   - Choose your trainer name
   - (Optional) Add avatar URL
   - Select your starter Pokemon from dropdown
   - Choose your Boon stat (Rank 2) and Bane stat (Rank 0)
   - Confirm your choices

2. **Access Menu**: `/menu`
   - View your party
   - Check trainer card
   - More features coming soon!

### Testing the Registration

1. Run `/register` in your Discord server
2. Click "Begin Registration"
3. Fill in your trainer name
4. Select a starter from the dropdown (e.g., Bulbasaur, Charmander, Squirtle)
5. Choose your Boon stat (what you're good at)
6. Choose your Bane stat (what you're weak at)
7. Confirm your choices
8. You should see a success message!

Try `/menu` to see your trainer card and party!

## 📁 Project Structure

```
pokemon-bot/
├── pokebot.py              # Main bot entry point
├── database.py             # Database loading and storage
├── models.py               # Pokemon and Trainer data models
├── player_manager.py       # Player CRUD operations
├── encounter_system.py     # Placeholder for encounters
├── requirements.txt        # Python dependencies
├── .env                    # Bot token (create this!)
│
├── ui/
│   ├── embeds.py          # Discord embed builders
│   └── buttons.py         # Interactive button views
│
├── cogs/
│   ├── registration_cog.py # Registration command
│   ├── wild_cog.py        # Placeholder
│   ├── pokemon_cog.py     # Placeholder
│   ├── battle_cog.py      # Placeholder
│   └── admin_cog.py       # Placeholder
│
└── data/
    ├── players.db         # SQLite database (auto-created)
    ├── pokemon_species.json
    ├── moves.json
    ├── abilities.json
    ├── items.json
    ├── natures.json
    └── type_chart.json
```

## 🔧 Database Schema

### Trainers Table
- discord_user_id (PRIMARY KEY)
- trainer_name, avatar_url
- current_location_id, money
- Social stats: boon_stat, bane_stat, heart_rank/points, insight_rank/points,
  charisma_rank/points, fortitude_rank/points, will_rank/points, stamina_current, stamina_max
- Ranked ladder: rank_tier_name, rank_tier_number, ladder_points, has_promotion_ticket
- following_pokemon_id

### Pokemon Instances Table
- pokemon_id (PRIMARY KEY)
- owner_discord_id, species_dex_number
- nickname, level, exp
- gender, nature, ability, held_item
- current_hp, max_hp, status_condition
- IVs: iv_hp, iv_attack, iv_defense, iv_sp_attack, iv_sp_defense, iv_speed
- EVs: ev_hp, ev_attack, ev_defense, ev_sp_attack, ev_sp_defense, ev_speed
- moves (JSON array)
- friendship, bond_level
- in_party, party_position, box_position
- is_shiny, can_mega_evolve, tera_type

### Other Tables
- inventory (items owned)
- pokedex (seen species)

## 🚀 What to Build Next

### Phase 2: Pokemon Management
- Party/Box swapping
- Pokemon summary screens
- Nickname changing
- Item giving/using
- Following Pokemon system

### Phase 3: Wild Encounters & Catching
- Location-based encounters
- Wild Pokemon generation
- Battle initiation
- Catch mechanics
- Wild Pokemon social interactions

### Phase 4: Battle Engine
- Damage calculation
- Move effects
- Status conditions
- Turn-based combat
- Singles battles

### Phase 5: Advanced Features
- Doubles/Multi battles
- Raid battles
- Ranked ladder
- Quest system
- Shop system
- Travel/Location system

## 💡 Tips for Development

1. **Test Frequently**: After each feature, test it in Discord
2. **Check Database**: Use a SQLite viewer to inspect the database
3. **Error Handling**: The bot will print errors to console
4. **Modular Design**: Each system is separate - easy to expand
5. **Data-Driven**: All Pokemon data is in JSON - easy to modify

## 🐛 Troubleshooting

### Bot doesn't start
- Check your token in `.env`
- Make sure all intents are enabled
- Verify all dependencies are installed

### Commands don't appear
- Wait a few minutes after bot starts
- Try kicking and re-inviting the bot
- Check bot has proper permissions

### Database errors
- Delete `data/players.db` and restart (WARNING: loses all data)
- Check file permissions

### Registration hangs
- Check console for errors
- Make sure all JSON files are in `data/` folder
- Verify Pokemon species data is loaded

## 📝 Notes

- **One Profile Per User**: Discord IDs are locked to one trainer
- **No Legendaries as Starters**: Filtered automatically from species data
- **Social Stats Matter**: They'll affect quests, shops, encounters later
- **Full Pokemon Stats**: Real IV/EV/Nature calculations like main games
- **Data-Driven**: Easy to add custom Pokemon, moves, abilities later

## 🎯 Current Limitations

These are placeholders for future development:
- Wild encounters (Phase 3)
- Battle system (Phase 4)
- Box management (Phase 2)
- Travel system (Phase 5)
- Shop system (Phase 5)
- Quest system (Phase 5)
- Ranked ladder battles (Phase 5)

---

**Ready to test?** Run the bot and try `/register` in your server!

Need help or want to build the next phase? Let me know!
