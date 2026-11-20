"""Opponent-adjusted scoring rates for covered domestic competitions."""
import math
import json
import re
import unicodedata
from datetime import date
from functools import lru_cache

@lru_cache(maxsize=1)
def rating_data():
    from .strength_data import RATING_JSON

    return json.loads(RATING_JSON)


def team_key(value):
    value = unicodedata.normalize('NFKD', value.casefold())
    value = ''.join(c for c in value if not unicodedata.combining(c))
    words = re.findall(r'[^\W_]+', value)
    return ' '.join(word for word in words if word not in {'fc', 'cf', 'afc', 'sc', 'fk'})


def scoring_rates(home, away, league):
    home_attack, home_defence = home[:2]
    away_attack, away_defence = away[:2]
    return {
        'home': min(4.8, max(0.25, league[0] * math.exp(home_attack + away_defence))),
        'away': min(4.8, max(0.25, league[1] * math.exp(away_attack + home_defence))),
    }


def covered_team_rates(artifact, country, home, away, kickoff):
    if not artifact or not country or not kickoff:
        return None
    as_of = date.fromisoformat(artifact['as_of'])
    age = (date.fromisoformat(kickoff[:10]) - as_of).days
    if not 0 < age <= 365:
        return None
    country_data = artifact['countries'].get(team_key(country), {})
    home_row = country_data.get(team_key(home))
    away_row = country_data.get(team_key(away))
    if not home_row or not away_row or home_row[3] != away_row[3] or min(home_row[2], away_row[2]) < 8:
        return None
    rates = scoring_rates(home_row, away_row, artifact['leagues'][home_row[3]])
    return {**rates, 'home_samples': home_row[2], 'away_samples': away_row[2], 'data_through': artifact['as_of']}
