"""Build a native seed from frozen official records, with real offline SPECTER2 vectors."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import copy
import difflib
import hashlib
import json
import os
import re
import sqlite3
import unicodedata
import numpy as np
from specter_runtime import LocalSpecter2
from native_inputs import native_context, sha, PHASE, SUPPLEMENT

parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True, type=Path)
parser.add_argument('--domain', required=True)
parser.add_argument('--raw-seed-id', required=True)
parser.add_argument('--metadata', required=True, type=Path)
parser.add_argument('--references', required=True, type=Path)
args = parser.parse_args()
boundary = json.loads((args.output/'offline_boundary.json').read_text())
assert os.readlink('/proc/self/ns/net') != boundary['parent_network_namespace']
assert os.environ.get('INSIGHTPRO_OFFLINE_ENFORCED') == '1'
metadata = json.loads(args.metadata.read_text())
reference_record = json.loads(args.references.read_text())
assert metadata['status'] == reference_record['status'] == 200
assert isinstance(metadata['response'], list) and len(metadata['response']) == 1
seed = copy.deepcopy(metadata['response'][0])
edges = reference_record['response']['data']
assert seed['referenceCount'] == len(edges) and not reference_record['response'].get('next')
assert all(seed.get(key) is not None for key in ('paperId','corpusId','title','abstract','referenceCount'))
db = sqlite3.connect('file:' + str(PHASE/'inputs/corpus/corpus.sqlite') + '?mode=ro&immutable=1', uri=True)
db.row_factory = sqlite3.Row
raw_seed = dict(db.execute('SELECT * FROM papers WHERE paper_id=?', (args.raw_seed_id,)).fetchone())
normalize = lambda text: re.sub(r'[^\w]+', '', unicodedata.normalize('NFKC', text).casefold())
assert normalize(raw_seed['title']) == normalize(seed['title'])
abstract_similarity = difflib.SequenceMatcher(None, normalize(raw_seed['abstract']), normalize(seed['abstract']), autojunk=False).ratio()
assert abstract_similarity > .98
titles = {}
for row in db.execute('SELECT paper_id,title FROM papers'):
    titles.setdefault(normalize(row['title']), []).append(row['paper_id'])
assert titles[normalize(seed['title'])] == [args.raw_seed_id]
links = {seed['paperId']: {'raw_paper_id': args.raw_seed_id, 'match': 'unique_normalized_title_and_abstract',
                         'normalized_abstract_similarity': abstract_similarity}}
seed['title'], seed['abstract'] = raw_seed['title'], raw_seed['abstract']
seed['raw_record_sha256'] = raw_seed['raw_record_sha256']
eligible = []
excluded = []
for index, edge in enumerate(edges):
    paper = edge.get('citedPaper')
    if not isinstance(paper, dict):
        excluded.append({'edge_index':index,'reason':'missing_cited_paper'})
        continue
    arxiv = (paper.get('externalIds') or {}).get('ArXiv')
    raw_ids = []
    method = 'unique_normalized_title'
    if arxiv:
        raw_ids = [row[0] for row in db.execute('SELECT DISTINCT paper_id FROM aliases WHERE alias=?',
                   (re.sub(r'v\d+$', '', arxiv.lower()),))]
        if raw_ids: method = 'exact_arxiv_alias'
    if not raw_ids: raw_ids = titles.get(normalize(paper.get('title') or ''), [])
    paper['abstract'] = None
    if len(raw_ids)==1:
        local = dict(db.execute('SELECT title,abstract,raw_record_sha256 FROM papers WHERE paper_id=?',(raw_ids[0],)).fetchone())
        paper['title'] = local['title']
        paper['abstract'] = local['abstract'] or None
        paper['raw_record_sha256'] = local['raw_record_sha256']
    if paper.get('paperId'):
        links[paper['paperId']] = {'raw_paper_id': raw_ids[0] if len(raw_ids)==1 else None,
                                  'match': method if len(raw_ids)==1 else 'index_only_not_readable_in_frozen_raw_corpus'}
    missing = [key for key in ('paperId','title','abstract') if paper.get(key) is None]
    if missing:
        excluded.append({'edge_index':index,'missing_native_required_fields':missing,
                         'reason':'Missing native identity or original text unavailable in frozen raw corpus'})
    else:
        eligible.append(paper)
db.close()
papers = list({paper['paperId']: paper for paper in [seed, *eligible]}.values())
encoder = LocalSpecter2()
vectors = encoder.encode(papers)
bundle = {'domain_id': args.domain, 'seed_raw_paper_id': args.raw_seed_id, 'seed': seed,
          'reference_edges': edges, 'shared_corpus_identity_links': links,
          'excluded_by_native_filter': excluded,
          'source_records': [{'path': str(path), 'sha256': sha(path), 'fetched_at': record['fetched_at'],
                              'source_url': record['source_url']} for path,record in
                             [(args.metadata,metadata),(args.references,reference_record)]],
          'model_revisions': encoder.manifest['models'], 'models_manifest_sha256': sha(Path(__file__).parent/'models_manifest.json'),
          'embedding_input': 'Existing frozen raw title + tokenizer.sep_token + abstract, max_length=512, CLS vector, CPU float32',
          'reference_scope': 'All official index edges are preserved. Only papers readable in the unchanged frozen raw corpus expose abstracts; other edges have abstract=None and the native filter excludes them.',
          'full_official_response_location': 'Host-only preparation evidence; not mounted into experimental runs',
          'generated_research_content_included': False}
context, evidence = native_context(bundle, vectors, [paper['paperId'] for paper in papers])
assert len(context['references']) == 10
for name,value in [('bundle.json',bundle),('context.json',context),('native_retrieval.json',evidence)]:
    (args.output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
np.savez(args.output/'embeddings.npz', vectors=vectors, paper_ids=np.array([paper['paperId'] for paper in papers]))
report = {'at':datetime.now(timezone.utc).isoformat(),'passed':True,'domain':args.domain,'seed_raw_paper_id':args.raw_seed_id,
          'seed_s2_paper_id':seed['paperId'],'reference_edges':len(edges),'eligible_references':len(eligible),
          'excluded_by_native_filter':len(excluded),'embedded_papers':len(papers),'selected_references':len(context['references']),
          'selected_reference_raw_membership':[{**links[paper['paperId']], 'paperId':paper['paperId']} for paper in context['references']],
          'entity_count':len(context['entities']),'public_runtime_requests':0,'model_api_requests':0,
          'checks':{'seed_in_frozen_common_corpus':True,'complete_real_reference_response':True,
                    'actual_pinned_specter2_vectors':True,'unmodified_native_reference_filter_cosine_top10':True,
                    'no_new_paper_abstracts_or_fulltexts':True,
                    'unmodified_knowledge_entity_retrieval':True,'no_generated_context_imported':True},
          'bindings':{str(path):sha(path) for path in [args.output/name for name in
                       ['bundle.json','context.json','native_retrieval.json','embeddings.npz']]}}
(args.output/'input_preparation_acceptance.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
