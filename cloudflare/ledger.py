"""Record in-play forecasts before the result and audit them against regulation scores."""
import json
from datetime import date, datetime, time, timedelta, timezone

import httpx

from football_ai.live import LIVE_MODEL_VERSION, regulation_probabilities
from football_ai.mania import call_tool, mania_session, raw_score


async def record_forecasts(db, fixtures, now):
    for start in range(0, len(fixtures), 20):
        statements = []
        for fixture in fixtures[start:start + 20]:
            statements.extend(forecast_statements(db, fixture, now))
        if statements:
            await db.batch(statements)


def forecast_statements(db, fixture, now):
    probabilities, kickoff = fixture['probabilities'], fixture['kickoff']
    if not probabilities or not kickoff:
        return []
    kickoff = datetime.fromisoformat(kickoff.replace('Z', '+00:00'))
    if not kickoff <= now < kickoff + timedelta(hours=3):
        return []
    minute, extra = fixture['minute'], fixture['extra']
    sample_minute = 45 if fixture['status'] == 'HT' else minute
    sample = 'half_time' if fixture['status'] == 'HT' else f"{fixture['status'].lower()}_{(sample_minute // 15) * 15}"
    baseline = regulation_probabilities(fixture['home_goals'], fixture['away_goals'], minute, fixture['status'],
                                        extra=extra, announced=fixture['announced_stoppage'])
    confidence = max(probabilities.values())
    leaders = [outcome for outcome, probability in probabilities.items() if probability == confidence]
    winner = leaders[0] if len(leaders) == 1 else None
    samples = [sample]
    if winner in {'home', 'away'} and confidence >= 0.70:
        samples.append('win_70')
    match_id = str(fixture['id'])
    statements = [db.prepare("""
        INSERT INTO live_matches(id,home,away,kickoff,next_check) VALUES (?,?,?,?,?)
        ON CONFLICT(id) DO NOTHING
        """).bind(match_id, fixture['home'], fixture['away'], kickoff.isoformat(),
                  (kickoff + timedelta(minutes=100)).isoformat())]
    reds = fixture['red_cards'] or {}
    reference = fixture.get('reference_probabilities')
    for sample in samples:
        statements.append(db.prepare("""
            INSERT INTO live_forecasts SELECT ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            WHERE EXISTS (SELECT 1 FROM live_matches WHERE id=? AND confirmed_at IS NULL)
            ON CONFLICT(match_id,model,sample) DO NOTHING
            """).bind(match_id, LIVE_MODEL_VERSION, sample, now.isoformat(), sample_minute, extra,
                      fixture['home_goals'], fixture['away_goals'], fixture['basis'], reds.get('home'), reds.get('away'),
                      probabilities['home'], probabilities['draw'], probabilities['away'], winner, confidence,
                      baseline['home'], baseline['draw'], baseline['away'], match_id))
        if reference:
            top = [key for key, value in reference.items() if value == max(reference.values())]
            statements.append(db.prepare("""
                INSERT INTO live_forecast_reference SELECT ?,?,?,?,?,?,?
                WHERE EXISTS (
                  SELECT 1 FROM live_forecasts WHERE match_id=? AND model=? AND sample=? AND observed_at=?
                )
                ON CONFLICT(match_id,model,sample) DO NOTHING
                """).bind(match_id, LIVE_MODEL_VERSION, sample, reference['home'], reference['draw'],
                          reference['away'], top[0] if len(top) == 1 else None,
                          match_id, LIVE_MODEL_VERSION, sample, now.isoformat()))
    return statements


async def settle_forecasts(db, now):
    due = await db.prepare("""
        SELECT id FROM live_matches WHERE confirmed_at IS NULL AND next_check <= ? AND kickoff >= ?
        ORDER BY next_check LIMIT 12
        """).bind(now.isoformat(), (now - timedelta(days=3)).isoformat()).all()
    if not due['results']:
        return
    async with mania_session() as client:
        for match in due['results']:
            match_id = match['id']
            try:
                result = await call_tool(client, 'get_match', {'id': match_id, 'format': 'json', 'h2h': False})
                row = json.loads(result['content'][0]['text'])
                score = regulation_result(row, match_id)
            except (httpx.HTTPError, IndexError, KeyError, TypeError, ValueError):
                score = None
            if score:
                await db.prepare("""
                    UPDATE live_matches SET final_home=?, final_away=?, confirmed_at=?
                    WHERE id=? AND confirmed_at IS NULL
                    """).bind(*score, now.isoformat(), match_id).run()
            else:
                await db.prepare("""
                    UPDATE live_matches SET next_check=? WHERE id=? AND confirmed_at IS NULL
                    """).bind((now + timedelta(minutes=5)).isoformat(), match_id).run()


def regulation_result(row, match_id):
    if str(row.get('id')) != match_id or row.get('status') != 'FT':
        return None
    if str(row.get('isET') or 0) != '0' or str(row.get('isOT') or 0) != '0':
        return None
    score = raw_score(row)
    return score if None not in score else None


async def performance(db):
    result = await db.prepare("""
        WITH scored AS (
          SELECT f.*, CASE WHEN m.confirmed_at IS NULL THEN NULL
                    WHEN m.final_home > m.final_away THEN 'home'
                    WHEN m.final_home < m.final_away THEN 'away' ELSE 'draw' END AS outcome
          FROM live_forecasts f JOIN live_matches m ON m.id=f.match_id
          WHERE f.model=? AND f.observed_at >= ?
        )
        SELECT sample, COUNT(*) AS recorded, COUNT(outcome) AS settled,
          SUM(CASE WHEN pick=outcome THEN 1 ELSE 0 END) AS correct,
          AVG(CASE WHEN outcome IS NOT NULL THEN pick_p END) AS average_confidence,
          AVG(CASE WHEN outcome IS NOT NULL THEN
            (home_p-(outcome='home'))*(home_p-(outcome='home'))+
            (draw_p-(outcome='draw'))*(draw_p-(outcome='draw'))+
            (away_p-(outcome='away'))*(away_p-(outcome='away')) END) AS brier,
          AVG(CASE WHEN outcome IS NOT NULL THEN
            (baseline_home-(outcome='home'))*(baseline_home-(outcome='home'))+
            (baseline_draw-(outcome='draw'))*(baseline_draw-(outcome='draw'))+
            (baseline_away-(outcome='away'))*(baseline_away-(outcome='away')) END) AS baseline_brier
        FROM scored GROUP BY sample ORDER BY sample
        """).bind(LIVE_MODEL_VERSION, (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()).all()
    recent = await db.prepare("""
        SELECT m.home, m.away, m.final_home, m.final_away, m.confirmed_at, f.observed_at,
               f.minute, f.extra, f.pick, f.pick_p, f.home_goals, f.away_goals
        FROM live_forecasts f JOIN live_matches m ON m.id=f.match_id
        WHERE f.model=? AND f.sample='win_70' ORDER BY f.observed_at DESC LIMIT 20
        """).bind(LIVE_MODEL_VERSION).all()
    paired = await db.prepare("""
        WITH ranked AS (
          SELECT f.pick, r.pick AS previous_pick,
            CASE WHEN m.final_home > m.final_away THEN 'home'
                 WHEN m.final_home < m.final_away THEN 'away' ELSE 'draw' END AS outcome,
            ROW_NUMBER() OVER(PARTITION BY f.match_id ORDER BY f.observed_at, f.sample) AS position
          FROM live_forecast_reference r JOIN live_forecasts f USING(match_id, model, sample)
          JOIN live_matches m ON m.id=f.match_id
          WHERE f.model=? AND f.sample<>'win_70' AND m.confirmed_at IS NOT NULL
            AND f.observed_at>=?
        )
        SELECT COUNT(*) AS matches, COALESCE(SUM(pick=outcome),0) AS correct,
               COALESCE(SUM(previous_pick=outcome),0) AS previous_correct
        FROM ranked WHERE position=1
        """).bind(LIVE_MODEL_VERSION, (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()).first()
    return {'model': LIVE_MODEL_VERSION, 'samples': result['results'], 'recent': recent['results'],
            'paired': paired, 'result_source': 'football_mania', 'window_days': 30}


async def forecast_history(db, day: date, cohort: str):
    thailand = timezone(timedelta(hours=7))
    start = datetime.combine(day, time.min, thailand).astimezone(timezone.utc)
    # All observations are recorded within three hours of kickoff. Include
    # these earlier candidates so a match straddling midnight is counted once.
    result = await db.prepare("""
        WITH ranked AS (
          SELECT f.*, ROW_NUMBER() OVER(
            PARTITION BY match_id ORDER BY observed_at, model, sample
          ) AS position
          FROM live_forecasts f
          WHERE f.observed_at >= ? AND f.observed_at < ? AND f.pick IS NOT NULL
            AND ((? = 'win70' AND f.sample = 'win_70') OR (? = 'all' AND f.sample <> 'win_70'))
        )
        SELECT f.match_id, f.model, m.home, m.away, f.observed_at, f.minute, f.extra,
               f.pick, f.pick_p, f.home_goals, f.away_goals,
               m.final_home, m.final_away, m.confirmed_at,
               CASE WHEN m.confirmed_at IS NULL THEN 'pending'
                    WHEN f.pick = CASE WHEN m.final_home > m.final_away THEN 'home'
                                       WHEN m.final_home < m.final_away THEN 'away' ELSE 'draw' END
                    THEN 'correct' ELSE 'wrong' END AS result
        FROM ranked f JOIN live_matches m ON m.id=f.match_id
        WHERE f.position=1 AND f.observed_at >= ?
        ORDER BY f.observed_at DESC, f.match_id
        """).bind((start - timedelta(hours=3)).isoformat(), (start + timedelta(days=1)).isoformat(),
                  cohort, cohort, start.isoformat()).all()
    matches = result['results']
    counts = {status: 0 for status in ('correct', 'wrong', 'pending')}
    for match in matches:
        counts[match['result']] += 1
    return {'date': day.isoformat(), 'cohort': cohort, 'matches': matches, 'counts': counts,
            'result_source': 'football_mania'}
