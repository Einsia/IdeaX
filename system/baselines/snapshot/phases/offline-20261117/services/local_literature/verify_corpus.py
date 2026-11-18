"""Read-only acceptance of raw evidence, representation isolation and local retrieval."""
from pathlib import Path
from unittest.mock import patch
import contextlib, datetime, hashlib, json, socket, sqlite3, sys
from cli import Corpus, CorpusError

ROOT=Path(__file__).resolve().parents[2]

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()

def run():
    manifest=json.loads((ROOT/'inputs/corpus/manifest.json').read_text())
    raw_path=ROOT/'inputs/corpus/corpus.sqlite';insight_path=ROOT/'inputs/insightpro_private/insights.sqlite'
    checks=[];calls=[]
    def block(*args,**kwargs):calls.append('attempt');raise AssertionError('No network allowed')
    with patch.object(socket.socket,'connect',side_effect=block),patch.object(socket,'create_connection',side_effect=block),contextlib.closing(Corpus(raw_path)) as raw:
        tables={r[0] for r in raw.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert 'insights' not in tables
        try:raw.db.execute("UPDATE papers SET title='mutated' WHERE paper_id='89614'")
        except sqlite3.OperationalError:pass
        else:raise AssertionError('Raw database accepted a mutation')
        checks.append('raw_database_has_no_compressed_table_and_rejects_writes')
        source=Path(manifest['sources']['raw_metadata']['path']);n=0;title_whitespace=0
        actual={r['paper_id']:(r['title'],r['abstract'],r['arxiv']) for r in raw.db.execute('SELECT paper_id,title,abstract,arxiv FROM papers')}
        with source.open() as f:
            for line in f:
                row=json.loads(line);ident=str(row['id'])
                if ident not in actual:continue
                title,abstract,arxiv=actual[ident]
                assert abstract==(row.get('abstract') or '')
                assert arxiv==(row.get('arxiv') or None)
                if title!=row['title']:
                    assert title==row['title'].strip();title_whitespace+=1
                n+=1
        assert n==manifest['statistics']['papers']
        checks.append('all_283008_paper_ids_abstracts_and_arxiv_ids_match_original_records')
        local=raw.read('https://arxiv.org/pdf/2409.07429v1.pdf')['data']
        assert local['paper_id']=='89614' and local['full_text_available'] and local['read_depth']=='full_text'
        source_text=Path(local['provenance']['path']).read_bytes()
        assert local['text'].encode()==source_text and local['content_sha256']==hashlib.sha256(source_text).hexdigest()
        checks.append('versioned_arxiv_pdf_url_resolves_to_exact_original_AWM_text_bytes')
        part=raw.read('89614',offset_chars=15,max_chars=250)['data'];assert part['text']==local['text'][15:265] and part['truncated']
        checks.append('explicit_text_pagination_preserves_original_content')
        expel=raw.read('2308.10144')['data'];assert expel['read_depth']=='abstract' and expel['missing_full_text']
        try:raw.read('2308.10144',require_full_text=True)
        except CorpusError as exc:assert exc.code=='full_text_unavailable'
        else:raise AssertionError('Corrupted ExpeL full text was accepted')
        checks.append('NUL_corrupted_ExpeL_is_abstract_only_and_fulltext_requirement_fails_honestly')
        try:raw.read('https://example.invalid/no-paper')
        except CorpusError as exc:assert exc.code=='paper_not_in_frozen_corpus'
        else:raise AssertionError('Unknown source unexpectedly returned evidence')
        checks.append('unknown_URL_does_not_trigger_network_or_generated_fallback')
        try:raw.read('89614',view='insights')
        except CorpusError as exc:assert exc.code=='insights_not_mounted'
        else:raise AssertionError('Raw profile exposed compressed content')
        checks.append('raw_profile_cannot_read_compressed_content')
        result=raw.search('Agent Workflow Memory',limit=7,mode='all',scope='same_source_fulltext')
        again=raw.search('Agent Workflow Memory',limit=7,mode='all',scope='same_source_fulltext')
        assert result==again and any(x['paper_id']=='89614' for x in result['data'])
        assert all(x['snippet_source']=='original_abstract' for x in result['data'])
        checks.append('deterministic_original_text_BM25_search')
        filtered=raw.search('language model',limit=10,date_before='2025-01-01')
        assert all(x['date']<'2025' for x in filtered['data'])
        checks.append('year_precision_cutoff_excludes_uncertain_same_year')
        with contextlib.closing(Corpus(raw_path,insight_path)) as combined:
            compressed=combined.search('Agent Workflow Memory',limit=7,mode='all',view='insights',scope='same_source_fulltext')
            assert [(x['paper_id'],x['bm25']) for x in compressed['data']]==[(x['paper_id'],x['bm25']) for x in result['data']]
            card=combined.read('89614',scope='same_source_fulltext',view='insights')['data']
            assert card['paper_id']==local['paper_id'] and card['read_depth']=='compressed_insights'
            assert card['provenance']['raw_paper_binding']=='exact_original_paper_id'
            assert card['text']!=local['text']
        checks.append('explicit_insightpro_profile_uses_same_raw_ranking_and_same_paper_identity')
        for row in raw.db.execute('SELECT paper_id,full_text,full_text_sha256,fulltext_provenance FROM papers WHERE full_text IS NOT NULL'):
            body=row['full_text'].encode();prov=json.loads(row['fulltext_provenance'])
            assert b'\0' not in body and hashlib.sha256(body).hexdigest()==row['full_text_sha256']==sha(prov['path'])
        checks.append('all_1948_included_texts_match_original_source_bytes_and_exclude_NUL')
    assert not calls
    assert sha(raw_path)==manifest['database']['sha256'] and sha(insight_path)==manifest['insights_database']['sha256']
    checks.append('frozen_raw_and_private_databases_match_manifest_SHA256')
    receipt={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'passed':True,'checks':checks,'network_calls':0,'model_calls':0,
             'corpus_id':manifest['corpus_id'],'statistics':manifest['statistics'],'title_outer_whitespace_normalizations':title_whitespace,
             'raw_database_sha256':sha(raw_path),'private_insights_database_sha256':sha(insight_path),
             'cli_sha256':sha(ROOT/'services/local_literature/cli.py'),'verification_sha256':sha(__file__)}
    (ROOT/'state/local_corpus_acceptance.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))

if __name__=='__main__':run()
