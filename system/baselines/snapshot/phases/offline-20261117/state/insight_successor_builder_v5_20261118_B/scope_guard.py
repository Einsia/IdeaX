"""Read-only fixed original phase scope and already-executed admission checks.

Membership is not launch authorization. No current registry is widened here.
"""
from pathlib import Path
import hashlib
import json


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def reference(path):
    return {'path': str(path), 'sha256': sha(path)}


def bound(ref, phase):
    path = Path(ref['path'])
    require(path.is_absolute() and path.resolve().is_relative_to(phase),
            'Evidence is outside this offline phase; online/retired evidence forbidden')
    require(sha(path) == ref['sha256'], 'Original admission evidence hash changed')
    return read(path)


def fixed_scope(release_dir, phase, method):
    scope = read(release_dir / 'frozen_scope.json')
    require(scope['phase'] == str(phase) and scope['method'] == method,
            'Recovery scope phase/method mismatch')
    for name, source in scope['sources'].items():
        require(Path(source['frozen_path']) == release_dir / 'scope_sources' / name,
                'Frozen scope source path differs')
        require(sha(source['frozen_path']) == source['sha256'], 'Frozen scope source changed')
    sources = scope['sources']
    domains = sorted(d['id'] for d in read(sources['domains.json']['frozen_path']))
    coverage = read(sources['coverage_38_domains.json']['frozen_path'])
    protocol = read(sources['protocol.json']['frozen_path'])
    require(len(domains) == len(set(domains)) == 38 and
            domains == sorted(d['domain_id'] for d in coverage['domains']),
            'Frozen original 38 domains differ')
    require(protocol['protocol_id'] == scope['protocol_id'] == 'offline-common-corpus-20261117'
            and protocol['domains'] == 38 and protocol['independent_final_slots_per_domain'] == 5,
            'Original phase protocol differs')
    expected = {(d, slot) for d in domains for slot in range(1, 6)}
    require(len(scope['rows']) == 190 and
            {(r['domain'], r['slot']) for r in scope['rows']} == expected,
            'Recovery scope must be exactly original 38 x 5')
    for row in scope['rows']:
        d, slot = row['domain'], row['slot']
        require(row['method'] == method and row['kind'] == 'generation' and
                row['job_key'] == f'{method}__{d}__{slot:02}__generation' and
                row['output_dir'] == str(phase / 'runs' / method / d / f'slot-{slot:02}') and
                row['domain_json'] == str(phase / 'inputs' / d / 'domain.json'),
                'Frozen scope row has a foreign identity or path')
    return {row['job_key']: row for row in scope['rows']}


def check_job(entry, job, spec, output):
    require(all(job.get(k) == entry[k] for k in ('method', 'kind', 'domain', 'slot')) and
            job.get('key') == entry['job_key'] and type(job.get('slot')) is int,
            'Campaign identity differs from original fixed slot')
    require(str(output) == entry['output_dir'] and output.resolve() == output,
            'Output is not this original offline phase slot')
    require(type(job.get('launches')) is int and job['launches'] > 0 and
            job.get('started') and isinstance(job.get('command'), list) and job['command'],
            'Unlaunched original slot cannot be recovered')
    require(spec.get('enabled') is True and job['domain'] in spec.get('eligible_domains', []),
            'Original method/domain is not currently enabled')
    require(spec.get('eligible_slots') is None or job['slot'] in spec['eligible_slots'],
            'Original slot is not currently enabled')
    per_domain = spec.get('eligible_slots_by_domain')
    require(isinstance(per_domain, dict) and job['slot'] in per_domain.get(job['domain'], []),
            'Original domain slot gate is closed; no sibling auto-admission')


def admitted_job(release_dir, phase, method, key, job, output):
    rows = fixed_scope(release_dir, phase, method)
    require(key in rows, 'Key outside frozen original phase recovery scope')
    entry = rows[key]
    methods_path = phase / 'state/methods.json'
    methods_bytes = methods_path.read_bytes()
    spec = json.loads(methods_bytes)[method]
    check_job(entry, job, spec, output)
    require(sha(entry['domain_json']) == entry['domain_sha256'], 'Original domain prompt changed')
    proof = {'frozen_scope': reference(release_dir / 'frozen_scope.json'), 'entry': entry,
             'observed_methods_sha256': hashlib.sha256(methods_bytes).hexdigest(),
             'observed_method_gate': {k: spec.get(k) for k in
                 ('enabled', 'eligible_domains', 'eligible_slots', 'eligible_slots_by_domain')},
             'already_launched': True, 'does_not_enable_or_launch_any_slot': True,
             'model_calls': 0, 'shared_mutations': False}
    return entry, spec, proof


def executed_recovery(job, action, manifest, manifest_path, phase):
    require(Path(manifest_path).resolve().is_relative_to(phase), 'Foreign recovery manifest')
    rid = action['recovery_id']
    launches = [r for r in job.get('recovery_launches', []) if r.get('recovery_id') == rid]
    require(rid in job.get('executed_recovery_ids', []) and len(launches) == 1 and
            launches[0]['command'] == action['command'] == job['command'],
            'Recovery lacks one exact already-executed command binding')
    require(manifest['recovery_id'] == rid and manifest['job_key'] == job['key'] and
            manifest['method'] == job['method'] and manifest['domain'] == job['domain'] and
            manifest['slot'] in (job['slot'], f"slot-{job['slot']:02}") and
            manifest['output_dir'] == str(phase / 'runs' / job['method'] / job['domain'] / f"slot-{job['slot']:02}"),
            'Executed recovery points to another original slot')


def check_insight_metadata(entry, host, admission, binding, package):
    identity = {'domain': entry['domain'], 'slot': f"slot-{entry['slot']:02}",
                'output': entry['output_dir'], 'fixture': False}
    require(all(host.get(k) == v and admission.get(k) == v and binding.get(k) == v
                for k, v in identity.items()), 'Insight host/admission/run identity differs')
    require(host.get('schema') == 'insightagents-original-slot-host-v2' and
            admission.get('schema') == 'insightagents-original-slot-admission-v2' and
            admission.get('enabled') is True and host['domain_json'] == entry['domain_json'],
            'Insight original host or enabled admission invalid')
    require(all(admission.get(k) == binding.get(k) for k in
                ('method', 'run_id', 'admission_id', 'purpose', 'comparison_scope', 'model', 'api')) and
            admission.get('method') == package.get('method') == 'insightagents' and
            admission.get('purpose') == 'original-native-generation' and
            admission.get('model') == 'gpt-6-astra' and admission.get('reasoning_effort') == binding.get('effort') == 'xhigh',
            'Insight original run identity/model differs')
    require(admission['manifest_sha256'] == host['manifest']['sha256'] == binding['package_sha256'] and
            host['admission']['sha256'] == binding['admission_receipt_sha256'],
            'Insight original manifest/admission binding differs')
    topic = package['topic_mapping']['domains'][entry['domain']]
    require(binding['topic_mapping'] == topic and topic['domain_source'] == entry['domain_json'] and
            topic['domain_source_sha256'] == entry['domain_sha256'] and
            admission['topic_sha256'] == topic['topic_sha256'] and
            admission['corpus_sha256'] == package['corpus_sha256'], 'Insight original material changed')


def insight_admission(entry, contract, output, phase):
    host = bound(contract, phase)
    admission = bound(host['admission'], phase)
    package = bound(host['manifest'], phase)
    binding = read(output / 'run_binding.json')
    check_insight_metadata(entry, host, admission, binding, package)
    require(all(sha(p) == h for p, h in host['bindings'].items()), 'Original host bindings changed')
    require(all(sha(r['path']) == r['sha256'] for r in package['bound_files']), 'Original native package changed')
    review = bound(admission['independent_review'], phase)
    require(review.get('passed') is True and review.get('status') == 'accepted_staging_package' and
            review.get('manifest_sha256') == host['manifest']['sha256'], 'Original package review invalid')
    if entry['slot'] > 1:
        terminal = bound(admission['domain_terminal_acceptance'], phase)
        require(terminal.get('passed') is True and terminal.get('fixture') is False and
                terminal.get('method') == 'insightagents' and terminal.get('domain') == entry['domain'] and
                terminal.get('checks') and all(v is True for v in terminal['checks'].values()),
                'Insight same-domain first-slot terminal gate not accepted')
    else:
        require(admission.get('domain_terminal_acceptance') is None, 'First slot borrowed a sibling terminal')
    registration = read(phase / 'state/new_method_accounting/registered.json')['registrations']
    require(registration.count(host['accounting_registration']) == 1,
            'Original Insight run lacks unique accounting registration')
    return {'host_contract': contract, 'admission': host['admission'],
            'run_binding': reference(output / 'run_binding.json'), 'enabled': True}


def check_sci_metadata(entry, material, canonical, graph, launch):
    for obj in (material, canonical, graph):
        require(obj.get('method') == 'sciagents' and obj.get('domain') == entry['domain'] and
                obj.get('comparison_scope') == 'matched-domain-abstract-graph' and
                obj.get('original_graph_transfer_included') is False,
                'Sci identity is not original offline matched domain graph')
    require(launch.get('fixture') is False and str(entry['output_dir']) in launch.get('command', []),
            'Sci original real native launch/output evidence missing')
    for obj in (material, canonical):
        require(obj.get('fixture') is not True and obj.get('native_context_fresh') is True and
                obj.get('slot', f"slot-{entry['slot']:02}") == f"slot-{entry['slot']:02}",
                'Sci fixture/slot/native context identity differs')
        require(all(obj.get(k) == material.get(k) for k in
                    ('manifest_path', 'manifest_sha256', 'corpus_id', 'corpus_sha256', 'data_version',
                     'graph_sha256', 'embedding_sha256')), 'Sci original run material identity differs')
    require(graph['domain_json'] == entry['domain_json'] and graph['domain_sha256'] == entry['domain_sha256'] and
            all(graph.get(k) == material.get(k) for k in
                ('corpus_id', 'corpus_sha256', 'data_version', 'graph_sha256', 'embedding_sha256')),
            'Sci original graph or domain prompt changed')


def sci_admission(entry, spec, output, phase):
    material = read(output / 'input_material_version.json')
    canonical = read(output / 'result.json')
    graph_ref = {'path': material['manifest_path'], 'sha256': material['manifest_sha256']}
    graph = bound(graph_ref, phase)
    launch = read(output / 'offline_launch.json')
    check_sci_metadata(entry, material, canonical, graph, launch)
    require(all(sha(p) == h for p, h in graph['bindings'].items()), 'Original Sci graph bindings changed')
    registered = spec.get('matched_first_slot_manifests', {}).get(entry['domain'])
    if registered:
        require(registered == graph_ref, 'Current Sci admission is not this original graph')
        bound(registered, phase)
    terminal_ref = spec.get('domain_terminal_acceptances', {}).get(entry['domain'])
    require(registered or terminal_ref, 'Original Sci graph has no domain admission')
    if entry['slot'] > 1:
        require(terminal_ref is not None, 'Sci sibling requires same-domain terminal admission')
    if terminal_ref:
        terminal = bound(terminal_ref, phase)
        require(terminal.get('passed') is True and terminal.get('domain') == entry['domain'] and
                terminal.get('checks') and all(v is True for v in terminal['checks'].values()),
                'Sci domain terminal acceptance invalid')
    return {'graph_manifest': graph_ref, 'domain_terminal_acceptance': terminal_ref,
            'input_material': reference(output / 'input_material_version.json'),
            'original_offline_launch': reference(output / 'offline_launch.json'), 'enabled': True}
