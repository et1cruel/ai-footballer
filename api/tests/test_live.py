from fastapi.testclient import TestClient
import httpx
import pytest

from football_ai.api import app
from football_ai import live
from football_ai.mania import raw_fixture
from football_ai.match_context import match_context, match_rates
from datetime import date


def test_in_play_probabilities_follow_score_and_clock():
    tied = live.regulation_probabilities(0, 0, 10, '1H')
    early_lead = live.regulation_probabilities(1, 0, 10, '1H')
    late_lead = live.regulation_probabilities(1, 0, 85, '2H')
    assert tied['home'] == tied['away']
    assert late_lead['home'] > early_lead['home'] > tied['home']
    assert sum(late_lead.values()) == pytest.approx(1, abs=0.00002)
    assert live.regulation_probabilities(1, 1, None, 'HT')['draw'] > tied['draw']
    assert live.regulation_probabilities(1, 0, None, 'LIVE') is None
    assert live.regulation_probabilities(1, 0, 110, 'ET') is None


def test_mania_clock_and_red_cards_reach_the_model():
    row = {'id': '1', 'date': '19/11/2026', 'time': '15:00', 'status': '90',
           'localteam': 'Home', 'visitorteam': 'Away', 'scoretime': '1 - 0',
           'leaguename': 'Example', 'injuryminute': '2', 'injurytime': '5', 'localteamrc': 1}
    fixture = live._format_fixture(raw_fixture(row))
    assert fixture['kickoff'] == '2026-11-19T15:00:00+00:00'
    assert fixture['minute'] == 90 and fixture['extra'] == 2
    assert fixture['announced_stoppage'] == 5
    assert fixture['red_cards'] == {'home': 1, 'away': None}
    assert fixture['probabilities']['home'] < live.regulation_probabilities(1, 0, 90, '2H')['home']
    assert live._format_fixture(raw_fixture({**row, 'status': '72'}))['extra'] is None
    assert live._format_fixture(raw_fixture({**row, 'status': '105'}))['probabilities'] is None
    assert raw_fixture({**row, 'status': 'FT'}) is None


def test_match_context_changes_rates_without_using_current_match_as_history():
    def game(i, day, home, away, score):
        return {'id': str(i), 'date': day, 'status': 'FT', 'scoretime': score,
                'gs_localteamid': home, 'gs_visitorteamid': away}

    detail = {
        'gs_localteamid': '1', 'gs_visitorteamid': '2', 'scoretime': '0 - 0',
        'localteamshapefixtures': [game(i, '18/11/2026', '1', '3', '3 - 0') for i in range(3)]
                                 + [game(9, '19/11/2026', '1', '2', '0 - 10')],
        'visitorteamshapefixtures': [game(i, '17/11/2026', '4', '2', '2 - 0') for i in range(3)],
        'lineups': {'localteam': [{'id': 'p1', 'name': 'Home player'}],
                    'visitorteam': [{'id': 'p2', 'name': 'Away player'}]},
        'commentaries': {'playerstats': {
            'localteam': [{'shotsOn': '1'}] * 8, 'visitorteam': [{'shotsOn': '0'}] * 8}},
    }
    past = {
        'home': {**game(1, '18/11/2026', '1', '3', '3 - 0'), 'events': [
            {'team': 'localteam', 'type': 'goal', 'playerId': 'p1'}]},
        'away': {**game(2, '17/11/2026', '4', '2', '2 - 1'), 'events': [
            {'team': 'visitorteam', 'type': 'goal', 'playerId': 'p2'}]},
    }
    context, _ = match_context(detail, date(2026, 11, 19), '2026-11-19T23:00:00+00:00', {}, past)
    assert context['recent_form']['home']['wins'] == 3
    assert context['recent_players']['home']['players'][0]['name'] == 'Home player'
    rates, factors = match_rates(context, None, (0, 0))
    assert rates['home'] > rates['away']
    assert factors == ['team_form', 'player_recent', 'live_shots']
    assert match_rates(context, None, (1, 0))[1] == ['team_form']


def test_live_endpoint_uses_shared_provider_snapshot(monkeypatch):
    monkeypatch.delenv('API_FOOTBALL_KEY', raising=False)
    monkeypatch.setattr(live, '_next_attempt', 0)
    monkeypatch.setattr(live, '_snapshot', None)
    client = TestClient(app)
    monkeypatch.setattr(live, 'live_rows', lambda: [])
    assert client.get('/api/live-fixtures').json()['source'] == 'football_mania'
    monkeypatch.setenv('API_FOOTBALL_KEY', 'test-key')
    calls = []

    def fixture_feed(url, **kwargs):
        calls.append(kwargs['params'])
        return httpx.Response(200, request=httpx.Request('GET', url), json={
            'errors': [],
            'response': [{
                'fixture': {'id': 123, 'status': {'short': '2H', 'elapsed': 85, 'extra': None}},
                'league': {'name': 'Example League', 'country': 'Example Country'},
                'teams': {'home': {'name': 'Home'}, 'away': {'name': 'Away'}},
                'goals': {'home': 0, 'away': 2},
            }],
        })

    monkeypatch.setattr(live.httpx, 'get', fixture_feed)
    first = client.get('/api/live-fixtures').json()
    second = client.get('/api/live-fixtures').json()
    assert first == second
    assert calls == [{'live': 'all'}]
    assert first['state'] == 'ready'
    assert first['fixtures'][0]['probabilities']['away'] > 0.99
