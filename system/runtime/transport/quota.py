"""Process-safe request limits, shared by generation, writing, and both judges."""
from contextlib import contextmanager, asynccontextmanager
from pathlib import Path
import asyncio
import fcntl
import json
import os
import random
import time

ROOT = Path(os.environ.get('IDEAX_STATE_DIR', str(Path(__file__).resolve().parents[3]/'.state'))) / 'admission'
LIMITS = {'astra_generation':300, 'astra_evaluation':100, 'opus_evaluation':100}

def config():
    path=ROOT/'control.json'
    value=json.loads(path.read_text()) if path.exists() else {}
    return value

def limit(role):
    if role not in LIMITS: raise ValueError('Unknown request role: '+role)
    cfg=config();n=int(cfg.get('limits',{}).get(role,LIMITS[role]))
    if not 0 <= n <= LIMITS[role]: raise ValueError('Configured limit exceeds user authorization')
    # Explicit reservations account for legacy workers not yet using this gate.
    return max(0,n-int(cfg.get('external_reserved',{}).get(role,0)))

def acquire(role, label=''):
    slots=list(range(limit(role)));random.shuffle(slots)
    for i in slots:
        path=ROOT/'locks'/role/f'{i:03}.lock';path.parent.mkdir(parents=True,exist_ok=True)
        stream=path.open('a+')
        try: fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: stream.close();continue
        stream.seek(0);stream.truncate()
        json.dump({'pid':os.getpid(),'role':role,'label':label,'started_epoch':time.time()},stream);stream.flush()
        return stream
    return None

@contextmanager
def slot(role='astra_generation',label=''):
    stream=None
    while stream is None:
        stream=acquire(role,label)
        if stream is None:time.sleep(.3+random.random()*.5)
    try:yield
    finally:stream.close()

@asynccontextmanager
async def async_slot(role='astra_generation',label=''):
    stream=None
    while stream is None:
        stream=acquire(role,label)
        if stream is None:await asyncio.sleep(.3+random.random()*.5)
    try:yield
    finally:stream.close()

def active():
    result={k:[] for k in LIMITS}
    for role in LIMITS:
        for path in (ROOT/'locks'/role).glob('*.lock'):
            with path.open('a+') as stream:
                try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:
                    stream.seek(0)
                    try:result[role].append(json.load(stream))
                    except ValueError:result[role].append({'label':'acquiring'})
    return result
