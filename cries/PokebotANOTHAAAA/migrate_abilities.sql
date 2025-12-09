
-- Creates the `abilities` table used by the importer. Safe to run multiple times.
CREATE TABLE IF NOT EXISTS abilities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    num INTEGER,
    gen INTEGER,
    rating REAL,
    is_nonstandard TEXT,
    short_desc TEXT,
    desc TEXT,
    flags_json TEXT,
    hooks_json TEXT,
    updated_at TEXT NOT NULL
);
