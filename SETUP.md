# 🚀 Quick Start Guide - Pokemon Discord Bot

## ✅ What You're Getting

Your **Phase 1: Registration System** is **100% complete and ready to run!**

This includes:
- ✅ `/register` command - Full interactive registration with starter selection
- ✅ `/menu` command - Main menu with party view and trainer card
- ✅ Full Pokemon stat system (IVs, EVs, natures, moves)
- ✅ Social stats system (Boon/Bane selection)
- ✅ SQLite database for player data
- ✅ All game data loaded from JSON files

## 📦 Step 1: Download & Setup

### 1. Extract Files
Extract all files to a folder on your computer (e.g., `pokemon-bot/`)

### 2. Install Python
Make sure you have Python 3.8+ installed:
```bash
python --version
```

### 3. Install Dependencies
Open a terminal in the bot folder and run:
```bash
pip install -r requirements.txt
```

This installs:
- `discord.py` - Discord bot library
- `python-dotenv` - Environment variable management

## 🤖 Step 2: Create Your Discord Bot

### 1. Go to Discord Developer Portal
Visit: https://discord.com/developers/applications

### 2. Create New Application
- Click "New Application"
- Name it (e.g., "Pokemon Bot")
- Click "Create"

### 3. Create Bot User
- Click "Bot" in the left sidebar
- Click "Add Bot"
- Click "Yes, do it!"

### 4. Enable Intents (IMPORTANT!)
In the Bot settings, scroll down to "Privileged Gateway Intents" and enable:
- ✅ Presence Intent
- ✅ Server Members Intent
- ✅ Message Content Intent

Click "Save Changes"

### 5. Copy Bot Token
- Under the "TOKEN" section, click "Reset Token"
- Copy the token (you'll need this in the next step!)
- **IMPORTANT**: Never share this token publicly!

## 🔑 Step 3: Configure Your Bot

### 1. Create .env File
In the bot folder, copy `.env.example` to `.env`:

**Windows:**
```bash
copy .env.example .env
```

**Mac/Linux:**
```bash
cp .env.example .env
```

### 2. Add Your Token
Open the `.env` file and paste your bot token:
```
DISCORD_BOT_TOKEN=your_actual_token_here
```

Save and close the file.

## 🎮 Step 4: Invite Bot to Your Server

### 1. Generate Invite Link
Back in the Discord Developer Portal:
- Click "OAuth2" → "URL Generator"
- Select scopes:
  - ✅ `bot`
  - ✅ `applications.commands`
- Select permissions:
  - ✅ Read Messages/View Channels
  - ✅ Send Messages
  - ✅ Send Messages in Threads
  - ✅ Embed Links
  - ✅ Attach Files
  - ✅ Use Slash Commands

### 2. Invite Bot
- Copy the generated URL at the bottom
- Open it in your browser
- Select your test server
- Click "Authorize"

## ▶️ Step 5: Run the Bot!

### 1. Start the Bot
In your terminal (in the bot folder):
```bash
python pokebot.py
```

### 2. Wait for Success Message
You should see:
```
🔧 Setting up bot...
📚 Loading databases...
✅ All databases loaded!
✅ Loaded cogs.registration_cog
🔄 Syncing commands...
✅ Commands synced!
==================================================
🎮 PokemonBot#1234 is online!
📊 Servers: 1
👥 Users: 5
==================================================
```

## 🎉 Step 6: Test It Out!

### 1. Register as a Trainer
In your Discord server, type:
```
/register
```

You'll see:
1. **Welcome screen** - Click "Begin Registration"
2. **Name entry** - Enter your trainer name and optional avatar URL
3. **Starter selection** - Choose any non-legendary Pokemon from the dropdown
4. **Social stats** - Choose your Boon (strength) and Bane (weakness)
5. **Confirmation** - Review and confirm your choices
6. **Success!** - You're registered!

### 2. Check Your Profile
Type:
```
/menu
```

Click the buttons to:
- 🎒 **Party** - View your starter Pokemon
- 👤 **Trainer Card** - See your full profile with social stats
- Other buttons are placeholders for future features

## 📁 Files You Received

```
pokemon-bot/
├── pokebot.py              # Main bot file - RUN THIS
├── database.py             # Database & data loading
├── models.py               # Pokemon & Trainer classes
├── player_manager.py       # Player data operations
├── encounter_system.py     # Placeholder for future
├── requirements.txt        # Dependencies
├── .env.example           # Token template
├── README.md              # Full documentation
├── SETUP.md               # This file!
│
├── ui/
│   ├── embeds.py          # Discord embeds
│   └── buttons.py         # Interactive buttons
│
├── cogs/
│   ├── registration_cog.py # /register command
│   └── [other cogs]       # Placeholders
│
└── data/
    ├── players.db         # Auto-created when you register
    ├── pokemon_species.json  # All 1000+ Pokemon
    ├── moves.json         # All moves
    ├── abilities.json     # All abilities
    ├── items.json         # All items
    ├── natures.json       # All natures
    └── type_chart.json    # Type effectiveness
```

## ❓ Troubleshooting

### Bot doesn't start
- ✅ Check your token in `.env` is correct
- ✅ Make sure you enabled all 3 intents in Discord Developer Portal
- ✅ Run `pip install -r requirements.txt` again

### Commands don't appear
- ⏰ Wait 1-2 minutes after bot starts
- 🔄 Try typing `/` in Discord to trigger command refresh
- 🎮 Make sure bot has "Use Application Commands" permission

### "Module not found" error
- 📦 Run: `pip install discord.py python-dotenv`
- 🐍 Make sure you're using Python 3.8+

### Registration hangs or fails
- 📊 Check the terminal/console for error messages
- 📁 Make sure all files in `data/` folder exist
- 🔄 Try restarting the bot

## 🎯 What's Next?

You now have a **fully functional registration system**! Players can:
- Create unique trainer profiles
- Choose any non-legendary starter
- Customize their social stats
- View their party and trainer card

### Ready to Build More?

When you're ready for the next phase, we can build:

**Phase 2: Pokemon Management**
- Party/Box swapping
- Pokemon summary screens
- Following Pokemon system

**Phase 3: Wild Encounters**
- Location-based spawns
- Social encounters with wild Pokemon
- Catching mechanics

**Phase 4: Battle Engine**
- Accurate Pokemon battle system
- Singles, Doubles, Multi-battles
- Real damage calculations

**Phase 5: Advanced Features**
- Ranked ladder with promotion matches
- Quest system
- Shop & economy
- Travel system

## 💬 Need Help?

If something isn't working:
1. Check the console/terminal for error messages
2. Verify all steps above were completed
3. Make sure you're in a text channel the bot can see
4. Try restarting the bot

---

**Congratulations! You're ready to start testing your Pokemon bot! 🎮**

Run `/register` in Discord and start your journey!
