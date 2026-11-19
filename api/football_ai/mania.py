"""Read live fixtures from Football Mania's public LiveScore MCP service."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import re

import httpx

ENDPOINT = 'https://livescoremcp.com/mcp'


def live_rows():
    return asyncio.run(async_live_rows())


@asynccontextmanager
async def mania_session():
    async with httpx.AsyncClient(timeout=5, headers={'Accept': 'application/json, text/event-stream'}) as client:
        init = await client.post(ENDPOINT, json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': '2025-03-26', 'capabilities': {},
            'clientInfo': {'name': 'football-ai-intelligence', 'version': '1'},
        }})
        init.raise_for_status()
        client.headers['MCP-Protocol-Version'] = init.json()['result']['protocolVersion']
        if session_id := init.headers.get('Mcp-Session-Id'):
            client.headers['Mcp-Session-Id'] = session_id
        initialized = await client.post(ENDPOINT, json={'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        initialized.raise_for_status()
        yield client


async def call_tool(client, name, arguments):
    response = await client.post(ENDPOINT, json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {
        'name': name, 'arguments': arguments,
    }})
    response.raise_for_status()
    result = response.json()['result']
    if result.get('isError'):
        raise ValueError(f'Football Mania returned an error for {name}')
    return result


async def async_live_rows():
    async with mania_session() as client:
        try:
            result = await call_tool(client, 'get_live_scores', {'format': 'json', 'timezone': 'UTC'})
            leagues = json.loads(result['content'][0]['text'])
            if not isinstance(leagues, list):
                raise ValueError('Expected a list of leagues')
            return [fixture for league in leagues for group in league['leagues'] for row in group['matches']
                    if (fixture := raw_fixture(row))]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            # The provider caps its raw JSON response. Keep compact scores available
            # when a busy matchday exceeds that cap.
            result = await call_tool(client, 'get_live_scores', {})
            return [_as_fixture(row) for row in result['structuredContent']['matches'] if row.get('state') == 'live']


def raw_score(row):
    score = re.fullmatch(r'(\d+)\s*-\s*(\d+)', str(row.get('scoretime', '')).strip())
    return (int(score[1]), int(score[2])) if score else (None, None)


def _number(value):
    return int(value) if str(value).isascii() and str(value).isdigit() else None


def raw_fixture(row):
    kickoff = datetime.strptime(f"{row['date']} {row['time']}", '%d/%m/%Y %H:%M').replace(tzinfo=timezone.utc)
    status = str(row['status']).strip().upper()
    if status in {'FT', 'AET', 'PEN', 'NS', 'POSTP', 'CANC', 'ABD'}:
        return None
    home_goals, away_goals = raw_score(row)
    fixture = _as_fixture({
        'id': row['id'], 'kickoffUtc': kickoff.isoformat(), 'status': status,
        'competition': row['leaguename'], 'country': row.get('filegroup'),
        'home': row['localteam'], 'away': row['visitorteam'],
        'homeScore': home_goals, 'awayScore': away_goals,
    })
    clock = fixture['fixture']['status']
    if clock['elapsed'] in {45, 90}:
        clock['extra'] = clock['extra'] or _number(row.get('injuryminute'))
        clock['announced'] = _number(row.get('injurytime'))
    fixture['red_cards'] = {'home': _number(row.get('localteamrc')), 'away': _number(row.get('visitorteamrc'))}
    return fixture


def _as_fixture(row):
    raw_status = str(row.get('status', '')).upper().strip()
    clock = re.fullmatch(r"(\d+)(?:\+(\d+))?'?", raw_status)
    minute = int(clock[1]) if clock else None
    extra = int(clock[2]) if clock and clock[2] else None
    status = raw_status if raw_status in {'HT', 'ET', 'BT', 'P', 'SUSP', 'INT'} else 'LIVE'
    if minute is not None and minute <= 90:
        status = '1H' if minute <= 45 else '2H'
    elif minute is not None:
        status = 'ET'
    return {
        'fixture': {'id': row['id'], 'date': row.get('kickoffUtc'),
                    'status': {'short': status, 'elapsed': minute, 'extra': extra}},
        'league': {'name': row['competition'], 'country': row.get('country')},
        'teams': {'home': {'name': row['home']}, 'away': {'name': row['away']}},
        'goals': {'home': row.get('homeScore'), 'away': row.get('awayScore')},
    }
