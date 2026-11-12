"""Local retrieval cache and cross-process request admission for native baselines."""
from contextlib import contextmanager, asynccontextmanager
from pathlib import Path
import asyncio
import fcntl
import json
import os
import random
import re
import time
import uuid
import sys
import hashlib
import importlib.util
from datetime import datetime, timezone

ROOT = Path(os.environ.get('IDEAX_BASELINE_STATE', str(Path(__file__).resolve().parents[2]/'.state/baselines')))
REPO = Path(__file__).resolve().parents[2]
MODEL = 'gpt-6-astra'
PROVIDER = 'https://sbtunnel.xiaoaojianghu.fun/v1'
METHODS = ('coi', 'ideascientist')
COI_PYTHON = os.environ.get('COI_PYTHON', sys.executable)
ISCI_PYTHON = os.environ.get('ISCI_PYTHON', sys.executable)

def now(): return datetime.now(timezone.utc).isoformat()
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def provider():
    sys.path.insert(0,str(REPO/'benchmarks/shared'))
    from native_judge import credentials
    base,key=credentials('astra')
    if base != PROVIDER:raise ValueError('This frozen baseline configuration requires sbtunnel')
    return base,key
def process_handle(pid):
    try:
        s=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
        return {'pid':pid,'start':s[19],'state':s[0]}
    except (OSError,IndexError):return None
def alive(handle):
    current=process_handle(handle['pid']) if handle else None
    return bool(current and current['start']==handle['start'] and current['state'] not in ('Z','X'))
def render(value,level=2):
    if isinstance(value,dict):return '\n\n'.join('#'*min(level,6)+' '+str(k)+'\n\n'+render(v,level+1) for k,v in value.items())
    if isinstance(value,list):return '\n\n'.join(render(v,level+1) for v in value)
    return str(value)

def read(path, default=None):
    try: return json.loads(Path(path).read_text())
    except (OSError, ValueError): return {} if default is None else default

def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)

def event(path, kind, **kwargs):
    path = Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        f.write(json.dumps({'at':time.time(),'event':kind,**kwargs},ensure_ascii=False)+'\n')

def safe(exc):
    return re.sub(r'\bsk-[A-Za-z0-9_-]{12,}', '[REDACTED]', str(exc))[:2000]

def acquire(kind):
    limits={'gpt':int(os.environ.get('IDEAX_BASELINE_GPT_CONCURRENCY','12')),'retrieval':8,'vault':2,'metadata':2}
    n=limits[kind]
    if n<1:raise ValueError('Baseline concurrency must be positive')
    slots=list(range(n));random.shuffle(slots)
    for i in slots:
        p=ROOT/'concurrency'/kind/f'{i}.lock';p.parent.mkdir(parents=True,exist_ok=True)
        f=p.open('a+')
        try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:f.close();continue
        return f
    return None

@contextmanager
def slot(kind='gpt',label=''):
    f=None
    while f is None:
        f=acquire(kind)
        if f is None:time.sleep(.3)
    try:yield
    finally:f.close()

@asynccontextmanager
async def async_slot(kind='gpt',label=''):
    f=None
    while f is None:
        f=acquire(kind)
        if f is None:await asyncio.sleep(.3)
    try:yield
    finally:f.close()
