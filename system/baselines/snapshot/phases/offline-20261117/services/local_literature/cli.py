"""Local-only shared raw-paper search/read. No network client or generated fallback."""
from pathlib import Path
import argparse, contextlib, datetime, hashlib, json, re, sqlite3, sys
from urllib.parse import unquote, urlsplit

SCOPES = ('all_local_metadata', 'same_source_fulltext')
VIEWS = ('raw', 'insights')


class CorpusError(Exception):
    def __init__(self, code, message, **details):
        self.code, self.message, self.details = code, message, details
        super().__init__(message)


def normalize_identifier(value):
    value = unquote(str(value).strip()).lower().rstrip('/')
    parsed = urlsplit(value)
    if parsed.hostname in ('arxiv.org', 'www.arxiv.org', 'export.arxiv.org'):
        match = re.match(r'^/(?:abs|pdf|html)/(.+?)(?:\.pdf)?$', parsed.path)
        if match:
            return re.sub(r'v\d+$', '', match.group(1))
    if value.startswith('arxiv:'):
        value = value[6:]
    if re.fullmatch(r'(?:\d{4}\.\d{4,5}|[a-z.-]+/\d{7})v\d+', value):
        value = re.sub(r'v\d+$', '', value)
    if parsed.hostname in ('doi.org', 'dx.doi.org'):
        return parsed.path.lstrip('/')
    return value


def query_terms(query):
    # Quote every literal token, so native queries cannot become FTS operators/SQL.
    return list(dict.fromkeys(re.findall(r'[^\W_]+(?:[.-][^\W_]+)*', str(query).lower(), re.UNICODE)))


class Corpus:
    def __init__(self, path, insights_path=None):
        self.path = Path(path).resolve()
        if not self.path.is_file():
            raise CorpusError('corpus_missing', 'The frozen corpus database is missing.')
        self.db = sqlite3.connect('file:' + str(self.path) + '?mode=ro&immutable=1', uri=True)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA query_only=ON')
        self.manifest = json.loads(self.db.execute("SELECT value FROM metadata WHERE key='manifest'").fetchone()[0])
        self.corpus_id = self.manifest['corpus_id']
        self.insights_db = None
        if insights_path is not None:
            insight_file=Path(insights_path).resolve()
            if not insight_file.is_file():
                raise CorpusError('insights_missing','The explicitly supplied compressed-card database is missing.')
            self.insights_db=sqlite3.connect('file:'+str(insight_file)+'?mode=ro&immutable=1',uri=True)
            self.insights_db.row_factory=sqlite3.Row
            self.insights_db.execute('PRAGMA query_only=ON')

    def close(self):
        self.db.close()
        if self.insights_db is not None: self.insights_db.close()

    def _card(self, paper_id):
        if self.insights_db is None:
            raise CorpusError('insights_not_mounted','Compressed content is physically separate; supply an explicit insights database only for the InsightPro profile.')
        return self.insights_db.execute('SELECT * FROM insights WHERE paper_id=?',(paper_id,)).fetchone()

    def envelope(self, data, **extra):
        return {'ok': True, 'corpus_id': self.corpus_id, 'offline': True, 'network_fallback': False, 'data': data, **extra}

    def stats(self):
        return self.envelope(self.manifest)

    def _row(self, identifier, scope):
        if scope not in SCOPES:
            raise CorpusError('invalid_scope', 'Unknown corpus scope.', scopes=SCOPES)
        key = normalize_identifier(identifier)
        rows = self.db.execute('SELECT DISTINCT p.* FROM aliases a JOIN papers p USING(paper_id) WHERE a.alias=?', (key,)).fetchall()
        if not rows:
            raise CorpusError('paper_not_in_frozen_corpus', 'No local frozen paper matches this identifier. Public-network lookup is disabled.', identifier=identifier)
        if len(rows) > 1:
            raise CorpusError('ambiguous_identifier', 'This identifier matches multiple local papers; use an exact paper_id.', paper_ids=[r['paper_id'] for r in rows])
        row = rows[0]
        if scope == 'same_source_fulltext' and not row['same_source_fulltext']:
            raise CorpusError('outside_same_source_fulltext_scope', 'This paper lacks either a valid local text extraction or a matching compressed card.', paper_id=row['paper_id'])
        return row

    @staticmethod
    def _biblio(row):
        depth = 'full_text' if row['full_text'] is not None else ('abstract' if row['abstract'] else 'metadata')
        local_provenance=json.loads(row['fulltext_provenance']) if row['fulltext_provenance'] else {}
        source_urls=local_provenance.get('source_url_candidates',[])
        return {'local_read_id': 'paper:'+row['paper_id'], 'paper_id': row['paper_id'], 'id': row['paper_id'], 'title': row['title'], 'date': row['date'],
                'date_precision': row['date_precision'], 'arxiv': row['arxiv'], 'venue': row['venue'],
                'source_url': row['source_url'] or (source_urls[0] if source_urls else None), 'read_depth': depth, 'full_text_available': row['full_text'] is not None,
                'missing_full_text': row['full_text'] is None, 'compressed_card_available': bool(row['has_insights']),
                'same_source_fulltext': bool(row['same_source_fulltext']), 'raw_record_sha256': row['raw_record_sha256']}

    def search(self, query, limit=10, offset=0, scope='all_local_metadata', view='raw', mode='any', date_before=None):
        if scope not in SCOPES or view not in VIEWS or mode not in ('any', 'all'):
            raise CorpusError('invalid_search_options', 'Unsupported scope, view, or match mode.')
        if not 1 <= int(limit) <= 1000 or int(offset) < 0:
            raise CorpusError('invalid_pagination', 'Use limit 1–1000 and a nonnegative offset.')
        terms = query_terms(query)
        if not terms:
            return self.envelope([], query=query, scope=scope, view=view, total=0, limit=limit, offset=offset)
        expression = (' OR ' if mode == 'any' else ' AND ').join('"' + token.replace('"', '""') + '"' for token in terms)
        where = ['papers_fts MATCH ?'];params=[expression]
        if scope == 'same_source_fulltext': where.append('p.same_source_fulltext=1')
        if date_before:
            if not re.fullmatch(r'\d{4}(?:-\d{2}(?:-\d{2})?)?', str(date_before)):
                raise CorpusError('invalid_date', 'date_before must be YYYY, YYYY-MM or YYYY-MM-DD.')
            # Source metadata has year precision. Include only years definitely before the cutoff.
            where.append('p.date IS NOT NULL AND p.date < ?');params.append(str(date_before)[:4])
        clause=' AND '.join(where)
        total=self.db.execute('SELECT count(*) FROM papers_fts JOIN papers p ON p.rowid=papers_fts.rowid WHERE '+clause,params).fetchone()[0]
        rows=self.db.execute('SELECT p.*,bm25(papers_fts,5.0,2.0,1.0) AS score FROM papers_fts JOIN papers p ON p.rowid=papers_fts.rowid WHERE '+clause+' ORDER BY score,p.paper_id LIMIT ? OFFSET ?',params+[int(limit),int(offset)]).fetchall()
        results=[]
        for row in rows:
            item=self._biblio(row);item.update(bm25=row['score'],view=view)
            if view == 'raw':
                item['snippet']=row['abstract'][:1200]
                item['snippet_source']='original_abstract'
                item['snippet_truncated']=len(row['abstract'])>1200
            else:
                card=self._card(row['paper_id'])
                value=json.loads(card['content']) if card else {}
                insight=value.get('insight') or {}
                item['snippet']=str(insight.get('statement','') if isinstance(insight,dict) else insight)[:1200]
                item['snippet_source']='existing_compressed_source_card' if card else 'unavailable'
                item['compressed_card_sha256']=card['sha256'] if card else None
            results.append(item)
        return self.envelope(results, query=query, scope=scope, view=view, total=total, limit=int(limit),offset=int(offset),
                             ranking='raw_title_abstract_fulltext_fts5_bm25', same_rank_for_raw_and_insights=True)

    def read(self, identifier, scope='all_local_metadata', view='raw', offset_chars=0, max_chars=None, require_full_text=False):
        if view not in VIEWS:
            raise CorpusError('invalid_view', 'Use raw or insights.')
        if int(offset_chars) < 0 or (max_chars is not None and int(max_chars) < 1):
            raise CorpusError('invalid_pagination', 'Character offset must be nonnegative and max_chars positive.')
        row=self._row(identifier,scope);item=self._biblio(row);item.update(view=view,scope=scope)
        if require_full_text and row['full_text'] is None:
            raise CorpusError('full_text_unavailable', 'Only frozen metadata/abstract is available; no generated or network fallback is permitted.',paper_id=row['paper_id'],read_depth=item['read_depth'])
        if view == 'raw':
            text=row['full_text'] if row['full_text'] is not None else row['abstract']
            expected=row['full_text_sha256'] if row['full_text'] is not None else hashlib.sha256(text.encode()).hexdigest()
            item['provenance']=json.loads(row['fulltext_provenance'] if row['full_text'] is not None else row['provenance'])
            item['metadata_provenance']=json.loads(row['provenance'])
            item['abstract']=row['abstract']
            item['content_kind']='original_local_text_extraction' if row['full_text'] is not None else 'original_abstract'
        else:
            card=self._card(row['paper_id'])
            if card is None:
                raise CorpusError('compressed_card_unavailable', 'No existing compressed card is bound to this paper ID.',paper_id=row['paper_id'])
            text=card['content'];expected=card['sha256'];item['provenance']=json.loads(card['provenance'])
            item['content_kind']='existing_compressed_source_card'
            item['read_depth']='compressed_insights'
            item['comparison_limit']='Paper-ID alignment only; broad abstract-only rows are not full-text-equivalent comparisons.'
        if hashlib.sha256(text.encode()).hexdigest()!=expected:
            raise CorpusError('content_hash_mismatch','The stored content failed its frozen hash check.',paper_id=row['paper_id'])
        start=int(offset_chars);stop=None if max_chars is None else start+int(max_chars)
        part=text[start:stop]
        item.update(text=part,content_sha256=expected,returned_text_sha256=hashlib.sha256(part.encode()).hexdigest(),
                    total_characters=len(text),offset_chars=start,returned_characters=len(part),truncated=start>0 or (stop is not None and stop<len(text)))
        return self.envelope(item,scope=scope,view=view)


def dispatch(corpus,args):
    if args.command=='stats': return corpus.stats()
    if args.command=='search': return corpus.search(args.query,args.limit,args.offset,args.scope,args.view,args.mode,args.date_before)
    return corpus.read(args.id,args.scope,args.view,args.offset_chars,args.max_chars,args.require_full_text)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus',type=Path,default=Path(__file__).resolve().parents[2]/'inputs/corpus/corpus.sqlite')
    parser.add_argument('--audit-log',type=Path)
    parser.add_argument('--insights',type=Path,help='Explicit separate compressed-card database; do not mount for raw baseline profiles.')
    sub=parser.add_subparsers(dest='command',required=True);sub.add_parser('stats')
    search=sub.add_parser('search');search.add_argument('--query',required=True);search.add_argument('--limit',type=int,default=10);search.add_argument('--offset',type=int,default=0);search.add_argument('--mode',choices=['any','all'],default='any');search.add_argument('--date-before')
    read=sub.add_parser('read');read.add_argument('--id',required=True);read.add_argument('--offset-chars',type=int,default=0);read.add_argument('--max-chars',type=int);read.add_argument('--require-full-text',action='store_true')
    for p in [search,read]:
        p.add_argument('--scope',choices=SCOPES,default='all_local_metadata');p.add_argument('--view',choices=VIEWS,default='raw')
    args=parser.parse_args();code=0
    try:
        with contextlib.closing(Corpus(args.corpus,args.insights)) as corpus: result=dispatch(corpus,args)
    except CorpusError as exc:
        result={'ok':False,'offline':True,'network_fallback':False,'error':{'code':exc.code,'message':exc.message,**exc.details}};code=2
    if args.audit_log:
        args.audit_log.parent.mkdir(parents=True,exist_ok=True)
        with args.audit_log.open('a') as stream:
            record={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':args.command,'corpus_id':result.get('corpus_id'),'arguments':{k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items() if k!='audit_log'},'response_sha256':hashlib.sha256(json.dumps(result,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),'ok':result['ok']}
            stream.write(json.dumps(record,ensure_ascii=False)+'\n')
    print(json.dumps(result,ensure_ascii=False))
    return code


if __name__=='__main__':
    sys.exit(main())
