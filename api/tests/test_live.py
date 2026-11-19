from fastapi.testclient import TestClient
import httpx
import pytest

from football_ai.api import app
from football_ai import live
from football_ai.mania import raw_fixture


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
