"""Run one research task with local corpus access and model-only external access."""
import argparse
import json
import os
from pathlib import Path
import subprocess

PHASE = Path(__file__).resolve().parents[1]
CAMPAIGN = PHASE.parents[1]


def build_command(output, model_socket, command, extra_readonly=(), method=None):
    output = Path(output).resolve()
    if not output.is_relative_to(PHASE) or output == PHASE:
        raise ValueError('Output must be a task directory inside the offline phase')
    output.mkdir(parents=True, exist_ok=True)
    model_socket = Path(model_socket).resolve()
    if not model_socket.is_socket():
        raise ValueError('Model bridge socket is unavailable')
    args = ['/usr/bin/bwrap', '--unshare-user', '--unshare-net', '--unshare-pid',
            '--unshare-ipc', '--unshare-uts', '--cap-drop', 'ALL',
            '--new-session', '--die-with-parent', '--clearenv']
    for p in ['/usr', '/bin', '/sbin', '/lib', '/lib64']:
        if Path(p).exists():
            args += ['--ro-bind', p, p]
    for p in ['/etc/ssl', '/etc/passwd', '/etc/group', '/etc/hosts', '/etc/nsswitch.conf']:
        if Path(p).exists():
            args += ['--ro-bind', p, p]
    args += ['--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--tmpfs', '/run']
    # Only program code, dependencies and frozen inputs; no old runs or credentials.
    source_names = {p.stem for p in map(Path, command) if p.name.endswith('.py')}
    method_sources = source_names & {'dr_claw', 'deepscientist', 'autoresearchclaw',
                                    'researchagent', 'ai_researcher', 'sciagents', 'cycleresearcher'}
    if method:
        if method not in {'dr_claw', 'deepscientist', 'autoresearchclaw', 'researchagent',
                          'ai_researcher', 'sciagents', 'cycleresearcher'}:
            raise ValueError('Unknown native method')
        method_sources.add(method)
    for extra in extra_readonly:
        path = Path(extra).resolve()
        if path == (CAMPAIGN/'sources').resolve():
            raise ValueError('Mount one native method source, never the entire source collection')
        if path.is_relative_to((CAMPAIGN/'sources').resolve()):
            method_sources.add(path.relative_to((CAMPAIGN/'sources').resolve()).parts[0])
    mounts = [CAMPAIGN/'sources'/name for name in sorted(method_sources)]
    mounts += [
              Path('/home/liuhanzuo/.local/share/uv/python'),
              Path('/mnt/einsia/aws01-nvme/liuhanzuo/ai-home/.local/lib/ai-tools/codex-pkg'),
              CAMPAIGN/'state/node-v22.16.0-linux-x64', CAMPAIGN/'state/dr_claw_runtime']
    mounts += list((CAMPAIGN/'state').glob('venv_*'))
    mounts += [PHASE/p for p in ('adapters', 'runtime', 'services', 'protocol')]
    mounts += [PHASE/'inputs/domains.json']
    # Raw metadata/text and compressed knowledge have separate access profiles.
    domains_file = PHASE/'inputs/domains.json'
    if domains_file.exists():
        domains = json.loads(domains_file.read_text())
        if isinstance(domains, dict):
            domains = domains.get('domains', [])
        for domain in domains:
            if isinstance(domain, dict) and domain.get('id'):
                mounts.append(PHASE/'inputs'/domain['id'])
    for name in ('corpus.sqlite', 'manifest.json', 'coverage.json', 'README.md'):
        mounts.append(PHASE/'inputs/corpus'/name)
    mounts += [Path(p) for p in extra_readonly]
    seen = set()
    for p in mounts:
        if p.exists():
            # Preserve both literal and resolved paths for venv/runtime symlinks.
            for dest in dict.fromkeys([str(p), str(p.resolve())]):
                if dest not in seen:
                    args += ['--ro-bind', str(p.resolve()), dest]
                    seen.add(dest)
    # Frozen upstream repositories sometimes contain unrelated developer credentials.
    # Mask their files in the task view without modifying the archived sources.
    for name in sorted(method_sources):
        source = CAMPAIGN/'sources'/name
        for secret in source.rglob('.env*'):
            if secret.is_file():
                args += ['--ro-bind', '/dev/null', str(secret)]
        for metadata in source.rglob('.git'):
            mask = PHASE/'runtime/empty_source_metadata' if metadata.is_dir() else Path('/dev/null')
            args += ['--ro-bind', str(mask), str(metadata)]
    args += ['--dir', str(CAMPAIGN/'sources'), '--dir', str(PHASE/'state'), '--symlink', str(CAMPAIGN/'sources'), str(PHASE/'sources')]
    for name in ('node-v22.16.0-linux-x64', 'dr_claw_runtime'):
        args += ['--symlink', str(CAMPAIGN/'state'/name), str(PHASE/'state'/name)]
    args += ['--bind', str(output), str(output), '--ro-bind', str(model_socket), '/model.sock']
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/tmp/home', 'TMPDIR': '/tmp',
           'LANG': 'C.UTF-8', 'PYTHONUNBUFFERED': '1', 'PYTHONDONTWRITEBYTECODE': '1',
           'INSIGHTPRO_OFFLINE_ENFORCED': '1', 'INSIGHTPRO_OFFLINE_PHASE': str(PHASE),
           'OPENAI_BASE_URL': 'http://127.0.0.1:8765/v1', 'OPENAI_API_KEY': 'offline-model-bridge',
           'AR_BASELINE_API_KEY': 'offline-model-bridge', 'NO_PROXY': '*',
           'OPENAI_LOGGING': 'disabled', 'UV_OFFLINE': '1', 'HF_HUB_OFFLINE': '1',
           'TRANSFORMERS_OFFLINE': '1', 'PIP_NO_INDEX': '1', 'GIT_CONFIG_NOSYSTEM': '1'}
    for key, value in env.items():
        args += ['--setenv', key, value]
    args += ['--chdir', str(output), '--', '/usr/bin/python3', str(PHASE/'runtime/inside.py'),
             '--output', str(output), '--parent-netns', os.readlink('/proc/self/ns/net'), '--', *command]
    return args


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', required=True)
    ap.add_argument('--model-socket', required=True)
    ap.add_argument('--read-only', action='append', default=[])
    ap.add_argument('--method')
    ap.add_argument('command', nargs=argparse.REMAINDER)
    args = ap.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        ap.error('Missing task command')
    from scoring_material_launch import build_if_scoring
    argv = build_if_scoring(args.output, args.model_socket, command, args.read_only, args.method)
    if argv is None:
        argv = build_command(args.output, args.model_socket, command, args.read_only, args.method)
    Path(args.output, 'offline_launch.json').write_text(json.dumps({'command': argv}, indent=2)+'\n')
    raise SystemExit(subprocess.run(argv).returncode)


if __name__ == '__main__':
    main()
