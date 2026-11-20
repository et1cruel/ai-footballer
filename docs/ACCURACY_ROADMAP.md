# Accuracy research and production readiness

## Live model v4 evaluation

The domestic team ratings are trained from the Football Charts match results
snapshot by Damir Devetak ([dataset and license](https://huggingface.co/datasets/Damir81/football-charts-results-goal-timing),
CC BY 4.0). The distributed ratings are adapted aggregates. Raw matches are not
bundled. Rebuild with `python scripts/train_live_strength.py football_charts_matches.csv --output api/football_ai/strength_data.py`.
The source CSV SHA-256 is `08d1a0863d703550fe6e7fb1ef9faed4ea3cea95c664012373b1a1e1f159be10`.

Predictions only use prior dates. July–December 2025 is validation, and
January–July 2026 is the final walk-forward benchmark. The baseline is the
short-term team form component without injuries, lineups or live events.

| Checkpoint | Matches | Form accuracy | Rated accuracy | Form Brier | Rated Brier |
| --- | ---: | ---: | ---: | ---: | ---: |
| Kickoff | 11,493 | 44.6% | 49.4% | 0.6412 | 0.6110 |
| Half-time | 11,482 | 59.3% | 61.2% | 0.5016 | 0.4887 |

In production, eligible forecasts are recorded alongside the exact previous
model on the same inputs for comparison after full time. The offline benchmark
does not measure performance at other match minutes or in uncovered leagues.

The included model is a well-defined independent-Poisson **baseline**, not a
proven state-of-the-art football predictor. Do not call the website "ultra
accurate" until an untouched prospective test demonstrates improvement.

## Quality gates before real decisions

1. Obtain multiple complete seasons for each intended league with legal rights
   to use the underlying data. Keep sources and timestamp provenance.
2. Separate validation periods from a final untouched time-ordered test set.
3. Compare independent Poisson against Elo, Dixon-Coles, gradient-boosted
   outcomes, xG-derived features, and bookmaker no-vig baselines where legal.
4. Calibrate probabilities and show reliability curves with bin counts.
5. Use walk-forward evaluation grouped by fixture date: no same-day outcomes
   can leak into a fixture when kickoff times are absent.
6. For real fixture integration store **issued_at**, **observed_at**,
   **data_cutoff** and model version for every prediction.
7. Monitor missing-data coverage, team renamings, promoted teams, lineup
   uncertainty, bookmaker-margin distortion, postponements, and odds age.
8. Train specialized card/corner/half-time/live models; their probabilities
   cannot be derived safely from a full-time result model alone.
9. Reject models that do not beat strong simple baselines on proper scores.
10. Deploy only with an authenticated admin job, safe rollback, and original
    predictions immutably stored. Implement and test backups.

## Present features vs. future work

Implemented: local data CSV import; real-data-only 1X2, BTTS, score probability,
O/U, first half where available, experimental corners/cards **means only**,
correct Asian handicap/quarter-total payout math, EV, historical walk-forward
metrics, responsive Thai UI, fixture CSV import and secure admin endpoint.

Not implemented: paid API data ingestion, continuous live odds, fully trained
XGBoost/LightGBM models, calibrated predictions, model registry in live API,
production Supabase synchronization, individual user login/favorites,
cloud Python inference hosting, automated notifications, live predictions.

These require additional development, access credentials, hosting, datasets,
provider terms, and out-of-sample validation. Do not silently relabel them as
complete or substitute generated data for missing data.
