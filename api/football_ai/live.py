"""API-Football live fixtures and score-and-clock probabilities for regulation time."""
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
import os

import httpx

from .model import score_matrix, estimate_rates, outcome_probabilities
from .store import list_matches
from .mania import live_rows
from .match_context import match_rates
from .team_strength import covered_team_rates, rating_data


ESTIMATE_STATUSES = {'1H', 'HT', '2H'}
LIVE_MODEL_VERSION = 'poisson-live-4'
LIVE_FIXTURES_URL = 'https://v3.football.api-sports.io/fixtures'
_lock = Lock()
_snapshot = None
_next_attempt = 0.0


def regulation_probabilities(home_goals, away_goals, minute, status, rates=None, *,
                             extra=None, announced=None, red_cards=None, second_half_share=None):
    """Use equal scoring rates when there is no verified team-strength input."""
    if status not in ESTIMATE_STATUSES:
        return None
    if status == 'HT':
        minute = 45
    if (type(minute) is not int or minute < 0 or type(home_goals) is not int
            or type(away_goals) is not int or min(home_goals, away_goals) < 0):
        return None

    # Include only the unexpired portion of announced stoppage from this half.
    stoppage_left = max(0, (announced or 0) - (extra or 0)) if minute in {45, 90} and status != 'HT' else 0
    if status == '1H':
        minute = min(minute, 45)
    remaining = max(1, 90 - minute + stoppage_left) / 90
    if second_half_share is not None:
        if status == '1H':
            remaining = second_half_share + (1 - second_half_share) * (45 - minute + stoppage_left) / 45
        else:
            remaining = max(1, 90 - minute + stoppage_left) * second_half_share / 45
    home_rate = rates['home'] if rates else 1.3
    away_rate = rates['away'] if rates else 1.3
    if red_cards:
        # Conservative provisional adjustment. Compare it with the clock-only
        # baseline on the same fixtures before claiming an accuracy gain.
        deficit = (red_cards.get('home') or 0) - (red_cards.get('away') or 0)
        home_rate *= 0.80 ** max(0, deficit) * 1.10 ** max(0, -deficit)
        away_rate *= 0.80 ** max(0, -deficit) * 1.10 ** max(0, deficit)
    matrix = score_matrix(home_rate * remaining, away_rate * remaining)
    return outcome_probabilities(matrix, home_goals - away_goals)


def _format_fixture(row, history=None, context=None, now=None):
    fixture = row['fixture']
    clock = fixture['status']
    status, minute = clock['short'], clock.get('elapsed')
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
    extra, announced = clock.get('extra'), clock.get('announced')
    reds = row.get('red_cards')
    basis = 'team_history' if rates else 'equal_rates'
    factors = []
    fresh_context = False
    if context and now:
        observed = datetime.fromisoformat(context['observed_at'])
        fresh_context = 0 <= (now - observed).total_seconds() <= 180
        rates, factors = match_rates(context, rates, (home_goals, away_goals), fresh_context)
    clock_args = {'extra': extra, 'announced': announced, 'red_cards': reds}
    reference = regulation_probabilities(home_goals, away_goals, minute, status, rates, **clock_args)
    artifact = rating_data()
    rated = covered_team_rates(artifact, row['league'].get('country'), home, away, fixture.get('date'))
    if rated:
        rates = rated
        factors = []
        if context and now:
            rates, factors = match_rates(context, rates, (home_goals, away_goals), fresh_context, use_team_form=False)
        probabilities = regulation_probabilities(home_goals, away_goals, minute, status, rates,
                                                  second_half_share=artifact['second_half_share'], **clock_args)
        basis = 'opponent_adjusted'
    else:
        probabilities = reference
    return {
        'id': fixture['id'],
        'kickoff': fixture.get('date'),
        'league': row['league']['name'],
        'country': row['league'].get('country'),
        'home': row['teams']['home']['name'],
        'away': row['teams']['away']['name'],
        'status': status,
        'minute': minute,
        'extra': extra,
        'announced_stoppage': announced,
        'red_cards': reds,
        'home_goals': home_goals,
        'away_goals': away_goals,
        'probabilities': probabilities,
        'reference_probabilities': reference if rated else None,
        'rating_evidence': {key: rated[key] for key in ('home_samples', 'away_samples', 'data_through')} if rated else None,
        'basis': basis,
        'factors': factors,
        'context': {**context, 'live_fresh': fresh_context} if context else None,
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
