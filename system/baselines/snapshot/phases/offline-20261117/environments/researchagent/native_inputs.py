"""Serve frozen official S2 records and locally computed SPECTER2 to native retrieval."""
from pathlib import Path
import copy
import hashlib
import json
import sys

ENVIRONMENT = Path(__file__).resolve().parent
PHASE = ENVIRONMENT.parents[1]
SOURCE = PHASE / 'sources/researchagent'
SUPPLEMENT = PHASE / 'inputs/researchagent_native_supplement'
sys.path.insert(0, str(SOURCE / 'code'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def native_context(bundle, vectors, vector_ids):
    """Only HTTP transport is substituted; native filtering, cosine/top-k and entities run."""
    from utils import s2
    from knowledge.store import KnowledgeStore
    import torch
    from sentence_transformers.util import cos_sim

    seed = copy.deepcopy(bundle['seed'])
    edges = bundle['reference_edges']
    paper_to_vector = {ident: values.tolist() for ident, values in zip(vector_ids, vectors)}
    if seed['paperId'] not in paper_to_vector:
        raise ValueError('Missing actual seed embedding')
    seed['embedding'] = {'model': 'specter_v2', 'vector': paper_to_vector[seed['paperId']]}
    old_get, old_post = s2.get_request, s2.post_request
    calls = []

    def local_get(url, headers, params, **kwargs):
        if url != 'https://api.semanticscholar.org/graph/v1/paper/' + seed['paperId'] + '/references':
            raise ValueError('Unfrozen native S2 GET request: ' + url)
        offset, limit = int(params['offset']), int(params['limit'])
        calls.append({'operation': 'references', 'offset': offset, 'limit': limit})
        return {'offset': offset, 'data': copy.deepcopy(edges[offset:offset+limit])}

    def local_post(url, headers, params, json, **kwargs):
        if url != 'https://api.semanticscholar.org/graph/v1/paper/batch' or params != {'fields': 'embedding.specter_v2'}:
            raise ValueError('Unfrozen native S2 POST request')
        ids = json['ids']
        calls.append({'operation': 'embeddings', 'paper_ids': ids})
        return [{'paperId': ident, 'embedding': {'model': 'specter_v2', 'vector': paper_to_vector[ident]}}
                if ident in paper_to_vector else {'paperId': ident, 'embedding': None} for ident in ids]

    s2.get_request, s2.post_request = local_get, local_post
    try:
        references = s2.get_relevant_references(seed)
    finally:
        s2.get_request, s2.post_request = old_get, old_post
    knowledge = KnowledgeStore(str(SOURCE / 'data/knowledge.jsonl'))
    corpus_ids = [seed['corpusId']] + [paper['corpusId'] for paper in references]
    entities = knowledge.get_relevant_entities(corpus_ids)
    eligible = [edge['citedPaper'] for edge in edges
                if isinstance(edge.get('citedPaper'), dict)
                and all(edge['citedPaper'].get(key) is not None for key in ('paperId', 'title', 'abstract'))]
    unique_ids = list(dict.fromkeys(paper['paperId'] for paper in eligible if paper['paperId'] in paper_to_vector))
    scores = cos_sim(paper_to_vector[seed['paperId']], [paper_to_vector[ident] for ident in unique_ids])[0]
    rank_indices = torch.topk(scores, k=len(unique_ids)).indices.tolist()
    ranking = [{'rank': rank+1, 'paperId': unique_ids[index], 'cosine_similarity': float(scores[index])}
               for rank, index in enumerate(rank_indices)]
    assert set(paper['paperId'] for paper in references) == {row['paperId'] for row in ranking[:10]}
    context = {'paper': {key: seed[key] for key in ('title', 'abstract')},
               'references': references, 'entities': entities}
    evidence = {'native_http_substitution_calls': calls, 'reference_edge_count': len(edges),
                'native_eligible_reference_count': len(eligible), 'native_selected_reference_count': len(references),
                'full_cosine_rank': ranking, 'native_output_reference_order': [paper['paperId'] for paper in references],
                'input_corpus_ids': corpus_ids, 'knowledge_covered_corpus_ids': [ident for ident in corpus_ids if ident in knowledge.paper2entities],
                'entity_count': len(entities), 'knowledge_sha256': sha(SOURCE / 'data/knowledge.jsonl'),
                'native_s2_source_sha256': sha(SOURCE / 'code/utils/s2.py')}
    return context, evidence


def load_context(domain_id):
    import numpy as np
    manifest_path = SUPPLEMENT / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    corpus_manifest = json.loads((PHASE / 'inputs/corpus/manifest.json').read_text())
    if manifest.get('corpus_id') != corpus_manifest['corpus_id'] or manifest.get('benchmark_inputs_ready') is not True:
        raise ValueError('Native supplement is not bound to the frozen common corpus')
    entry = manifest.get('domains', {}).get(domain_id)
    if not entry or entry.get('ready') is not True:
        raise ValueError('No verified native seed/reference supplement for domain: ' + domain_id)
    for relative, digest in entry['bindings'].items():
        path = (SUPPLEMENT / relative).resolve()
        if not path.is_relative_to(SUPPLEMENT.resolve()) or not path.is_file() or sha(path) != digest:
            raise ValueError('Native supplement hash mismatch: ' + relative)
    bundle = json.loads((SUPPLEMENT / entry['bundle']).read_text())
    if bundle['seed_raw_paper_id'] != entry['seed_raw_paper_id'] or bundle['domain_id'] != domain_id:
        raise ValueError('Native seed identity mismatch')
    with np.load(SUPPLEMENT / entry['vectors'], allow_pickle=False) as values:
        vectors, ids = values['vectors'], values['paper_ids'].tolist()
        if vectors.shape != (len(ids), 768) or vectors.dtype != np.float32 or not np.isfinite(vectors).all() or len(ids) != len(set(ids)):
            raise ValueError('Invalid frozen actual SPECTER2 vector array')
        context, evidence = native_context(bundle, vectors, ids)
    expected_context = json.loads((SUPPLEMENT / entry['context']).read_text())
    if context != expected_context:
        raise ValueError('Native frozen retrieval did not reproduce the accepted context')
    return context, {**evidence, 'supplement_manifest': str(manifest_path),
                     'supplement_manifest_sha256': sha(manifest_path), 'supplement_id': manifest['supplement_id'],
                     'seed_raw_paper_id': entry['seed_raw_paper_id'], 'fresh_generation_context': True,
                     'embedding_origin': 'Pinned official local SPECTER2 base plus proximity adapter; no lexical substitute',
                     'shared_reference_metadata_extension': True,
                     'new_paper_abstracts_or_fulltexts': False,
                     'reference_text_scope': 'Only unchanged frozen common corpus title/abstract records; unavailable reference texts remain missing'}
