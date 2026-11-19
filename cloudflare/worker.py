"""Cloudflare entrypoint for the existing analysis API and static UI."""
import asyncio
from base64 import b64decode
from datetime import date, datetime, timezone
from pathlib import Path
import sys
from time import monotonic

import httpx
from fastapi import Depends, FastAPI
from workers import asgi

sys.path.insert(0, str(Path(__file__).parent))
from football_ai import api, store
from football_ai.live import _format_fixture
from football_ai.mania import async_live_rows
from football_ai.schedule import LEAGUES, build_analysis
from seed import DATABASE

store.DB_PATH = Path('/tmp/football.sqlite')


async def restore_seed():
    if not store.DB_PATH.is_file():
        store.DB_PATH.write_bytes(b64decode(DATABASE))


app = FastAPI(title='Football AI Intelligence', docs_url='/api/docs', openapi_url='/api/openapi.json',
              redoc_url=None, dependencies=[Depends(restore_seed)])
Default = asgi.entrypoint(app)


@app.get('/api/health')
async def health():
    return api.health()


@app.get('/api/meta')
async def metadata():
    return api.metadata()


@app.get('/api/fixtures')
async def fixtures():
    return api.fixtures()


@app.get('/api/predict')
async def predict(league: str, home: str, away: str, match_date: date | None = None):
    return api.predict_match(league, home, away, match_date)


@app.get('/api/performance')
async def performance(league: str, last_n: int = 100):
    return api.performance(league, last_n)


@app.post('/api/odds/estimate')
async def odds_estimate(params: api.OddsInput):
    return api.odds_estimate(params)


live_cache = None
live_expires = 0.0
live_lock = asyncio.Lock()


@app.get('/api/live-fixtures')
async def live():
    global live_cache, live_expires
    async with live_lock:
        if monotonic() >= live_expires:
            try:
                rows = await async_live_rows()
                history = store.list_matches() if rows else []
                live_cache = {'state': 'ready', 'fixtures': [_format_fixture(row, history) for row in rows],
                              'updated_at': datetime.now(timezone.utc).isoformat(), 'source': 'football_mania'}
            except (httpx.HTTPError, AttributeError, KeyError, TypeError, ValueError):
                live_cache = {'state': 'unavailable', 'fixtures': [], 'updated_at': None, 'source': 'football_mania'}
            live_expires = monotonic() + 60
        return live_cache


schedule_cache = None
schedule_expires = 0.0
schedule_lock = asyncio.Lock()


@app.get('/api/upcoming-analysis')
async def upcoming():
    global schedule_cache, schedule_expires
    async with schedule_lock:
        if monotonic() < schedule_expires:
            return schedule_cache
        today = date.today()
        year = today.year if today.month >= 7 else today.year - 1
        season = f'{year}-{str(year + 1)[-2:]}'
        datasets, failed = {}, []
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            for filename, league in LEAGUES.items():
                try:
                    url = f'https://raw.githubusercontent.com/openfootball/football.json/master/{season}/{filename}.json'
                    response = await client.get(url)
                    response.raise_for_status()
                    datasets[league] = response.json()['matches']
                except (httpx.HTTPError, KeyError, TypeError, ValueError):
                    failed.append(league)
        schedule_cache = build_analysis(datasets, failed, today, store.list_matches())
        schedule_expires = monotonic() + (120 if failed else 1800)
        return schedule_cache
