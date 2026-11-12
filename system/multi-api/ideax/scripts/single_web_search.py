#!/usr/bin/env python3
"""Public scholarly search/fetch for both single-agent experiment conditions."""
import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def get(url):
    record = {'at': datetime.now(timezone.utc).isoformat(), 'url': url}
    try:
        with urlopen(Request(url, headers={'User-Agent': 'IdeaX-research/1.0'}), timeout=45) as r:
            raw = r.read(4_000_000)
            record.update(status=r.status, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        return raw.decode('utf-8', errors='replace')
    except Exception as e:
        record['error'] = type(e).__name__
        raise
    finally:
        log = Path('/work/out/web_requests.jsonl')
        if log.parent.is_dir():
            fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, (json.dumps(record) + '\n').encode())
            finally:
                os.close(fd)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='command', required=True)
    search = sub.add_parser('search')
    search.add_argument('query')
    search.add_argument('--source', choices=['crossref', 'datacite'], default='crossref')
    search.add_argument('--limit', type=int, default=12)
    fetch = sub.add_parser('fetch')
    fetch.add_argument('url')
    fetch.add_argument('--chars', type=int, default=24000)
    args = ap.parse_args()
    if args.command == 'fetch':
        if not args.url.startswith('https://'):
            raise SystemExit('Use an HTTPS source URL')
        raw = get(args.url)
        clean = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', raw, flags=re.S | re.I)
        clean = re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', ' ', clean)))
        result = {'url': args.url, 'text': clean[:args.chars], 'truncated': len(clean) > args.chars}
    else:
        limit = min(50, max(1, args.limit))
        if args.source == 'crossref':
            url = 'https://api.crossref.org/works?' + urlencode({'query.bibliographic': args.query, 'rows': limit})
            data = json.loads(get(url))['message']
            rows = [{'title': ' / '.join(x.get('title', [])), 'doi': x.get('DOI'),
                     'url': x.get('URL'), 'abstract': x.get('abstract'),
                     'published': x.get('published'), 'links': x.get('link', [])}
                    for x in data.get('items', [])]
            total = data.get('total-results')
        else:
            url = 'https://api.datacite.org/dois?' + urlencode({'query': args.query, 'page[size]': limit})
            data = json.loads(get(url))
            rows = []
            for item in data.get('data', []):
                x = item['attributes']
                rows.append({'title': ' / '.join(t['title'] for t in x.get('titles', [])),
                             'doi': x.get('doi'), 'url': x.get('url'), 'year': x.get('publicationYear'),
                             'description': ' '.join(t['description'] for t in x.get('descriptions', []))[:8000]})
            total = data.get('meta', {}).get('total')
        result = {'url': url, 'total': total, 'papers': rows,
                  'limitation': 'Coverage and ranking vary. Open original sources and vary terminology; no match is not proof of novelty.'}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
