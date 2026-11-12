#!/usr/bin/env python3
"""Select a complete IdeaX condition and invoke its native runtime."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
CONDITIONS = ('single-full', 'single-api', 'light-multi-full', 'light-multi-api')


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in CONDITIONS:
        print('Usage: python system/run.py {' + ','.join(CONDITIONS) + '} <action> [options]')
        print('Actions: check, prepare, run, status, export, prepare-review, blueprint')
        return 0 if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help') else 2
    env = os.environ.copy()
    env['IDEAX_CURRENT_SYSTEM'] = str(ROOT/'system'/sys.argv[1])
    env.setdefault('IDEAX_CODEX_RAW_BIN', shutil.which('codex') or 'codex')
    env.setdefault('LITGRAPH_PY_PREFIX', sys.base_prefix)
    env.setdefault('IDEAX_SCRATCH', str(ROOT/'.scratch'))
    if env.get('IDEAX_GPT_PROFILE_FILE'):
        env['LITGRAPH_CODEX_ENV_FILE'] = env['IDEAX_GPT_PROFILE_FILE']
    Path(env['IDEAX_SCRATCH']).mkdir(parents=True, exist_ok=True)
    args=sys.argv[2:]
    entry='cli.py'
    if args and args[0]=='blueprint':entry='blueprint_cli.py';args=args[1:]
    return subprocess.call([sys.executable, '-B', str(ROOT/'system/runtime'/entry), *args], env=env)


if __name__ == '__main__':
    raise SystemExit(main())
