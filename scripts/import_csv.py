#!/usr/bin/env python3
"""Offline import of an authorized historical results CSV into local SQLite.

Run from repository root: PYTHONPATH=api python scripts/import_csv.py path/to/E0.csv
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))
from football_ai.data import parse_history_csv
from football_ai.store import insert_matches

ap = argparse.ArgumentParser()
ap.add_argument('file', help='Path to Football-Data compatible CSV')
ap.add_argument('--source', default='manually-imported-csv')
args = ap.parse_args()
rows = parse_history_csv(Path(args.file).read_bytes())
if not rows: raise SystemExit('No valid completed matches in file')
print(f'Parsed {len(rows)}; inserted {insert_matches(rows,args.source)} new matches')
