"""Audit transport/turn evidence without treating HTTP 200 as model completion."""
from collections import Counter
import json
import re
from pathlib import Path


def events(path):
    if not path.exists():
        return
    with path.open(errors='replace') as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def audit(run):
    run = Path(run)
    http, gate_errors, terminal_errors, recoveries = Counter(), [], [], []
    atomic, delivery_errors, request_hashes, client_disconnects = Counter(), [], {}, []
    for row in events(run / 'gate/egress.log'):
        if row.get('upstream'):
            http[str(row['upstream'])] += 1
        if row.get('error'):
            gate_errors.append({k: row.get(k) for k in ('agent', 'target', 'error')})
        if str(row.get('event', '')).startswith('atomic_'):
            atomic[row['event']] += 1
            group = row.get('request_group')
            if group and row.get('request_sha256'):
                previous = request_hashes.setdefault(group, row['request_sha256'])
                if previous != row['request_sha256']:
                    delivery_errors.append({'request_group': group, 'reason': 'request body changed during retry'})
            if (row['event'] in ('atomic_output_withheld', 'atomic_attempt_rejected', 'atomic_exhausted')
                    and row.get('forwarded_model_bytes') != 0):
                delivery_errors.append({'request_group': group, 'reason': 'unverified output reached the client'})
            if row['event'] == 'atomic_downstream_closed':
                # A gate retry keeps the same client stream open. A closed client
                # stream is a distinct failure even when model bytes were withheld.
                client_disconnects.append({k: row.get(k) for k in ('t', 'agent', 'request_group', 'after_commit')})
                if row.get('after_commit'):
                    delivery_errors.append({'request_group': group, 'reason': 'downstream failed after delivery began'})
    library_tool_errors = []
    config = run / 'work/library_api.json'
    library_base = json.loads(config.read_text()).get('base_url') if config.exists() else None
    library_failure = (re.compile(r'litgraph (?:HTTP (?:429|5\d\d)|unavailable): '
                                  + re.escape(library_base.rstrip('/')) + r'/[^\s"<>]+')
                       if library_base else None)
    sessions, active, completed, aborted, failed = 0, 0, 0, 0, 0
    completed_by_agent, cli_completed_by_agent = Counter(), Counter()
    for path in run.glob('homes/*/.codex/sessions/**/*.jsonl'):
        sessions += 1
        agent = path.relative_to(run / 'homes').parts[0]
        pending = False
        errors = []
        for row in events(path):
            payload = row.get('payload') or {}
            t = payload.get('type')
            if (library_failure and row.get('type') == 'response_item'
                    and t in ('function_call_output', 'custom_tool_call_output')):
                output = payload.get('output', '')
                if isinstance(output, list):
                    output = '\n'.join(item.get('text', '') for item in output if isinstance(item, dict))
                if isinstance(output, str):
                    for message in sorted(set(library_failure.findall(output))):
                        library_tool_errors.append({'agent': agent, 'session': path.stem,
                            'at': row.get('timestamp'), 'call_id': payload.get('call_id'), 'message': message[:600]})
            if row.get('type') != 'event_msg':
                continue
            if t == 'task_started':
                pending = True
            elif t in ('task_complete', 'task_completed'):
                # Native Codex records terminal failures as task_complete too.
                # The event name means the turn ended, not that it succeeded.
                if payload.get('error'):
                    failed += 1
                    pending = False
                    errors.append({'session': path.stem, 'type': t,
                                   'message': str(payload['error'])[:400]})
                    continue
                completed += 1
                completed_by_agent[agent] += 1
                pending = False
                recoveries.extend(errors)
                errors = []
            elif t in ('turn_aborted', 'task_aborted'):
                aborted += 1
                errors.append({'session': path.stem, 'type': t})
            elif t in ('error', 'turn_failed', 'task_failed'):
                errors.append({'session': path.stem, 'type': t,
                               'message': str(payload.get('message', payload.get('error', '')))[:400]})
        terminal_errors.extend(errors)
        active += int(pending)
    cli_errors, cli_failed, cli_completed, cli_streams = [], 0, 0, 0
    paths = list(run.glob('evidence/codex_calls/*.events.jsonl'))
    session_file = run / 'session.json'
    if session_file.exists():
        session = json.loads(session_file.read_text())
        paths.append(run / session.get('latest_events', 'codex.events.jsonl'))
    for path in paths:
        if not path.exists():
            continue
        cli_streams += 1
        agent = (path.name.rsplit('-', 1)[0] if path.parent.name == 'codex_calls' else
                 next(iter(completed_by_agent)) if len(completed_by_agent) == 1 else '<unmapped>')
        for row in events(path):
            if row.get('type') == 'error':
                cli_errors.append({'file': str(path.relative_to(run)),
                                   'message': str(row.get('message', row.get('error', '')))[:400]})
            elif row.get('type') == 'turn.failed':
                cli_failed += 1
            elif row.get('type') == 'turn.completed':
                cli_completed += 1
                cli_completed_by_agent[agent] += 1
    return {'sessions': sessions, 'completed_turns': completed, 'open_turns': active,
            'aborted_turns': aborted, 'failed_native_turns': failed, 'terminal_errors': terminal_errors,
            'recovered_error_events': recoveries, 'gate_http_statuses': dict(http),
            'gate_errors': gate_errors,
            'atomic_transport_events': dict(atomic), 'atomic_delivery_errors': delivery_errors,
            'client_stream_disconnects': client_disconnects,
            'library_tool_errors': library_tool_errors,
            'cli_event_streams': cli_streams, 'cli_error_events': cli_errors,
            'cli_failed_turns': cli_failed, 'cli_completed_turns': cli_completed,
            'native_completed_by_agent': dict(completed_by_agent),
            'cli_completed_by_agent': dict(cli_completed_by_agent),
            'transport_evidence_complete': bool(completed) and cli_completed_by_agent == completed_by_agent and cli_streams >= completed,
            'unobserved_completed_turns': sum(max(0, n - cli_completed_by_agent[a]) for a, n in completed_by_agent.items()),
            'cli_transport_clean': not cli_errors and not cli_failed if cli_streams else None,
            'clean_terminal_state': bool(sessions) and not terminal_errors and not active and not aborted,
            'interpretation': 'HTTP 200 alone is insufficient; complete turn and pipeline gates are checked separately'}
