"""Read live fixtures from Football Mania's public LiveScore MCP service."""
import re

import httpx

ENDPOINT = 'https://livescoremcp.com/mcp'


def live_rows():
    with httpx.Client(timeout=5, headers={'Accept': 'application/json, text/event-stream'}) as client:
        init = client.post(ENDPOINT, json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': '2025-03-26', 'capabilities': {},
            'clientInfo': {'name': 'football-ai-intelligence', 'version': '1'},
        }})
        init.raise_for_status()
        client.headers['MCP-Protocol-Version'] = init.json()['result']['protocolVersion']
        if session_id := init.headers.get('Mcp-Session-Id'):
            client.headers['Mcp-Session-Id'] = session_id
        client.post(ENDPOINT, json={'jsonrpc': '2.0', 'method': 'notifications/initialized'}).raise_for_status()
        response = client.post(ENDPOINT, json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {
            'name': 'get_live_scores', 'arguments': {},
        }})
        response.raise_for_status()
        result = response.json()['result']
        if result.get('isError') or not isinstance(result['structuredContent']['matches'], list):
            raise ValueError('LiveScore MCP returned no match list')
        return [_as_fixture(row) for row in result['structuredContent']['matches'] if row.get('state') == 'live']


def _as_fixture(row):
    raw_status = str(row.get('status', '')).upper().strip()
    clock = re.fullmatch(r"(\d+)(?:\+(\d+))?'?", raw_status)
    minute = int(clock[1]) if clock else None
    extra = int(clock[2]) if clock and clock[2] else None
    status = raw_status if raw_status in {'HT', 'ET', 'BT', 'P', 'SUSP', 'INT'} else 'LIVE'
    if minute is not None and minute <= 90:
        status = '1H' if minute <= 45 else '2H'
    return {
        'fixture': {'id': row['id'], 'date': row.get('kickoffUtc'),
                    'status': {'short': status, 'elapsed': minute, 'extra': extra}},
        'league': {'name': row['competition'], 'country': row.get('country')},
        'teams': {'home': {'name': row['home']}, 'away': {'name': row['away']}},
        'goals': {'home': row.get('homeScore'), 'away': row.get('awayScore')},
    }
