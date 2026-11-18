"""Staged single-slot InsightAgents runner. No registration or scheduler ownership."""
import argparse
import copy
import datetime
import fcntl
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
PHASE = ROOT.parents[1]
sys.path[:0] = [str(ROOT / 'native/src'), str(PHASE / 'adapters')]
sys.dont_write_bytecode = True

from evidence import digest, encode, event, freeze, freeze_bytes, sha, signature

COMPARISON_SCOPE = "official-recommendation-graph-local-common-corpus-retrieval-adaptation"
from local_client import LocalS2Client


def configure(output):
    import config as cfg
    cfg.LLM_PROVIDER = 'openai'
    cfg.DEBATE_MODEL = cfg.INSIGHT_MODEL = 'gpt-6-astra'
    cfg.OPENAI_REASONING_EFFORT = 'xhigh'
    cfg.OPENAI_API_STYLE = 'responses'
    cfg.OPENAI_BASE_URL = 'http://127.0.0.1:8765/v1'
    cfg.OPENAI_API_KEY = 'offline-model-bridge'
    cfg.OUTPUT_DIR = Path(output) / 'native'
    cfg.S2_CACHE_DIR = Path(output) / 'unused_s2_cache'
    cfg.ACL_CACHE_DIR = Path(output) / 'unused_acl_cache'
    if (cfg.EXPERTISE_SOURCE != 'semantic_scholar' or cfg.REASONING_TOKEN_RESERVE != 2000
            or cfg.S2_KEEP_PER_LEVEL != [5, 3, 2] or cfg.NUM_AGENTS != 3
            or cfg.PROBLEM_TURNS != 2 or cfg.DEBATE_TURNS != 3 or cfg.BLIND_OPENING_TURNS):
        raise RuntimeError('Native algorithm configuration changed')
    return cfg


def fixed_config():
    import config as cfg
    excluded = {'ROOT', 'DATA_DIR', 'OUTPUT_DIR', 'S2_CACHE_DIR', 'ACL_CACHE_DIR',
                'ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'S2_API_KEY', 'ANTHROPIC_BASE_URL'}
    return {key: value for key, value in vars(cfg).items() if key.isupper() and key not in excluded}


class BoundPackage:
    def __init__(self, manifest_path):
        self.path = Path(manifest_path)
        self.manifest_sha = sha(self.path)
        self.value = json.loads(self.path.read_text())
        self.material_path = Path(self.value['material_manifest']['path'])
        self.material = json.loads(self.material_path.read_text())
        self.check()

    def check(self):
        if sha(self.path) != self.manifest_sha:
            raise RuntimeError('Package manifest changed')
        for row in self.value['bound_files']:
            if sha(row['path']) != row['sha256']:
                raise RuntimeError('Frozen source, input or dependency changed: ' + row['path'])
        corpus = self.material['raw_corpus']
        if signature(corpus['path']) != self.value['corpus_signature']:
            raise RuntimeError('Frozen corpus signature changed')


def edge_receipts(output, graph):
    records = []
    for path in sorted((Path(output) / 'retrieval').glob('*.json')):
        receipt = json.loads(path.read_text())
        if receipt['method'] == 'recommendations':
            records.append((path, receipt))
    nodes = {node['label']: node for node in graph['nodes']}
    result = []
    for edge in graph['edges']:
        parent = nodes[edge['expanded_from']]
        target = edge['to_paper_id'] if edge['from_paper_id'] == parent['paper_id'] else edge['from_paper_id']
        matches = [path for path, rec in records if rec['arguments']['paper_id'] == parent['paper_id']
                   and target in [paper['paperId'] for paper in rec['result']]]
        if not matches: raise RuntimeError('Graph edge has no frozen local recommendation provenance')
        left, right = nodes[edge['from_label']], nodes[edge['to_label']]
        result.append({'native_edge': edge, 'relation': 'local_similarity_recommendation',
                       'source_parent_id': parent['paper_id'], 'recommended_id': target,
                       'receipt_bindings': [{'path': str(p), 'sha256': sha(p)} for p in matches],
                       'source_date_precision': 'year', 'citation_or_prerequisite_claim': False,
                       'same_year_temporal_order_unknown': left['year'] == right['year'],
                       'native_dated_is_sort_proxy_not_publication_day': True})
    return result


def validate_calls(output):
    from journal_client import JournaledLLMClient
    returned, pending, provider_incomplete = [], [], []
    for directory in sorted((Path(output) / 'model_calls').glob('*')):
        if not (directory / 'native_returned.json').exists():
            pending.append(str(directory))
            continue
        receipt = JournaledLLMClient.validate_cache(directory)
        returned.append({'path': str(directory), 'receipt_sha256': sha(directory / 'native_returned.json')})
        physical = directory / f"physical-{receipt['physical_attempts']:02}"
        row = json.loads((physical / 'receipt.json').read_text())
        if row['provider_status'] != 'completed':
            body = json.loads((physical / 'response_body.bin').read_text())
            provider_incomplete.append({'logical_call': str(directory), 'provider_status': row['provider_status'],
                                        'incomplete_details': body.get('incomplete_details'), 'error': body.get('error')})
    return {'returned_native_calls': returned, 'unresolved_original_calls': pending,
            'consumed_noncompleted_provider_responses': provider_incomplete,
            'all_consumed_provider_responses_completed': not pending and not provider_incomplete}


def run_slot(output, manifest_path, domain_id, slot, *, resume=False, fixture=False, client_factory=None, admission_receipt=None, admission_sha256=None):
    from offline_support import require_offline
    from journal_client import JournaledLLMClient
    output = Path(output).resolve()
    require_offline(output)
    output.mkdir(parents=True, exist_ok=True)
    lock = (output / '.slot.lock').open('a+')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    package = BoundPackage(manifest_path)
    authorization = None
    if not fixture:
        from controlled_gate import verify_admission
        authorization = verify_admission(admission_receipt, admission_sha256, manifest_path, output, domain_id, slot)
    configure(output)
    if fixed_config() != package.value['fixed_config']:
        raise RuntimeError('Frozen native config differs from reviewed package')
    import experiment
    import expertise.semantic_scholar as backend
    from topics import TopicSpec
    row = package.value['topic_mapping']['domains'][domain_id]
    binding = {'method': 'insightagents', 'slot': slot, 'domain': domain_id, 'output': str(output),
               'fixture': fixture, 'run_id': authorization['run_id'] if authorization else 'fixture:' + slot,
               'admission_id': authorization['admission_id'] if authorization else 'fixture:no-paid-admission',
               'purpose': authorization['purpose'] if authorization else 'offline-fake-integration',
               'admission_receipt_sha256': admission_sha256 if authorization else None,
               'package_sha256': package.manifest_sha,
               'material_sha256': sha(package.material_path), 'topic_mapping': row,
               'native_source_commit': package.value['source_commit'],
               'model': 'gpt-6-astra', 'effort': 'xhigh', 'api': 'responses',
               'comparison_scope': COMPARISON_SCOPE, 'comparison_scope_label': package.material['comparison_scope']}
    binding_path = output / 'run_binding.json'
    if binding_path.exists() and not resume: raise RuntimeError('Existing independent slot requires explicit resume')
    if not binding_path.exists() and resume: raise RuntimeError('No original independent slot exists to resume')
    freeze(binding_path, binding)
    binding_sha = sha(binding_path)
    material_identity = {'data_version': package.material['raw_corpus']['data_version'],
                         'corpus_id': package.material['raw_corpus']['corpus_id'],
                         'corpus_sha256': package.material['raw_corpus']['sha256'],
                         'comparison_scope': COMPARISON_SCOPE}
    freeze(output / 'input_material_version.json', material_identity | {'method': 'insightagents', 'domain': domain_id,
           'fixture': fixture, 'run_binding_sha256': binding_sha})
    if (output / 'terminal.json').exists():
        raise RuntimeError('Terminal native slot is immutable and cannot be relaunched')
    def verify():
        package.check()
        if fixed_config() != package.value['fixed_config']:
            raise RuntimeError('Native runtime configuration changed')
        if authorization:
            from controlled_gate import verify_admission
            verify_admission(admission_receipt, admission_sha256, manifest_path, output, domain_id, slot)
        if sha(binding_path) != binding_sha: raise RuntimeError('Slot binding changed')
    snapshots = sorted((output / 'checkpoints').glob('*.json'))
    latest = None
    for i, path in enumerate(snapshots, 1):
        latest = json.loads(path.read_text())
        if path.name != f"{i:06}-{digest(encode(latest))}.json" or latest['run_binding_sha256'] != binding_sha:
            raise RuntimeError('Native checkpoint receipt changed')
        if latest['previous_checkpoint_sha256'] != (sha(snapshots[i - 2]) if i > 1 else None):
            raise RuntimeError('Native checkpoint chain changed')
    progress = copy.deepcopy(latest['native_progress']) if latest else experiment._new_progress(row['topic'], 'semantic_scholar')
    factory = client_factory or JournaledLLMClient
    clients = {role: factory(role, output, binding_sha, lambda: progress, verify) for role in ('insight', 'debate')}
    if latest:
        for role, client in clients.items(): client.restore(latest['clients'][role])
        for item in latest['returned_calls']:
            if sha(item['path']) != item['sha256']: raise RuntimeError('Checkpoint-bound original call changed')
        validate_calls(output)
    def save():
        verify()
        state = {'run_binding_sha256': binding_sha, 'native_progress': copy.deepcopy(progress),
                 'clients': {role: client.snapshot() for role, client in clients.items()},
                 'previous_checkpoint_sha256': sha(snapshots[-1]) if snapshots else None,
                 'returned_calls': [{'path': str(p), 'sha256': sha(p)} for p in sorted((output / 'model_calls').glob('*/native_returned.json'))]}
        path = output / 'checkpoints' / f'{len(snapshots) + 1:06}-{digest(encode(state))}.json'
        freeze(path, state)
        snapshots.append(path)
        experiment._atomic_write_json(output / 'progress.json', progress)
    local = LocalS2Client(output, package.material, package.value['corpus_signature'], seed_mapping=row)
    original_factory = backend.S2Client
    backend.S2Client = lambda: local
    try:
        save()
        backend.run_pretrain(TopicSpec(topic=row['topic'], entry_id=domain_id), clients['insight'], progress, save, experiment._record_error)
        if progress['error']:
            raise RuntimeError('Native pretrain rejected this original slot')
        if progress['pretrain_completed_at'] is None:
            progress['pretrain_completed_at'] = datetime.datetime.now().isoformat()
            save()
        native_result = experiment.run_topic_debate(progress, clients['debate'], save)
        freeze(output / 'native_result.json', native_result)
        edges = edge_receipts(output, progress['trajectory']['graph'])
        freeze(output / 'edge_provenance.json', {'edges': edges, 'material_manifest_sha256': sha(package.material_path),
              'citation_count_unknown_despite_native_zero_display': True})
        calls = validate_calls(output)
        ideas = native_result['final_ideas']
        native_valid = len(ideas) == 1 and bool(ideas[0].get('title')) and bool(ideas[0].get('method'))
        strict_valid = native_valid and calls['all_consumed_provider_responses_completed']
        terminal = {'status': ('fixture_native_terminal' if fixture else 'native_terminal_completed') if strict_valid else 'native_terminal_not_eligible',
                    'fixture': fixture, 'formal_comparison_eligible': strict_valid and not fixture,
                    'native_proposal_valid': native_valid, 'strict_provider_completion_valid': strict_valid,
                    'native_result_sha256': sha(output / 'native_result.json'),
                    'run_binding_sha256': binding_sha, 'edge_provenance_sha256': sha(output / 'edge_provenance.json'),
                    'native_final_ideas_count': len(ideas), 'usable_experts': len(progress['insight']['expert_prompts']),
                    'unknown_usd': None, 'scoring_launched': False, **calls}
        freeze(output / 'terminal.json', terminal)
        proposal_markdown = None
        if native_valid:
            freeze(output / 'proposal.json', ideas[0])
            # Complete unchanged proposal object, with no lossy field selection.
            proposal_markdown = '```json\n' + json.dumps(ideas[0], ensure_ascii=False, indent=2) + '\n```\n'
            freeze_bytes(output / 'proposal.md', proposal_markdown.encode())
        freeze(output / 'result.json', {**material_identity, 'method': 'insightagents', 'domain': domain_id,
            'slot': slot, 'fixture': fixture,
            'status': ('fixture_completed' if fixture else 'completed') if strict_valid else 'native_terminal_not_eligible',
            'proposal_markdown': proposal_markdown, 'native_output_paths': [str(output / name) for name in
                ('native_result.json', 'edge_provenance.json', 'terminal.json', 'run_binding.json')],
            'native_proposal_valid': native_valid, 'strict_provider_completion_valid': strict_valid,
            'formal_comparison_eligible': strict_valid and not fixture,
            'terminal_reason': None if strict_valid else 'native_proposal_or_consumed_provider_completion_invalid',
            'run_id': binding['run_id'], 'admission_id': binding['admission_id'], 'purpose': binding['purpose'],
            'score': None, 'cost_usd': None})
        verify()
        return terminal
    except BaseException as exc:
        # Never checkpoint a partial turn's mutated state after an exception.
        event(output / 'failures.jsonl', 'original_slot_interrupted', error_type=type(exc).__name__,
              paid_retry_authorized=False, usage=None, usd=None, preserved_checkpoint_count=len(snapshots))
        raise
    finally:
        backend.S2Client = original_factory
        local.close()
        for client in clients.values(): client.close()
        lock.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', required=True)
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--domain', required=True)
    ap.add_argument('--slot', required=True)
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--fixture', action='store_true')
    ap.add_argument('--admission-receipt')
    ap.add_argument('--admission-sha256')
    args = ap.parse_args()
    factory = None
    if args.fixture:
        from fixture_transport import client_factory
        factory = client_factory
    run_slot(args.output, args.manifest, args.domain, args.slot, resume=args.resume, fixture=args.fixture, client_factory=factory,
             admission_receipt=args.admission_receipt, admission_sha256=args.admission_sha256)


if __name__ == '__main__': main()
