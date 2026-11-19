CREATE INDEX IF NOT EXISTS live_forecasts_by_observation
  ON live_forecasts(observed_at);
