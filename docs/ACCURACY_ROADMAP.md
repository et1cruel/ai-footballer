# Accuracy research and production readiness

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
