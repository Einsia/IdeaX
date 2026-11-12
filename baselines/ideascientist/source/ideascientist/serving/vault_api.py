"""Read-only field-aware Idea Vault API, intended for other research agents."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import threading
import time
from contextlib import closing
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .technique_index import EXTRACTION_VERSION, INDEX_VERSION, _fingerprint, technique_fields

FIELDS = ('title', 'problem_definition', 'challenge', 'intuition', 'solution')


class RequestError(ValueError):
    pass


def connect(path):
    con = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA query_only=ON')
    return con


def integer(value, name, default, minimum, maximum):
    if value is None:
        if default is None:
            raise RequestError(f'{name} is required')
        return default
    if isinstance(value, bool) or not re.fullmatch(r'[0-9]+', str(value)):
        raise RequestError(f'{name} must be an integer')
    number = int(value)
    if not minimum <= number <= maximum:
        raise RequestError(f'{name} must be between {minimum} and {maximum}')
    return number


def iso_date(value, name):
    if value is None or value == '':
        return None
    try:
        parsed = date.fromisoformat(value)
    except (ValueError, TypeError):
        raise RequestError(f'{name} must be YYYY-MM-DD') from None
    if parsed.isoformat() != value:
        raise RequestError(f'{name} must be YYYY-MM-DD')
    return value


class VaultAPI:
    def __init__(self, vault, index, timeout=20):
        self.vault = Path(vault)
        self.index = Path(index)
        self.timeout = timeout
        # Fail at launch rather than offer an empty corpus.
        with closing(connect(self.vault)) as con:
            con.execute('SELECT paper_id FROM metadata_results_masked LIMIT 1').fetchone()
        with closing(connect(self.index)) as con:
            con.execute('SELECT paper_id FROM techniques_meta LIMIT 1').fetchone()
            self.meta = {row['key']: json.loads(row['value']) for row in con.execute('SELECT * FROM build_meta')}
        if self.meta.get('status') != 'complete':
            raise RuntimeError('technique index is not complete')
        if self.meta.get('source_fingerprint') != _fingerprint(self.vault):
            raise RuntimeError('index/source mismatch; rebuild the index for this vault snapshot')
        if (self.meta.get('extraction_version') != EXTRACTION_VERSION
                or self.meta.get('index_version') != INDEX_VERSION):
            raise RuntimeError('index version mismatch; rebuild with the current extraction version')

    def health(self):
        return {'status': 'ok', 'schema_version': 'vault-api-v1', 'indexed_papers': self.meta.get('count'),
                'search': 'field-specific FTS5 BM25', 'fields': list(FIELDS), 'field_counts': self.meta.get('field_counts', {}),
                'solution_sources': self.meta.get('solution_sources', {}),
                'cutoff_policy': 'No default cutoff on this read-only API. date_before is exclusive; harness evaluation cutoff is unchanged.',
                'source': 'SvalbardIdeaVault results-masked structured records',
                'extraction_version': self.meta.get('extraction_version')}

    @staticmethod
    def _record(row):
        fields = json.loads(row['fields_json'])
        structured = technique_fields(fields)
        source = fields.get('_svalbard', {})
        return {'paper_id': row['id'], 'arxiv_id': row['arxiv_id'], 'title': row['title'],
                'date': row['date'], 'url': row['url'], 'authors': json.loads(row['authors'] or '[]'),
                'abstract': row['abstract'], 'categories': source.get('categories', []),
                'fields': {key: structured[key] for key in FIELDS if key != 'title'},
                'proposal_masked': source.get('proposal_masked', ''),
                'provenance': {'source': 'SvalbardIdeaVault', 'results_masked': True,
                    'solution_source': structured['solution_source'],
                    'challenge_source': structured.get('challenge_source', 'core_problem'),
                    'intuition_source': structured.get('intuition_source', 'key_novelty'),
                    'model': row['model'], 'abstract_results_masked': False,
                    'masked_fields': ['problem_definition', 'challenge', 'intuition', 'solution', 'proposal_masked']}}

    def papers(self, ids):
        if not isinstance(ids, list) or not 1 <= len(ids) <= 50:
            raise RequestError('ids must be an array of 1 to 50 integer paper IDs')
        ids = list(dict.fromkeys(integer(i, 'paper_id', None, 1, 2**63-1) for i in ids))
        with closing(connect(self.vault)) as con:
            rows = con.execute('SELECT p.*, m.fields_json, m.model FROM papers p JOIN metadata_results_masked m '
                               'ON m.paper_id=p.id WHERE p.id IN (' + ','.join('?' for _ in ids) + ')', ids).fetchall()
        found = {row['id']: self._record(row) for row in rows}
        return {'items': [found[i] for i in ids if i in found], 'missing_ids': [i for i in ids if i not in found]}

    def by_arxiv(self, arxiv_id):
        if not isinstance(arxiv_id, str) or not re.fullmatch(r'[A-Za-z0-9.\-/]+(?:v[0-9]+)?', arxiv_id) or len(arxiv_id) > 100:
            raise RequestError('invalid arxiv_id')
        arxiv_id = re.sub(r'v\d+$', '', arxiv_id)
        with closing(connect(self.vault)) as con:
            row = con.execute('SELECT id FROM papers WHERE arxiv_id=?', (arxiv_id,)).fetchone()
        if row is None:
            raise KeyError('paper not found')
        return self.papers([row['id']])['items'][0]

    def search(self, params):
        query = params.get('q', '').strip()
        if not query or len(query) > 500:
            raise RequestError('q is required (1–500 characters)')
        requested = params.get('fields', 'solution,intuition').split(',')
        if not requested or any(f not in FIELDS for f in requested):
            raise RequestError('fields must be comma-separated: ' + ','.join(FIELDS))
        tokens = list(dict.fromkeys(re.findall(r'[^\W_]+', query, re.UNICODE)))
        if not tokens or len(tokens) > 24:
            raise RequestError('q must contain 1–24 words; use concise technical terms')
        mode = params.get('mode', 'all')
        if mode not in ('all', 'any'):
            raise RequestError('mode must be all or any')
        limit = integer(params.get('limit'), 'limit', 10, 1, 50)
        offset = integer(params.get('offset'), 'offset', 0, 0, 5000)
        before = iso_date(params.get('date_before'), 'date_before')
        after = iso_date(params.get('date_from'), 'date_from')
        if before and after and after >= before:
            raise RequestError('date_from must precede date_before')
        category = params.get('category', '').strip()
        if category and not re.fullmatch(r'[A-Za-z0-9.\-]+', category):
            raise RequestError('category must be an arXiv category such as cs.LG')
        expr = '{' + ' '.join(dict.fromkeys(requested)) + '} : (' + (' AND ' if mode == 'all' else ' OR ').join('"' + t + '"' for t in tokens) + ')'
        where, values = ['techniques_fts MATCH ?'], [expr]
        if before:
            # Dates of unknown precision must be fully before the cutoff.
            where.append("m.date != '' AND (CASE length(m.date) WHEN 4 THEN m.date||'-12-31' WHEN 7 THEN m.date||'-31' ELSE m.date END) < ?")
            values.append(before)
        if after:
            where.append("m.date != '' AND (CASE length(m.date) WHEN 4 THEN m.date||'-01-01' WHEN 7 THEN m.date||'-01' ELSE m.date END) >= ?")
            values.append(after)
        if category:
            where.append('EXISTS (SELECT 1 FROM json_each(m.categories) WHERE value=?)')
            values.append(category)
        start = time.monotonic()
        con = connect(self.index)
        con.set_progress_handler(lambda: int(time.monotonic()-start > self.timeout), 10000)
        try:
            rows = con.execute('SELECT m.paper_id, bm25(techniques_fts) AS bm25 FROM techniques_fts '
                               'JOIN techniques_meta m ON m.paper_id=techniques_fts.rowid WHERE ' + ' AND '.join(where) +
                               ' ORDER BY bm25, m.paper_id LIMIT ? OFFSET ?', values + [limit+1, offset]).fetchall()
        finally:
            con.close()
        has_more = len(rows) > limit
        rows = rows[:limit]
        records = self.papers([r['paper_id'] for r in rows])['items'] if rows else []
        scores = {r['paper_id']: r['bm25'] for r in rows}
        for item in records:
            item.pop('proposal_masked', None)  # Full record is available from /papers/{id}.
            item['bm25'] = scores[item['paper_id']]
            item['searched_fields'] = list(dict.fromkeys(requested))
        return {'query': query, 'fields': requested, 'mode': mode, 'method': 'FTS5 BM25 (lower is better)',
                'limit': limit, 'offset': offset, 'count': len(records), 'has_more': has_more,
                'next_offset': offset+len(records) if has_more else None,
                'date_before': before, 'date_from': after, 'category': category or None,
                'elapsed_seconds': round(time.monotonic()-start, 3), 'items': records}


def openapi():
    query_params = [{'name': n, 'in': 'query', 'required': n == 'q', 'schema': {'type': 'string'}, 'description': desc}
                    for n, desc in [('q', 'Concise technical query; English matches the corpus best'), ('fields', 'Comma-separated fields; default solution,intuition'),
                                    ('mode', 'all (AND, default) or any (OR)'), ('limit', '1–50, default 10'), ('offset', '0–5000'),
                                    ('date_before', 'Exclusive YYYY-MM-DD'), ('date_from', 'Inclusive YYYY-MM-DD'), ('category', 'Exact arXiv category, e.g. cs.LG')]]
    ok = {'200': {'description': 'JSON response'}, '400': {'description': 'Invalid input'}, '503': {'description': 'Busy or search timeout'}}
    return {'openapi': '3.1.0', 'info': {'title': 'IdeaScientist technique retrieval API', 'version': '1.0.0'},
            'servers': [{'url': '/'}], 'paths': {
                '/health': {'get': {'operationId': 'health', 'responses': ok}},
                '/api/v1/search': {'get': {'operationId': 'searchTechniques', 'parameters': query_params, 'responses': ok}},
                '/api/v1/papers/{paper_id}': {'get': {'operationId': 'getPaper', 'parameters': [{'name': 'paper_id','in': 'path','required': True,'schema': {'type': 'integer'}}], 'responses': ok}},
                '/api/v1/papers/by-arxiv': {'get': {'operationId': 'getPaperByArxiv', 'parameters': [{'name': 'id','in': 'query','required': True,'schema': {'type': 'string'}}], 'responses': ok}},
                '/api/v1/papers/batch': {'post': {'operationId': 'getPapers', 'requestBody': {'required': True,'content': {'application/json': {'schema': {'type': 'object','required': ['ids'],'properties': {'ids': {'type':'array','minItems':1,'maxItems':50,'items':{'type':'integer'}}}}}}}, 'responses': ok}}}}


class Handler(BaseHTTPRequestHandler):
    api: VaultAPI
    slots = threading.BoundedSemaphore(4)

    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def reply(self, body, status=200, content_type='application/json; charset=utf-8'):
        raw = (json.dumps(body, ensure_ascii=False) if not isinstance(body, str) else body).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, HEAD, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch()

    def dispatch(self):
        if not self.slots.acquire(blocking=False):
            self.reply({'error': 'busy; retry later'}, 503)
            return
        try:
            parsed = urlsplit(self.path)
            path = unquote(parsed.path)
            params = {k: v[-1] for k, v in parse_qs(parsed.query, keep_blank_values=True).items()}
            if self.command == 'POST':
                if path != '/api/v1/papers/batch':
                    raise KeyError('unknown endpoint')
                size = integer(self.headers.get('Content-Length'), 'Content-Length', 0, 1, 10000)
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise RequestError('body must be a JSON object')
                result = self.api.papers(body.get('ids'))
            elif path in ('/health', '/api/v1/stats'):
                result = self.api.health()
            elif path in ('/openapi.json', '/api/v1/openapi.json'):
                result = openapi()
            elif path in ('/api/v1/search', '/api/v1/techniques'):
                result = self.api.search(params)
            elif path == '/api/v1/papers/by-arxiv':
                result = self.api.by_arxiv(params.get('id'))
            elif re.fullmatch(r'/api/v1/papers/[0-9]+', path):
                pid = integer(path.rsplit('/',1)[1], 'paper_id', None, 1, 2**63-1)
                rows = self.api.papers([pid])['items']
                if not rows:
                    raise KeyError('paper not found')
                result = rows[0]
            elif path == '/llms.txt':
                self.reply("IdeaScientist technique retrieval API\n"
                           "GET /health and /openapi.json to inspect coverage and the API contract.\n"
                           "GET /api/v1/search?q=activation+quantization&fields=solution,intuition&limit=5\n"
                           "Fields: title,problem_definition,challenge,intuition,solution. Default: solution,intuition.\n"
                           "Use concise English technical terms. mode=all requires all words; mode=any broadens recall.\n"
                           "Optional date_before (exclusive), date_from (inclusive), category, limit (1..50), offset (0..5000).\n"
                           "GET /api/v1/papers/{paper_id} retrieves the full results-masked proposal and provenance.\n"
                           "GET /api/v1/papers/by-arxiv?id=2401.01234 resolves an arXiv ID.\n"
                           'POST /api/v1/papers/batch with JSON {"ids":[1,2]} retrieves up to 50 records.\n'
                           "Use next_offset for pagination. Cite returned title, arxiv_id, URL and relevant method text.\n"
                           "Search is field-specific BM25, not semantic similarity. Smaller BM25 ranks first.\n"
                           "Records are masked proposals, not full papers or verified measured results.\n"
                           "Read provenance before interpreting a field. Missing method text is not invented.\n"
                           "There is no default date cutoff; specify one for historical evaluation.\n",
                           content_type='text/plain; charset=utf-8')
                return
            elif path in ('/', '/docs'):
                self.reply('<!doctype html><meta charset="utf-8"><title>IdeaScientist API</title><style>body{font:18px system-ui;max-width:900px;margin:50px auto;padding:20px;line-height:1.6}code{background:#eee;padding:4px}</style>'
                           '<h1>IdeaScientist · 技术检索 API</h1><p>搜索论文的方法与机制，并获取结构化论文依据。</p>'
                           '<ul><li><a href="/health">数据库状态</a></li><li><a href="/openapi.json">OpenAPI 文档</a> · <a href="/llms.txt">Agent 调用说明</a></li>'
                           '<li><a href="/api/v1/search?q=quantization&amp;fields=solution,intuition&amp;limit=3">示例：量化方法</a></li></ul>'
                           '<p><code>GET /api/v1/search?q=low+rank&amp;fields=solution&amp;limit=10</code></p>'
                           '<p>可搜索 title、problem_definition、challenge、intuition、solution；默认检索 solution,intuition。mode=all 要求全部词命中，mode=any 扩大召回。</p>'
                           '<p><code>GET /api/v1/papers/{paper_id}</code> 返回完整结构化记录；'
                           '<code>POST /api/v1/papers/batch</code> 接收 {"ids":[1,2]}，最多 50 条。</p>'
                           '<p>语料为英文，使用英文技术词查询。当前使用 BM25 词项检索；返回的是结果屏蔽后的提案依据。</p>', content_type='text/html; charset=utf-8')
                return
            else:
                raise KeyError('unknown endpoint')
            self.reply(result)
        except (RequestError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.reply({'error': str(exc)}, 400)
        except KeyError as exc:
            self.reply({'error': str(exc)}, 404)
        except sqlite3.OperationalError:
            self.reply({'error': 'search timeout or database unavailable; narrow the query and retry'}, 503)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except Exception:
            self.log_error('unexpected request error')
            self.reply({'error': 'internal server error'}, 500)
        finally:
            self.slots.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True, type=Path)
    parser.add_argument('--index', required=True, type=Path)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8901)
    parser.add_argument('--search-timeout', type=float, default=20)
    args = parser.parse_args()
    Handler.api = VaultAPI(args.db, args.index, args.search_timeout)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(json.dumps({'event': 'listening', 'host': args.host, 'port': args.port, **Handler.api.health()}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
