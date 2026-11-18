"""Build the existing offline boundary without editing shared runtime registries."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
PHASE = ROOT.parents[1]


def build(output, model_socket, manifest_path, domain, slot, resume=False, fixture=False, admission_receipt=None, admission_sha256=None):
    authorization = None
    if not fixture:
        from controlled_gate import verify_admission
        authorization = verify_admission(admission_receipt, admission_sha256, manifest_path, output, domain, slot, model_socket)
    manifest = json.loads(Path(manifest_path).read_text())
    spec = importlib.util.spec_from_file_location('bound_offline_exec', PHASE / 'runtime/offline_exec.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    command = [manifest['python_executable'], str(ROOT / 'adapter.py'), '--output', str(output),
               '--manifest', str(manifest_path), '--domain', domain, '--slot', slot]
    if fixture: command.append('--fixture')
    else: command += ['--admission-receipt', str(admission_receipt), '--admission-sha256', admission_sha256]
    if resume: command.append('--resume')
    # Mount program/material files individually, never previous fixture outputs.
    mounts = [ROOT / 'native', Path(manifest['python_executable']).parent.parent, Path(manifest_path)]
    mounts += [Path(row['path']) for row in manifest['bound_files']
               if Path(row['path']).is_relative_to(ROOT) and not Path(row['path']).is_relative_to(ROOT / 'native')]
    mounts += [Path(manifest['material_manifest']['path']), PHASE / 'inputs/corpus/coverage_38_domains.json']
    previous = PHASE / 'staging/insightagents_local_recommendation_adapter_v1'
    mounts += [previous / 'native']
    mounts += [Path(row['path']) for row in manifest['bound_files'] if Path(row['path']).is_relative_to(previous) and not Path(row['path']).is_relative_to(previous / 'native')]
    mounts += [PHASE / 'state/insightagents_stream_continuation_v5/stream_transport.py']
    if authorization:
        mounts += [Path(admission_receipt), Path(authorization['independent_review']['path'])]
        terminal = authorization.get('domain_terminal_acceptance')
        if terminal:
            mounts += [Path(terminal['path']), PHASE / 'runs/insightagents' / domain / 'slot-01/result.json']
    return module.build_command(output, model_socket, command, extra_readonly=mounts, method=None)


def main():
    ap = argparse.ArgumentParser()
    for name in ('output', 'model-socket', 'manifest', 'domain', 'slot'): ap.add_argument('--' + name, required=True)
    ap.add_argument('--resume', action='store_true'); ap.add_argument('--fixture', action='store_true')
    ap.add_argument('--admission-receipt'); ap.add_argument('--admission-sha256')
    args = ap.parse_args()
    argv = build(args.output, args.model_socket, args.manifest, args.domain, args.slot, args.resume, args.fixture, args.admission_receipt, args.admission_sha256)
    Path(args.output, 'offline_launch.json').write_text(json.dumps({'command': argv}, indent=2) + '\n')
    raise SystemExit(subprocess.run(argv).returncode)


if __name__ == '__main__': main()
