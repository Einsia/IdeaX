"""Clearly labelled offline metadata fixtures. Never invoke a production runner."""
from pathlib import Path
import argparse
import copy
import importlib.util
import json
import sys
from unittest import mock

S = Path(__file__).resolve().parent
P = S.parents[1]
sys.path.insert(0, str(S))
import scope_guard as G


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    require_new = not args.output.exists()
    assert require_new, 'Never replace an existing acceptance'
    fixture = G.read(S / 'scope_fixture_metadata.json')
    method = fixture['method']
    scope = G.fixed_scope(S, P, method)
    results = []

    def accept(name, function):
        function()
        results.append({'case': name, 'passed': True, 'expected': 'accepted'})

    def reject(name, function):
        try:
            function()
        except (RuntimeError, KeyError, ValueError) as exc:
            results.append({'case': name, 'passed': True, 'expected': 'rejected', 'reason': str(exc)})
            return
        raise AssertionError(name + ' unexpectedly accepted')

    entry = scope[fixture['job']['key']]
    job = fixture['job']
    spec = fixture['spec']
    output = Path(entry['output_dir'])
    accept('real_frozen_original_admitted_job_metadata', lambda: G.check_job(entry, job, spec, output))
    for key, row in scope.items():
        # Synthetic execution metadata only; membership does not grant launch permission.
        simulated = {**row, 'key': key, 'launches': 1, 'started': 'synthetic-fixture', 'command': ['synthetic-fixture']}
        enabled = {'enabled': True, 'eligible_domains': [row['domain']], 'eligible_slots': [1, 2, 3, 4, 5],
                   'eligible_slots_by_domain': {row['domain']: [1, 2, 3, 4, 5]}}
        with mock.patch.object(Path, 'resolve', lambda path: path):
            G.check_job(row, simulated, enabled, Path(row['output_dir']))
    accept('all_190_original_identities_with_synthetic_execution_metadata', lambda: None)
    for name, changes in [('never_launched', {'launches': 0}), ('wrong_domain', {'domain': 'foreign'}),
                          ('slot_06', {'slot': 6}), ('slot_00', {'slot': 0}), ('boolean_slot', {'slot': True}),
                          ('scoring_kind', {'kind': 'card'}), ('wrong_method', {'method': 'cycleresearcher'}),
                          ('missing_original_command', {'command': []}), ('missing_original_start', {'started': None})]:
        reject(name, lambda changes=changes: G.check_job(entry, {**job, **changes}, spec, output))
    for name, changes in [('method_disabled', {'enabled': False}), ('domain_disabled', {'eligible_domains': []}),
                          ('global_slots_closed', {'eligible_slots': []}),
                          ('domain_sibling_gate_closed', {'eligible_slots_by_domain': {entry['domain']: []}}),
                          ('domain_gate_absent', {'eligible_slots_by_domain': {}})]:
        reject(name, lambda changes=changes: G.check_job(entry, job, {**spec, **changes}, output))
    reject('old_online_output', lambda: G.check_job(entry, job, spec, P.parents[1] / 'runs' / method / entry['domain'] / output.name))
    reject('foreign_phase_output', lambda: G.check_job(entry, job, spec, P.parent / 'other-phase' / 'runs' / method / entry['domain'] / output.name))
    with mock.patch.object(Path, 'resolve', lambda path: P / 'runs-invalid-integration' / 'retired'):
        reject('redirected_retired_run', lambda: G.check_job(entry, job, spec, output))
    reject('unknown_key_membership', lambda: G.require(method + '__foreign__01__generation' in scope, 'Outside frozen scope'))
    original_read = G.read
    for name, mutation in [('scope_extra_slot', lambda s: s['rows'].append(copy.deepcopy(s['rows'][0]))),
                           ('scope_missing_slot', lambda s: s['rows'].pop()),
                           ('scope_foreign_phase', lambda s: s.update(phase=str(P.parent))),
                           ('scope_wrong_method', lambda s: s.update(method='cycleresearcher')),
                           ('scope_foreign_output', lambda s: s['rows'][0].update(output_dir='/tmp/foreign'))]:
        altered = G.read(S / 'frozen_scope.json')
        mutation(altered)
        with mock.patch.object(G, 'read', lambda p: altered if Path(p) == S / 'frozen_scope.json' else original_read(p)):
            reject(name, lambda: G.fixed_scope(S, P, method))
    with mock.patch.object(G, 'sha', lambda p: 'synthetic-wrong-hash'):
        reject('frozen_scope_source_hash_change', lambda: G.fixed_scope(S, P, method))

    action, recovery = fixture['action'], fixture['recovery_manifest']
    accept('real_executed_recovery_binding', lambda: G.executed_recovery(job, action, recovery, fixture['recovery_manifest_path'], P))
    reject('unexecuted_recovery', lambda: G.executed_recovery({**job, 'executed_recovery_ids': []}, action, recovery, fixture['recovery_manifest_path'], P))
    reject('recovery_wrong_slot', lambda: G.executed_recovery(job, action, {**recovery, 'slot': 6}, fixture['recovery_manifest_path'], P))
    reject('recovery_changed_command', lambda: G.executed_recovery(job, {**action, 'command': ['foreign']}, recovery, fixture['recovery_manifest_path'], P))
    reject('recovery_online_manifest', lambda: G.executed_recovery(job, action, recovery, P.parents[1] / 'state/online.json', P))

    if method == 'insightagents':
        keys = ('host', 'admission', 'binding', 'package')
        def validate(values):
            G.check_insight_metadata(entry, *(values[k] for k in keys))
        mutations = [
            ('admission_disabled', 'admission', {'enabled': False}),
            ('admission_foreign_domain', 'admission', {'domain': 'foreign'}),
            ('admission_foreign_slot', 'admission', {'slot': 'slot-06'}),
            ('admission_fixture', 'admission', {'fixture': True}),
            ('run_binding_foreign_output', 'binding', {'output': '/tmp/foreign'}),
            ('run_binding_other_run', 'binding', {'run_id': 'other-run'}),
            ('run_binding_other_package', 'binding', {'package_sha256': 'other-package'}),
            ('run_binding_other_admission', 'binding', {'admission_receipt_sha256': 'other-admission'}),
            ('admission_other_prompt', 'admission', {'topic_sha256': 'other-prompt'}),
            ('host_other_domain_prompt', 'host', {'domain_json': '/tmp/foreign.json'}),
        ]
    else:
        keys = ('material', 'canonical', 'graph', 'launch')
        def validate(values):
            G.check_sci_metadata(entry, *(values[k] for k in keys))
        mutations = [
            ('graph_online_scope', 'graph', {'comparison_scope': 'online'}),
            ('graph_original_transfer', 'graph', {'original_graph_transfer_included': True}),
            ('graph_other_domain', 'graph', {'domain': 'foreign'}),
            ('graph_other_prompt', 'graph', {'domain_sha256': 'other-prompt'}),
            ('canonical_other_manifest', 'canonical', {'manifest_sha256': 'other-manifest'}),
            ('canonical_other_slot', 'canonical', {'slot': 'slot-06'}),
            ('material_reused_context', 'material', {'native_context_fresh': False}),
            ('material_fixture', 'material', {'fixture': True}),
            ('launch_fixture', 'launch', {'fixture': True}),
            ('launch_foreign_output', 'launch', {'command': ['foreign-output']}),
        ]
    accept('real_frozen_native_admission_metadata', lambda: validate(fixture))
    for name, field, change in mutations:
        altered = copy.deepcopy(fixture)
        altered[field].update(change)
        reject(name, lambda altered=altered: validate(altered))

    loader = importlib.util.spec_from_file_location('scope_fixture_builder', S / 'builder.py')
    builder = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(builder)
    for status, live in [('pending', False), ('running', True), ('completed', False), ('native_failure', False), ('infrastructure_failure', True)]:
        observed = {**job, 'status': status, 'launches': 0 if status == 'pending' else job['launches']}
        with mock.patch.object(builder, 'read', return_value={'jobs': {job['key']: observed}}), mock.patch.object(builder.C, 'alive', return_value=live):
            assert builder.classify(job['key'])['skip'] == 'not_idle_api_failure'
        results.append({'case': f'classification_{status}_live_{live}', 'passed': True, 'expected': 'skip'})
    prior = G.read(S / 'predecessor_release.json')
    assert G.sha(prior['path']) == prior['sha256']
    assert all(G.sha(p) == h for p, h in prior['bindings'].items())
    old = Path(prior['path']).parent
    unchanged = [p for p in (S / 'templates').iterdir() if p.is_file()]
    unchanged += [S / n for n in ('ledger_reconciliation.py', 'provider_failure.py') if (S / n).exists()]
    assert all(G.sha(p) == G.sha(old / p.relative_to(S)) for p in unchanged)
    results.append({'case': 'predecessor_and_all_runtime_classification_accounting_files_unchanged', 'passed': True, 'expected': 'identical'})
    report = {'passed': True, 'method': method, 'original_slots': 190, 'checks': results,
              'fixture_kind': fixture['fixture_kind'], 'model_calls': 0, 'shared_mutations': False,
              'no_live_handoff_or_worker': True, 'scope': G.reference(S / 'frozen_scope.json'),
              'builder': G.reference(S / 'builder.py'), 'guard': G.reference(S / 'scope_guard.py')}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'passed': True, 'method': method, 'checks': len(results), 'acceptance': G.reference(args.output)}))


if __name__ == '__main__':
    main()
