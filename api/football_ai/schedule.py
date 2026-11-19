"""Upcoming match dates from OpenFootball, with historical model estimates."""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from threading import Lock
from time import monotonic

import httpx

from .model import estimate_fixture_rates, outcome_probabilities, score_matrix
from .store import list_matches

LEAGUES = {'en.1': 'E0', 'de.1': 'D1', 'es.1': 'SP1', 'it.1': 'I1', 'fr.1': 'F1'}
_lock = Lock()
_cached = None
_expires = 0.0


def upcoming():
    global _cached, _expires
    with _lock:
        if _cached is not None and monotonic() < _expires:
            return _cached
        today = date.today()
        year = today.year if today.month >= 7 else today.year - 1
        season = f'{year}-{str(year + 1)[-2:]}'
        datasets, failed = {}, []
        with httpx.Client(timeout=8, follow_redirects=True) as client:
            for filename, league in LEAGUES.items():
                try:
                    url = f'https://raw.githubusercontent.com/openfootball/football.json/master/{season}/{filename}.json'
                    response = client.get(url)
                    response.raise_for_status()
                    datasets[league] = response.json()['matches']
                except (httpx.HTTPError, KeyError, TypeError, ValueError):
                    failed.append(league)
        _cached = build_analysis(datasets, failed, today, list_matches())
        _expires = monotonic() + (120 if failed else 1800)
        return _cached


def build_analysis(datasets, failed, today, history):
    fixtures = []
    for league, games in datasets.items():
        rows = [r for r in history if r['league'] == league and not r['source'].startswith('DEMO:')]
        by_day = defaultdict(list)
        for game in games:
            match_date = date.fromisoformat(game['date'])
            if not today <= match_date <= today + timedelta(days=14) or game.get('score'):
                continue
            by_day[match_date].append((game['team1'], game['team2']))
        for match_date, pairs in by_day.items():
            date_text = match_date.isoformat()
            last_result = max((r['date'] for r in rows if r['date'] < date_text), default=None)
            day_rates = estimate_fixture_rates(rows, pairs, match_date)
            for home, away in pairs:
                rates = day_rates.get((home, away))
                probabilities = outcome_probabilities(score_matrix(rates['home'], rates['away'])) if rates else None
                fixtures.append({'league': league, 'date': date_text, 'home': home, 'away': away,
                                 'probabilities': probabilities, 'last_result': last_result, 'samples': rates})
    return {'fixtures': sorted(fixtures, key=lambda f: (f['date'], f['league'], f['home'])),
            'failed_leagues': failed, 'updated_at': datetime.now(timezone.utc).isoformat()}
