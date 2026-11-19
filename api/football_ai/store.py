"""Local persistent SQLite store; Supabase SQL schema supplied for hosted deployment."""
from __future__ import annotations
import sqlite3
import os
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL
from datetime import datetime, timezone

DB_PATH = Path(os.environ.get('FOOTBALL_DB_PATH', str(Path(__file__).parents[1] / 'data' / 'football.sqlite')))


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS matches(
      id TEXT PRIMARY KEY, league TEXT NOT NULL, date TEXT NOT NULL,
      home TEXT NOT NULL, away TEXT NOT NULL, hg INTEGER NOT NULL, ag INTEGER NOT NULL,
      hthg INTEGER, htag INTEGER, hc INTEGER, ac INTEGER, hy INTEGER, ay INTEGER,
      imported_at TEXT NOT NULL, source TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_matches_date_league ON matches(league,date);
    CREATE TABLE IF NOT EXISTS fixtures(
      id TEXT PRIMARY KEY, league TEXT NOT NULL, kickoff TEXT NOT NULL,
      home TEXT NOT NULL, away TEXT NOT NULL, source TEXT NOT NULL,
      imported_at TEXT NOT NULL
    );
    ''')
    return conn


def insert_matches(rows: list[dict], source: str) -> int:
    if not 1 <= len(source) <= 200: raise ValueError('Invalid source')
    now = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        before = db.total_changes
        for m in rows:
            mid = str(uuid5(NAMESPACE_URL, '|'.join([m['league'], m['date'], m['home'], m['away']])))
            db.execute('''INSERT OR IGNORE INTO matches(id,league,date,home,away,hg,ag,hthg,htag,hc,ac,hy,ay,imported_at,source)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                       [mid, m['league'],m['date'],m['home'],m['away'],m['hg'],m['ag'],m.get('hthg'),m.get('htag'),
                        m.get('hc'),m.get('ac'),m.get('hy'),m.get('ay'),now,source])
        return db.total_changes-before


def list_matches(league: str | None = None) -> list[dict]:
    with connect() as db:
        if league:
            rs = db.execute('SELECT * FROM matches WHERE league=? ORDER BY date ASC', (league,)).fetchall()
        else:
            rs = db.execute('SELECT * FROM matches ORDER BY date ASC').fetchall()
        return [dict(r) for r in rs]


def list_fixtures():
    with connect() as db:
        rs = db.execute('SELECT * FROM fixtures ORDER BY kickoff ASC').fetchall()
        return [dict(r) for r in rs]


def insert_fixtures(rows: list[dict], source: str) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        before = db.total_changes
        for f in rows:
            fid = str(uuid5(NAMESPACE_URL, '|'.join([f['league'],f['kickoff'],f['home'],f['away']])))
            db.execute('''INSERT OR IGNORE INTO fixtures(id,league,kickoff,home,away,source,imported_at)
                       VALUES (?,?,?,?,?,?,?)''', (fid,f['league'],f['kickoff'],f['home'],f['away'],source,now))
        return db.total_changes-before
