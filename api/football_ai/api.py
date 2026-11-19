"""Read-only public football analytics API. Imports require a server-only token."""
from __future__ import annotations
import csv
import io
import os
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / '.env', override=False)
from fastapi import FastAPI, HTTPException, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from .data import parse_history_csv
from .model import predict, score_matrix, market_ev, MODEL_VERSION
from .evaluation import evaluate
from .live import live_fixtures
from .schedule import upcoming
from .store import list_matches, insert_matches, list_fixtures, insert_fixtures

app = FastAPI(title='Football AI Intelligence', version='0.2.0', docs_url='/api/docs')
origins = [x.strip() for x in os.getenv('CORS_ORIGINS','http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000').split(',') if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                   allow_methods=['GET','POST'], allow_headers=['Content-Type','X-Admin-Token'])


def league_data(league: str) -> list[dict]:
    rows = list_matches(league)
    if not rows: raise HTTPException(404, 'No recorded match data for this league')
    return rows


def require_admin(token: str | None) -> None:
    import secrets
    expected = os.getenv('FOOTBALL_ADMIN_TOKEN')
    if not expected:
        raise HTTPException(503, 'Administrative imports disabled: configure FOOTBALL_ADMIN_TOKEN')
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(403, 'Unauthorized')


@app.get('/api/health')
def health():
    return {'status':'ok', 'model':MODEL_VERSION,'server_time_utc':datetime.now(timezone.utc).isoformat()}


@app.get('/api/meta')
def metadata():
    rows = list_matches()
    sources = {r['source'] for r in rows}
    mode = 'empty' if not rows else ('demo_only' if all(x.startswith('DEMO:') for x in sources) else 'real_or_mixed')
    leagues = {}
    for r in rows:
        l = leagues.setdefault(r['league'], {'code':r['league'], 'matches':0, 'teams':set(), 'last_match':r['date']})
        l['matches'] += 1; l['teams'].update((r['home'],r['away']))
        if r['date'] > l['last_match']: l['last_match'] = r['date']
    result = [{**v, 'teams':sorted(v['teams'])} for v in leagues.values()]
    return {'data_mode':mode,'match_count':len(rows),'leagues':sorted(result, key=lambda x:x['code']),
            'fixture_count':len(list_fixtures()), 'model':MODEL_VERSION,
            'warning':'DEMONSTRATION DATA: NOT REAL FOOTBALL RESULTS' if mode=='demo_only' else None}


@app.get('/api/fixtures')
def fixtures():
    today = date.today()
    return {'fixtures':[f for f in list_fixtures() if date.fromisoformat(f['kickoff'][:10]) >= today],
            'notice':'Fixtures appear only after a licensed schedule is imported. No matches are fabricated.'}


@app.get('/api/live-fixtures')
def current_matches():
    return live_fixtures()


@app.get('/api/upcoming-analysis')
def upcoming_analysis():
    return upcoming()


@app.get('/api/predict')
def predict_match(league: str, home: str, away: str, match_date: date | None = None):
    at = match_date or (date.today() + timedelta(days=1))
    if at > date.today() + timedelta(days=365):
        raise HTTPException(422, 'Prediction date too far in the future')
    if len(home)>120 or len(away)>120 or len(league)>24:
        raise HTTPException(422,'Invalid team or league')
    rows = league_data(league)
    value = predict(rows,home,away,at,league)
    if value is None:
        raise HTTPException(422, 'Insufficient prior match data for this pairing/date')
    scheduled = [f for f in list_fixtures() if f['league']==league and f['home']==home and f['away']==away
                 and f['kickoff'][:10]==at.isoformat()]
    if scheduled:
        value['match']['is_scheduled_fixture'] = True
        value['match']['kickoff'] = scheduled[0]['kickoff']
    sources = {r['source'] for r in rows if r['date'] < at.isoformat()}
    value['data_mode'] = 'demo_only' if sources and all(s.startswith('DEMO:') for s in sources) else 'real_or_mixed'
    return value


class OddsInput(BaseModel):
    league: str = Field(min_length=1,max_length=24)
    home: str = Field(min_length=1,max_length=120)
    away: str = Field(min_length=1,max_length=120)
    match_date: date
    kind: str
    selection: str
    line: float = Field(ge=-10, le=15)
    odds: float = Field(gt=1, le=1000)


@app.post('/api/odds/estimate')
def odds_estimate(params: OddsInput):
    if params.kind not in ('handicap', 'total'):
        raise HTTPException(422, 'Market must be handicap or total')
    if params.kind=='handicap' and params.selection not in ('home','away'):
        raise HTTPException(422,'Handicap selection invalid')
    if params.kind=='total' and params.selection not in ('over','under'):
        raise HTTPException(422,'Total selection invalid')
    if abs(params.line*4-round(params.line*4)) > 1e-8:
        raise HTTPException(422,'Only quarter-goal lines supported')
    p = predict(league_data(params.league),params.home,params.away,params.match_date,params.league)
    if p is None: raise HTTPException(422,'Insufficient prior data')
    m = score_matrix(p['expected_goals']['home'],p['expected_goals']['away'])
    return {'model':MODEL_VERSION,'results':market_ev(m,params.kind,params.selection,params.line,params.odds),
            'notice':'Estimated value is not a guarantee. No wager is placed.'}


@app.get('/api/performance')
def performance(league: str, last_n: int = 100):
    if last_n < 1 or last_n > 150:
        raise HTTPException(422,'last_n must be 1–150')
    return evaluate(league_data(league),league,last_n)


@app.post('/api/admin/import-history')
async def import_history(file: UploadFile = File(...), x_admin_token: str | None = Header(default=None)):
    require_admin(x_admin_token)
    body = await file.read(8_000_001)
    if len(body)>8_000_000: raise HTTPException(413,'Maximum upload size 8MB')
    try:
        rows = parse_history_csv(body)
    except ValueError as e:
        raise HTTPException(422,str(e))
    if not rows: raise HTTPException(422,'No valid completed matches')
    return {'parsed':len(rows),'inserted':insert_matches(rows,source='manual-csv-upload')}


@app.post('/api/admin/import-fixtures')
async def import_fixtures(file: UploadFile = File(...), x_admin_token: str | None = Header(default=None)):
    require_admin(x_admin_token)
    body = await file.read(2_000_001)
    if len(body)>2_000_000: raise HTTPException(413,'Max 2MB')
    reader=csv.DictReader(io.StringIO(body.decode('utf-8-sig')))
    if not {'league','kickoff','home','away'}.issubset(set(reader.fieldnames or [])):
        raise HTTPException(422,'CSV needs league,kickoff,home,away')
    result=[]
    for r in reader:
        try:
            kickoff=datetime.fromisoformat(r['kickoff'].strip().replace('Z','+00:00'))
            if kickoff.tzinfo is None: raise ValueError('Timezone required')
            if date.today() - timedelta(days=1) <= kickoff.date() <= date.today()+timedelta(days=365) and r['home']!=r['away']:
                result.append({'league':r['league'].strip(),'kickoff':kickoff.astimezone(timezone.utc).isoformat(),
                               'home':r['home'].strip(),'away':r['away'].strip()})
        except (ValueError, KeyError, AttributeError): continue
    return {'parsed':len(result),'inserted':insert_fixtures(result,'manual-licensed-fixtures')}

# The local single-command experience serves the deployable static frontend too.
from fastapi.staticfiles import StaticFiles
from pathlib import Path
_static = Path(__file__).resolve().parents[2] / 'web'
if _static.is_dir():
    app.mount('/', StaticFiles(directory=str(_static), html=True), name='web')
