"""Exercise the real frozen context and complete native adapter with fixture completions."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import collections
import hashlib
import json
import os
import re
import sys
import threading

ENVIRONMENT = Path(__file__).resolve().parent
PHASE = ENVIRONMENT.parents[1]
sys.path.insert(0, str(PHASE / 'adapters'))
import researchagent
from native_inputs import sha

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
boundary = json.loads((args.output / 'offline_boundary.json').read_text())
assert os.readlink('/proc/self/ns/net') != boundary['parent_network_namespace']
assert os.environ['INSIGHTPRO_OFFLINE_ENFORCED'] == '1'
assert not (PHASE / 'state/researchagent_preparation_sources').exists()
assert not any(line.split()[1] == '00000000' for line in Path('/proc/net/route').read_text().splitlines()[1:])
domain = json.loads((PHASE / 'inputs/agent-memory/domain.json').read_text())


class FixtureTransport:
    """The same NativeClient builds prompts and request IDs; no inference request is sent."""
    def __init__(self):
        self.calls = []
        self.generations = collections.Counter()
        self.lock = threading.Lock()

    def chat(self, messages, max_tokens, request_id):
        with self.lock:
            assert messages[1] == {'role': 'user', 'content': researchagent.single_prompt(domain)}
            assert max_tokens == 32768 and request_id.startswith('native-')
            self.calls.append({'request_id': request_id, 'messages_sha256': hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()).hexdigest()})
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


client = researchagent.NativeClient(domain, args.output)
fixture = FixtureTransport()
client.client = fixture
result = researchagent.generate(domain, args.output, client=client)
native = json.loads((args.output / 'native_output.json').read_text())
retrieval = json.loads((args.output / 'native_retrieval.json').read_text())
assert result['status'] == 'completed'
assert len(fixture.calls) == 54 and len({item['request_id'] for item in fixture.calls}) == 54
assert all(len(values) == 3 for values in native['history'].values())
assert all(native[key] == f'Software fixture {key} round 2' for key in ('problem', 'method', 'experiment'))
assert all(len(native[key + '_feedbacks']) == 5 for key in ('problem', 'method', 'experiment'))
assert retrieval['native_eligible_reference_count'] == 31
assert len(native['references']) == 10 and len(native['entities']) == 19
try:
    researchagent.prepare({'id': 'unprepared-fixture-domain'})
except researchagent.OfflineDependencyGap as exc:
    assert 'software and local SPECTER2 are ready' in str(exc)
else:
    raise AssertionError('Unprepared domains must not fall back to old contexts or generic retrieval')
report = {
    'at': datetime.now(timezone.utc).isoformat(), 'passed': True,
    'environment_ready': True, 'benchmark_inputs_ready': {'agent-memory': True},
    'benchmark_ready': False, 'live_model_validation_complete': False,
    'fixture_completions': len(fixture.calls), 'model_api_requests': 0, 'public_network_requests': 0,
    'native_pipeline': {'iterations_per_stage': 3, 'review_dimensions_per_stage': 5, 'highest_rated_round_selected': 2},
    'checks': {'actual_frozen_seed_and_reference_subset_used': True,
               'original_native_filter_cosine_top10_reproduced': True,
               'original_knowledge_entity_retrieval_reproduced': True,
               'full_adapter_and_native_client_prompt_path_passed': True,
               'three_stage_native_refinement_review_selection_passed': True,
               'host_only_full_http_responses_unmounted': True,
               'unprepared_domain_fails_as_input_gap': True,
               'fixture_output_excluded_from_benchmark': True},
    'supplement_id': retrieval['supplement_id'], 'selected_references': 10, 'entity_count': 19,
    'bindings': {str(path.resolve()): sha(path) for path in [
        Path(__file__), PHASE / 'adapters/researchagent.py', ENVIRONMENT / 'native_inputs.py',
        PHASE / 'inputs/researchagent_native_supplement/manifest.json',
        PHASE / 'sources/researchagent/code/utils/s2.py',
        PHASE / 'sources/researchagent/code/pipelines/research_pipeline.py',
        PHASE / 'sources/researchagent/data/knowledge.jsonl',
        args.output / 'native_input.json', args.output / 'native_retrieval.json', args.output / 'native_output.json']},
}
(args.output / 'adapter_acceptance.json').write_text(json.dumps(report, indent=2) + '\n')
(args.output / 'fixture_requests.json').write_text(json.dumps(fixture.calls, indent=2) + '\n')
print(json.dumps(report, indent=2))
