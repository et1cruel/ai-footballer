"""Generate labeled fictional training data ONLY for local UX testing."""
from __future__ import annotations
from datetime import date,timedelta
from pathlib import Path
import random,sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))
from football_ai.store import insert_matches

rng=random.Random(1736)
teams=['Demo Atlas','Demo Orion','Demo Aurora','Demo Falcon','Demo Titan','Demo Phoenix','Demo Nova','Demo Storm']
strength={t: 0.75+0.11*i for i,t in enumerate(teams)}

def draw_poisson(l):
    import math
    v=math.exp(-l); p=1.0; n=0
    while p > v:
        n+=1;p*=rng.random()
    return n-1
rows=[]
for week in range(100):
    shuffled=teams[:];rng.shuffle(shuffled)
    day=date(2023,1,1)+timedelta(days=week*7)
    for i in range(0,len(teams),2):
        h,a=shuffled[i:i+2]; hg=draw_poisson(1.42*strength[h]/strength[a]);ag=draw_poisson(1.10*strength[a]/strength[h])
        rows.append({'date':day.isoformat(),'league':'DEMO','home':h,'away':a,'hg':hg,'ag':ag,
                     'hthg':min(hg,draw_poisson(hg*0.45)), 'htag':min(ag,draw_poisson(ag*0.45)),
                     'hc':draw_poisson(5), 'ac':draw_poisson(4), 'hy':draw_poisson(2), 'ay':draw_poisson(2)})
print('Fictional matches inserted:',insert_matches(rows,'DEMO:generated-fictional-results'))
print('Do not use these data to evaluate actual football prediction accuracy.')
