"""Build a clean Cloudflare upload directory with public OpenFootball data."""
import base64
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    root = Path(__file__).resolve().parents[1]
    target = Path(sys.argv[1]).resolve()
    source = target / 'src'
    source.mkdir(parents=True, exist_ok=True)
    for name in ('wrangler.toml', 'pyproject.toml'):
        shutil.copyfile(root / 'cloudflare' / name, target / name)
    for name in ('worker.py', 'ledger.py'):
        shutil.copyfile(root / 'cloudflare' / name, source / name)
    shutil.copytree(root / 'cloudflare' / 'migrations', target / 'migrations', dirs_exist_ok=True)
    shutil.copytree(root / 'api' / 'football_ai', source / 'football_ai', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(root / 'web', target / 'web', dirs_exist_ok=True)
    with tempfile.TemporaryDirectory() as data_dir:
        db = Path(data_dir) / 'football.sqlite'
        env = {**os.environ, 'FOOTBALL_DB_PATH': str(db)}
        subprocess.run([sys.executable, str(root / 'scripts' / 'import_openfootball.py')], env=env, check=True)
        encoded = base64.b64encode(db.read_bytes()).decode('ascii')
    (source / 'seed.py').write_text(f'DATABASE = {encoded!r}\n', encoding='ascii')


if __name__ == '__main__':
    main()
