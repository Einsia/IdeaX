"""Read existing per-directory LitGraph logs without rewriting research evidence."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit


def collect(out, base_url):
    out = Path(out).resolve()
    expected = urlsplit(base_url)
    rows, sources, seen = [], {}, {}
    for path in sorted(out.rglob('api_requests.jsonl')):
        if not path.resolve().is_relative_to(out):
            raise ValueError('API evidence must remain within this output directory')
        current = path
        while current != out:
            if current.is_symlink():
                raise ValueError('Symlinked API evidence is not accepted')
            current = current.parent
        sources[str(path.relative_to(out))] = hashlib.sha256(path.read_bytes()).hexdigest()
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError('API log record must be an object')
            url = urlsplit(row.get('url', ''))
            if (url.scheme, url.netloc) != (expected.scheme, expected.netloc):
                raise ValueError('API log belongs to a different service')
            if not row.get('request_id') or not row.get('at') or not row.get('sha256'):
                raise ValueError('API evidence lacks request identity, time or response hash')
            identity = (row['request_id'], row.get('attempt'))
            encoded = json.dumps(row, sort_keys=True, separators=(',', ':'))
            if identity in seen:
                if seen[identity] != encoded:
                    raise ValueError('Conflicting API records for the same request attempt')
                continue
            seen[identity] = encoded
            rows.append(row)
    return rows, sources
