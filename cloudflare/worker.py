"""Cloudflare entrypoint for the existing analysis API and static UI."""
import asyncio
from base64 import b64decode
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
from time import monotonic
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi import Depends, FastAPI
from workers import Response, asgi, fetch, wait_until

sys.path.insert(0, str(Path(__file__).parent))
from football_ai import api, store
from football_ai.live import LIVE_MODEL_VERSION, _format_fixture
from football_ai.mania import async_live_rows
from football_ai.schedule import LEAGUES, build_analysis
from context_feed import load_contexts, refresh_contexts
from ledger import forecast_history, performance as live_performance, record_forecasts, settle_forecasts
from seed import DATABASE

store.DB_PATH = Path('/tmp/football.sqlite')


async def restore_seed():
    if not store.DB_PATH.is_file():
        store.DB_PATH.write_bytes(b64decode(DATABASE))


app = FastAPI(title='Football AI Intelligence', docs_url='/api/docs', openapi_url='/api/openapi.json',
              redoc_url=None, dependencies=[Depends(restore_seed)])


class Default(asgi.entrypoint(app)):
    async def fetch(self, request):
        if request.method == 'GET':
            url = urlsplit(request.url)
            path = url.path
            if path == '/api/live-fixtures':
                await restore_seed()
                snapshot = await live(self.env.FORECASTS)
                if snapshot['state'] == 'ready' and snapshot['fixtures']:
                    wait_until(record_snapshot(self.env.FORECASTS, snapshot))
                return Response.json(snapshot)
            if path == '/api/live-performance':
                return Response.json(await live_performance(self.env.FORECASTS))
            if path == '/api/forecast-history':
                return await forecast_history_response(self.env.FORECASTS, url.query)
            if path == '/api/upcoming-analysis':
                await restore_seed()
                return Response.json(await upcoming())
        return await super().fetch(request)

    async def scheduled(self, controller, env, ctx):
        await restore_seed()
        now = datetime.now(timezone.utc)
        try:
            data = await live(self.env.FORECASTS)
            if data['state'] == 'ready' and data['fixtures']:
                try:
                    await refresh_contexts(self.env.FORECASTS, data['fixtures'], now)
                except (httpx.HTTPError, KeyError, TypeError, ValueError):
                    pass
                data = await live(self.env.FORECASTS, refresh=True)
                await record_snapshot(self.env.FORECASTS, data)
        finally:
            await settle_forecasts(self.env.FORECASTS, now)


async def forecast_history_response(db, query):
    params = parse_qs(query)
    today = datetime.now(timezone(timedelta(hours=7))).date()
    cohort = params.get('cohort', ['all'])[0]
    try:
        day = date.fromisoformat(params.get('date', [today.isoformat()])[0])
    except ValueError:
        return Response.from_json({'detail': 'วันที่ไม่ถูกต้อง'}, status=400)
    if cohort not in {'all', 'win70'} or day < date(2000, 1, 1) or day > today:
        return Response.from_json({'detail': 'ช่วงวันที่หรือชุดคำทายไม่ถูกต้อง'}, status=400)
    return Response.from_json(await forecast_history(db, day, cohort))


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
recorded_snapshot_at = None


async def record_snapshot(db, snapshot):
    global recorded_snapshot_at
    timestamp = snapshot['updated_at']
    if recorded_snapshot_at != timestamp:
        await record_forecasts(db, snapshot['fixtures'], datetime.fromisoformat(timestamp))
        recorded_snapshot_at = timestamp


@app.get('/api/live-fixtures')
async def live_route(env=asgi.env):
    return await live(env.FORECASTS)


async def live(db, refresh=False):
    global live_cache, live_expires
    if not refresh and live_cache is not None and monotonic() < live_expires:
        return live_cache
    # Keep async fetches owned by the current request. Sharing an asyncio lock
    # across Worker requests can strand waiters on another I/O context.
    try:
        rows = await async_live_rows()
        history = store.list_matches() if rows else []
        now = datetime.now(timezone.utc)
        contexts = await load_contexts(db, [str(row['fixture']['id']) for row in rows])
        live_cache = {'state': 'ready', 'fixtures': [
            _format_fixture(row, history, contexts.get(str(row['fixture']['id'])), now) for row in rows],
                      'updated_at': now.isoformat(), 'source': 'football_mania',
                      'model': LIVE_MODEL_VERSION}
    except (httpx.HTTPError, AttributeError, IndexError, KeyError, TypeError, ValueError):
        live_cache = {'state': 'unavailable', 'fixtures': [], 'updated_at': None, 'source': 'football_mania'}
    live_expires = monotonic() + (20 if live_cache['state'] == 'ready' else 5)
    return live_cache


@app.get('/api/live-performance')
async def tracked_live_performance(env=asgi.env):
    return await live_performance(env.FORECASTS)


schedule_cache = None
schedule_expires = 0.0
@app.get('/api/upcoming-analysis')
async def upcoming():
    global schedule_cache, schedule_expires
    if schedule_cache is not None and monotonic() < schedule_expires:
        return schedule_cache
    today = date.today()
    year = today.year if today.month >= 7 else today.year - 1
    season = f'{year}-{str(year + 1)[-2:]}'
    datasets, failed = {}, []
    async def fetch_league(filename, league):
        try:
            url = f'https://raw.githubusercontent.com/openfootball/football.json/master/{season}/{filename}.json'
            response = await fetch(url)
            if not response.ok:
                failed.append(league)
                return
            datasets[league] = (await response.json())['matches']
        except (KeyError, TypeError, ValueError, OSError):
            failed.append(league)

    await asyncio.gather(*(fetch_league(filename, league) for filename, league in LEAGUES.items()))
    schedule_cache = build_analysis(datasets, sorted(failed), today, store.list_matches())
    schedule_expires = monotonic() + (120 if failed else 1800)
    return schedule_cache
