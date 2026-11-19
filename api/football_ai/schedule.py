"""Upcoming match dates from OpenFootball, with historical model estimates."""
from datetime import date, datetime, timedelta, timezone
from threading import Lock
from time import monotonic

import httpx

from .model import predict
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
        history = list_matches()
        history_by_league = {code: [r for r in history if r['league'] == code and not r['source'].startswith('DEMO:')]
                             for code in LEAGUES.values()}
        fixtures, failed = [], []
        with httpx.Client(timeout=8, follow_redirects=True) as client:
            for filename, league in LEAGUES.items():
                try:
                    url = f'https://raw.githubusercontent.com/openfootball/football.json/master/{season}/{filename}.json'
                    response = client.get(url)
                    response.raise_for_status()
                    for game in response.json()['matches']:
                        match_date = date.fromisoformat(game['date'])
                        if not today <= match_date <= today + timedelta(days=14) or game.get('score'):
                            continue
                        home, away = game['team1'], game['team2']
                        rows = history_by_league[league]
                        prediction = predict(rows, home, away, match_date, league)
                        fixtures.append({'league': league, 'date': match_date.isoformat(),
                                         'home': home, 'away': away,
                                         'probabilities': prediction['markets']['one_x_two'] if prediction else None,
                                         'last_result': max((r['date'] for r in rows if r['date'] < match_date.isoformat()), default=None),
                                         'samples': prediction['samples'] if prediction else None})
                except (httpx.HTTPError, KeyError, TypeError, ValueError):
                    failed.append(league)
        _cached = {'fixtures': sorted(fixtures, key=lambda f: (f['date'], f['league'], f['home'])),
                   'failed_leagues': failed, 'updated_at': datetime.now(timezone.utc).isoformat()}
        _expires = monotonic() + (120 if failed else 1800)
        return _cached
