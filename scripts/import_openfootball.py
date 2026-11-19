"""Import public-domain historical results from openfootball/football.json."""
from datetime import date
from pathlib import Path
import sys

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))
from football_ai.store import insert_matches

LEAGUES = {'en.1': 'E0', 'de.1': 'D1', 'es.1': 'SP1', 'it.1': 'I1', 'fr.1': 'F1'}
SEASONS = ('2024-25', '2025-26', '2026-27')
BASE = 'https://raw.githubusercontent.com/openfootball/football.json/master'


def main():
    failures = []
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        for season in SEASONS:
            for filename, league in LEAGUES.items():
                url = f'{BASE}/{season}/{filename}.json'
                try:
                    response = client.get(url)
                    response.raise_for_status()
                    games = response.json()['matches']
                    rows = []
                    for game in games:
                        score = game.get('score', {})
                        full = score if isinstance(score, list) else score.get('ft')
                        if not full or len(full) != 2 or game['date'] >= date.today().isoformat():
                            continue
                        half = score.get('ht') or [None, None] if isinstance(score, dict) else [None, None]
                        rows.append({'date': game['date'], 'league': league,
                                     'home': game['team1'], 'away': game['team2'],
                                     'hg': full[0], 'ag': full[1],
                                     'hthg': half[0], 'htag': half[1]})
                    inserted = insert_matches(rows, f'openfootball:{season}:{filename}') if rows else 0
                    print(f'{season} {league}: {len(rows)} results, {inserted} added')
                except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                    failures.append(f'{season} {league}: {exc}')
    for failure in failures:
        print(f'Unavailable: {failure}', file=sys.stderr)
    if failures:
        sys.exit(1)


if __name__ == '__main__':
    main()
