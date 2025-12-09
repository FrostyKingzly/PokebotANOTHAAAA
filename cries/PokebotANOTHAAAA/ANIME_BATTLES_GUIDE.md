# 🔥 ANIME BATTLE SYSTEM - SETUP GUIDE

## What's New?

Your Pokemon bot now has **anime-style battles**! Players can type natural language commands like:
- "Pikachu, use Thunderbolt!"
- "Dodge!"
- "Hit it with Flamethrower!"

The bot uses **OpenAI GPT-4o-mini** to generate dramatic, anime-style battle narration!

---

## 🚀 Quick Setup

### Step 1: Get an OpenAI API Key

1. Go to [https://platform.openai.com/](https://platform.openai.com/)
2. Sign up or log in
3. Go to **API Keys** section
4. Click **"Create new secret key"**
5. Copy the key (it starts with `sk-...`)

### Step 2: Add API Key to Your .env File

Open your `.env` file and add:

```
DISCORD_BOT_TOKEN=your_discord_token_here
OPENAI_API_KEY=sk-your_openai_key_here
```

**Important:** Keep this key secret! Never share it or commit it to GitHub!

### Step 3: Install New Dependencies

```bash
pip install -r requirements.txt
```

This will install the `openai` package.

### Step 4: Copy New Files to Your Project

Copy these new files to your project folder:
- `anime_battle_engine.py` (core battle system)
- `wild_cog.py` (Discord cog for wild battles)

### Step 5: Restart Your Bot

```bash
python pokebot.py
```

---

## 💰 Cost Information

**OpenAI GPT-4o-mini Pricing:**
- Input: $0.15 per 1M tokens (~$0.00015 per 1000 tokens)
- Output: $0.60 per 1M tokens (~$0.0006 per 1000 tokens)

**Per Battle Turn:**
- Input: ~500 tokens (battle state, move data, Pokemon info)
- Output: ~150 tokens (narration)
- **Cost: ~$0.00016 per turn** (less than 1/50th of a penny!)

**Per Full Battle:** (~15 turns average)
- **Cost: ~$0.0024** (less than 1/4 of a penny!)

**Monthly Cost Estimate:**
- 100 active users × 10 battles each = 1,000 battles
- **Total: ~$2.40/month** 🎉

*Extremely affordable!*

---

## 🎮 How to Use

### Starting a Wild Battle

1. Use `/wild` command
2. A random wild Pokemon appears!
3. Battle starts automatically

### During Battle

**Option 1: Natural Language Commands** (Recommended!)
Type in chat:
- `"Pikachu, use Thunderbolt!"`
- `"Use Flamethrower!"`
- `"Dodge!"`
- `"Hit it with Quick Attack!"`

**Option 2: Buttons**
- ⚔️ **Fight** - Prompts you to type a command
- 🎒 **Bag** - (Coming soon)
- ⚪ **Pokéball** - (Coming soon)
- 🏃 **Run** - Flee from battle

### Example Battle Flow

```
Bot: A wild Charizard (Lv. 8) appeared!
You: Pikachu, use Thunderbolt!

Bot: 🎬 Pikachu's cheeks sparked with electricity as it gathered power! 
A massive bolt of lightning erupted from its body, striking Charizard 
with tremendous force! The Flying-type Pokemon cried out as the 
super-effective attack coursed through its body!

💥 45 damage! It's super effective!
HP: 32/77

Wild Charizard: The wild Charizard retaliated with a fierce 
Flamethrower attack!

You: Dodge!

Bot: 💨 With incredible speed, Pikachu darted to the side, 
narrowly avoiding the blazing flames!
```

---

## 🎯 Features Implemented

### ✅ Working Now
- Natural language command parsing
- AI-generated battle narration
- Damage calculation (accurate Pokemon formula)
- Type effectiveness
- Critical hits
- Dodge/evasion mechanic (speed-based)
- Turn priority system
- Wild Pokemon AI
- Battle state management
- Win/loss detection

### 🚧 Coming Soon (Phase 2)
- Pokeball throwing & catching
- Bag/item usage during battle
- Status conditions (BRN, PAR, SLP, etc.)
- Abilities & held items
- Stat modifiers
- Weather & terrain
- Multi-turn moves
- Trainer battles (PvP & NPC)

---

## 📖 Command Parsing Examples

The bot can understand many different phrasings:

| What You Type | Bot Understands |
|---------------|-----------------|
| "Pikachu, use Thunderbolt!" | Uses Thunderbolt |
| "Use Thunderbolt!" | Uses Thunderbolt |
| "Thunderbolt!" | Uses Thunderbolt |
| "Hit it with Thunderbolt!" | Uses Thunderbolt |
| "Attack with Thunderbolt!" | Uses Thunderbolt |
| "Dodge!" | Attempts dodge |
| "Evade!" | Attempts dodge |
| "Get out of the way!" | Attempts dodge |

The parser is **fuzzy** - it can handle:
- Partial matches: "extreme" will match "Extreme Speed"
- Case insensitive: "THUNDERBOLT" = "thunderbolt" = "ThunderBolt"
- Different formats: "extremespeed" = "extreme speed" = "extreme-speed"

---

## 🐛 Troubleshooting

### "OPENAI_API_KEY not found"
**Problem:** Bot can't find your OpenAI API key
**Solution:** 
1. Check `.env` file has `OPENAI_API_KEY=sk-...`
2. Make sure `.env` is in same folder as `pokebot.py`
3. Restart the bot

### "Couldn't understand that command"
**Problem:** Bot couldn't parse your command
**Solution:**
- Make sure you're using a move your Pokemon knows
- Try simpler phrasing: just type the move name
- Check the move list shown in battle embed

### API Rate Limits
**Problem:** OpenAI API request failed
**Solution:**
- Wait a few seconds and try again
- Check your OpenAI account has billing set up
- The bot has fallback narration if API fails

### Battle Stuck/Frozen
**Problem:** Battle isn't progressing
**Solution:**
- Wait 60 seconds - battle will timeout
- Use `/wild` to start a new battle
- Contact admin if issue persists

---

## 🔧 Technical Details

### Architecture

```
Player types command
    ↓
CommandParser extracts move/action
    ↓
Battle engine determines turn order (priority → speed)
    ↓
DamageCalculator computes damage (Pokemon formula)
    ↓
AIBattleNarrator generates description (OpenAI API)
    ↓
Results displayed to player
    ↓
Check for battle end
```

### Files Structure

```
pokemon-bot/
├── anime_battle_engine.py    # Core battle logic
│   ├── CommandParser          # Parses "use Thunderbolt!"
│   ├── DamageCalculator       # Pokemon damage formula
│   ├── DodgeSystem            # Dodge mechanics
│   ├── AIBattleNarrator       # OpenAI integration
│   └── AnimeBattleEngine      # Main engine
│
├── wild_cog.py                # Discord commands
│   ├── /wild command          # Start battles
│   ├── WildBattleView         # Battle buttons
│   └── Command listening      # Natural language input
│
└── [existing files...]
```

### Dodge Mechanics

Dodge chance is based on Pokemon Speed:
- Base chance: 30% at Speed 50
- Max chance: 70% at Speed 150+
- **Consecutive dodges:** Each dodge in a row reduces chance by 50%
  - 1st dodge: Normal chance
  - 2nd dodge: 50% of normal
  - 3rd dodge: 25% of normal
- Using an attack resets the counter

---

## 🎨 AI Narration Examples

The AI generates unique narration every time! Here are some examples:

**Thunderbolt (Super Effective):**
> "Pikachu's cheeks crackled with electricity, the energy building to a crescendo! With a determined cry, it unleashed a devastating bolt of lightning that struck Charizard directly, the Flying-type's wings seizing up as electricity coursed through its body!"

**Dodge (Successful):**
> "With lightning-fast reflexes, Pikachu leaped into the air just as the flames roared past beneath it, landing gracefully as the attack dissipated harmlessly!"

**Critical Hit:**
> "Lucario's aura blazed to life around its paws! It surged forward with blinding speed, its fist connecting with perfect precision right in Charizard's center of mass - a devastating blow that sent shockwaves through the air!"

---

## 📊 Performance

- **Turn processing:** ~1-2 seconds
- **API latency:** ~0.5-1.5 seconds
- **Command parsing:** Instant
- **Damage calculation:** Instant

The slowest part is waiting for OpenAI's response, but this actually adds dramatic tension! 🎬

---

## 🔮 Future Enhancements

### Phase 2: Full Battle System
- Status conditions with AI narration
- Abilities triggering with descriptions
- Weather/terrain effects
- Multi-turn moves (Dig, Fly, etc.)

### Phase 3: Trainer Battles
- PvP with both players typing commands
- NPC trainers with personality-based AI
- Promotion matches with special narration

### Phase 4: Advanced Features
- Mega Evolution with transformation narration
- Z-Moves with epic descriptions
- Dynamax battles
- Custom moves with user-defined effects

---

## ❓ FAQ

**Q: Can I use this without OpenAI?**
A: Yes! The bot has fallback narration if API fails. But you'll miss out on the amazing AI descriptions.

**Q: Can players battle each other?**
A: Not yet! PvP is Phase 3. For now it's just wild battles.

**Q: Do abilities and items work?**
A: Not yet! Phase 2 will add these mechanics.

**Q: Can I customize the AI narration style?**
A: Yes! Edit the prompt in `anime_battle_engine.py` → `AIBattleNarrator.narrate_move()`

**Q: Is the damage calculation accurate?**
A: Yes! It uses the real Pokemon Gen 8+ damage formula with STAB, type effectiveness, critical hits, etc.

**Q: Can I turn off AI narration to save costs?**
A: Yes! You can modify the code to use only the fallback templates. Or just don't set the API key.

---

## 🎉 You're Ready!

Your bot now has anime-style battles! Players can:
1. Use `/wild` to start a battle
2. Type natural commands like "Pikachu, use Thunderbolt!"
3. Experience AI-generated battle narration
4. Use dodge mechanics for extra strategy

**Test it out and enjoy!** 🔥

---

## 📞 Need Help?

If you run into issues:
1. Check the bot console for error messages
2. Verify your OpenAI API key is correct
3. Make sure you installed `openai` package
4. Check that your Pokemon have moves in their moveset

**Happy battling!** ⚔️
