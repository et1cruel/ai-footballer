"""Collect optional provider details with a shared, bounded background budget."""
from datetime import datetime, timedelta
import json

import httpx

from football_ai.mania import call_tool, mania_session
from football_ai.match_context import SIDES, historical_games, match_context, team_id


async def load_contexts(db, ids):
    contexts = {}
    for start in range(0, len(ids), 80):
        chunk = ids[start:start + 80]
        slots = ','.join('?' for _ in chunk)
        result = await db.prepare(f'SELECT id, payload FROM match_context WHERE id IN ({slots})').bind(*chunk).all()
        contexts.update((row['id'], json.loads(row['payload'])) for row in result['results'])
    return contexts


async def refresh_contexts(db, fixtures, now):
    eligible = [f for f in fixtures if f['kickoff'] and f['status'] in {'1H', 'HT', '2H'}]
    known = await load_contexts(db, [str(f['id']) for f in eligible])
    eligible.sort(key=lambda f: known.get(str(f['id']), {}).get('observed_at', ''))
    player_budget = 4
    recent_budget = 2
    if not eligible:
        return
    async with mania_session() as client:
        for fixture in eligible[:8]:
            mid = str(fixture['id'])
            before = datetime.fromisoformat(fixture['kickoff'].replace('Z', '+00:00')).date()
            try:
                detail = await provider_json(client, 'get_match', mid, h2h=True, timezone='UTC')
                if str(detail.get('id')) != mid:
                    continue
                _, active = match_context(detail, before, now.isoformat(), {})
                pairs = list(zip(active['home'], active['away']))
                candidates = list(dict.fromkeys(pid for pair in pairs for pid in pair))
                profiles = {}
                if candidates:
                    slots = ','.join('?' for _ in candidates)
                    cached = await db.prepare(f'SELECT id,payload FROM player_profiles WHERE id IN ({slots}) AND observed_at>=?').bind(
                        *candidates, (now - timedelta(days=7)).isoformat()).all()
                    profiles = {row['id']: json.loads(row['payload']) for row in cached['results']}
                missing = [pid for pid in candidates if pid not in profiles]
                for pid in missing[:player_budget]:
                    player_budget -= 1
                    try:
                        profile = await provider_json(client, 'get_player', pid)
                        if str(profile.get('id')) != pid:
                            continue
                        profiles[pid] = {'statistics': profile.get('statistics', [])}
                        await db.prepare('INSERT OR REPLACE INTO player_profiles VALUES (?,?,?)').bind(
                            pid, now.isoformat(), json.dumps(profiles[pid])).run()
                    except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError):
                        continue
                previous = {}
                for side, key in SIDES.items():
                    if not active[side]:
                        continue
                    games = historical_games(detail.get(key + 'shapefixtures'), team_id(detail, key), before)
                    if not games:
                        continue
                    previous_id = games[0][3]
                    cache_key = f'match:{previous_id}'
                    cached_match = await db.prepare('SELECT payload FROM player_profiles WHERE id=?').bind(cache_key).first()
                    if cached_match:
                        previous[side] = json.loads(cached_match['payload'])
                    elif recent_budget:
                        recent_budget -= 1
                        try:
                            prior = await provider_json(client, 'get_match', previous_id, h2h=False, timezone='UTC')
                            if str(prior.get('id')) != previous_id or prior.get('status') != 'FT':
                                continue
                            previous[side] = {k: prior.get(k) for k in
                                              ('date','status','gs_localteamid','gs_visitorteamid','localteamid','visitorteamid','events')}
                            await db.prepare('INSERT OR IGNORE INTO player_profiles VALUES (?,?,?)').bind(
                                cache_key, now.isoformat(), json.dumps(previous[side])).run()
                        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError):
                            continue
                context, _ = match_context(detail, before, now.isoformat(), profiles, previous)
                await db.prepare("""
                    INSERT INTO match_context VALUES (?,?,?)
                    ON CONFLICT(id) DO UPDATE SET observed_at=excluded.observed_at, payload=excluded.payload
                    WHERE excluded.observed_at >= match_context.observed_at
                    """).bind(mid, now.isoformat(), json.dumps(context)).run()
            except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError):
                continue


async def provider_json(client, tool, uid, **options):
    result = await call_tool(client, tool, {'id': uid, 'format': 'json', **options})
    return json.loads(result['content'][0]['text'])
