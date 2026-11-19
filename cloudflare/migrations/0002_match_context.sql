CREATE TABLE IF NOT EXISTS match_context (
  id TEXT PRIMARY KEY,
  observed_at TEXT NOT NULL,
  payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS player_profiles (
  id TEXT PRIMARY KEY,
  observed_at TEXT NOT NULL,
  payload TEXT NOT NULL
);
