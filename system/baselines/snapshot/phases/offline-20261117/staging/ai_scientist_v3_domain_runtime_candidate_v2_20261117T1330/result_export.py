from pathlib import Path
import hashlib,json,subprocess
D=Path(__file__).resolve().parent
CHECKER=Path("/home/liuhanzuo/new-ar-baseline-survey-20261117/review_tools/check_sakana_artifacts.py")
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2)+"\n")

def export_result(run, output, identity, returncode, fixture=False):
    """Preserve complete native objects. Scoring admission belongs to coordinator."""
    run, output = Path(run), Path(output)
    result = {**identity, 'fixture': fixture, 'native_returncode': returncode,
        'status': 'native_failure', 'scoring_gate_open': False, 'ideas': [],
        'native_run': str(run), 'journal_relative_root': 'native', 'external_CIS_feedback_to_native': False,
        'native_stage_only': True, 'main_comparison_included': False}
    paths = {'idea_bundle': run / 'results/idea/idea_bundle.json',
             'target_rubrics': run / 'results/idea/target_rubrics.json'}
    if returncode == 0 and all(p.is_file() for p in paths.values()):
        check = subprocess.run(['/usr/bin/python3', '-B', str(CHECKER), '--source-root', str(D / 'official_source'),
            '--raw-dir', str(run / 'pre_normalization'), '--terminal-dir', str(run / 'results/idea'), '--cycle-index', '1'],
            capture_output=True, text=True)
        (output / 'artifact_review.stdout.json').write_text(check.stdout)
        (output / 'artifact_review.stderr.txt').write_text(check.stderr)
        if check.returncode == 0:
            bundle = json.loads(paths['idea_bundle'].read_text())
            rubrics = json.loads(paths['target_rubrics'].read_text())
            presentation = 'Original native idea_bundle.json (complete):\n' + json.dumps(bundle, ensure_ascii=False, sort_keys=True, indent=2)
            presentation += '\n\nOriginal native target_rubrics.json (complete):\n' + json.dumps(rubrics, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
            card = {**identity, 'idea_bundle': bundle, 'target_rubrics': rubrics,
                'source_bindings': {str(p): sha(p) for p in paths.values()},
                'presentation': presentation, 'presentation_sha256': hashlib.sha256(presentation.encode()).hexdigest(),
                'LLM_summarization': False, 'fixture': fixture}
            save(output / 'external_CIS_input.json', card)
            (output / 'external_CIS_input.txt').write_text(presentation)
            result.update(status='native_terminal_pending_independent_acceptance',
                ideas=[{'idea_id': bundle.get('idea_id'), 'title': bundle.get('title'),
                        'content': presentation, 'idea_bundle': bundle, 'target_rubrics': rubrics}],
                artifact_replay_passed=True, external_CIS_input=str(output / 'external_CIS_input.json'))
        else: result['failure_reason'] = 'native_artifact_replay_or_required_rubrics_failed'
    else:
        result['failure_reason'] = 'native_stage_nonzero_or_missing_required_artifacts'
    events_path = run / 'transport/events.jsonl'
    events = [json.loads(x) for x in events_path.read_text().splitlines()] if events_path.exists() else []
    attempts = [x for x in events if x['event'] == 'attempt_start']
    terminal = {x['physical_attempt_id']: x for x in events if x['event'] in ('attempt_end', 'attempt_error')}
    result['usage_accounting'] = {'journal': str(events_path), 'physical_attempts': len(attempts),
        'usage_unknown_attempts': sum(not terminal.get(x['physical_attempt_id'], {}).get('usage_known', False) for x in attempts),
        'usd': None, 'paid_model_calls': 0 if fixture else None, 'logical_identity_kind': 'payload_group',
        'real_usage_source': 'transport journal plus exact bridge_request_id reconciliation; no missing value is zero'}
    unresolved = [x['physical_attempt_id'] for x in attempts if x['physical_attempt_id'] not in terminal]
    transport_failures = [x for x in terminal.values() if x.get('provider_status') == 'transport_error'
        or (x.get('provider_http_status') or 0) >= 500 or x.get('provider_http_status') == 429
        or (x.get('provider_http_status') == 200 and not x.get('completed', False))]
    result['transport_infrastructure_failure_attempts'] = [x['physical_attempt_id'] for x in transport_failures] + unresolved
    if not (run / 'process_receipt.json').exists() or (returncode != 0 and (transport_failures or unresolved)):
        result['status'] = 'infrastructure_failure'
        result['failure_reason'] = 'native stage incomplete with recorded transport failure; original trace retained; no automatic retry'
    save(output / 'result.json', result)
    return result

