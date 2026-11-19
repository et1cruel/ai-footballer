"""Walk-forward backtesting. Predictions are always calculated before match date."""
import math
from datetime import date
from .model import predict, MODEL_VERSION


def evaluate(matches: list[dict], league: str, last_n: int = 100) -> dict:
    history = sorted([m for m in matches if m['league'] == league], key=lambda x: x['date'])
    if len(history) < 120:
        return {'status':'insufficient_data','reason':'Need >=120 recorded matches for chronological evaluation', 'sample_size':0}
    tested = correct = 0
    logloss = brier = baseline_logloss = baseline_brier = 0.0
    skipped = 0
    for m in history[-min(max(1,last_n),150):]:
        day = date.fromisoformat(m['date'])
        # exclude matches on same date as well: we do not know exact kickoff order
        past = [x for x in history if x['date'] < m['date']]
        pred = predict(past, m['home'], m['away'], day, league)
        if pred is None:
            skipped += 1
            continue
        p = pred['markets']['one_x_two']
        outcome = 'home' if m['hg'] > m['ag'] else ('away' if m['hg'] < m['ag'] else 'draw')
        actual = {'home': 0, 'draw': 0, 'away': 0}; actual[outcome] = 1
        logloss -= math.log(max(1e-9, p[outcome]))
        brier += sum((p[k]-actual[k])**2 for k in actual)
        # Historical league frequency baseline with Laplace smoothing (no future scores)
        n_past = len(past)
        base_counts = {'home': 1, 'draw': 1, 'away': 1}
        for old in past:
            k = 'home' if old['hg'] > old['ag'] else ('away' if old['hg'] < old['ag'] else 'draw')
            base_counts[k] += 1
        baseline = {k: v/(n_past+3) for k,v in base_counts.items()}
        baseline_logloss -= math.log(max(1e-9,baseline[outcome]))
        baseline_brier += sum((baseline[k]-actual[k])**2 for k in actual)
        correct += max(p, key=p.get) == outcome
        tested += 1
    if not tested:
        return {'status':'insufficient_data', 'reason':'Too few comparable pre-match predictions', 'sample_size':0, 'skipped':skipped}
    return {'status':'evaluated', 'model': MODEL_VERSION, 'sample_size':tested, 'skipped':skipped,
            'accuracy':round(correct/tested, 4), 'log_loss':round(logloss/tested, 4),
            'brier_multiclass':round(brier/tested, 4),
            'baseline_log_loss':round(baseline_logloss/tested,4),
            'baseline_brier':round(baseline_brier/tested,4),
            'beats_frequency_baseline':bool(logloss < baseline_logloss),
            'method':'chronological walk-forward; match-date prior only; no same-day outcomes'}
