"""Transparent, historical-data-only football probability baseline.

No LLM guesses. Every computed probability originates from supplied completed
match results. Initial model is a shrinkage/recency-weighted independent Poisson
model; replace it only after a real chronological benchmark improves metrics.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime
from typing import Any

MODEL_VERSION = 'poisson-shrinkage-1.0.0'


def _weighted_avg(rows: list[dict], key: str, at: date, half_life_days: int = 420) -> tuple[float, float]:
    n = 0.0
    s = 0.0
    for r in rows:
        v = r.get(key)
        if v is None:
            continue
        day = date.fromisoformat(r['date'][:10])
        if day >= at:  # NEVER allow current-day or future outcomes
            continue
        w = 0.5 ** ((at - day).days / half_life_days)
        n += w
        s += w * float(v)
    return s, n


def _smoothed(rows: list[dict], key: str, at: date, baseline: float, prior: float = 8.0) -> tuple[float, float]:
    s, n = _weighted_avg(rows, key, at)
    return (s + baseline * prior) / (n + prior), n


def _poisson(lam: float, n: int = 13) -> list[float]:
    p = [math.exp(-lam)]
    for k in range(1, n):
        p.append(p[-1] * lam / k)
    return p


def estimate_rates(matches: list[dict], home: str, away: str, at: date,
                   home_key='hg', away_key='ag') -> dict[str, float] | None:
    earlier = [m for m in matches if date.fromisoformat(m['date'][:10]) < at
               and m.get(home_key) is not None and m.get(away_key) is not None]
    if len(earlier) < 80 or home == away:
        return None
    base_h, _ = _smoothed(earlier, home_key, at, 1.45, prior=20)
    base_a, _ = _smoothed(earlier, away_key, at, 1.15, prior=20)
    home_rows = [r for r in earlier if r['home'] == home]
    away_rows = [r for r in earlier if r['away'] == away]
    return _team_rates(home_rows, away_rows, at, home_key, away_key, base_h, base_a, len(earlier))


def estimate_fixture_rates(matches: list[dict], fixtures: list[tuple[str, str]], at: date) -> dict:
    """Share the league prior and team indexes across fixtures on the same date."""
    cutoff = at.isoformat()
    earlier = [m for m in matches if m['date'][:10] < cutoff and m.get('hg') is not None and m.get('ag') is not None]
    if len(earlier) < 80:
        return {}
    base_h, _ = _smoothed(earlier, 'hg', at, 1.45, prior=20)
    base_a, _ = _smoothed(earlier, 'ag', at, 1.15, prior=20)
    home_rows, away_rows = defaultdict(list), defaultdict(list)
    for row in earlier:
        home_rows[row['home']].append(row)
        away_rows[row['away']].append(row)
    return {(home, away): _team_rates(home_rows[home], away_rows[away], at, 'hg', 'ag', base_h, base_a, len(earlier))
            for home, away in fixtures if home != away}


def _team_rates(home_rows, away_rows, at, home_key, away_key, base_h, base_a, training_matches):
    # require team-specific evidence, not just a league-wide prior
    if len(home_rows) < 4 or len(away_rows) < 4:
        return None
    h_for, h_n = _smoothed(home_rows, home_key, at, base_h)
    h_against, _ = _smoothed(home_rows, away_key, at, base_a)
    a_for, a_n = _smoothed(away_rows, away_key, at, base_a)
    a_against, _ = _smoothed(away_rows, home_key, at, base_h)
    lam_h = min(4.50, max(0.20, h_for * a_against / base_h))
    lam_a = min(4.50, max(0.20, a_for * h_against / base_a))
    return {'home': float(lam_h), 'away': float(lam_a), 'home_samples': len(home_rows),
            'away_samples': len(away_rows), 'effective_home_samples': round(h_n, 1),
            'effective_away_samples': round(a_n, 1), 'training_matches': training_matches}


class ScoreMatrix(list):
    def sum(self):
        return sum(map(sum, self))


def score_matrix(home_goals: float, away_goals: float, max_score: int = 15) -> ScoreMatrix:
    a = _poisson(home_goals, max_score+1)
    b = _poisson(away_goals, max_score+1)
    mass = sum(a) * sum(b)
    return ScoreMatrix([home * away / mass for away in b] for home in a)


def outcome_probabilities(matrix, score_difference=0):
    home = draw = away = 0.0
    for i, row in enumerate(matrix):
        split = min(len(row), max(0, i + score_difference))
        home += sum(row[:split])
        if 0 <= i + score_difference < len(row):
            draw += row[split]
            split += 1
        away += sum(row[split:])
    return {'home': round(home, 5), 'draw': round(draw, 5), 'away': round(away, 5)}


def score_markets(m: ScoreMatrix) -> dict[str, Any]:
    both = sum(sum(row[1:]) for row in m[1:])
    totals = {}
    for line in (0.5, 1.5, 2.5, 3.5, 4.5):
        over = sum(sum(row[max(0, int(line) + 1 - i):]) for i, row in enumerate(m))
        totals[str(line)] = {'over': round(over, 5), 'under': round(1-over, 5)}
    flat = [(i, j, p) for i, row in enumerate(m) for j, p in enumerate(row)]
    top = sorted(flat, key=lambda x: x[2], reverse=True)[:6]
    return {
        'one_x_two': outcome_probabilities(m),
        'btts': {'yes': round(both, 5), 'no': round(1-both, 5)},
        'totals': totals,
        'top_scores': [{'score': f'{i}-{j}', 'p': round(p, 5)} for i, j, p in top]
    }


def _settlement(change: float) -> float:
    return 1.0 if change > 1e-9 else (-1.0 if change < -1e-9 else 0.0)


def _legs(line: float) -> tuple[float, ...]:
    """Split x.25/x.75 into adjacent half-goal lines."""
    n = round(line * 4)
    if abs(n/4-line) > 1e-8:
        raise ValueError('Line must be multiple of 0.25')
    if n % 2 == 0:
        return (n/4,)
    lower = math.floor(line * 2) / 2
    return lower, lower + 0.5


def payout_unit(goals_home: int, goals_away: int, kind: str, selection: str, line: float, decimal_odds: float) -> float:
    """Profit per 1 unit staked; full/half win, push, half/full loss."""
    if decimal_odds <= 1.0:
        raise ValueError('Decimal odds must be > 1.0')
    legs = _legs(line)
    results = []
    for leg in legs:
        if kind == 'handicap':
            if selection not in ('home', 'away'):
                raise ValueError('Handicap selection must be home or away')
            margin = (goals_home-goals_away if selection == 'home' else goals_away-goals_home) + leg
        elif kind == 'total':
            if selection not in ('over', 'under'):
                raise ValueError('Total selection must be over or under')
            margin = (goals_home + goals_away - leg) * (1 if selection == 'over' else -1)
        else:
            raise ValueError('Unsupported market type')
        outcome = _settlement(margin)
        results.append((decimal_odds-1) if outcome > 0 else (-1.0 if outcome < 0 else 0.0))
    return sum(results) / len(results)


def market_ev(matrix: ScoreMatrix, kind: str, selection: str, line: float, decimal_odds: float) -> dict[str, float]:
    if decimal_odds <= 1:
        raise ValueError('Invalid odds')
    win_units = 0.0
    loss_units = 0.0
    ev = 0.0
    full_win = half_win = push = half_loss = full_loss = 0.0
    for i, row in enumerate(matrix):
        for j, p in enumerate(row):
            payoff = payout_unit(i, j, kind, selection, line, decimal_odds)
            ev += p * payoff
            if payoff > 1e-8:
                win_units += p * payoff / (decimal_odds - 1)
                if abs(payoff-(decimal_odds-1)) < 1e-7: full_win += p
                else: half_win += p
            elif payoff < -1e-8:
                loss_units += p * (-payoff)
                if abs(payoff+1) < 1e-7: full_loss += p
                else: half_loss += p
            else: push += p
    fair_odds = 1 + loss_units/win_units if win_units > 1e-10 else None
    return {'ev': round(ev, 6), 'fair_odds': round(fair_odds, 4) if fair_odds else None,
            'full_win': round(full_win, 5), 'half_win': round(half_win, 5),
            'push': round(push, 5), 'half_loss': round(half_loss, 5), 'full_loss': round(full_loss, 5)}


def predict(matches: list[dict], home: str, away: str, at: date, league: str) -> dict | None:
    rows = [m for m in matches if m['league'] == league]
    rates = estimate_rates(rows, home, away, at)
    if rates is None:
        return None
    matrix = score_matrix(rates['home'], rates['away'])
    markets = score_markets(matrix)
    halftime_rows = [r for r in rows if r.get('hthg') is not None and r.get('htag') is not None]
    half = estimate_rates(halftime_rows, home, away, at, 'hthg', 'htag')
    if half:
        markets['first_half'] = score_markets(score_matrix(half['home'], half['away']))
    # Additional count markets: experimental only, never predict without enough records
    experimental = {}
    for name, h, a in [('corners', 'hc', 'ac'), ('yellow_cards', 'hy', 'ay')]:
        filtered = [r for r in rows if r.get(h) is not None and r.get(a) is not None]
        est = estimate_rates(filtered, home, away, at, h, a)
        if est and est['training_matches'] >= 200 and min(est['home_samples'], est['away_samples']) >= 12:
            experimental[name] = {'expected_home': round(est['home'], 2),
                                  'expected_away': round(est['away'], 2),
                                  'status': 'experimental_unvalidated'}
    return {'model': MODEL_VERSION, 'match': {'home': home, 'away': away, 'league': league, 'date': at.isoformat(),
                'is_scheduled_fixture': False}, 'expected_goals': {'home': round(rates['home'], 3), 'away': round(rates['away'], 3)},
            'markets': markets, 'experimental': experimental, 'samples': rates,
            'score_matrix': [[round(float(x), 8) for x in row] for row in matrix],
            'disclaimer': 'Statistical estimate from prior match results; not guaranteed; hypothetical pairing unless backed by a verified fixture.'}
