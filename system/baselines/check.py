#!/usr/bin/env python3
"""Validate the source release without importing adapters or contacting services."""
import ast
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
EXPECTED = {'autoresearchclaw', 'dr_claw', 'researchagent', 'cycleresearcher',
            'sciagents', 'deepscientist', 'insightagents', 'ai_scientist_v3_native_ideation'}
FORBIDDEN = {'runs', 'evaluations', 'api_requests', 'model_calls', 'original_run',
             '.git', '.env', 'reviewed_queue.json', 'campaign.json', 'activation.json',
             'credentials.json', 'auth.json'}


def load(path):
    return json.loads(path.read_text())


def validate(root=ROOT):
    catalog = load(root/'catalog.json')
    methods = catalog['methods']
    assert len(methods) == 8 and {m['id'] for m in methods} == EXPECTED
    assert catalog['shared_physical_request_limit'] == 250
    assert catalog['model'] == 'gpt-6-astra' and catalog['reasoning_effort'] == 'xhigh'
    assert [m['id'] for m in methods if m['comparison'] == 'additional'] == ['ai_scientist_v3_native_ideation']
    manifest = load(root/'source_manifest.json')
    assert manifest['published_runtime_approval'] is False
    assert manifest['native_prompts_or_selection_changed_by_export'] is False
    rows = manifest['files']
    paths = {r['path'] for r in rows}
    assert len(paths) == len(rows)
    actual = {str(p.relative_to(root)) for p in (root/'snapshot').rglob('*') if p.is_file()}
    assert paths == actual, 'Unlisted or missing snapshot file'
    patterns = [rb'\bsk-[A-Za-z0-9_-]{20,}', rb'\bgh[pousr]_[A-Za-z0-9]{20,}',
                rb'-----BEGIN (?:OPENSSH|RSA|EC|DSA) PRIVATE KEY-----']
    python_files = 0
    for row in rows:
        relative = Path(row['path'])
        assert not relative.is_absolute() and '..' not in relative.parts
        assert not (FORBIDDEN & set(relative.parts)), relative
        assert relative.suffix not in {'.jsonl', '.sqlite', '.db', '.log', '.pem', '.key', '.pyc'}
        path = root/relative
        assert not path.is_symlink(), relative
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == row['sha256'], relative
        # 'renamed': only the project name was changed (IdeaX -> InsightPro, 2026-11-27); the hash is still pinned.
        assert row['mode'] in ('verbatim', 'renamed'), relative
        assert (row['sha256'] == row['source_sha256']) == (row['mode'] == 'verbatim'), relative
        assert not any(re.search(pattern, data) for pattern in patterns), relative
        if path.suffix == '.py':
            ast.parse(data, filename=str(relative))
            python_files += 1
    for method in methods:
        assert all(p in paths for p in method['entrypoints'])
        upstream = load(root/method['id']/'source.json')
        assert upstream == method['upstream']
        assert re.fullmatch(r'[a-f0-9]{40}', upstream['commit'])
        assert upstream['repository'].startswith('https://github.com/')
        assert upstream['bundled_upstream_source'] is False
        assert all((root/p).is_file() for p in upstream['license_notices'])
    return {'ok': True, 'methods': len(methods), 'source_files': len(rows),
            'python_files': python_files, 'model_calls': 0, 'runtime_approval': False}


if __name__ == '__main__':
    print(json.dumps(validate()))
