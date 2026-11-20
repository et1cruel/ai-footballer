CREATE TABLE IF NOT EXISTS live_forecast_reference (
  match_id TEXT NOT NULL,
  model TEXT NOT NULL,
  sample TEXT NOT NULL,
  home_p REAL NOT NULL,
  draw_p REAL NOT NULL,
  away_p REAL NOT NULL,
  pick TEXT,
  PRIMARY KEY (match_id, model, sample),
  FOREIGN KEY (match_id, model, sample) REFERENCES live_forecasts(match_id, model, sample)
);
