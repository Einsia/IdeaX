"""Fresh tools-disabled Codex/Claude CLI sessions with explicit credentials.

The scientific prompts and parsers remain in each benchmark. No transport
fallback, score imputation, or lower-effort retry is performed here.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
import uuid

MODELS = {'astra': 'gpt-6-astra', 'opus': 'claude-opus-5-5'}
ROOT = Path(__file__).resolve().parents[2]


def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def credentials(judge):
    """Load a profile OR its paired environment values; never mix providers."""
    path = os.environ.get('IDEAX_GPT_PROFILE_FILE' if judge == 'astra' else 'IDEAX_OPUS_PROFILE_FILE')
    if path:
        profile = json.loads(Path(path).expanduser().read_text())
        if 'api_key_env_file' in profile:
            values = {}
            for line in Path(profile['api_key_env_file']).expanduser().read_text().splitlines():
                line = line.strip().removeprefix('export ')
                if not line or line.startswith('#') or '=' not in line: continue
                name, raw = line.split('=', 1)
                parts = shlex.split(raw, comments=True)
                if parts: values[name.strip()] = parts[0]
            key = values.get(profile['api_key_env_name'])
        else:
            key = profile.get('api_key') or profile.get('auth_token')
        base = profile.get('base_url')
    elif judge == 'astra':
        base = os.environ.get('OPENAI_BASE_URL', 'https://sbtunnel.xiaoaojianghu.fun/v1')
        key = os.environ.get('OPENAI_API_KEY')
    else:
        base = os.environ.get('ANTHROPIC_BASE_URL', 'https://sbtunnel.xiaoaojianghu.fun')
        key = os.environ.get('ANTHROPIC_AUTH_TOKEN') or os.environ.get('ANTHROPIC_API_KEY')
    if not isinstance(base, str) or not base.startswith('https://') or not isinstance(key, str) or not key.strip():
        raise ValueError('Configure an HTTPS endpoint and credential for '+judge)
    return base.rstrip('/'), key


def execute(command, body, env, attempt, timeout=3600):
    with (attempt/'stdout.log').open('wb') as out, (attempt/'stderr.log').open('wb') as err:
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=out, stderr=err,
                                cwd=attempt, env=env, start_new_session=True)
        save(attempt/'process.json', {'pid':proc.pid, 'started_epoch':time.time()})
        try:
            proc.communicate(body.encode(), timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL); proc.wait()
            raise RuntimeError('Native judge timed out; attempt was preserved')
    if proc.returncode:
        raise RuntimeError('Native judge failed; inspect this attempt stderr (exit '+str(proc.returncode)+')')
    return (attempt/'stdout.log').read_text()


def model_call(judge, prompt, packet, attempt):
    attempt = Path(attempt).resolve(); attempt.mkdir(parents=True, exist_ok=False)
    base, key = credentials(judge)
    model = MODELS[judge]
    body = '## Current item (JSON)\n'+json.dumps(packet, ensure_ascii=False)
    (attempt/'system_prompt.md').write_text(prompt)
    (attempt/'input.json').write_text(json.dumps(packet, ensure_ascii=False, indent=2))
    save(attempt/'binding.json', {'model':model,'effort':'xhigh','endpoint':base,
         'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'input_sha256':digest(packet),
         'transport':'portable-native-cli-v1'})
    scratch = Path(os.environ.get('IDEAX_SCRATCH', str(ROOT/'.scratch')))
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='judge-', dir=scratch) as private:
        env = {k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','HTTPS_PROXY','HTTP_PROXY','NO_PROXY')}
        env.update(HOME=private, CODEX_HOME=private, TMPDIR=private,
                   DISABLE_AUTOUPDATER='1', CLAUDE_CODE_DISABLE_AUTO_MEMORY='1',
                   CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1')
        if judge == 'astra':
            env['IDEAX_BENCH_GPT_KEY'] = key
            command = [os.environ.get('IDEAX_CODEX_RAW_BIN') or shutil.which('codex') or 'codex',
                'exec','--json','--skip-git-repo-check','--sandbox','read-only','--model',model,
                '--ignore-user-config','-c','model_reasoning_effort="xhigh"','-c','approval_policy="never"',
                '-c','model_provider="ideax_judge"','-c','model_providers.ideax_judge.name="IdeaX judge"',
                '-c','model_providers.ideax_judge.base_url='+json.dumps(base),
                '-c','model_providers.ideax_judge.wire_api="responses"',
                '-c','model_providers.ideax_judge.env_key="IDEAX_BENCH_GPT_KEY"',
                '-c','project_doc_max_bytes=0','-c','web_search="disabled"',
                '--enable','skip_host_skill_discovery']
            for feature in ('multi_agent','shell_tool','apps','plugins','skill_search','sleep_tool',
                            'view_image','workspace_dependencies','browser_use','computer_use','hooks'):
                command += ['--disable',feature]
            command += ['-']
            raw = execute(command, prompt+'\n\n'+body, env, attempt)
            events = [json.loads(line) for line in raw.splitlines() if line.strip()]
            starts = [e for e in events if e.get('type')=='thread.started']
            ends = [e for e in events if e.get('type')=='turn.completed']
            if len(starts)!=1 or len(ends)!=1 or any(e.get('type') in ('error','turn.failed') for e in events):
                raise ValueError('Expected one complete, fresh native judge turn')
            items = [e['item'] for e in events if e.get('type')=='item.completed']
            if any(i.get('type') not in ('agent_message','reasoning') for i in items):
                raise ValueError('Tools-disabled judge emitted a tool call')
            messages = [i['text'] for i in items if i.get('type')=='agent_message']
            if not messages: raise ValueError('No judge answer')
            text, session, usage = messages[-1], starts[0]['thread_id'], ends[0].get('usage',{})
        else:
            env.update(ANTHROPIC_BASE_URL=base, ANTHROPIC_AUTH_TOKEN=key,
                       CLAUDE_CODE_MAX_OUTPUT_TOKENS='64000', API_TIMEOUT_MS='3600000')
            session = str(uuid.uuid4())
            command = [os.environ.get('IDEAX_CLAUDE_RAW_BIN') or shutil.which('claude') or 'claude',
                '--bare','-p','--model',model,'--effort','xhigh','--output-format','json',
                '--tools','','--strict-mcp-config','--mcp-config','{"mcpServers":{}}',
                '--disable-slash-commands','--setting-sources','','--session-id',session,
                '--system-prompt',prompt]
            raw = execute(command, body, env, attempt)
            result = json.loads(raw)
            if result.get('is_error') or result.get('num_turns',1)!=1:
                raise ValueError('Opus judge did not complete one independent turn')
            text, usage = result['result'], result.get('usage',{})
    if 'frontier_llm' in text.lower(): raise ValueError('Retryable frontier_llm refusal')
    text = text.strip()
    if text.startswith('```') and text.endswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)[:-3].strip()
    value = json.loads(text)
    if not isinstance(value, dict): raise ValueError('Expected one JSON object')
    save(attempt/'parsed.json', value)
    receipt = {'judge':judge,'model':model,'effort':'xhigh','native_session':session,'usage':usage,
               'parsed_sha256':hashlib.sha256((attempt/'parsed.json').read_bytes()).hexdigest()}
    save(attempt/'call_receipt.json', receipt)
    return value, receipt
