
import os, json, sqlite3, datetime, argparse

DEFAULT_DB = os.getenv("POKEBOT_DB_PATH", "data/players.db")
DEFAULT_JSON = os.getenv("POKEBOT_ABILITIES_JSON", "data/normalized_abilities.json")

SCHEMA_SQL = """
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
"""

UPSERT_SQL = """
INSERT INTO abilities (id, name, num, gen, rating, is_nonstandard, short_desc, desc, flags_json, hooks_json, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
  name=excluded.name,
  num=excluded.num,
  gen=excluded.gen,
  rating=excluded.rating,
  is_nonstandard=excluded.is_nonstandard,
  short_desc=excluded.short_desc,
  desc=excluded.desc,
  flags_json=excluded.flags_json,
  hooks_json=excluded.hooks_json,
  updated_at=excluded.updated_at;
"""

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def ensure_schema(conn):
    with conn:
        conn.executescript(SCHEMA_SQL)

def upsert_abilities(conn, abilities):
    now = datetime.datetime.utcnow().isoformat()
    rows = []
    for a in abilities:
        rows.append((
            a.get("id"),
            a.get("name"),
            a.get("num"),
            a.get("gen"),
            a.get("rating"),
            a.get("isNonstandard"),
            a.get("shortDesc"),
            a.get("desc"),
            json.dumps(a.get("flags") or []),
            json.dumps(a.get("hooks") or []),
            now
        ))
    with conn:
        conn.executemany(UPSERT_SQL, rows)
    return len(rows)

def main():
    parser = argparse.ArgumentParser(description="Import normalized Showdown abilities into SQLite.")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to SQLite database (default: data/players.db or $POKEBOT_DB_PATH).")
    parser.add_argument("--json", default=DEFAULT_JSON, help="Path to normalized_abilities.json (default: data/normalized_abilities.json or $POKEBOT_ABILITIES_JSON).")
    args = parser.parse_args()

    # Ensure DB directory exists
    os.makedirs(os.path.dirname(args.db) or ".", exist_ok=True)

    conn = sqlite3.connect(args.db)
    try:
        ensure_schema(conn)
        abilities = load_json(args.json)
        count = upsert_abilities(conn, abilities)
        print(f"Imported/updated {count} abilities into {args.db}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
