"""Host-only immutable per-domain dispatch to the existing offline execution boundary."""
import argparse
import hashlib
import json
import os
from pathlib import Path

PHASE = Path(__file__).resolve().parents[1]


def checked(path, digest):
    path = Path(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('Frozen domain route hash mismatch: ' + str(path))
    return json.loads(path.read_text())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--routes', required=True)
    ap.add_argument('--domain-json', required=True)
    ap.add_argument('--output-dir', required=True)
    ap.add_argument('--prepare-only', action='store_true')
    args = ap.parse_args()
    index = json.loads(Path(args.routes).read_text())
    domain = json.loads(Path(args.domain_json).read_text())['id']
    reference = index['domains'][domain]
    route = checked(reference['path'], reference['sha256'])
    assert route['method'] == 'researchagent' and route['domain'] == domain
    assert route['domain_json'] == str(Path(args.domain_json).resolve())
    for name, digest in route['host_bindings'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
            raise ValueError('Frozen native input changed: ' + name)
    command = ['/usr/bin/python3', str(PHASE / 'runtime/offline_exec.py'), '--method', 'researchagent',
               '--output', str(Path(args.output_dir).resolve()), '--model-socket', '/tmp/insightpro-offline-model-20261117.sock']
    for path in route['read_only'] + [reference['path']]:
        command += ['--read-only', path]
    command += ['--', str(PHASE / 'environments/researchagent/venv/bin/python'),
                str(PHASE / 'adapters/researchagent_versioned.py'), '--route', reference['path'],
                '--domain-json', args.domain_json, '--output-dir', args.output_dir]
    if args.prepare_only:
        command.append('--prepare-only')
    os.execv(command[0], command)


if __name__ == '__main__':
    main()
