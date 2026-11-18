"""Freeze existing local paper metadata, text and separately stored insight cards."""
from pathlib import Path
import argparse, collections, datetime, hashlib, json, re, sqlite3, time


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def norm_title(value):
    return ''.join(re.findall(r'[a-z0-9]+', str(value).lower()))


def ro(path):
    return sqlite3.connect('file:' + str(Path(path).resolve()) + '?mode=ro&immutable=1', uri=True)


def build(snapshot, output, domains_path):
    snapshot, output = Path(snapshot).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    target = output / 'corpus.sqlite'
    if target.exists():
        raise SystemExit('Refusing to replace an existing frozen corpus')
    at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    inputs = {'raw_metadata': snapshot / 'data/allpapers/papers.jsonl',
              'work_metadata': snapshot / 'lit.db',
              'compressed_cards': snapshot / 'data/allpapers/insight_lib/library.db',
              'domain_index': snapshot / 'data/allpapers/insight_lib/api_index.db'}
    sources = {key: {'path': str(path), 'sha256': sha_file(path), 'bytes': path.stat().st_size,
                     'mtime_ns': path.stat().st_mtime_ns} for key, path in inputs.items()}
    db = sqlite3.connect(output / 'corpus.building.sqlite')
    insights_db = sqlite3.connect(output / 'insights.building.sqlite')
    insights_db.execute('CREATE TABLE insights(paper_id TEXT PRIMARY KEY, content TEXT NOT NULL, sha256 TEXT NOT NULL, provenance TEXT NOT NULL)')
    db.executescript('''
    PRAGMA journal_mode=OFF;
    PRAGMA synchronous=OFF;
    CREATE TABLE papers(paper_id TEXT PRIMARY KEY, title TEXT NOT NULL, abstract TEXT NOT NULL,
        date TEXT, date_precision TEXT, arxiv TEXT, venue TEXT, source_url TEXT,
        full_text TEXT, full_text_sha256 TEXT, raw_record_sha256 TEXT NOT NULL,
        provenance TEXT NOT NULL, fulltext_provenance TEXT, has_insights INTEGER NOT NULL DEFAULT 0,
        same_source_fulltext INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE aliases(alias TEXT NOT NULL, paper_id TEXT NOT NULL, kind TEXT NOT NULL,
        PRIMARY KEY(alias,paper_id));
    CREATE TABLE domain_papers(domain_id TEXT NOT NULL,paper_id TEXT NOT NULL,PRIMARY KEY(domain_id,paper_id));
    CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE VIRTUAL TABLE papers_fts USING fts5(title,abstract,full_text,content='papers',content_rowid='rowid', tokenize='unicode61');
    ''')
    arxiv_map, title_map = collections.defaultdict(list), collections.defaultdict(list)
    origin_counts = collections.Counter()
    excluded, text_manifest = [], []
    papers_digest = hashlib.sha256()
    with inputs['raw_metadata'].open('rb') as stream:
        for line_number, line in enumerate(stream, 1):
            value = json.loads(line)
            ident, title = str(value['id']), str(value.get('title') or '').strip()
            if not title or value.get('src') not in ('official', 'svalbard'):
                excluded.append({'kind': 'metadata', 'line': line_number, 'reason': 'missing_title_or_unrecognized_raw_metadata_origin'})
                continue
            abstract = str(value.get('abstract') or '')
            if '\x00' in title or '\x00' in abstract:
                excluded.append({'kind': 'metadata', 'line': line_number, 'reason': 'nul_corruption'})
                continue
            arxiv = str(value.get('arxiv') or '').strip() or None
            year = str(value.get('year') or '')
            date = year if re.fullmatch(r'\d{4}', year) else None
            url = 'https://arxiv.org/abs/' + arxiv if arxiv else None
            line_sha = hashlib.sha256(line).hexdigest()
            raw_fields = {'paper_id': ident, 'title': title, 'abstract': abstract, 'date': date,
                          'arxiv': arxiv, 'venue': value.get('conference'), 'source_url': url}
            raw_sha = hashlib.sha256(dump(raw_fields).encode()).hexdigest()
            provenance = {'source_path': sources['raw_metadata']['path'], 'source_sha256': sources['raw_metadata']['sha256'],
                          'source_line': line_number, 'source_line_sha256': line_sha, 'metadata_origin': value['src'],
                          'raw_fields': ['title', 'abstract', 'conference', 'year', 'arxiv'],
                          'excluded_generated_fields': ['problem_definition', 'intuition'],
                          'source_mtime_ns': sources['raw_metadata']['mtime_ns'], 'acquired_at': None,
                          'acquisition_date_status': 'not_recorded_in_frozen_metadata', 'frozen_at': at}
            db.execute('INSERT INTO papers(paper_id,title,abstract,date,date_precision,arxiv,venue,source_url,raw_record_sha256,provenance) VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (ident, title, abstract, date, 'year' if date else 'unknown', arxiv, value.get('conference'), url, raw_sha, dump(provenance)))
            aliases = [(ident, ident, 'paper_id'), ('paper:' + ident, ident, 'paper_id')]
            if arxiv:
                arxiv_map[arxiv.lower()].append(ident)
                aliases.extend((a, ident, 'arxiv') for a in [arxiv.lower(), 'arxiv:' + arxiv.lower(), url.lower(), 'https://arxiv.org/pdf/' + arxiv.lower()])
            title_map[norm_title(title)].append(ident)
            db.executemany('INSERT OR IGNORE INTO aliases VALUES(?,?,?)', aliases)
            origin_counts[value['src']] += 1
            papers_digest.update((ident + ':' + raw_sha + '\n').encode())
    db.commit()
    print(dump({'stage': 'raw_metadata', 'counts': dict(origin_counts)}), flush=True)
    work_db = ro(inputs['work_metadata']); work_db.row_factory = sqlite3.Row
    id_map = collections.defaultdict(list)
    for row in work_db.execute('SELECT work_id,type,value FROM identifiers'):
        id_map[row['work_id']].append((row['type'], row['value']))
    works = {row['work_id']: dict(row) for row in work_db.execute('SELECT * FROM works')}
    urls = collections.defaultdict(list)
    for row in work_db.execute("SELECT work_id,url FROM venue_papers WHERE url IS NOT NULL AND url<>''"):
        urls[row['work_id']].append(row['url'])
    attached = set()
    for path in sorted((snapshot / 'fetched').glob('*.txt')):
        raw = path.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
        record = {'path': str(path), 'sha256': digest, 'bytes': len(raw), 'mtime_ns': path.stat().st_mtime_ns, 'work_id': path.stem}
        reason = None
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            text = ''; reason = 'invalid_utf8'
        if b'\0' in raw: reason = 'nul_corruption'
        elif len(text.strip()) < 1000: reason = 'less_than_1000_characters'
        elif re.search(r'(?is)^\s*(?:<!doctype\s+html|<html|access denied|404 not found)', text): reason = 'html_or_error_response'
        work = works.get(path.stem)
        if work is None: reason = reason or 'no_work_metadata'
        candidates = []
        for kind, val in id_map[path.stem]:
            if kind == 'arxiv': candidates += arxiv_map.get(re.sub(r'v\d+$', '', val.lower()), [])
        method = 'exact_arxiv_identifier'
        if not candidates and work:
            candidates = title_map.get(norm_title(work['title']), []); method = 'unique_normalized_title'
        candidates = sorted(set(candidates))
        if len(candidates) != 1: reason = reason or ('ambiguous_raw_paper_identity' if candidates else 'no_raw_paper_identity')
        ident = candidates[0] if len(candidates) == 1 else None
        if ident in attached: reason = reason or 'duplicate_text_for_same_paper'
        record.update(paper_id=ident, identity_binding=method, status='excluded' if reason else 'included', reason=reason)
        text_manifest.append(record)
        if reason:
            excluded.append(record);continue
        prov = {**record, 'work_source': sources['work_metadata'], 'source_url_candidates': sorted(set(urls[path.stem])),
                'work_earliest': work['earliest'], 'local_extraction_only': True, 'extraction_completeness_manually_verified': False,
                'acquired_at': None, 'frozen_at': at}
        db.execute('UPDATE papers SET full_text=?,full_text_sha256=?,fulltext_provenance=? WHERE paper_id=?', (text,digest,dump(prov),ident))
        aliases = [(path.stem.lower(),ident,'litgraph_work')]
        for kind,val in id_map[path.stem]:
            if kind in ('arxiv','doi','url'):
                aliases.append((val.lower().rstrip('/'),ident,kind))
                if kind=='doi':aliases.append(('https://doi.org/'+val.lower(),ident,kind))
        aliases.extend((url.lower().rstrip('/'),ident,'source_url') for url in urls[path.stem])
        db.executemany('INSERT OR IGNORE INTO aliases VALUES(?,?,?)', aliases)
        attached.add(ident);papers_digest.update((ident+':full_text:'+digest+'\n').encode())
    db.commit();work_db.close()
    print(dump({'stage':'local_texts','included':len(attached),'examined':len(text_manifest)}),flush=True)
    cards = ro(inputs['compressed_cards']);card_count=0
    paper_ids = {row[0] for row in db.execute('SELECT paper_id FROM papers')}
    for ident,content in cards.execute('SELECT id,data FROM papers ORDER BY id'):
        if str(ident) not in paper_ids: continue
        digest=hashlib.sha256(content.encode()).hexdigest()
        prov={'source_path':sources['compressed_cards']['path'],'source_sha256':sources['compressed_cards']['sha256'],
              'table':'papers','row_id':str(ident),'content_sha256':digest,'representation':'existing_compressed_source_card',
              'generated_by_model':True,'compression_created_at':None,'frozen_at':at,
              'raw_paper_binding':'exact_original_paper_id','claims_not_substitute_for_original_text':True}
        insights_db.execute('INSERT INTO insights VALUES(?,?,?,?)',(str(ident),content,digest,dump(prov)))
        db.execute('UPDATE papers SET has_insights=1,same_source_fulltext=(full_text IS NOT NULL) WHERE paper_id=?',(str(ident),))
        papers_digest.update((str(ident)+':insights:'+digest+'\n').encode());card_count+=1
    cards.close();db.commit();insights_db.commit()
    idx=ro(inputs['domain_index'])
    db.executemany('INSERT INTO domain_papers VALUES(?,?)',((d,str(p)) for d,p in idx.execute('SELECT domain_id,paper_id FROM domain_papers') if str(p) in paper_ids))
    idx.close()
    print(dump({'stage':'compressed_cards','included':card_count}),flush=True)
    db.execute("INSERT INTO papers_fts(papers_fts) VALUES('rebuild')")
    db.execute('CREATE INDEX domain_by_paper ON domain_papers(paper_id)')
    db.execute('CREATE INDEX strict_scope ON papers(same_source_fulltext)')
    stats=dict(db.execute('''SELECT 'papers',count(*) FROM papers UNION ALL SELECT 'with_abstract',count(*) FROM papers WHERE length(abstract)>0 UNION ALL SELECT 'with_full_text',count(*) FROM papers WHERE full_text IS NOT NULL UNION ALL SELECT 'same_source_fulltext',count(*) FROM papers WHERE same_source_fulltext=1'''))
    stats['compressed_cards']=card_count
    coverage=[]
    domains=json.loads(Path(domains_path).read_text())
    for domain in domains:
        counts=db.execute('''SELECT count(*),coalesce(sum(length(p.abstract)>0),0),coalesce(sum(p.full_text IS NOT NULL),0),coalesce(sum(p.has_insights),0),coalesce(sum(p.same_source_fulltext),0) FROM domain_papers d JOIN papers p USING(paper_id) WHERE d.domain_id=?''',(domain['id'],)).fetchone()
        coverage.append(dict(domain_id=domain['id'],papers=counts[0],with_abstract=counts[1],with_full_text=counts[2],with_insights=counts[3],same_source_fulltext=counts[4],missing_full_text=counts[0]-counts[2]))
    corpus_id='offline-local-'+papers_digest.hexdigest()
    manifest={'schema_version':1,'corpus_id':corpus_id,'frozen_at':at,'default_scope':'all_local_metadata',
              'scopes':{'all_local_metadata':'All frozen authentic paper titles/abstracts plus local full text when available. Missing text is explicit; no network fallback.',
                        'same_source_fulltext':'Subset with both a validated local text extraction and existing compressed source card bound to exactly the same original paper ID.'},
              'statistics':stats,'metadata_origins':dict(origin_counts),'sources':sources,
              'text_validation':{'examined':len(text_manifest),'included':len(attached),'excluded_reasons':dict(collections.Counter(x['reason'] for x in text_manifest if x['reason']))},
              'network_calls':0,'model_calls':0,'online_generation_history_imported':False,
              'raw_search_fields':['title','abstract','full_text'],'ranking':'SQLite FTS5 BM25, weights title=5 abstract=2 full_text=1; ascending score then paper_id',
              'raw_forbidden_fields':['problem_definition','intuition','proposal_masked','insight','thesis','evaluation','observations'],
              'date_policy':'Retain supplied year precision; do not fabricate a publication day or acquisition date.',
              'same_source_limitation':'Matching paper ID does not prove extraction completeness or that every compressed claim is supported. Abstract-only broad corpus is not a full-text-equivalent compression comparison.',
              'representation_isolation':'Raw database has no compressed content; a separate insights database requires an explicit path and must not be mounted in baseline containers.',
              'old_insightpro_results_comparable':False,'builder_sha256':sha_file(__file__)}
    db.execute('INSERT INTO metadata VALUES(?,?)',('manifest',dump(manifest)));db.commit()
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok';db.close()
    assert insights_db.execute('PRAGMA integrity_check').fetchone()[0]=='ok';insights_db.close()
    insights_target=output.parent/'insightpro_private'/'insights.sqlite'
    insights_target.parent.mkdir(parents=True,exist_ok=True)
    (output/'insights.building.sqlite').rename(insights_target)
    insights_target.chmod(0o444)
    (output/'corpus.building.sqlite').rename(target)
    manifest['database']={'path':str(target),'bytes':target.stat().st_size,'sha256':sha_file(target)}
    manifest['insights_database']={'path':str(insights_target),'bytes':insights_target.stat().st_size,'sha256':sha_file(insights_target)}
    for name,value in [('manifest.json',manifest),('coverage_38_domains.json',coverage),('text_manifest.json',text_manifest),('excluded_records.json',excluded)]:
        (output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    target.chmod(0o444)
    print(dump({'stage':'completed','manifest':str(output/'manifest.json'),'statistics':stats,'corpus_id':corpus_id}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot',required=True);parser.add_argument('--output',required=True);parser.add_argument('--domains',required=True);args=parser.parse_args()
    build(args.snapshot,args.output,args.domains)
