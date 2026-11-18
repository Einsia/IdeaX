"""The native S2 data interface, backed solely by the frozen common corpus."""
import datetime
import importlib.util
import json
from pathlib import Path
import re
import sqlite3

from evidence import digest, encode, event, freeze, sha, signature

ADAPTER_REVISION = 'local-bm25-v1-recommendation-only'
NAMESPACE = 'localpaper:'


def date_year_bounds(value):
    if value is None: return None, None
    if not isinstance(value, str): raise ValueError('Date filter must be a string or None')
    def bound(text, upper=False):
        if not text: return None
        if not re.fullmatch(r'\d{4}(?:-\d{2}(?:-\d{2})?)?', text):
            raise ValueError('Unsupported native date filter')
        pieces = [int(x) for x in text.split('-')]
        year = pieces[0]
        if len(pieces) == 1: return year
        if len(pieces) == 2:
            month = pieces[1]
            datetime.date(year, month, 1)
            return year if (month == 12 if upper else month == 1) else year - 1 if upper else year + 1
        day = datetime.date(*pieces)
        if upper: return year if day.month == 12 and day.day == 31 else year - 1
        return year if day.month == 1 and day.day == 1 else year + 1
    if ':' not in value:
        return bound(value), bound(value, upper=True)
    if value.count(':') != 1: raise ValueError('Invalid native date range')
    lower, upper = value.split(':')
    return bound(lower), bound(upper, upper=True)


class LocalS2Client:
    def __init__(self, output, material, corpus_signature, seed_mapping=None):
        self.output = Path(output)
        self.seed_mapping = seed_mapping
        self.material = material
        self.path = Path(material['raw_corpus']['path'])
        self.expected_signature = list(corpus_signature)
        self._verify_corpus()
        code = Path(material['selected_retrieval_policy']['source'])
        if sha(code) != material['selected_retrieval_policy']['source_sha256']:
            raise RuntimeError('Frozen common retrieval implementation changed')
        spec = importlib.util.spec_from_file_location('bound_common_corpus_cli', code)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        self.query_terms, self.normalize_identifier = helper.query_terms, helper.normalize_identifier
        self.db = sqlite3.connect('file:' + str(self.path) + '?mode=ro&immutable=1', uri=True)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA query_only=ON')
        db_manifest = json.loads(self.db.execute("SELECT value FROM metadata WHERE key='manifest'").fetchone()[0])
        if db_manifest['corpus_id'] != material['raw_corpus']['corpus_id']:
            raise RuntimeError('Frozen corpus identity mismatch')
        self.receipts = []

    def _verify_corpus(self):
        if signature(self.path) != self.expected_signature:
            raise RuntimeError('Reviewed immutable corpus file metadata changed')

    def close(self): self.db.close()

    @staticmethod
    def paper(row):
        date = row['date']
        year = int(date[:4]) if date and re.fullmatch(r'\d{4}', date) else None
        return {'paperId': NAMESPACE + row['paper_id'], 'title': row['title'],
                'abstract': row['abstract'], 'year': year, 'publicationDate': None,
                'citationCount': None, 'venue': row['venue'] or '', 'authors': [],
                'externalIds': {'ArXiv': row['arxiv']} if row['arxiv'] else {},
                'url': row['source_url'] or ''}

    def _record(self, method, arguments, rows, result, **details):
        value = {'adapter_revision': ADAPTER_REVISION, 'method': method, 'arguments': arguments,
                 'corpus_id': self.material['raw_corpus']['corpus_id'],
                 'corpus_sha256': self.material['raw_corpus']['sha256'],
                 'data_version': self.material['raw_corpus']['data_version'],
                 'comparison_scope': 'official-recommendation-graph-local-common-corpus-retrieval-adaptation',
                 'comparison_scope_label': self.material['comparison_scope'],
                 'result': result, 'records': [
                     {'raw_id': r['paper_id'], 'raw_record_sha256': r['raw_record_sha256'],
                      'title_sha256': digest(r['title'].encode()),
                      'abstract_sha256': digest((r['abstract'] or '').encode()),
                      'bm25': r['score'] if 'score' in r.keys() else None,
                      'rank': i + 1} for i, r in enumerate(rows)],
                 'public_network': False, 'network_fallback': False, **details}
        ident = digest(encode(value))
        path = self.output / 'retrieval' / (ident + '.json')
        freeze(path, value)
        event(self.output / 'retrieval_events.jsonl', 'local_data_response', method=method,
              receipt=str(path), receipt_sha256=sha(path), result_count=len(rows))
        self.receipts.append(value | {'receipt': str(path), 'receipt_sha256': sha(path)})
        return result

    def _search(self, query, limit, date_filter, exclude=None, method='search_papers', pool=None, original_query=None, alias_evidence=None):
        self._verify_corpus()
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError('Native retrieval limit must be between 1 and 1000')
        tokens = self.query_terms(query)
        expression = ' OR '.join('"' + token.replace('"', '""') + '"' for token in tokens)
        lower, upper = date_year_bounds(date_filter)
        where, params = ['papers_fts MATCH ?'], [expression]
        if date_filter is not None:
            where.append("p.date IS NOT NULL AND length(p.date)=4")
            if lower is not None: where.append('CAST(p.date AS INTEGER)>=?'); params.append(lower)
            if upper is not None: where.append('CAST(p.date AS INTEGER)<=?'); params.append(upper)
        if exclude is not None: where.append('p.paper_id<>?'); params.append(exclude)
        sql = ('SELECT p.*,bm25(papers_fts,5.0,2.0,1.0) AS score FROM papers_fts '
               'JOIN papers p ON p.rowid=papers_fts.rowid WHERE ' + ' AND '.join(where)
               + ' ORDER BY score,p.paper_id LIMIT ?')
        rows = self.db.execute(sql, params + [limit]).fetchall() if tokens else []
        ids = [r['paper_id'] for r in rows]
        if len(set(ids)) != len(ids): raise RuntimeError('Frozen corpus returned duplicate raw IDs')
        arguments = {'query': original_query if original_query is not None else query, 'limit': limit, 'publication_date_or_year': date_filter}
        if method == 'recommendations': arguments = {'paper_id': NAMESPACE + exclude, 'limit': limit, 'pool': pool}
        result = [self.paper(r) for r in rows]
        return self._record(method, arguments, rows, result, effective_query=query,
                            seed_alias_evidence=alias_evidence,
                            original_query_sha256=digest((original_query if original_query is not None else query).encode()),
                            effective_fts_expression=expression, effective_year_bounds=[lower, upper],
                            date_precision='year', excluded_self_raw_id=exclude,
                            effective_pool='entire_selected_frozen_common_corpus',
                            ranking='fts5_bm25_title5_abstract2_fulltext1_ascending_then_raw_id',
                            edge_semantics='local_similarity_recommendation' if exclude is not None else None)

    def search_papers(self, query, limit, publication_date_or_year=None):
        mapping = self.seed_mapping
        if mapping is not None and query == mapping['topic']:
            return self._search(mapping['raw_query'], limit, publication_date_or_year, original_query=query,
                                alias_evidence={k: mapping[k] for k in ('domain_id', 'topic_sha256',
                                    'alias_source', 'alias_source_sha256', 'alias_source_field', 'raw_query')})
        return self._search(query, limit, publication_date_or_year)

    def _get_row(self, paper_id):
        if paper_id.startswith(NAMESPACE):
            return self.db.execute('SELECT * FROM papers WHERE paper_id=?', (paper_id[len(NAMESPACE):],)).fetchone()
        normalized = self.normalize_identifier(paper_id)
        rows = self.db.execute('SELECT DISTINCT p.* FROM aliases a JOIN papers p USING(paper_id) WHERE a.alias=?',
                               (normalized,)).fetchall()
        if len(rows) > 1: raise RuntimeError('Ambiguous local alias; an exact localpaper ID is required')
        return rows[0] if rows else None

    def recommendations(self, paper_id, limit, pool=None):
        self._verify_corpus()
        if pool not in (None, 'recent', 'all-cs'): raise ValueError('Unrecognized native recommendation pool')
        if not paper_id.startswith(NAMESPACE): raise ValueError('Recommendations require an exact localpaper ID')
        row = self._get_row(paper_id)
        if row is None:
            return self._record('recommendations', {'paper_id': paper_id, 'limit': limit, 'pool': pool}, [], [],
                                source_missing=True, effective_pool='entire_selected_frozen_common_corpus')
        return self._search(row['title'], limit, None, exclude=row['paper_id'], method='recommendations', pool=pool)

    def get_paper(self, paper_id):
        self._verify_corpus()
        row = self._get_row(paper_id)
        return self._record('get_paper', {'paper_id': paper_id}, [row] if row is not None else [],
                            self.paper(row) if row is not None else None)
