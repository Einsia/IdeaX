"""Launch a fresh isolated recording fixture; no real model socket is mounted."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess

D = Path(__file__).resolve().parent
P = D.parents[1]
B = P.parents[1]
NODE = B / 'state/node-v22.16.0-linux-x64/bin/node'
CODEX_BIN = D / 'codex_runtime/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin'


def build_command(run, run_id, admission_id, task_source, mode="recording"):
    run = Path(run).resolve()
    run.mkdir(parents=True, exist_ok=False)
    (run / 'results').mkdir()
    shutil.copytree(Path(task_source), run / 'results/task')
    shutil.copytree(Path(task_source), run / 'task_source')
    (run / 'home/.codex').mkdir(parents=True)
    config = '''model = "gpt-6-astra"
model_provider = "shared250"
model_reasoning_effort = "xhigh"
web_search = "disabled"
cli_auth_credentials_store = "file"
[agents]
max_threads = 1
[features]
shell_snapshot = false
shell_tool = false
unified_exec = false
code_mode = false
code_mode_host = true
multi_agent = false
apps = false
browser_use = false
computer_use = false
image_generation = false
[model_providers.shared250]
name = "Shared fixed Astra model-only bridge"
base_url = "http://127.0.0.1:8765/v1"
wire_api = "responses"
env_key = "OPENAI_API_KEY"
requires_openai_auth = false
supports_websockets = false
[mcp_servers.native_files]
command = "/usr/bin/python3"
args = ["''' + str(D / 'file_tools.py') + '''"]
startup_timeout_sec = 20
tool_timeout_sec = 60
env_vars = ["SAKANA_RESULTS"]
'''
    (run / 'home/.codex/config.toml').write_text(config)
    command = ['/usr/bin/bwrap', '--unshare-user', '--unshare-net', '--unshare-pid', '--unshare-ipc', '--unshare-uts',
        '--cap-drop', 'ALL', '--new-session', '--die-with-parent', '--clearenv']
    for path in ['/usr', '/bin', '/sbin', '/lib', '/lib64', '/etc/ssl', '/etc/passwd', '/etc/group', '/etc/hosts', '/etc/nsswitch.conf']:
        if Path(path).exists(): command += ['--ro-bind', path, path]
    command += ['--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--tmpfs', '/run']
    mounts = [D / 'official_source', D / 'headless_source', D / 'codex_runtime', D / 'runtime_venv', Path(task_source),
        D / 'file_tools.py', D / 'headless_capture.py', D / 'probe_inside.py', D / 'exec_locked.py', D / 'transport_policy.py', P / 'runtime', NODE.parent.parent,
        Path('/home/liuhanzuo/.local/share/uv/python')]
    for path in mounts:
        for dest in dict.fromkeys([str(path), str(path.resolve())]): command += ['--ro-bind', str(path.resolve()), dest]
    command += ['--bind', str(run), str(run), '--bind', str(run / 'home'), '/isolated_home',
        '--ro-bind', str(run / 'results/task'), str(run / 'results/task'),
        '--ro-bind', str(run / 'task_source'), str(run / 'task_source'),
        '--ro-bind', str(run / 'home/.codex/config.toml'), str(run / 'home/.codex/config.toml'),
        '--ro-bind', str(run / 'home/.codex/config.toml'), '/isolated_home/.codex/config.toml']
    if mode == 'controlled_real':
        command += ['--ro-bind', '/tmp/insightpro-offline-model-20261117.sock', '/model.sock']
    elif mode != 'recording':
        raise ValueError('Unsupported transport mode')
    env = {'PATH': str(CODEX_BIN) + ':' + str(NODE.parent) + ':/usr/bin:/bin', 'HOME': '/isolated_home', 'TMPDIR': '/tmp',
        'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1',
        'WRAPPER_PYTHON': str(D / 'runtime_venv/bin/python'), 'HEADLESS_BIN': str(D / 'headless_capture.py'),
        'SAKANA_RUN': str(run), 'SAKANA_RESULTS': str(run / 'results'), 'SAKANA_NODE': str(NODE),
        'SAKANA_PHASE_RUNTIME': str(P / 'runtime'), 'SAKANA_TRANSPORT_MODE': mode,
        'SAKANA_RUN_ID': run_id, 'SAKANA_ADMISSION_ID': admission_id,
        'OPENAI_API_KEY': 'offline-recording-fixture', 'OPENAI_BASE_URL': 'http://127.0.0.1:8765/v1',
        'UV_OFFLINE': '1', 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'PIP_NO_INDEX': '1', 'NO_PROXY': '*'}
    for key, value in env.items(): command += ['--setenv', key, value]
    command += ['--chdir', str(run), '--', '/usr/bin/python3', str(D / 'probe_inside.py')]
    (run / 'launcher.json').write_text(json.dumps({'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'command': command, 'paid_model_calls_allowed': mode == 'controlled_real', 'shared_model_socket_mounted': mode == 'controlled_real',
        'initial_history_empty': sorted(p.name for p in (run / 'results').iterdir()) == ['task'], 'source_original_prompt': str(D / 'official_source/src/prompts/idea.md')}, indent=2) + '\n')
    return command
