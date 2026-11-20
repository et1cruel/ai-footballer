"""Train with Football Charts match results (CC BY 4.0) and test forward in time.

Data by Damir Devetak / Football Charts, adapted into ratings.
https://huggingface.co/datasets/Damir81/football-charts-results-goal-timing
"""
import argparse
import csv
from collections import Counter, defaultdict
from itertools import groupby
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))
from football_ai.model import outcome_probabilities, score_matrix
from football_ai.team_strength import scoring_rates, team_key


def load(path):
    with open(path, encoding='utf-8-sig', newline='') as stream:
        return sorted(csv.DictReader(stream), key=lambda row: row['match_date'])


def probabilities(rates, score, remaining):
    return outcome_probabilities(score_matrix(rates['home'] * remaining, rates['away'] * remaining, max_score=11), score)


def comparable_form(home, away):
    # Rebuild the existing recent-form signal using only those teams' last five
    # results. Historical replay has no contemporaneous injury or live event data.
    def strength(rows):
        n = len(rows)
        points = (sum(g > a for g, a in rows) + 0.33 * sum(g == a for g, a in rows) + 1.5) / (n + 3)
        margin = sum(g - a for g, a in rows) / (n + 5)
        return points + 0.15 * max(-1.0, min(1.0, margin))
    shift = 0.5 * (strength(home) - strength(away))
    return {'home': 1.3 * math.exp(shift), 'away': 1.3 * math.exp(-shift)}


def run(matches, learning_rate, collect=True):
    ratings = defaultdict(lambda: [0.0, 0.0, 0])
    league_goals = defaultdict(lambda: [145.0, 115.0, 100])
    recent = defaultdict(list)
    latest_league = {}
    stats = defaultdict(Counter)
    first_half_goals = goals = 0
    for day, rows in groupby(matches, key=lambda row: row['match_date']):
        updates = []
        for row in rows:
            country, league = team_key(row['country']), row['league']
            home_key, away_key = [(country, row[key]) for key in ('home_team','away_team')]
            home, away = ratings[home_key], ratings[away_key]
            gh, ga = int(row['home_goals']), int(row['away_goals'])
            try:
                hh, ha = map(int, row['ht_result'].split(':'))
                half = (hh, ha) if 0 <= hh <= gh and 0 <= ha <= ga else None
            except (ValueError, AttributeError):
                half = None
            h, a, n = league_goals[league]
            rates = scoring_rates(home, away, (h / n, a / n))
            observed = 'home' if gh > ga else 'away' if ga > gh else 'draw'
            if collect and min(home[2], away[2]) >= 8 and day >= '2025-07-01':
                period = 'validation' if day < '2026-01-01' else 'holdout'
                start = comparable_form(recent[home_key], recent[away_key])
                phases = [('kickoff', 0, 1.0, 1.0)]
                if half:
                    second_half = (goals - first_half_goals) / goals if goals else 0.55
                    phases.append(('half_time', half[0] - half[1], 0.5, second_half))
                for phase, gap, old_time, new_time in phases:
                    for label, rated, time_share in [('recent_form', start, old_time), ('opponent_adjusted', rates, new_time)]:
                        p = probabilities(rated, gap, time_share)
                        cell = stats[(period, phase, label)]
                        cell['count'] += 1
                        cell['correct'] += max(p, key=p.get) == observed
                        cell['brier'] += sum((v - (k == observed)) ** 2 for k,v in p.items())
                        cell['log_loss'] -= math.log(max(1e-9, p[observed]))
            updates.append((league, row['match_date'], home_key, away_key,
                            gh, ga, gh - rates['home'], ga - rates['away'], half))
        for league, day, home, away, gh, ga, err_h, err_a, half in updates:
            for key, attack_err, defence_err, score in [(home, err_h, err_a, (gh,ga)), (away, err_a, err_h, (ga,gh))]:
                rating = ratings[key]
                rating[0] = max(-1.3, min(1.3, rating[0] * 0.995 + learning_rate * max(-3, min(3, attack_err))))
                rating[1] = max(-1.3, min(1.3, rating[1] * 0.995 + learning_rate * max(-3, min(3, defence_err))))
                rating[2] += 1
                recent[key] = (recent[key] + [score])[-5:]
                latest_league[key] = day, league
            accum = league_goals[league]
            accum[0] += gh
            accum[1] += ga
            accum[2] += 1
            if half:
                first_half_goals += sum(half)
                goals += gh + ga
    report = {'/'.join(key): {**m, 'accuracy': round(m['correct']/m['count'],5),
                             'brier': round(m['brier']/m['count'],5), 'log_loss': round(m['log_loss']/m['count'],5)}
              for key, m in stats.items()}
    countries = defaultdict(dict)
    for (country, name), rating in ratings.items():
        day, league = latest_league[country, name]
        if rating[2] >= 8 and day >= '2025-07-01':
            key = team_key(name)
            entry = countries[country]
            entry[key] = [round(rating[0],4), round(rating[1],4), rating[2], league] if key not in entry else None
    artifact = {'as_of': matches[-1]['match_date'], 'second_half_share': round((goals-first_half_goals)/goals,4),
                'countries': countries, 'leagues': {k:[round(h/n,4), round(a/n,4)] for k,(h,a,n) in league_goals.items()},
                'source': 'Football Charts / Damir Devetak (CC BY 4.0)', 'benchmark': report}
    return artifact


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('matches', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--rate', type=float, default=0.022)
    args = parser.parse_args()
    artifact = run(load(args.matches), args.rate)
    print(json.dumps(artifact['benchmark'], indent=2))
    if args.output:
        data = json.dumps(artifact, ensure_ascii=False, separators=(',', ':'))
        args.output.write_text(
            '# Generated by scripts/train_live_strength.py from Football Charts / Damir Devetak (CC BY 4.0).\n'
            f'RATING_JSON = {data!r}\n', encoding='utf-8')
