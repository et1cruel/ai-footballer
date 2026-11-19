from datetime import date, timedelta
from pathlib import Path
from fastapi.testclient import TestClient
from football_ai import store
from football_ai.api import app


def test_public_endpoints_and_admin_security(tmp_path, monkeypatch):
    monkeypatch.setattr(store,'DB_PATH',tmp_path/'isolated.sqlite')
    monkeypatch.delenv('FOOTBALL_ADMIN_TOKEN',raising=False)
    rows=[]
    teams=['A','B','C','D','E','F']
    for i in range(210):
        day=date(2023,1,1)+timedelta(days=i//3*7)
        h=teams[i%6]
        a=teams[(i+1+(i//6)%4)%6]
        if h==a:a=teams[(teams.index(a)+1)%6]
        rows.append({'date':day.isoformat(),'league':'TESTAPI','home':h,'away':a,
                    'hg':i%4,'ag':(i+1)%3,'hthg':i%2,'htag':(i+1)%2})
    assert store.insert_matches(rows,'test-source')>0
    c=TestClient(app)
    assert c.get('/api/health').status_code==200
    assert c.get('/').status_code==200
    assert c.get('/api/meta').json()['match_count']>0
    kwargs={'league':'TESTAPI','home':'A','away':'B','match_date':(date.today()+timedelta(days=1)).isoformat()}
    resp=c.get('/api/predict',params=kwargs)
    assert resp.status_code==200,resp.text
    assert resp.json()['match']['is_scheduled_fixture'] is False
    odds=c.post('/api/odds/estimate',json={**kwargs,'kind':'total','selection':'over','line':2.25,'odds':1.91})
    assert odds.status_code==200,odds.text
    assert 'ev' in odds.json()['results']
    resp=c.post('/api/admin/import-history',files={'file':('x.csv',b'Date,HomeTeam,AwayTeam,FTHG,FTAG\n', 'text/csv')})
    assert resp.status_code==503
    assert c.get('/api/performance',params={'league':'TESTAPI'}).status_code==200
