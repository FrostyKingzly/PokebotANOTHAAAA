-- Dream Dive Gamemode Database Schema
-- This file contains all table definitions for the Dream Dive roguelike mode

-- Main runs table - tracks each Dream Dive run
CREATE TABLE IF NOT EXISTS dream_rogue_runs (
    run_id TEXT PRIMARY KEY,
    session_id TEXT,  -- If started from session mode
    guild_id INTEGER NOT NULL,
    initiator_id INTEGER NOT NULL,

    -- Stage and floor progression
    stage_level INTEGER DEFAULT 10,  -- Base level for this stage (e.g., 10, 20, 30)
    current_floor INTEGER DEFAULT 1,
    starting_floor INTEGER DEFAULT 1,

    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    extracted_at TIMESTAMP,

    -- Floor state
    current_instance_id TEXT,  -- Current instance being processed
    floor_instances_remaining INTEGER DEFAULT 0,  -- Instances left on floor

    -- Map state
    map_data TEXT,  -- JSON map definition for the run
    current_node_id TEXT,  -- Active node in the map

    -- Boss state
    boss_defeated INTEGER DEFAULT 0,

    FOREIGN KEY (initiator_id) REFERENCES trainers(discord_user_id),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

-- Participants in a run
CREATE TABLE IF NOT EXISTS dream_rogue_participants (
    run_id TEXT NOT NULL,
    discord_user_id INTEGER NOT NULL,
    dreamlites INTEGER DEFAULT 100,  -- Starting Dreamlites
    is_ready INTEGER DEFAULT 0,  -- Ready check for floor progression
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (run_id, discord_user_id),
    FOREIGN KEY (run_id) REFERENCES dream_rogue_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (discord_user_id) REFERENCES trainers(discord_user_id)
);

-- Snapshot of party levels/EXP for temporary dive buffs
CREATE TABLE IF NOT EXISTS dream_rogue_party_snapshots (
    run_id TEXT NOT NULL,
    discord_user_id INTEGER NOT NULL,
    pokemon_id TEXT NOT NULL,
    original_level INTEGER NOT NULL,
    original_exp INTEGER NOT NULL,
    original_stored_exp INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (run_id, pokemon_id),
    FOREIGN KEY (run_id) REFERENCES dream_rogue_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (discord_user_id) REFERENCES trainers(discord_user_id)
);

-- Active buffs/curses on participants or teams
CREATE TABLE IF NOT EXISTS dream_rogue_buffs (
    buff_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    buff_type TEXT NOT NULL,  -- 'buff', 'curse', 'domain', 'nightmare'
    buff_name TEXT NOT NULL,
    buff_description TEXT,

    -- Scope
    scope TEXT NOT NULL,  -- 'individual' or 'team'
    target_user_id INTEGER,  -- NULL if team-wide

    -- Effect parameters (JSON)
    effect_data TEXT,  -- JSON object with effect parameters

    -- Duration
    duration TEXT NOT NULL,  -- 'battle', 'floor', 'run', 'permanent'
    battles_remaining INTEGER,
    floors_remaining INTEGER,

    -- Stacking
    is_stackable INTEGER DEFAULT 0,
    stack_count INTEGER DEFAULT 1,

    -- Metadata
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (run_id) REFERENCES dream_rogue_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (target_user_id) REFERENCES trainers(discord_user_id)
);

-- Instance definitions (pre-defined or dynamic)
CREATE TABLE IF NOT EXISTS dream_rogue_instance_templates (
    instance_template_id TEXT PRIMARY KEY,
    instance_name TEXT NOT NULL,
    instance_description TEXT,

    -- Categories (comma-separated tags)
    categories TEXT NOT NULL,  -- 'battle', 'buff', 'curse', 'economy', 'social', 'risk', 'recovery', 'chaos'

    -- Scope
    scope TEXT NOT NULL,  -- 'individual' or 'team'

    -- Risk/Reward
    risk_level TEXT DEFAULT 'medium',  -- 'low', 'medium', 'high'

    -- Requirements
    dreamlite_cost INTEGER DEFAULT 0,
    stamina_cost INTEGER DEFAULT 0,
    star_stat_required TEXT,  -- NULL or 'heart', 'insight', 'charisma', 'fortitude', 'will'
    star_stat_threshold INTEGER,  -- Minimum stat value needed

    -- Effects (JSON)
    effect_data TEXT,  -- JSON object defining what happens

    -- Visibility
    visibility TEXT DEFAULT 'public',  -- 'public' or 'private'

    -- Floor restrictions
    min_floor INTEGER DEFAULT 1,
    max_floor INTEGER,

    -- Metadata
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Active votes for team-wide instances
CREATE TABLE IF NOT EXISTS dream_rogue_votes (
    vote_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    instance_template_id TEXT,  -- Which instance is being voted on
    vote_prompt TEXT NOT NULL,

    -- Vote options (JSON array)
    vote_options TEXT NOT NULL,  -- JSON array of option objects

    -- Vote tracking
    votes TEXT,  -- JSON object mapping user_id -> chosen_option_index

    -- State
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    result_index INTEGER,  -- Which option was chosen

    FOREIGN KEY (run_id) REFERENCES dream_rogue_runs(run_id) ON DELETE CASCADE
);

-- Floor history - track instances completed per floor
CREATE TABLE IF NOT EXISTS dream_rogue_floor_history (
    history_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    floor_number INTEGER NOT NULL,
    instance_template_id TEXT,
    instance_type TEXT NOT NULL,  -- 'battle', 'rest', 'shop', 'event', etc.

    -- Results
    outcome TEXT,  -- 'victory', 'defeat', 'extracted', 'skipped', etc.
    dreamlites_gained INTEGER DEFAULT 0,
    dreamlites_spent INTEGER DEFAULT 0,

    -- Metadata
    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (run_id) REFERENCES dream_rogue_runs(run_id) ON DELETE CASCADE
);

-- Personal dreamlite totals (persistent across runs)
CREATE TABLE IF NOT EXISTS dream_rogue_currency (
    discord_user_id INTEGER PRIMARY KEY,
    total_dreamlites INTEGER DEFAULT 0,
    lifetime_earned INTEGER DEFAULT 0,
    lifetime_spent INTEGER DEFAULT 0,

    FOREIGN KEY (discord_user_id) REFERENCES trainers(discord_user_id)
);

-- Stats and achievements
CREATE TABLE IF NOT EXISTS dream_rogue_stats (
    discord_user_id INTEGER PRIMARY KEY,
    total_runs INTEGER DEFAULT 0,
    successful_extractions INTEGER DEFAULT 0,
    bosses_defeated INTEGER DEFAULT 0,
    highest_floor INTEGER DEFAULT 0,
    total_battles_won INTEGER DEFAULT 0,
    total_battles_lost INTEGER DEFAULT 0,

    -- First completion timestamps
    first_floor_10_clear TIMESTAMP,

    FOREIGN KEY (discord_user_id) REFERENCES trainers(discord_user_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_dream_runs_active ON dream_rogue_runs(is_active, guild_id);
CREATE INDEX IF NOT EXISTS idx_dream_participants_run ON dream_rogue_participants(run_id);
CREATE INDEX IF NOT EXISTS idx_dream_buffs_run ON dream_rogue_buffs(run_id);
CREATE INDEX IF NOT EXISTS idx_dream_buffs_user ON dream_rogue_buffs(run_id, target_user_id);
CREATE INDEX IF NOT EXISTS idx_dream_votes_active ON dream_rogue_votes(run_id, is_active);
CREATE INDEX IF NOT EXISTS idx_dream_floor_history ON dream_rogue_floor_history(run_id, floor_number);
