"""API-Football live fixtures and score-and-clock probabilities for regulation time."""
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
import os

import httpx

from .model import score_matrix, estimate_rates, outcome_probabilities
from .store import list_matches
from .mania import live_rows


ESTIMATE_STATUSES = {'1H', 'HT', '2H'}
LIVE_FIXTURES_URL = 'https://v3.football.api-sports.io/fixtures'
_lock = Lock()
_snapshot = None
_next_attempt = 0.0


def regulation_probabilities(home_goals, away_goals, minute, status, rates=None):
    """Use equal scoring rates when there is no verified team-strength input."""
    if status not in ESTIMATE_STATUSES:
        return None
    if status == 'HT':
        minute = 45
    if (type(minute) is not int or minute < 0 or type(home_goals) is not int
            or type(away_goals) is not int or min(home_goals, away_goals) < 0):
        return None

    # The feed reports regulation minute and stoppage separately. Keep some time
    # remaining in the model while the provider still reports the half in play.
    if status == '1H':
        minute = min(minute, 45)
    remaining = max(1, 90 - minute) / 90
    home_rate = rates['home'] if rates else 1.3
    away_rate = rates['away'] if rates else 1.3
    matrix = score_matrix(home_rate * remaining, away_rate * remaining)
    return outcome_probabilities(matrix, home_goals - away_goals)


def _format_fixture(row, history=None):
    fixture = row['fixture']
    status = fixture['status']['short']
    minute = fixture['status'].get('elapsed')
    home_goals = row['goals']['home']
    away_goals = row['goals']['away']
    home = row['teams']['home']['name']
    away = row['teams']['away']['name']
    eligible = [match for match in (history or []) if not match['source'].startswith('DEMO:')]
    leagues = {match['league'] for match in eligible if home in (match['home'], match['away'])}
    leagues &= {match['league'] for match in eligible if away in (match['home'], match['away'])}
    rates = None
    if len(leagues) == 1 and fixture.get('date'):
        league = next(iter(leagues))
        match_date = datetime.fromisoformat(fixture['date'].replace('Z', '+00:00')).date()
        rates = estimate_rates([match for match in eligible if match['league'] == league], home, away, match_date)
    return {
        'id': fixture['id'],
        'league': row['league']['name'],
        'country': row['league'].get('country'),
        'home': row['teams']['home']['name'],
        'away': row['teams']['away']['name'],
        'status': status,
        'minute': minute,
        'extra': fixture['status'].get('extra'),
        'home_goals': home_goals,
        'away_goals': away_goals,
        'probabilities': regulation_probabilities(home_goals, away_goals, minute, status, rates),
        'basis': 'team_history' if rates else 'equal_rates',
    }


def live_fixtures():
    key = os.getenv('API_FOOTBALL_KEY', '').strip()
    source = 'api_football' if key else 'football_mania'

    global _snapshot, _next_attempt
    with _lock:
        if _snapshot is None or _snapshot['source'] != source or monotonic() >= _next_attempt:
            try:
                if key:
                    response = httpx.get(LIVE_FIXTURES_URL, params={'live': 'all'},
                                         headers={'x-apisports-key': key}, timeout=5)
                    response.raise_for_status()
                    payload = response.json()
                    if payload.get('errors') or not isinstance(payload.get('response'), list):
                        raise ValueError('Live fixture feed unavailable')
                    rows = payload['response']
                else:
                    rows = live_rows()
                history = list_matches() if rows else []
                _snapshot = {
                    'state': 'ready',
                    'fixtures': [_format_fixture(row, history) for row in rows],
                    'updated_at': datetime.now(timezone.utc).isoformat(),
                    'source': source,
                }
            except (httpx.HTTPError, AttributeError, KeyError, TypeError, ValueError):
                _snapshot = {
                    'state': 'unavailable',
                    'fixtures': [],
                    'updated_at': None,
                    'source': source,
                }
            _next_attempt = monotonic() + (900 if key else 60)
        return _snapshot
