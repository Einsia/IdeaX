"""Bind accepted multi top-five cards to immutable scoring inputs without rewriting a run."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def epoch(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).replace(tzinfo=timezone.utc).timestamp()


def save_frozen(path, value):
    raw = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if path.exists():
        if path.read_text() != raw:
            raise ValueError('Frozen multi scoring export changed: ' + str(path))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x') as stream:
            stream.write(raw)


def accepted_multi_source(run, condition, storage, since):
    run = Path(run).resolve()
    check_path = run / 'completion_check.json'
    if not check_path.exists():
        return None
    check = read(check_path)
    if check.get('ok') is not True or check.get('errors'):
        return None
    meta = read(run / 'run.json')
    if epoch(meta['created']) < epoch(since):
        return None
    if (meta.get('model'), meta.get('effort'), meta.get('matrix_condition')) != ('gpt-6-astra', 'xhigh', condition):
        return None
    state_path = run / 'work/ideas/idea_run_state.json'
    state = read(state_path)
    if not state.get('rank', {}).get('complete'):
        return None
    top_path = run / 'work/ideas/top5.json'
    top = sorted(read(top_path)['top5'], key=lambda row: row['rank'])
    if (len(top) != 5 or [r['rank'] for r in top] != [1, 2, 3, 4, 5]
            or len({r['card'] for r in top}) != 5):
        raise ValueError('Accepted multi source does not contain five distinct ranked cards')
    files = {str(p): sha(p) for p in (check_path, run / 'run.json', state_path, top_path)}
    cards, selected = [], []
    for row in top:
        cid = row['card']
        if not isinstance(cid, str) or not re.fullmatch(r'c-\d+', cid):
            raise ValueError('Invalid selected card ID')
        path = run / 'work/ideas/pool' / (cid + '.json')
        card = read(path)
        if card.get('id') != cid or card.get('status') != 'active':
            raise ValueError('Selected card identity/status mismatch')
        digest = sha(path)
        files[str(path)] = digest
        cards.append(card)
        selected.append({'rank': row['rank'], 'card': cid, 'path': str(path), 'sha256': digest})
    domain = meta['matrix_domain']
    if not re.fullmatch(r'[a-z0-9_-]+', domain):
        raise ValueError('Invalid domain ID')
    signature = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    out = Path(storage) / 'accepted-multi' / (domain + '__' + condition) / signature
    ideas_path = out / 'IDEAS.json'
    acceptance = out / 'acceptance.json'
    save_frozen(ideas_path, cards)
    save_frozen(acceptance, {'source_kind': 'multi', 'run': str(run), 'selected': selected,
                           'source_files': files, 'ideas_sha256': sha(ideas_path)})
    source = {'source_kind': 'multi', 'domain': domain, 'condition': condition, 'run': str(run),
              'ideas': str(ideas_path), 'ideas_sha256': sha(ideas_path), 'source_files': files,
              'acceptance_file': str(acceptance), 'acceptance_sha256': sha(acceptance),
              'accepted_at': check.get('checked_at') or check.get('at') or meta['created'],
              'provider': meta.get('provider')}
    validate_source(source)
    return source


def validate_source(source):
    for path, digest in source['source_files'].items():
        if sha(path) != digest:
            raise ValueError('Accepted multi input changed: ' + path)
    if sha(source['ideas']) != source['ideas_sha256'] or sha(source['acceptance_file']) != source['acceptance_sha256']:
        raise ValueError('Frozen multi scoring export changed')
    receipt = read(source['acceptance_file'])
    if receipt['source_files'] != source['source_files'] or receipt['ideas_sha256'] != source['ideas_sha256']:
        raise ValueError('Multi acceptance binding mismatch')
    actual = [read(row['path']) for row in receipt['selected']]
    if read(source['ideas']) != actual:
        raise ValueError('Scoring export differs from selected formal cards')
