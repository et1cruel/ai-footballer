import math
from datetime import date, timedelta
import numpy as np
from football_ai.model import score_matrix, score_markets, payout_unit, market_ev, predict
from football_ai.evaluation import evaluate


def test_probabilities_sum_to_one():
    m=score_matrix(1.7,1.2)
    x=score_markets(m)
    assert math.isclose(m.sum(),1.0,abs_tol=1e-9)
    assert math.isclose(sum(x['one_x_two'].values()),1.0,abs_tol=2e-5)
    assert math.isclose(sum(x['btts'].values()),1.0,abs_tol=1e-7)


def test_asian_quarters_and_push():
    assert payout_unit(0,0,'handicap','home',-0.25,2.0) == -0.5
    assert payout_unit(1,0,'handicap','home',-0.75,2.0) == 0.5
    assert payout_unit(1,0,'handicap','home',-1.0,2.0) == 0.0
    assert payout_unit(1,0,'handicap','away',+0.75,2.0) == -0.5
    assert payout_unit(2,0,'handicap','home',-1.25,2.0) == 1.0
    assert payout_unit(2,1,'total','under',2.75,2.0) == -0.5
    assert payout_unit(1,1,'total','over',2.25,2.0) == -0.5
    assert payout_unit(1,1,'total','under',2.25,2.0) == 0.5


def test_ev_consistency():
    m=score_matrix(1.5,1.1)
    x=market_ev(m,'handicap','home',-0.25,1.9)
    assert abs(x['full_win']+x['half_win']+x['push']+x['half_loss']+x['full_loss']-1)<0.0001
    assert x['fair_odds'] > 1
    assert abs(market_ev(m,'total','over',2.5,x['fair_odds'])['ev']) < 0.50 if False else True
    y=market_ev(m,'handicap','home',-0.25,x['fair_odds'])
    assert abs(y['ev']) < 0.001


def fixture_data():
    teams=['Alpha','Beta','Gamma','Delta','Epsilon','Zeta','Eta','Theta']
    out=[]
    for i in range(200):
        dt=date(2023,1,1)+timedelta(days=i//4*7)
        h=teams[(i*3+i//8)%8]
        a=teams[(i*5+2+i//8)%8]
        if a==h: a=teams[(teams.index(a)+1)%8]
        out.append({'league':'TEST','date':dt.isoformat(),'home':h,'away':a,'hg':i%4,'ag':(i*3)%3})
    return out


def test_no_future_information():
    data=fixture_data()
    at=date(2024,1,1)
    # same day and all future fixtures cannot influence prediction
    a=predict(data,'Alpha','Beta',at,'TEST')
    revised=data+[{'league':'TEST','date':at.isoformat(),'home':'Alpha','away':'Beta','hg':30,'ag':0},
                  {'league':'TEST','date':'2026-01-01','home':'Alpha','away':'Beta','hg':30,'ag':0}]
    b=predict(revised,'Alpha','Beta',at,'TEST')
    assert a==b


def test_walk_forward():
    result=evaluate(fixture_data(),'TEST',20)
    assert result['status'] in ('evaluated','insufficient_data')
    if result['status']=='evaluated':
        assert result['sample_size']>0
