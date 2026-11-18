"""Frozen full-pool replay under the upstream parser and tutorial selector.

Only this candidate directory is writable. No model transport is constructed.
Historical carriers and every original request/response remain unchanged.
"""
from pathlib import Path
import argparse
import ast
import collections
import datetime
import hashlib
import importlib.util
import json
import shutil
import socket
import sys
import threading
import traceback

S = Path(__file__).resolve().parent
P = S.parents[1]
D = P / 'environments/cycleresearcher_revisions/native-n10-standard4-source-spans-v4'
SOURCE = P.parents[1] / 'sources/cycleresearcher'
REVISION = 'cycleresearcher-upstream-parser-tutorial-fallback-v5-20261118'
NORMATIVE = P / 'state/native_failure_evidence_expansion_20261117T2055/cycle_official_selection_semantics_20261118T0645_v2'
sys.path.insert(0, str(D))
spec = importlib.util.spec_from_file_location('cycle_v4_frozen', D / 'adapter.py')
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def read(p):
    return json.loads(Path(p).read_text())


def sha(p):
    return V.sha(p)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(p, data):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    assert not p.exists(), 'Already frozen: ' + str(p)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def ref(p):
    return {'path': str(p), 'sha256': sha(p)}


def filemap(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}


def payload(messages, system, max_tokens, kwargs):
    value = {'model': 'gpt-6-astra', 'messages': ([{'role': 'system', 'content': system}] + list(messages)) if system is not None else list(messages),
             'reasoning_effort': 'xhigh', 'max_completion_tokens': max_tokens, 'stream': True, 'stream_options': {'include_usage': True}}
    for key in ['tools', 'tool_choice', 'response_format', 'stop', 'n', 'seed', 'parallel_tool_calls']:
        if kwargs.get(key) is not None:
            value[key] = kwargs[key]
    return value


def reassemble(path):
    data = {'choices': []}
    choices, usage = {}, {}
    for line in path.read_text().splitlines():
        chunk = json.loads(line)
        assert not chunk.get('error')
        for key in ['id', 'model', 'created', 'system_fingerprint']:
            if key in chunk:
                data[key] = chunk[key]
        if chunk.get('usage'):
            usage = chunk['usage']
        for choice in chunk.get('choices', []):
            acc = choices.setdefault(choice['index'], {'index': choice['index'], 'message': {'role': 'assistant', 'content': ''}, 'finish_reason': None})
            delta = choice.get('delta', {})
            for field in ['content', 'reasoning_content', 'refusal']:
                if delta.get(field):
                    acc['message'][field] = acc['message'].get(field, '') + delta[field]
            for tool in delta.get('tool_calls', []):
                target = acc.setdefault('_tools', {}).setdefault(tool['index'], {'id': '', 'type': 'function', 'function': {'name': '', 'arguments': ''}})
                if tool.get('id'):
                    target['id'] += tool['id']
                for field in ['name', 'arguments']:
                    if tool.get('function', {}).get(field):
                        target['function'][field] += tool['function'][field]
            if choice.get('finish_reason'):
                acc['finish_reason'] = choice['finish_reason']
    for acc in choices.values():
        if '_tools' in acc:
            acc['message']['tool_calls'] = [t for _, t in sorted(acc.pop('_tools').items())]
    data['choices'] = [v for _, v in sorted(choices.items())]
    data['usage'] = usage
    return data


def native_select(reviews):
    notebook = read(SOURCE / 'Tutorial/tutorial_3.ipynb')
    tree = ast.parse(''.join(notebook['cells'][13]['source']))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'extract_average_rating')
    best = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'best_paper' for t in n.targets))
    scope = {'np': V.np}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE / 'Tutorial/tutorial_3.ipynb') + ':cell13:rating', 'exec'), scope)
    ratings = [{'index': i, 'avg_rating': float(scope['extract_average_rating'](review)),
                'decision': review.get('decision', 'No decision'), 'reviewer_count': len(review.get('reviews', [])),
                'score_source': V.rating_source(review)} for i, review in enumerate(reviews)]
    scope['paper_ratings'] = ratings
    exec(compile(ast.Module(body=[best], type_ignores=[]), str(SOURCE / 'Tutorial/tutorial_3.ipynb') + ':cell13:max', 'exec'), scope)
    return scope['best_paper'], ratings


def prepare_inventory():
    V.verify_manifest()
    campaign = read(P / 'state/campaign.json')
    rows = []
    for key, job in sorted(campaign['jobs'].items()):
        if job.get('method') != 'cycleresearcher' or job.get('kind') != 'generation' or job['status'] not in ['completed', 'native_failure']:
            continue
        out = P / 'runs/cycleresearcher' / job['domain'] / f"slot-{job['slot']:02}"
        result = read(out / 'result.json')
        assert result['status'] == job['status']
        assert len(list((out / 'researcher/completed').glob('*.json'))) == 10
        assert len(list((out / 'reviewer/completed').glob('*.json'))) == 10
        rows.append({'job_key': key, 'domain': job['domain'], 'slot': job['slot'], 'launches': job['launches'],
                     'prior_status': result['status'], 'output_dir': str(out), 'original_result': ref(out / 'result.json')})
    assert len(rows) == 189 and collections.Counter(x['prior_status'] for x in rows) == {'native_failure': 159, 'completed': 30}
    bindings = {str(p): sha(p) for p in [Path(__file__), D / 'adapter.py', D / 'format_compatibility.py', D / 'manifest.json',
        SOURCE / 'ai_researcher/cycle_researcher.py', SOURCE / 'ai_researcher/deep_reviewer.py', SOURCE / 'ai_researcher/utils.py',
        SOURCE / 'Tutorial/tutorial_3.ipynb', NORMATIVE / 'handoff.json', NORMATIVE / 'normative_protocol_candidate.json', NORMATIVE / 'REPLAY_SPEC.zh.md']}
    save(S / 'derivation_manifest.json', {
        'at': now(), 'selection_semantics_revision': REVISION, 'source_commit': '8c1b253092f3f41b3efc414fb189004855bb49f8',
        'source_bindings': bindings, 'upstream_parser': 'DeepReviewer._parse_review on the complete original raw text',
        'selector': 'original cell13 extract_average_rating function AST and best_paper=max assignment AST in original candidate order',
        'display_only_title_fields_omitted': True, 'missing_score_policy': 'upstream_internal_zero_then_first_max',
        'review_schema_compatibility_selection_role': 'none; previous outputs retained only as historical diagnostics',
        'carrier_policy': 'preserve original issued reviewer input carriers byte for byte',
        'generator_n': 10, 'review_mode': 'Standard Mode', 'reviewer_num': 4, 'model': 'gpt-6-astra', 'effort': 'xhigh',
        'config_change_disclosure': 'The frozen config blocked selection on absent scores. This derived revision replaces that additional policy and removes compatibility mapping from selection; old config and deployment hashes remain evidence.',
        'scope': 'all 189 terminal slots including 159 previously native_failure and 30 previously completed',
        'cis_policy': 'do not transfer prior CIS to a changed proposal; prior score applicability must be independently checked by proposal hash and protocol',
        'model_calls': 0, 'raw_or_canonical_mutations': False})
    save(S / 'inventory.json', {'at': now(), 'slots': rows, 'counts': {'native_failure': 159, 'completed': 30},
                               'excluded_unfinished_slot': 'cycleresearcher__ai-control-deception__05__generation'})


def gateway_index(inventory):
    wanted = set()
    for row in inventory['slots']:
        out = Path(row['output_dir'])
        for component in ['researcher', 'reviewer']:
            for i in range(1, 11):
                value = read(out / component / 'api_requests' / f'{component}-{i:04}' / 'request.json')
                wanted.add(digest(json.dumps(value, ensure_ascii=False).encode()))
    starts, ends = {}, {}
    with (P / 'logs/model_gateway.jsonl').open() as stream:
        for line in stream:
            e = json.loads(line)
            if e.get('mock') is not False or e.get('request_sha256') not in wanted:
                continue
            if e['event'] == 'attempt_start':
                starts[e['request_id']] = e
            elif e['event'] == 'attempt_end':
                ends[e['request_id']] = e
    result = collections.defaultdict(list)
    for ident, end in ends.items():
        if ident in starts:
            result[starts[ident]['request_sha256']].append({'start': starts[ident], 'end': end})
    return result


def run_slot(item, gateways):
    key = item['job_key']
    task = S / 'packages' / key
    task.mkdir(parents=True, exist_ok=True)
    assert not (task / 'handoff.json').exists()
    out = Path(item['output_dir'])
    assert sha(out / 'result.json') == item['original_result']['sha256']
    original_files = filemap(out)
    snap = task / 'original_run'
    assert not snap.exists(), 'Partial package requires independent inspection before reuse'
    shutil.copytree(out, snap)
    assert original_files == filemap(snap)
    original = read(snap / 'result.json')
    config_path = V.INPUTS / item['domain'] / 'configuration.json'
    config = read(config_path)
    binding = read(snap / 'run_binding.json')
    assert sha(config_path) == binding['configuration_sha256']
    assert config['released_generator'] == {'class': 'CycleResearcher', 'function': 'generate_paper', 'n': 10, 'max_tokens': 19000}
    assert config['released_reviewer'] == {'class': 'DeepReviewer', 'function': 'evaluate', 'mode': 'Standard Mode', 'reviewer_num': 4, 'max_tokens': 35000}
    derived = {**config, 'configuration_id': REVISION, 'selection_semantics_revision': REVISION,
               'original_configuration_sha256': sha(config_path), 'original_configuration_id': config['configuration_id'],
               'original_deployment_manifest_sha256': binding['deployment_manifest_sha256'],
               'previous_result_deployment_manifest_sha256': original.get('deployment_manifest_sha256'),
               'missing_score_policy': 'upstream_internal_zero_then_first_max',
               'historical_missing_score_policy': config['missing_score_policy'],
               'review_format_compatibility_role': 'historical only; no effect on derived selection',
               'derived_review_parser': 'upstream DeepReviewer._parse_review without mapping',
               'derived_selection': 'upstream tutorial cell13 rating function and max assignment',
               'derivation_manifest': ref(S / 'derivation_manifest.json')}
    save(task / 'derived_configuration.json', derived)
    rows, all_ends = [], []
    for component in ['researcher', 'reviewer']:
        events = [json.loads(line) for line in (snap / component / 'api_events.jsonl').read_text().splitlines()]
        ends = {e['attempt_id']: e for e in events if e.get('event') == 'attempt_end'}
        all_ends.extend(ends.values())
        for i in range(1, 11):
            ident = f'{component}-{i:04}'
            req = snap / component / 'api_requests' / ident
            receipt, response, request = [read(req / n) for n in ['receipt.json', 'response.json', 'request.json']]
            end = ends[receipt['attempt_id']]
            assert receipt['status'] == end['status'] == 'completed'
            assert len(response['choices']) == 1 and response['choices'][0]['finish_reason'] == 'stop'
            assert response['model'] == request['model'] == 'gpt-6-astra' and request['reasoning_effort'] == 'xhigh'
            assert end['usage_known'] is True and response['usage'] == end['usage']
            assert digest(json.dumps(response, ensure_ascii=False).encode()) == receipt['response_sha256']
            assert digest(json.dumps(request, ensure_ascii=False, sort_keys=True).encode()) == receipt['request_sha256']
            physical = req / 'attempts' / receipt['attempt_id']
            assert read(physical / 'response.json') == response
            if (physical / 'stream.jsonl').exists():
                assert reassemble(physical / 'stream.jsonl') == response
            raw = snap / component / 'raw' / (ident + '.txt')
            assert raw.read_bytes() == response['choices'][0]['message']['content'].encode()
            assert read(snap / component / 'completed' / (ident + '.json'))['text_sha256'] == sha(raw)
            wire = digest(json.dumps(request, ensure_ascii=False).encode())
            matches = [g for g in gateways[wire] if receipt['started'] <= g['start']['at'] <= receipt['completed']
                       and g['start']['at'] <= g['end']['at']
                       and abs((datetime.datetime.fromisoformat(g['end']['at']) - datetime.datetime.fromisoformat(receipt['completed'])).total_seconds()) <= 1
                       and g['end'].get('usage') == response['usage'] and g['end'].get('completed') is True and g['end'].get('http_status') == 200]
            assert len(matches) == 1, (key, ident, len(matches))
            rows.append({'component': component, 'request_id': ident, 'receipt': receipt, 'usage': response['usage'], 'wire_sha256': wire,
                         'raw_sha256': sha(raw), 'successful_physical_response': ref(physical / 'response.json'),
                         'stream_reassembly_exact': (physical / 'stream.jsonl').exists(), 'gateway': matches[0]})
    assert len({r['gateway']['start']['request_id'] for r in rows}) == 20
    replay = task / 'replay'
    replay.mkdir()
    calls, lock = [], threading.Lock()

    class Recorded:
        def __init__(self, component):
            self.component = component

        def completion(self, messages, system=None, max_tokens=32768, request_id=None, **kwargs):
            directory = snap / self.component / 'api_requests' / request_id
            assert payload(messages, system, max_tokens, kwargs) == read(directory / 'request.json'), (key, self.component, request_id)
            with lock:
                calls.append({'component': self.component, 'request_id': request_id})
            return read(directory / 'response.json')

    old_socket = socket.socket
    def forbidden(*args, **kwargs):
        raise AssertionError('Network forbidden: deterministic cached replay')
    socket.socket = forbidden
    try:
        researcher = V.CycleResearcher.__new__(V.CycleResearcher)
        researcher.tokenizer = V.MessageTransport()
        researcher.model = V.ModelTransport(replay, 'researcher', Recorded('researcher'))
        references = Path(config['references_file']).read_text()
        assert digest(references.encode()) == config['references_sha256']
        papers = researcher.generate_paper(topic=config['topic'], references=references, max_tokens=19000, n=10)
        assert papers == read(snap / 'generated_papers.json')
        save(replay / 'generated_papers.json', papers)
        mapping = read(snap / 'carrier_mapping.json')
        carriers = []
        for i, paper in enumerate(papers):
            assert read(snap / 'candidates' / f'{i:02}.json') == paper
            carrier = (snap / 'carriers' / f'{i:02}.txt').read_text()
            assert digest(carrier.encode()) == mapping[i]['carrier_sha256']
            assert digest(paper['generated_text'].encode()) == mapping[i]['generated_text_sha256']
            carriers.append(carrier)
        save(replay / 'carrier_mapping.json', mapping)
        reviewer = V.DeepReviewer.__new__(V.DeepReviewer)
        reviewer.tokenizer = V.MessageTransport()
        reviewer.model = V.ModelTransport(replay, 'reviewer', Recorded('reviewer'))
        reviews = reviewer.evaluate(carriers, mode='Standard Mode', reviewer_num=4, max_tokens=35000)
        for i, review in enumerate(reviews):
            raw = (snap / 'reviewer/raw' / f'reviewer-{i+1:04}.txt').read_text()
            assert review == V.DeepReviewer._parse_review(reviewer, raw)
        assert reviews == read(snap / 'native_reviews.json')
        save(replay / 'upstream_reviews.json', reviews)
        best, ratings = native_select(reviews)
        best2, ratings2 = native_select(reviews)
        assert best == best2 and ratings == ratings2
    finally:
        socket.socket = old_socket
    assert len(calls) == 20 and len({(c['component'], c['request_id']) for c in calls}) == 20
    for component in ['researcher', 'reviewer']:
        assert read(replay / component / 'batch_plan.json') == read(snap / component / 'batch_plan.json')
        for i in range(1, 11):
            ident = f'{component}-{i:04}'
            for relative in [f'raw/{ident}.txt', f'completed/{ident}.json', f'native_calls/{ident}.json']:
                assert (replay / component / relative).read_bytes() == (snap / component / relative).read_bytes()
    proposal = carriers[best['index']]
    selection = {'selection_semantics_revision': REVISION, 'selected_original_index': best['index'], 'ratings': ratings,
                 'parse_fallback_count': sum(r['score_source'] == 'tutorial_zero_no_parsed_numeric_score' for r in ratings),
                 'all_ratings_zero': all(r['avg_rating'] == 0 for r in ratings), 'tie_break': 'first original index',
                 'score_scope': 'internal_candidate_selection_only; never CIS or failure credit',
                 'completed_logical_responses': {'generation': 10, 'review': 10}, 'selected_carrier': mapping[best['index']]}
    save(replay / 'selection.json', selection)
    (replay / 'proposal.md').write_bytes(proposal.encode())
    old_proposal_sha = sha(snap / 'proposal.md') if (snap / 'proposal.md').exists() else None
    previous_selection = read(snap / 'selection.json') if (snap / 'selection.json').exists() else None
    comparison = {'prior_status': original['status'], 'prior_selected_original_index': original.get('selected_original_index'),
                  'prior_proposal_sha256': old_proposal_sha, 'new_selected_original_index': best['index'], 'new_proposal_sha256': sha(replay / 'proposal.md'),
                  'selected_index_changed': original.get('selected_original_index') != best['index'],
                  'proposal_changed': old_proposal_sha != sha(replay / 'proposal.md'), 'prior_cis_auto_transfer_allowed': False,
                  'prior_ratings': previous_selection.get('ratings') if previous_selection else None, 'new_ratings': ratings}
    known = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
    unknown = 0
    for end in all_ends:
        if end.get('usage') is None:
            unknown += 1
        else:
            for name in known:
                known[name] += end['usage'].get(name, 0)
    save(task / 'all20_transport_evidence.json', rows)
    save(task / 'comparison.json', comparison)
    checks = {'all20_original_full_payloads_replayed_once': True, 'all20_raw_response_receipt_and_usage_exact': True,
              'all20_successful_gateway_identities_unique': True, 'official_generator_and_reviewer_invoked': True,
              'complete_raw_review_direct_upstream_parse_exact': True, 'original_native_artifacts_and_carriers_preserved': True,
              'original_standard4_and_generation_n10_unchanged': True, 'original_tutorial_rating_and_max_ast_executed': True,
              'repeat_selection_deterministic': True, 'compatibility_not_used_for_selection': True,
              'network_forbidden': True, 'live_original_files_unchanged': original_files == filemap(out)}
    assert all(checks.values())
    save(task / 'replay_acceptance.json', {'at': now(), 'passed': True, 'checks': checks, 'calls': sorted(calls, key=lambda c: (c['component'], c['request_id'])),
                                          'model_calls': 0, 'live_mutations': False})
    manifest = {'at': now(), 'job_key': key, 'expected_launches': item['launches'], 'original_snapshot': str(snap), 'original_files': original_files,
                'original_result_sha256': original_files['result.json'], 'original_configuration': ref(config_path), 'derived_configuration': ref(task / 'derived_configuration.json'),
                'derivation_manifest': ref(S / 'derivation_manifest.json'), 'replay_acceptance': ref(task / 'replay_acceptance.json'),
                'transport_evidence': ref(task / 'all20_transport_evidence.json'), 'selection': ref(replay / 'selection.json'),
                'proposal': ref(replay / 'proposal.md'), 'comparison': ref(task / 'comparison.json'), 'completed_responses': 20,
                'physical_attempts_total': len(all_ends), 'unknown_usage_attempts': unknown, 'known_usage_subtotal': known,
                'usage': None if unknown else known, 'usd': None, 'model_calls': 0, 'same_slot': True, 'same_material': True, 'new_sample': False}
    save(task / 'derivation_evidence.json', manifest)
    material_fields = ['method', 'domain', 'data_version', 'corpus_id', 'corpus_sha256', 'corpus_manifest_sha256', 'references_sha256', 'comparison_scope']
    candidate = {k: original[k] for k in material_fields if k in original}
    candidate.update(status='completed', terminal_reason=None, native_failure=False, proposal_markdown=proposal,
        selected_original_index=best['index'], completed_logical_responses=20, configuration_id=REVISION,
        configuration_sha256=sha(task / 'derived_configuration.json'), deployment_manifest_sha256=sha(S / 'derivation_manifest.json'),
        original_configuration_sha256=sha(config_path), original_deployment_manifest_sha256=binding['deployment_manifest_sha256'],
        selection_semantics_revision=REVISION, missing_score_policy='upstream_internal_zero_then_first_max',
        review_parser='upstream DeepReviewer._parse_review without compatibility mapping',
        parse_fallback_count=selection['parse_fallback_count'], all_ratings_zero=selection['all_ratings_zero'],
        completed_at=now(), native_output_paths=[str(replay / n) for n in ['generated_papers.json', 'upstream_reviews.json', 'carrier_mapping.json', 'selection.json', 'proposal.md']],
        native_terminal_evidence=ref(task / 'derivation_evidence.json'), known_usage_subtotal=known,
        failed_attempts_usage_unknown=unknown, usage=None if unknown else known, usd=None, raw_corpus_modified=False,
        material_reselection=False, same_slot=True, same_material=True, new_sample=False, new_context=False,
        original_all20responses_retained=True, new_model_calls=0, new_generation_attempts=0, new_candidates=0,
        is_exact_is_configuration=False, independent_native_publication_required=True, prior_cis_auto_transfer_allowed=False,
        selection_comparison=ref(task / 'comparison.json'))
    save(task / 'candidate_result.json', candidate)
    handoff = {'at': now(), 'job_key': key, 'status': 'derived_upstream_selection_candidate_ready_for_independent_review',
               'expected_launches': item['launches'], 'expected_old_result_sha256': original_files['result.json'],
               'manifest': ref(task / 'derivation_evidence.json'), 'candidate_result': ref(task / 'candidate_result.json'),
               'replay_acceptance': ref(task / 'replay_acceptance.json'), 'comparison': comparison,
               'selection_semantics_revision': REVISION, 'model_calls': 0, 'shared_live_mutations': False}
    save(task / 'handoff.json', handoff)
    return {**handoff, 'handoff': ref(task / 'handoff.json')}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--prepare', action='store_true')
    ap.add_argument('--key', action='append')
    a = ap.parse_args()
    if a.prepare:
        prepare_inventory()
        print('Frozen all 189 terminal slot identities; no model calls', flush=True)
        return
    inventory = read(S / 'inventory.json')
    for p, h in read(S / 'derivation_manifest.json')['source_bindings'].items():
        assert sha(p) == h, p
    gateways = gateway_index(inventory)
    ready, failed = [], []
    for item in inventory['slots']:
        if a.key and item['job_key'] not in a.key:
            continue
        handoff = S / 'packages' / item['job_key'] / 'handoff.json'
        if handoff.exists():
            ready.append({**read(handoff), 'handoff': ref(handoff)})
            continue
        try:
            result = run_slot(item, gateways)
            ready.append(result)
            print(json.dumps({'job_key': item['job_key'], 'passed': True, 'count': len(ready), 'comparison': result['comparison']}), flush=True)
        except Exception as exc:
            failed.append({'job_key': item['job_key'], 'error': str(exc), 'type': type(exc).__name__})
            traceback.print_exc()
            print(json.dumps({'job_key': item['job_key'], 'passed': False, 'error': str(exc)}), flush=True)
        (S / 'progress.json').write_text(json.dumps({'at': now(), 'passed': len(ready), 'failed': failed, 'model_calls': 0}, indent=2) + '\n')
    suffix = 'subset' if a.key else 'all189'
    save(S / ('ready_handoffs_' + suffix + '.json'), {'at': now(), 'ready': ready, 'failed': failed, 'model_calls': 0, 'live_mutations': False})
    if not a.key:
        assert len(ready) == 189 and not failed
        success = [h for h in ready if h['comparison']['prior_status'] == 'completed']
        summary = {'at': now(), 'passed': True, 'slots': 189, 'previous_completed': len(success), 'previous_native_failure': 159,
                   'previous_completed_proposal_changed': sum(h['comparison']['proposal_changed'] for h in success),
                   'previous_completed_selection_changed': sum(h['comparison']['selected_index_changed'] for h in success),
                   'responses_replayed': 3780, 'model_calls': 0, 'live_mutations': False,
                   'ready_handoffs': ref(S / 'ready_handoffs_all189.json'), 'derivation_manifest': ref(S / 'derivation_manifest.json')}
        save(S / 'sealed_delivery.json', summary)
        print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
