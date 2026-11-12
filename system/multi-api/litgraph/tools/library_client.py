"""Read-only litgraph API client used by IdeaX, including inside its sandbox.

Configuration: --base-url, a run's library_api.json, or LITGRAPH_API_BASE_URL.
No local-database fallback: a failed API request remains an explicit failure.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import random
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen


class LibraryAPIError(RuntimeError):
    pass


def run_config():
    path = Path(__file__).resolve().parent.parent / 'library_api.json'
    return json.loads(path.read_text()) if path.is_file() else {}


def configured_url():
    return run_config().get('base_url') or os.environ.get('LITGRAPH_API_BASE_URL')


def normalize_base(value):
    parts = urlsplit(str(value or ''))
    if (parts.scheme not in ('http', 'https') or not parts.netloc or parts.username
            or parts.password or parts.query or parts.fragment or parts.path not in ('', '/')):
        raise LibraryAPIError('Configure the service root URL, without credentials, query or /api/v1 suffix')
    return value.rstrip('/')


def paper_id(value):
    if isinstance(value, bool) or not re.fullmatch(r'[0-9]{1,20}', str(value)):
        raise LibraryAPIError('paper_id must be a numeric litgraph ID, not a W ID or entry ID')
    return int(value)


class LibraryClient:
    def __init__(self, base_url=None, timeout=15, retries=5, log_path=None):
        self.base_url = normalize_base(base_url or configured_url())
        self.timeout, self.retries = timeout, retries
        config = run_config()
        configured_log = config.get('request_log')
        self.log_path = Path(log_path) if log_path else (
            Path(__file__).resolve().parent.parent / configured_log if configured_log else None)

    def _log(self, method, url, status, raw=b'', **details):
        if not self.log_path:
            return
        if raw and status == 200:
            evidence = self.log_path.parent / 'api_responses' / (hashlib.sha256(raw).hexdigest()+'.json')
            evidence.parent.mkdir(parents=True,exist_ok=True)
            if not evidence.exists(): evidence.write_bytes(raw)
        record = dict(at=datetime.now(timezone.utc).isoformat(), method=method, url=url,
                      status=status, sha256=hashlib.sha256(raw).hexdigest(), **details)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, (json.dumps(record) + '\n').encode())
        finally:
            os.close(fd)

    def request(self, path, params=None, body=None):
        # The only POST is the service's read-only batch lookup.
        if not path.startswith('/api/v1/') or '?' in path or '#' in path or '..' in path:
            raise LibraryAPIError('Expected a litgraph /api/v1/ resource path')
        if body is not None and path != '/api/v1/papers/batch':
            raise LibraryAPIError('Only the read-only paper batch endpoint accepts a body')
        url = self.base_url + path
        if params:
            url += '?' + urlencode({k: v for k, v in params.items() if v is not None})
        payload = json.dumps(body).encode() if body is not None else None
        method = 'POST' if payload is not None else 'GET'
        req = Request(url, data=payload, headers={'Accept': 'application/json',
                      'Content-Type': 'application/json', 'User-Agent': 'IdeaX-litgraph/1.0'})
        request_id = uuid.uuid4().hex
        for attempt in range(self.retries + 1):
            details = dict(request_id=request_id, attempt=attempt + 1, max_attempts=self.retries + 1)
            try:
                with urlopen(req, timeout=self.timeout) as response:
                    raw = response.read()
                    self._log(method, url, response.status, raw, retrying=False, **details)
                result = json.loads(raw)
                if not isinstance(result, dict) or result.get('ok') is not True or 'data' not in result:
                    raise LibraryAPIError(f'Invalid or unsuccessful API envelope: {url}')
                return result
            except HTTPError as exc:
                retrying = exc.code in (429, 500, 502, 503, 504) and attempt < self.retries
                try:
                    raw = exc.read(65536)
                except (OSError, TimeoutError):
                    raw = b''
                finally:
                    exc.close()
                self._log(method, url, exc.code, raw, retrying=retrying, **details)
                if not retrying:
                    raise LibraryAPIError(f'litgraph HTTP {exc.code}: {url}') from exc
            except (URLError, TimeoutError, OSError) as exc:
                self._log(method, url, 'unavailable', retrying=attempt < self.retries, **details)
                if attempt == self.retries:
                    raise LibraryAPIError(f'litgraph unavailable: {url} ({type(exc).__name__})') from exc
            except (ValueError, UnicodeError) as exc:
                raise LibraryAPIError(f'litgraph returned invalid JSON: {url}') from exc
            # Bursts from thirty scouts can outlast sub-second retries. Spread
            # read-only retries across ~16 seconds without changing the query,
            # switching databases or reducing model concurrency.
            time.sleep(min(8.0, 0.5 * 2 ** attempt) + random.uniform(0, 0.25))

    def entry(self, identifier):
        return self.request('/api/v1/entries/' + quote(identifier, safe=''))['data']

    def paper(self, identifier):
        identifier = paper_id(identifier)
        data = self.request(f'/api/v1/papers/{identifier}')['data']
        if paper_id(data.get('paper_id', data.get('id'))) != identifier:
            raise LibraryAPIError('API returned a different paper_id')
        return data

    def domain_context(self, identifier):
        """List both entry kinds completely; refuse truncated or changing pages."""
        path = '/api/v1/domains/' + quote(identifier, safe='')
        domain = self.request(path)['data']
        rows, counts, endpoints = [], {}, []
        for resource, kind in (('insights', 'insight'), ('problems', 'problem')):
            after, cursors, seen = None, set(), set()
            while True:
                params = {'limit': 100, 'after': after}
                result = self.request(path + '/' + resource, params)
                endpoints.append(path + '/' + resource + '?' + urlencode(
                    {k: v for k, v in params.items() if v is not None}))
                data, page = result.get('data'), result.get('page')
                if not isinstance(data, list) or not isinstance(page, dict) or type(page.get('has_more')) is not bool:
                    raise LibraryAPIError('Missing data/page completeness metadata')
                for row in data:
                    if (not isinstance(row, dict) or not isinstance(row.get('id'), str)
                            or not row['id'] or row.get('kind') != kind or row['id'] in seen):
                        raise LibraryAPIError('Invalid or duplicate domain entry')
                    seen.add(row['id'])
                    rows.append(row)
                if not page['has_more']:
                    break
                after = page.get('next_after')
                if not data or not isinstance(after, str) or not after or after in cursors:
                    raise LibraryAPIError('Domain pagination did not advance')
                cursors.add(after)
            counts[resource] = len(seen)
            if counts[resource] != domain.get('counts', {}).get(resource):
                raise LibraryAPIError('Domain count mismatch; full context is incomplete or changed')
        current = self.request(path)['data']
        if any(current.get('counts', {}).get(k) != v for k, v in counts.items()):
            raise LibraryAPIError('Domain changed during full-context retrieval')
        return rows, {'domain_id': identifier, 'domain': domain, 'counts': counts,
                      'entries': len(rows), 'complete': True, 'endpoints': endpoints,
                      'base_url': self.base_url, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                      'scope': 'Complete paginated live listing; not a transactional snapshot or proof of reading.'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base-url')
    sub = ap.add_subparsers(dest='command', required=True)
    domains = sub.add_parser('domains')
    domains.add_argument('--q'); domains.add_argument('--offset', type=int, default=0)
    domains.add_argument('--limit', type=int, default=20)
    domain = sub.add_parser('domain'); domain.add_argument('id')
    domain.add_argument('--resource', choices=['problems', 'insights', 'papers'])
    domain.add_argument('--q'); domain.add_argument('--after'); domain.add_argument('--offset', type=int)
    domain.add_argument('--limit', type=int, default=20)
    domain.add_argument('--sort', choices=['id', 'relevance', 'paper_count'],
                        help='insights/problems only; paper_count sorts by distinct supporting papers, descending')
    search = sub.add_parser('search'); search.add_argument('query', nargs='+')
    search.add_argument('--kind', choices=['problem', 'insight']); search.add_argument('--unit')
    search.add_argument('--mode', choices=['all', 'any'], default='all')
    search.add_argument('--fields'); search.add_argument('--limit', type=int, default=10)
    search.add_argument('--offset', type=int, default=0)
    search.add_argument('--sort', choices=['id', 'relevance', 'paper_count'])
    for name in ('show', 'paper', 'by-arxiv'):
        sub.add_parser(name).add_argument('id')
    sub.add_parser('batch').add_argument('ids', nargs='+')
    sub.add_parser('stats')
    context = sub.add_parser('domain-context', help='List ALL insights and problems with count and pagination checks')
    context.add_argument('id')
    context.add_argument('--output-dir', type=Path, required=True, help='New directory for entries.jsonl and manifest.json')
    check = sub.add_parser('check-card'); check.add_argument('file')
    args = ap.parse_args()
    try:
        client = LibraryClient(args.base_url)
        if args.command == 'check-card':
            from idea_provenance import validate_previous_work, validate_entry_usage
            card = json.loads(Path(args.file).read_text())
            validate_previous_work(card, client.paper)
            marker = Path(args.file).resolve().parent / 'REQUIRE_ENTRY_USAGE'
            if not marker.exists():
                marker = Path(args.file).resolve().parent.parent / 'REQUIRE_ENTRY_USAGE'
            run_marker = Path(__file__).resolve().parent.parent / 'ideas/REQUIRE_ENTRY_USAGE'
            if marker.exists() or run_marker.exists() or any(
                    card.get(key) for key in ('source_entry_ids', 'entry_usage', 'litgraph_queries')):
                validate_entry_usage(card, client.entry)
            result = {'ok': True, 'data': card}
        elif args.command == 'domain-context':
            if args.output_dir.exists():
                raise LibraryAPIError('Output directory already exists; choose a new one')
            rows, manifest = client.domain_context(args.id)
            raw = ''.join(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n' for row in rows)
            manifest.update(chars=len(raw), sha256=hashlib.sha256(raw.encode()).hexdigest(),
                            context_file='entries.jsonl')
            args.output_dir.mkdir(parents=True, exist_ok=False)
            (args.output_dir / 'entries.jsonl').write_text(raw, encoding='utf-8')
            (args.output_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
            result = {'ok': True, 'data': manifest, 'output_dir': str(args.output_dir)}
        elif args.command == 'show':
            result = {'ok': True, 'data': client.entry(args.id)}
        elif args.command == 'paper':
            result = {'ok': True, 'data': client.paper(args.id)}
        elif args.command == 'batch':
            ids = [paper_id(x) for x in args.ids]
            if not 1 <= len(ids) <= 50:
                raise LibraryAPIError('Batch accepts 1–50 IDs')
            result = client.request('/api/v1/papers/batch', body={'ids': ids})
        elif args.command == 'by-arxiv':
            result = client.request('/api/v1/papers/by-arxiv', {'id': args.id})
        elif args.command == 'search':
            result = client.request('/api/v1/search', dict(q=' '.join(args.query), kind=args.kind,
                unit=args.unit, mode=args.mode, fields=args.fields, limit=args.limit, offset=args.offset, sort=args.sort))
        elif args.command == 'domain':
            if args.sort is not None and args.resource not in ('insights', 'problems'):
                raise LibraryAPIError('--sort requires --resource insights or problems')
            path = '/api/v1/domains/' + quote(args.id, safe='')
            params = None
            if args.resource:
                path += '/' + args.resource
                params = dict(q=args.q, after=args.after, limit=args.limit, offset=args.offset, sort=args.sort)
            result = client.request(path, params)
        elif args.command == 'domains':
            result = client.request('/api/v1/domains', dict(q=args.q, limit=args.limit, offset=args.offset))
        else:
            result = client.request('/api/v1/stats')
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (LibraryAPIError, ValueError) as exc:
        ap.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
