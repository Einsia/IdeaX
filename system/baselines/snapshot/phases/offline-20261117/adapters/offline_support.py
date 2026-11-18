"""Shared offline environment checks and raw-literature integration helpers."""
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import threading

PHASE = Path(__file__).resolve().parents[1]
CORPUS = PHASE / 'inputs/corpus/corpus.sqlite'
CLI = PHASE / 'services/local_literature/cli.py'
_spec = importlib.util.spec_from_file_location('offline_raw_literature', CLI)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def require_offline(output, *, fresh_markers=()):
    output = Path(output).resolve()
    if os.environ.get('INSIGHTPRO_OFFLINE_ENFORCED') != '1':
        raise RuntimeError('Native offline worker requires the verified isolation launcher')
    if Path(os.environ.get('INSIGHTPRO_OFFLINE_PHASE', '/missing')).resolve() != PHASE:
        raise RuntimeError('Wrong offline phase')
    if not output.is_relative_to(PHASE) or output == PHASE:
        raise RuntimeError('Output must belong to this fresh offline phase')
    for name in fresh_markers:
        if (output / name).exists():
            raise RuntimeError('Fresh native context required; existing artifact: '+name)
    if not CORPUS.is_file():
        raise RuntimeError('Frozen raw corpus is unavailable')
    return output


def environment_text(output):
    base = (PHASE / 'protocol/offline_environment.txt').read_text().strip()
    prefix = f'/usr/bin/python3 {CLI} --corpus {CORPUS} --audit-log {Path(output) / "offline_literature.jsonl"}'
    return base + '\n\nLocal raw-paper tools (run through the ordinary shell tool):\n' + \
        f'{prefix} search --query "research query" --limit 10 --view raw\n' + \
        f'{prefix} read --id "paper identifier returned by search" --view raw\n' + \
        'Read reports whether the returned material is original full text, an abstract, or metadata. Search snippets are abstracts. Public source URLs identify sources; use local read to access their frozen contents.\n'


class RawLibrary:
    def __init__(self, output):
        self.output = Path(output)
        self.lock = threading.Lock()

    def call(self, operation, *args, **kwargs):
        with contextlib.closing(_mod.Corpus(CORPUS)) as corpus:
            value = getattr(corpus, operation)(*args, **kwargs)
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        dest = self.output / 'offline_literature' / (digest+'.json')
        with self.lock:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists(): dest.write_text(encoded+'\n')
            with (self.output / 'offline_literature.jsonl').open('a') as stream:
                stream.write(json.dumps({'operation':operation,'args':args,'kwargs':kwargs,'response':str(dest),
                    'response_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'offline':True,'network_fallback':False})+'\n')
        return value

    def search(self, query, limit=10):
        return self.call('search', query, limit=limit, view='raw')['data']

    def read(self, identifier, **kwargs):
        return self.call('read', identifier, view='raw', **kwargs)['data']
