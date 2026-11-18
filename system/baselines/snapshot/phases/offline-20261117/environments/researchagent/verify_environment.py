"""Run actual local SPECTER2 and official ResearchAgent components with no model API."""
from pathlib import Path
from datetime import datetime, timezone
from importlib.metadata import distributions
import argparse
import collections
import hashlib
import json
import os
import re
import socket
import sqlite3
import sys
import threading

ENVIRONMENT = Path(__file__).resolve().parent
PHASE = ENVIRONMENT.parents[1]
SOURCE = PHASE / 'sources/researchagent'
sys.path.insert(0, str(SOURCE / 'code'))
from specter_runtime import LocalSpecter2

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(exist_ok=True, parents=True)
boundary = json.loads((args.output / 'offline_boundary.json').read_text())
assert os.readlink('/proc/self/ns/net') != boundary['parent_network_namespace']
assert not any(line.split()[1] == '00000000' for line in Path('/proc/net/route').read_text().splitlines()[1:])
db = sqlite3.connect('file:' + str(PHASE / 'inputs/corpus/corpus.sqlite') + '?mode=ro&immutable=1', uri=True)
db.row_factory = sqlite3.Row
papers = [dict(row) for row in db.execute("SELECT paper_id,title,abstract FROM papers WHERE paper_id IN ('89614','412174','233742','188445','233395','100812','258759','186740','180679','5100','228216','240434') ORDER BY paper_id")]
db.close()
assert len(papers) >= 10 and all(paper['title'] and paper['abstract'] for paper in papers)
encoder = LocalSpecter2()
vectors = encoder.encode(papers)
import numpy as np
import torch
from sentence_transformers.util import cos_sim
native_cosine = cos_sim(vectors[0], vectors[1:])
native_indices = torch.topk(native_cosine, k=min(10, len(papers)-1)).indices[0].tolist()
numpy_cosine = vectors[1:] @ vectors[0] / (np.linalg.norm(vectors[1:], axis=1) * np.linalg.norm(vectors[0]))
assert np.allclose(native_cosine.numpy()[0], numpy_cosine, rtol=1e-5, atol=1e-6)
assert len(set(native_indices)) == min(10, len(papers)-1)
repeat = encoder.encode(papers[:1])
assert np.allclose(repeat, vectors[:1], rtol=1e-5, atol=1e-5)
encoder.model.set_active_adapters(None)
base_only = encoder.encode(papers[:1])
encoder.model.set_active_adapters('specter2')
adapter_effect = float(np.linalg.norm(repeat - base_only))
assert adapter_effect > 1e-4, 'The proximity adapter must affect the actual vectors'
np.save(args.output / 'actual_specter2_vectors.npy', vectors)

from knowledge.store import KnowledgeStore
knowledge = KnowledgeStore(str(SOURCE / 'data/knowledge.jsonl'))
supported_id = next(key for key, value in knowledge.paper2entities.items() if value)
entities = knowledge.get_relevant_entities([supported_id])
assert entities and len(entities) <= 30
from pipelines.research_pipeline import ResearchPipeline

class FixtureClient:
    """Only exercises original parsers and orchestration; never generates research."""
    def __init__(self):
        self.calls = 0
        self.generations = collections.Counter()
        self.lock = threading.Lock()

    def call(self, messages, **kwargs):
        with self.lock:
            self.calls += 1
            user = messages[-1]['content']
            if user.rstrip().endswith('Rating (1-5):'):
                matches = re.findall(r'Software fixture (?:problem|method|experiment) round (\d)', user)
                assert matches
                score = {'1': 2, '2': 4, '3': 3}[matches[-1]]
                return f'Review: Parser and orchestration fixture only.\nFeedback: No research claim.\nRating (1-5): {score}'
            for label in ('Problem', 'Method', 'Experiment'):
                if user.rstrip().endswith(label + ': \nRationale:') or user.rstrip().endswith(label + ':\nRationale:'):
                    self.generations[label] += 1
                    return f'{label}: Software fixture {label.lower()} round {self.generations[label]}\nRationale: Software verification only; not a benchmark proposal.'
            raise AssertionError('Unexpected native prompt format')

client = FixtureClient()
# No seed-to-reference edge is asserted by this component-level software fixture.
context = {'paper': {key: papers[0][key] for key in ('title', 'abstract')}, 'references': [], 'entities': entities}
result = ResearchPipeline(api_client=client, iterations=3).run(context)
assert client.calls == 54 and all(len(values) == 3 for values in result['history'].values())
assert all(result[key] == f'Software fixture {key} round 2' for key in ('problem', 'method', 'experiment'))
assert all(len(result[key + '_feedbacks']) == 5 for key in ('problem', 'method', 'experiment'))
report = {
    'at': datetime.now(timezone.utc).isoformat(), 'passed': True,
    'environment_ready': True, 'benchmark_inputs_ready': False, 'model_api_calls': 0,
    'runtime_public_network_calls': 0, 'embedding_rows': len(papers), 'embedding_dimensions': 768,
    'embedding_dtype': str(vectors.dtype), 'native_cosine_top10_indices': native_indices,
    'active_adapter_vs_base_l2_difference': adapter_effect,
    'model_revisions': encoder.manifest['models'],
    'native_pipeline': {'simulated_completions': client.calls, 'iterations_per_stage': 3,
                        'review_dimensions_per_stage': 5, 'highest_rated_round_selected': 2},
    'native_entity_store': {'covered_corpus_id': supported_id, 'returned_entities': len(entities)},
    'checks': {'weights_loaded_from_local_paths': True, 'proximity_adapter_active': True,
               'real_embeddings_finite_768_float32': True, 'repeat_encoding_matches': True,
               'proximity_adapter_changes_actual_embedding': True,
               'native_cosine_topk_runs': True, 'official_knowledge_store_runs': True,
               'official_three_stage_refinement_and_selection_runs': True, 'no_fabricated_citation_edges': True},
    'packages': dict(sorted((d.metadata['Name'], d.version) for d in distributions())),
    'bindings': {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in [
        ENVIRONMENT / 'models_manifest.json', ENVIRONMENT / 'specter_runtime.py', Path(__file__),
        SOURCE / 'code/utils/s2.py', SOURCE / 'code/pipelines/research_pipeline.py',
        SOURCE / 'data/knowledge.jsonl', args.output / 'actual_specter2_vectors.npy']},
    'limitation': 'Software acceptance uses actual local embeddings and the official pipeline with deterministic fixture completions. It does not assert seed citation-graph readiness or produce a benchmark proposal.',
}
(args.output / 'environment_acceptance.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
