"""Bind an immutable domain input to a fresh, unchanged native ResearchAgent process."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

PHASE = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--route', required=True)
    ap.add_argument('--domain-json', required=True)
    ap.add_argument('--output-dir', required=True)
    ap.add_argument('--prepare-only', action='store_true')
    args = ap.parse_args()
    route_path = Path(args.route)
    route = json.loads(route_path.read_text())
    domain = json.loads(Path(args.domain_json).read_text())
    assert route['method'] == 'researchagent' and domain['id'] == route['domain']
    assert str(Path(args.domain_json).resolve()) == route['domain_json']
    for name, digest in route['worker_bindings'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    import researchagent
    import native_inputs
    native_inputs.SUPPLEMENT = Path(route['supplement'])
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    material = {key: route[key] for key in ('method', 'domain', 'data_version', 'corpus_id', 'corpus_sha256', 'supplement_id')}
    material.update(route_path=str(route_path), route_sha256=hashlib.sha256(route_path.read_bytes()).hexdigest(),
                    raw_corpus_modified=False, fresh_native_context=True)
    researchagent.save(output / 'input_material_version.json', material)
    if args.prepare_only:
        context = researchagent.prepare(domain, output)
        boundary = json.loads((output / 'offline_boundary.json').read_text())
        expected = json.loads(Path(route['context']).read_text())
        checks = {'native_context_reproduced': context == expected,
                  'domain_and_package_bound': True,
                  'public_network_denied': boundary.get('public_network') is False,
                  'no_default_route': boundary.get('no_default_route') is True,
                  'separate_network_namespace': boundary.get('network_namespace') != boundary.get('parent_network_namespace')}
        value = {'passed': all(checks.values()), 'domain': domain['id'], 'checks': checks,
                 'native_references': len(context['references']), 'native_entities': len(context['entities']),
                 'model_api_requests': 0, 'public_runtime_requests': 0, 'material': material}
        researchagent.save(output / 'domain_dispatch_acceptance.json', value)
        print(json.dumps(value))
        raise SystemExit(0 if value['passed'] else 2)
    sys.argv = [str(PHASE / 'adapters/researchagent.py'), '--domain-json', args.domain_json, '--output-dir', args.output_dir]
    researchagent.main()


if __name__ == '__main__':
    main()
