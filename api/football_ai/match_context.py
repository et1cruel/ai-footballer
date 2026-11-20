"""Turn verified match details into small, inspectable forecasting inputs."""
from datetime import datetime, timedelta
from math import exp

from .mania import _number, raw_score

SIDES = {'home': 'localteam', 'away': 'visitorteam'}


def team_id(row, provider_side):
    return str(row.get(f'gs_{provider_side}id') or row.get(f'{provider_side}id') or '')


def historical_games(rows, team, before, opponent=None, days=365):
    if not team:
        return []
    games = {}
    for row in rows or []:
        if not row.get('id') or row.get('status') != 'FT':
            continue
        try:
            played = datetime.strptime(row['date'], '%d/%m/%Y').date()
        except (KeyError, TypeError, ValueError):
            continue
        if not before - timedelta(days=days) <= played < before:
            continue
        home, away = team_id(row, 'localteam'), team_id(row, 'visitorteam')
        if team not in {home, away} or (opponent and {home, away} != {team, opponent}):
            continue
        scored, conceded = raw_score(row)
        if scored is None:
            continue
        if team == away:
            scored, conceded = conceded, scored
        games[str(row['id'])] = (played, scored, conceded, str(row['id']))
    return sorted(games.values(), reverse=True)[:5]


def summarize(games):
    if not games:
        return None
    return {'matches': len(games), 'wins': sum(g > a for _, g, a, _ in games),
            'draws': sum(g == a for _, g, a, _ in games), 'goals': sum(g for _, g, _, _ in games),
            'conceded': sum(a for _, _, a, _ in games)}


def player_history(profile, team, before, name):
    # Provider aggregates may already include the in-progress fixture. Use
    # completed seasons only, scoped to this player's confirmed team.
    records = []
    for stat in profile.get('statistics', []):
        parts = str(stat.get('season', '')).replace('-', '/').split('/')
        end = _number(parts[-1])
        apps = _number(stat.get('appearences'))
        goals, assists = _number(stat.get('goals')), _number(stat.get('assists'))
        if (str(stat.get('teamid')) == team and end and before.year - 2 <= end < before.year
                and apps and apps >= 5 and goals is not None):
            records.append((end, apps, goals, assists, stat['season']))
    if not records:
        return None
    _, apps, goals, assists, season = max(records, key=lambda row: (row[0], row[1]))
    return {'name': name, 'season': season, 'appearances': apps, 'goals': goals, 'assists': assists}


def match_context(detail, before, observed_at, profiles, previous=None):
    teams = {side: team_id(detail, key) for side, key in SIDES.items()}
    commentary = detail.get('commentaries') or {}
    events = commentary.get('events') or detail.get('events') or []
    active = {}
    lineup_counts = {}
    for side, key in SIDES.items():
        starters = (detail.get('lineups') or {}).get(key) or []
        active[side] = {str(p['id']): p['name'] for p in starters if p.get('id') and p.get('name')}
        lineup_counts[side] = len(active[side])
    highlights = []
    for event in events:
        side = next((s for s, key in SIDES.items() if key == event.get('team')), None)
        kind, player = event.get('type'), event.get('player')
        player_id = str(event.get('playerId') or '')
        if not side or not player or kind not in {'subst', 'redcard', 'yellowred', 'goal', 'yellowcard'}:
            continue
        if kind == 'subst' and (outgoing := str(event.get('assistid') or '')) and player_id:
            # Only use substitutions for roster inference when the feed provides both IDs.
            active[side].pop(outgoing, None)
            active[side][player_id] = player
        if kind in {'redcard', 'yellowred'}:
            active[side].pop(player_id, None)
        highlights.append({'side': side, 'type': kind, 'player': player,
                           'outgoing': event.get('assist') if kind == 'subst' else None,
                           'minute': _number(event.get('minute')), 'extra': _number(event.get('extra_min'))})
    recent = {side: summarize(historical_games(detail.get(key + 'shapefixtures'), teams[side], before))
              for side, key in SIDES.items()}
    h2h = summarize(historical_games(detail.get('h2hMatches'), teams['home'], before, teams['away'], days=730))
    players, shots = {}, {}
    for side, key in SIDES.items():
        players[side] = [summary for pid, name in active[side].items()
                         if (profile := profiles.get(pid))
                         and (summary := player_history(profile, teams[side], before, name))]
        rows = (commentary.get('playerstats') or {}).get(key) or []
        values = [_number(p.get('shotsOn')) for p in rows]
        shots[side] = sum(values) if len(values) >= 8 and all(n is not None for n in values) else None
    recent_players = {}
    for side, prior in (previous or {}).items():
        team = teams[side]
        provider_side = next((key for key in SIDES.values() if team and team_id(prior, key) == team), None)
        if prior.get('status') != 'FT' or not provider_side:
            continue
        contributions = {}
        for event in prior.get('events') or []:
            if event.get('team') != provider_side or event.get('type') != 'goal':
                continue
            for field, weight in [('playerId', 1), ('assistId', 0.5)]:
                pid = str(event.get(field) or '')
                if pid in active[side]:
                    contributions[pid] = contributions.get(pid, 0) + weight
        if contributions:
            recent_players[side] = {'match_date': prior.get('date'), 'players': [
                {'name': active[side][pid], 'contribution': points} for pid, points in contributions.items()]}
    return {'recent_form': recent, 'head_to_head': h2h, 'player_history': players,
            'lineup_counts': lineup_counts, 'shots_on_target': shots, 'events': highlights[-6:],
            'recent_players': recent_players, 'score': raw_score(detail), 'observed_at': observed_at,
            'match_finished': detail.get('status') in {'FT','AET','PEN'}}, active


def match_rates(context, base, current_score, allow_live=True, *, use_team_form=True):
    base = base or {'home': 1.3, 'away': 1.3}
    factors = {}
    home, away = (context['recent_form'][side] for side in SIDES)
    if use_team_form and home and away and min(home['matches'], away['matches']) >= 3:
        def form(team):
            n = team['matches']
            points = (team['wins'] + 0.33 * team['draws'] + 1.5) / (n + 3)
            margin = (team['goals'] - team['conceded']) / (n + 5)
            return points + 0.15 * max(-1.0, min(1.0, margin))
        factors['team_form'] = 0.5 * (form(home) - form(away))
    if use_team_form and (h2h := context.get('head_to_head')) and h2h['matches'] >= 2:
        losses = h2h['matches'] - h2h['wins'] - h2h['draws']
        factors['head_to_head'] = 0.18 * (h2h['wins'] - losses) / (h2h['matches'] + 3)
    players = context['player_history']
    if allow_live and not context.get('match_finished') and tuple(context['score']) == current_score:
        if len(players['home']) == len(players['away']) and len(players['home']) >= 2:
            def production(group):
                return sum((p['goals'] + 0.5 * (p['assists'] or 0)) / p['appearances'] for p in group) / len(group)
            factors['player_history'] = max(-0.10, min(0.10, 0.2 * (production(players['home']) - production(players['away']))))
        recent_players = context.get('recent_players') or {}
        if 'home' in recent_players and 'away' in recent_players:
            home_points = sum(p['contribution'] for p in recent_players['home']['players'])
            away_points = sum(p['contribution'] for p in recent_players['away']['players'])
            factors['player_recent'] = max(-0.08, min(0.08, 0.03 * (home_points - away_points)))
        shots = context['shots_on_target']
        if all(n is not None for n in shots.values()):
            factors['live_shots'] = max(-0.15, min(0.15, 0.025 * (shots['home'] - shots['away'])))
    adjustment = sum(factors.values())
    return {'home': base['home'] * exp(adjustment), 'away': base['away'] * exp(-adjustment)}, list(factors)
