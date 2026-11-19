CREATE TABLE IF NOT EXISTS live_matches (
  id TEXT PRIMARY KEY,
  home TEXT NOT NULL,
  away TEXT NOT NULL,
  kickoff TEXT NOT NULL,
  next_check TEXT NOT NULL,
  final_home INTEGER,
  final_away INTEGER,
  confirmed_at TEXT
);

CREATE INDEX IF NOT EXISTS live_matches_due
  ON live_matches(next_check) WHERE confirmed_at IS NULL;

CREATE TABLE IF NOT EXISTS live_forecasts (
  match_id TEXT NOT NULL REFERENCES live_matches(id),
  model TEXT NOT NULL,
  sample TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  minute INTEGER NOT NULL,
  extra INTEGER,
  home_goals INTEGER NOT NULL,
  away_goals INTEGER NOT NULL,
  basis TEXT NOT NULL,
  red_home INTEGER,
  red_away INTEGER,
  home_p REAL NOT NULL,
  draw_p REAL NOT NULL,
  away_p REAL NOT NULL,
  pick TEXT,
  pick_p REAL NOT NULL,
  baseline_home REAL NOT NULL,
  baseline_draw REAL NOT NULL,
  baseline_away REAL NOT NULL,
  PRIMARY KEY (match_id, model, sample)
);

CREATE INDEX IF NOT EXISTS live_forecasts_observed
  ON live_forecasts(model, observed_at DESC);
