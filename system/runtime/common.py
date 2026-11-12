"""Paths, immutable evidence and conservative GPT capacity for original single38."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import uuid

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
SYSTEM = Path(os.environ.get('IDEAX_CURRENT_SYSTEM', str(HERE.parent/'single-full'))).resolve()
PROVIDER = 'https://sbtunnel.xiaoaojianghu.fun/v1'
RELEASE = json.loads((SYSTEM/'release.json').read_text())
ACCESS = RELEASE['access']
CONDITION = RELEASE['version']
AUTHORS = tuple(f'author-{i:02d}' for i in range(1,7))

def read(path, default=None):
    try: return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        if default is None: raise
        return default

def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n'); temp.replace(path)

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()
def handle(pid):
    try:
        row = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return {'pid': pid, 'start': row[19], 'state': row[0]}
    except (OSError, IndexError): return None
def alive(h):
    actual = handle(h['pid']) if h else None
    return bool(actual and actual['state'] not in ('Z', 'X') and actual['start'] == str(h.get('start', actual['start'])))
def verify(files):
    for path, expected in files.items():
        if sha(path) != expected: raise ValueError('Frozen input changed: ' + str(path))

def freeze(path, value):
    if Path(path).exists():
        if read(path) != value: raise ValueError('Frozen artifact changed: '+str(path))
    else: save(path,value)
