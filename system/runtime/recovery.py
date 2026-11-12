"""Bounded native-agent recovery, with immutable attempt evidence and phase identity."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import threading
import time
import uuid

VERSION = 'multi-agent-recovery-v1'
DELAYS = (30, 90, 180)
TOTAL_SECONDS = 14400
LOCK = threading.RLock()
AGENT_LOCKS = {}
RESUME_NOTE = ('上次调用因基础设施故障中断。继续当前 agent 的同一阶段、同一会话任务。'
               '先检查自己已经写出的卡片、评审、消息和文件，保留完整产物，只补齐未完成部分；'
               '不要重复提交或重做已完成研究，不读取其他 agent 的独立生成过程。'
               '不得自行推进阶段或增加 debate 轮数。原任务如下：\n')


def now(): return datetime.now(timezone.utc).isoformat()
def read(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(p, obj):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.' + uuid.uuid4().hex + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n'); tmp.replace(p)


def phase_of(run):
    p = Path(run) / 'work/research_phase.json'
    return read(p).get('phase', 'unknown') if p.exists() else 'unknown'


def retryable(result):
    if result.get('ok'): return False
    text = str(result.get('error') or result.get('tail') or '').lower()
    if any(s in text for s in ('invalid_api_key', 'authentication_error', 'insufficient_quota',
            'context_length_exceeded', 'invalid_request_error', 'unsupported_parameter',
            'unauthorized', 'forbidden', 'permission denied', 'no space left')):
        return False
    codes = re.findall(r'(?:http[_ :]+|status[ :]+)(\d{3})\b', text)
    if codes: return all(int(c) in (408, 429) or 500 <= int(c) <= 599 for c in codes)
    return any(s in text for s in ('stream disconnected', 'stream closed before', 'connection reset',
        'connection lost', 'connectionerror', 'incompletereaderror', 'missing_response_completed',
        'truncated_chunk', 'upstream_error', 'server_error', 'atomic_upstream_incomplete',
        'timeout after', 'timeouterror', 'retry_time_budget_exhausted'))


def block(run, agent, reason, call_id):
    path = Path(run) / 'recovery_blocked.json'
    with LOCK:
        data = read(path) if path.exists() else {'version': VERSION, 'at': now(), 'blockers': []}
        data['blockers'].append({'agent': agent, 'reason': reason, 'call_id': call_id, 'at': now()})
        save(path, data)


def evidence(run, result):
    path = result.get('evidence_events')
    if not path: return {}
    p = Path(path).resolve(); root = Path(run).resolve()
    if not p.is_relative_to(root / 'evidence/codex_calls'): raise ValueError('Evidence outside this run')
    files = [p, p.with_name(p.name.replace('.events.jsonl', '.stderr.log')),
             p.with_name(p.name.replace('.events.jsonl', '.transport.json'))]
    return {str(f.relative_to(root)): sha(f) for f in files if f.is_file()}


def delivery_uncertain(run, agent, offset):
    path = Path(run) / 'gate/egress.log'
    if not path.exists(): return False
    with path.open() as stream:
        stream.seek(offset)
        for line in stream:
            try: row = json.loads(line)
            except ValueError: continue
            if (row.get('agent') == agent and row.get('event') == 'atomic_downstream_closed'
                    and row.get('after_commit')):
                return True
    return False


def recover_call(native, run, tag, agent, prompt, *, thread_id=None, resume=False,
                 model=None, effort='high', web=False, timeout=3600,
                 delays=DELAYS, sleep=time.sleep, clock=time.monotonic):
    run = Path(run)
    with LOCK: guard = AGENT_LOCKS.setdefault((str(run.resolve()), agent), threading.Lock())
    if not guard.acquire(blocking=False): raise RuntimeError('Concurrent calls for one agent are forbidden')
    cid = uuid.uuid4().hex; path = run / 'multi_recovery' / (cid + '.json')
    phase = phase_of(run)
    record = {'version': VERSION, 'id': cid, 'agent': agent, 'phase': phase, 'model': model,
              'effort': effort, 'web': web, 'created': now(), 'status': 'running',
              'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(), 'attempts': [],
              'max_attempts': len(delays) + 1, 'retry_delays': list(delays)}
    deadline = clock() + min(timeout, TOTAL_SECONDS)
    native_id = thread_id; last = {'ok': False, 'error': 'No attempt', 'cost': 0, 'session': native_id}
    try:
        save(path, record)
        for number in range(1, len(delays) + 2):
            if (run / 'recovery_blocked.json').exists():
                record['status'] = 'blocked'; record['reason'] = 'This run has an unresolved agent failure'
                break
            if phase_of(run) != phase:
                raise RuntimeError('Research phase changed during an agent retry')
            remaining = int(deadline - clock())
            if remaining <= 0:
                record.update(status='exhausted', reason='Agent recovery time budget exhausted')
                block(run, agent, record['reason'], cid); break
            actual = prompt if number == 1 or not native_id else RESUME_NOTE + prompt
            record.update(status='running', current_attempt=number)
            save(path, record)
            started = now()
            gate_log = run / 'gate/egress.log'
            gate_offset = gate_log.stat().st_size if gate_log.exists() else 0
            # Native call has returned and its subprocess exited before any retry starts.
            result = native(str(run), tag, agent, actual, thread_id=native_id, resume=bool(native_id),
                            model=model, effort=effort, web=web, timeout=remaining)
            last = dict(result)
            returned_id = result.get('session')
            if native_id and returned_id != native_id:
                raise RuntimeError('Retry changed native session identity')
            if returned_id: native_id = returned_id
            proofs = evidence(run, result)
            item = {'number': number, 'started': started, 'ended': now(), 'session': native_id,
                    'phase': phase, 'retryable': retryable(result), 'result': dict(result),
                    'evidence_sha256': proofs}
            record['attempts'].append(item)
            if delivery_uncertain(run, agent, gate_offset):
                raise RuntimeError('Partial delivery may have reached the client; automatic replay forbidden')
            if result.get('ok'):
                if not native_id or not proofs or not result.get('transport', {}).get('clean'):
                    raise RuntimeError('Successful retry lacks native identity or clean raw evidence')
                record.update(status='recovered' if number > 1 else 'completed', finished=now())
                save(path, record)
                result = dict(result, recovery_call_id=cid, recovery_attempts=number,
                              recovered=number > 1,
                              cost=sum(a['result'].get('cost') or 0 for a in record['attempts']))
                return result
            if not item['retryable'] or number > len(delays):
                record.update(status='exhausted', reason=result.get('error') or result.get('tail'))
                block(run, agent, record['reason'], cid); break
            # Without a known native ID, retry only when no session was ever created.
            if not native_id and list((run / 'homes' / agent / '.codex/sessions').glob('**/*.jsonl')):
                raise RuntimeError('Interrupted native session exists without an unambiguous ID')
            delay = delays[number - 1]
            if delay >= deadline - clock():
                record.update(status='exhausted', reason='Agent recovery time budget exhausted')
                block(run, agent, record['reason'], cid); break
            record.update(status='retry_wait', retry_after_seconds=delay)
            save(path, record)
            print(f'{agent}: retry {number}/{len(delays)} in {delay}s; same session and {phase} phase', flush=True)
            sleep(delay)
        record['finished'] = now(); save(path, record)
        return dict(last, ok=False, cost=sum(a['result'].get('cost') or 0 for a in record['attempts']),
                    error=record.get('reason') or last.get('error'), recovery_call_id=cid,
                    recovery_attempts=len(record['attempts']))
    except Exception as exc:
        record.update(status='blocked', reason=f'{type(exc).__name__}: {exc}', finished=now())
        save(path, record); block(run, agent, record['reason'], cid)
        raise
    finally:
        guard.release()


def audit_recovery(run, runtime):
    """Never waive an unaccounted error, altered evidence, phase violation or partial delivery."""
    from isolate import codex_transport_events
    run = Path(run); errors = []; covered = set(); failed_streams = set(); recovered = 0
    for p in sorted((run / 'multi_recovery').glob('*.json')):
        record = read(p); attempts = record['attempts']
        if record.get('version') != VERSION or record['status'] not in ('completed', 'recovered'):
            errors.append(f'Unresolved recovery: {p.name}'); continue
        if not attempts or len(attempts) > record['max_attempts']:
            errors.append(f'Invalid retry budget: {p.name}'); continue
        identities = {a['session'] for a in attempts if a['session']}
        if len(identities) != 1: errors.append(f'Native session changed: {p.name}')
        for i, a in enumerate(attempts):
            if a['phase'] != record['phase']: errors.append(f'Phase changed: {p.name}')
            proofs = a['evidence_sha256']
            eventfiles = [name for name in proofs if name.endswith('.events.jsonl')]
            if len(eventfiles) != 1: errors.append(f'Missing attempt evidence: {p.name}'); continue
            for name, expected in proofs.items():
                path = (run / name).resolve()
                if not path.is_relative_to(run.resolve()) or not path.is_file() or sha(path) != expected:
                    errors.append(f'Changed attempt evidence: {name}')
            name = eventfiles[0]
            if name in covered: errors.append(f'Reused attempt evidence: {name}')
            covered.add(name)
            if not (run / name).exists(): continue
            transport = codex_transport_events((run / name).read_text())
            if i == len(attempts) - 1:
                if not a['result'].get('ok') or not transport['clean'] or not transport['completed_turns']:
                    errors.append(f'Recovery did not finish normally: {p.name}')
            else:
                if a['result'].get('ok') or not retryable(a['result']):
                    errors.append(f'Ineligible failed attempt: {p.name}')
                failed_streams.add(name)
        recovered += len(attempts) > 1
    actual = {str(p.relative_to(run)) for p in (run / 'evidence/codex_calls').glob('*.events.jsonl')}
    if not covered or actual != covered: errors.append('Untracked or missing native invocation evidence')
    if (run / 'recovery_blocked.json').exists(): errors.append('Run has an unresolved recovery blocker')
    if not runtime['clean_terminal_state']: errors.append('Native session did not finish normally')
    if not runtime['transport_evidence_complete']: errors.append('Incomplete raw CLI/native completion evidence')
    for error in runtime['cli_error_events']:
        if error['file'] not in failed_streams: errors.append('CLI error outside a recovered attempt')
    failed_count = 0
    for name in failed_streams:
        failed_count += codex_transport_events((run / name).read_text())['failed_turns']
    if failed_count != runtime['cli_failed_turns']: errors.append('Unaccounted failed native turn')
    if runtime['atomic_delivery_errors']: errors.append('Unverified/partial delivery or changed request input')
    if runtime['client_stream_disconnects']: errors.append('Client disconnect requires explicit inspection')
    if runtime['library_tool_errors']: errors.append('Unresolved LitGraph tool failures')
    return {'ok': not errors, 'errors': errors, 'recovered_calls': recovered,
            'tracked_attempts': len(covered), 'historical_failures_retained': len(failed_streams)}


def install(isolate):
    original = isolate.run_codex
    def run_codex(run, tag, agent, prompt, **kwargs):
        return recover_call(original, run, tag, agent, prompt, **kwargs)
    isolate.run_codex = run_codex


def admission_blockers(jobs):
    """A retrying run owns its slots; a terminal failure latches the scheduler shut."""
    blockers = []
    for job in jobs:
        if job['status'] in ('blocked', 'needs_review', 'stopped_by_user', 'paused_by_user'):
            blockers.append({'job': job['id'], 'reason': job['status'], 'terminal': True})
        if job['status'] not in ('running', 'blocked'): continue
        run = Path(job['run'])
        if (run / 'recovery_blocked.json').exists():
            blockers.append({'job': job['id'], 'reason': 'agent_recovery_exhausted', 'terminal': True})
        for p in (run / 'multi_recovery').glob('*.json'):
            r = read(p)
            if r['status'] == 'retry_wait' or (r['status'] == 'running' and len(r['attempts']) > 0):
                blockers.append({'job': job['id'], 'reason': 'agent_retrying', 'terminal': False})
    return blockers
