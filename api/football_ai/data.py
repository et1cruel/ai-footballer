"""CSV adapters for user-supplied Football-Data style match history."""
from __future__ import annotations
from datetime import date
import csv
import io

ALLOWED_LEAGUES = {'E0', 'SP1', 'D1', 'I1', 'F1', 'N1', 'P1', 'B1', 'SC0', 'TR1'}


def parse_history_csv(body: bytes, default_league='E0') -> list[dict]:
    text = body.decode('utf-8-sig', errors='replace')
    reader = csv.DictReader(io.StringIO(text))
    cols = set(reader.fieldnames or [])
    needed = {'Date', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG'}
    if not needed.issubset(cols):
        raise ValueError('CSV missing columns: ' + ', '.join(sorted(needed-cols)))
    result = []
    for r in reader:
        try:
            raw = (r.get('Date') or '').strip()
            parsed = None
            for fmt in ('%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d', '%d/%m/%Y %H:%M', '%d/%m/%y %H:%M'):
                try:
                    parsed = date.fromisoformat(raw) if fmt == '%Y-%m-%d' else __import__('datetime').datetime.strptime(raw, fmt).date()
                    break
                except ValueError:
                    pass
            if parsed is None or parsed > date.today():
                continue
            home, away = (r.get('HomeTeam') or '').strip(), (r.get('AwayTeam') or '').strip()
            if not home or not away or home == away:
                continue
            hg, ag = int(r['FTHG']), int(r['FTAG'])
            if min(hg, ag) < 0 or max(hg, ag) > 30: continue
            match = {'date': parsed.isoformat(), 'league': (r.get('Div') or default_league).strip() or default_league,
                     'home': home, 'away': away, 'hg': hg, 'ag': ag}
            for name, col in [('hthg', 'HTHG'), ('htag', 'HTAG'), ('hc', 'HC'), ('ac', 'AC'), ('hy', 'HY'), ('ay', 'AY')]:
                try:
                    v = int(r[col])
                    match[name] = v if 0 <= v <= 40 else None
                except (TypeError, ValueError, KeyError):
                    match[name] = None
            result.append(match)
        except (ValueError, TypeError, KeyError):
            continue
    return result
