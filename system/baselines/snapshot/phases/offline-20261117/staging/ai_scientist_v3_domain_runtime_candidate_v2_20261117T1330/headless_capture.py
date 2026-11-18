#!/usr/bin/python3
"""Transparent Headless runner; snapshot native files before idea.sh rewrites them."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

D = Path(__file__).resolve().parent
RUN = Path(os.environ['SAKANA_RUN'])
CAPTURE = RUN / 'pre_normalization'


def main():
    CAPTURE.mkdir(exist_ok=False)
    names = ['idea_bundle.json', 'target_rubrics.json']
    output = Path(os.environ['IDEA_OUTPUT_DIR'])
    before = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'argv': sys.argv[1:],
              'output_files_absent': all(not (output / name).exists() for name in names),
              'cycle_index': os.environ['CYCLE_INDEX'], 'cwd': os.getcwd()}
    (CAPTURE / 'before.json').write_text(json.dumps(before, indent=2) + '\n')
    instructions = [output / 'idea_prompt.md', *sorted((output / '.codex/skills').rglob('*'))]
    instructions = [p for p in instructions if p.is_file()]
    before['instruction_bindings'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in instructions}
    (CAPTURE / 'before.json').write_text(json.dumps(before, indent=2) + '\n')
    command = ['/usr/bin/bwrap', '--ro-bind', '/', '/', '--bind', str(RUN / 'results'), str(RUN / 'results'),
        '--bind', str(RUN / 'home'), str(RUN / 'home'),
        '--bind', str(RUN / 'home'), '/isolated_home', '--tmpfs', '/tmp',
        '--ro-bind', str(RUN / 'results/task'), str(RUN / 'results/task'),
        '--ro-bind', str(output / 'idea_prompt.md'), str(output / 'idea_prompt.md'),
        '--ro-bind', str(output / '.codex/skills'), str(output / '.codex/skills'),
        '--ro-bind', str(RUN / 'home/.codex/config.toml'), str(RUN / 'home/.codex/config.toml'),
        '--ro-bind', str(RUN / 'home/.codex/config.toml'), '/isolated_home/.codex/config.toml',
        '--cap-drop', 'ALL', '--die-with-parent', '--', '/usr/bin/python3', str(D / 'exec_locked.py'),
        os.environ['SAKANA_NODE'], str(D / 'headless_source/dist/cli.js'), *sys.argv[1:]]
    with (RUN / 'agent_runtime_boundary.json').open('wb') as boundary:
        environment = {**os.environ, 'SAKANA_BOUNDARY_FD': str(boundary.fileno())}
        result = subprocess.run(command, env=environment, pass_fds=(boundary.fileno(),))
    copied = {}
    for name in names:
        path = output / name
        if path.is_file():
            data = path.read_bytes(); (CAPTURE / name).write_bytes(data)
            copied[name] = {'original': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    memory = {}
    for key in ('GLOBAL_MEMORY_MD_FILE', 'GLOBAL_MEMORY_JSONL_FILE', 'CONCLUSIONS_MD_FILE', 'CONCLUSIONS_HISTORY_FILE'):
        path = Path(os.environ[key])
        if path.is_file():
            data = path.read_bytes(); (CAPTURE / path.name).write_bytes(data)
            memory[key] = {'original': str(path), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    after = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'headless_exit_code': result.returncode,
             'capture_stage': 'after real Headless returned, before original idea.sh postprocess',
             'output_copies': copied, 'memory_copies': memory, 'external_repair': False,
             'instructions_unchanged': all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p,h in before['instruction_bindings'].items())}
    (CAPTURE / 'capture_receipt.json').write_text(json.dumps(after, indent=2) + '\n')
    return result.returncode


if __name__ == '__main__': raise SystemExit(main())
