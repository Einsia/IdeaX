"""Read-only replay of final Interesting scores against original CLI responses."""
import argparse
import json
from pathlib import Path

from . import focused60_coi as S


def require(condition, message):
    if not condition:
        raise ValueError(message)


def native_response(attempt, judge, prompt, payload, cfg):
    """Check locally observable model request and native completion evidence."""
    response = S.read(attempt / 'response.json')
    if judge == 'astra':
        command = S.read(attempt / 'codex_command.json')
        argv = command['command']
        require(argv[argv.index('--model') + 1] == cfg['models'][judge], 'Astra model mismatch')
        overrides = [argv[i + 1] for i, value in enumerate(argv[:-1]) if value == '-c']
        require('model_reasoning_effort=' + json.dumps(cfg['effort']) in overrides, 'Astra effort mismatch')
        full_prompt = prompt + '\n\n## Current item (JSON)\n' + json.dumps(payload, ensure_ascii=False)
        require((attempt / 'codex_prompt.md').read_text() == full_prompt, 'Native prompt mismatch')
        require(command['prompt_sha256'] == S.sha(full_prompt.encode()), 'Native prompt hash mismatch')
        events = [json.loads(line) for line in (attempt / 'codex.stdout.jsonl').read_text().splitlines() if line.strip()]
        require(not any(e.get('type') == 'turn.failed' for e in events), 'Native failed turn')
        completions = [e for e in events if e.get('type') == 'turn.completed']
        threads = [e['thread_id'] for e in events if e.get('type') == 'thread.started']
        require(len(completions) == 1 and len(threads) == 1, 'Native completion/session count')
        items = [e['item'] for e in events if e.get('type') == 'item.completed']
        require(all(i['type'] in {'agent_message', 'reasoning'} for i in items), 'Judge used tools')
        messages = [i['text'] for i in items if i['type'] == 'agent_message']
        require(bool(messages), 'Missing native final text')
        text = messages[-1]
        require(response['status'] == 'completed' and response['id'] == threads[0], 'Normalized session mismatch')
        require(response['output'][0]['content'][0]['text'] == text, 'Normalized text mismatch')
        require(response['codex_usage'] == completions[0]['usage'], 'Native usage mismatch')
        session = threads[0]
    else:
        command = S.read(attempt / 'command.json')
        argv = command['command']
        require(argv[argv.index('--model') + 1] == cfg['models'][judge], 'Opus model mismatch')
        require(argv[argv.index('--effort') + 1] == cfg['effort'], 'Opus effort mismatch')
        require(argv[argv.index('--tools') + 1] == '' and '--strict-mcp-config' in argv, 'Opus tools not disabled')
        require(argv[argv.index('--system-prompt') + 1] == prompt, 'Opus system prompt mismatch')
        body = '## Current item (JSON)\n' + json.dumps(payload, ensure_ascii=False)
        require(command['system_prompt_sha256'] == S.sha(prompt.encode()), 'System prompt hash mismatch')
        require(command['user_prompt_sha256'] == S.sha(body.encode()), 'User prompt hash mismatch')
        require(S.read(attempt / 'stdout.json') == response, 'Native response mismatch')
        require(not response.get('is_error') and response.get('num_turns', 1) == 1, 'Unsuccessful Opus turn')
        text = response['result']
        session = response.get('session_id')
    require(bool(session), 'Missing native session identity')
    require((attempt / 'raw.txt').read_text() == text, 'Raw response mismatch')
    return S.strip(text), session


def audit(out):
    S.verify(out)
    cfg = S.read(out / 'config.json')
    cards = {c['card_id']: c for c in S.read(out / 'cards.json')}
    require(len(cards) == 60, 'Expected 60 distinct cards')
    stages = S.read(out / 'stages.json')
    require(stages == S.stages(list(cards)), 'Unexpected stage schedule')
    prompt = (out / 'prompt.txt').read_text()
    sessions = set()
    result = {'complete': True, 'judges': {}, 'identity_limit': 'CLI requested model identity; upstream implementation not independently verified'}
    for judge in cfg['models']:
        state = S.initial_state()
        completed = 0
        directory = out / 'runs' / judge
        for stage in stages:
            dest = directory / stage['stage_id']
            if not (dest / 'accepted.json').exists():
                break
            accepted = S.read(dest / 'accepted.json')
            require(Path(accepted['attempt']).name == accepted['attempt'], 'Invalid attempt path')
            attempt = dest / accepted['attempt']
            record = S.read(attempt / 'record.json')
            payload = S.payload_for(stage, cards, state)
            digest = S.sha(S.canonical(payload))
            require(record['state'] == 'valid', 'Attempt is not valid')
            require(record['model'] == cfg['models'][judge] and record['effort'] == cfg['effort'], 'Attempt model/effort mismatch')
            require(accepted['input_sha256'] == record['input_sha256'] == digest, 'Replay context mismatch')
            require(S.read(attempt / 'input.json') == payload, 'Stored payload mismatch')
            obj, session = native_response(attempt, judge, prompt, payload, cfg)
            require(session not in sessions, 'Reused session across stages or judges')
            sessions.add(session)
            require(obj == accepted['result'], 'Accepted result differs from native reply')
            S.validate_result(obj, stage, cards, state)
            state = S.advance(state, obj, stage)
            completed += 1
        complete = completed == len(stages)
        if complete:
            require(set(state['ledger']) == set(cards), 'Missing final cards')
            require(S.read(directory / 'state.json') == state, 'Final ledger/history mismatch')
            require(S.read(directory / 'status.json')['state'] == 'complete', 'Lane not terminal')
            for ident, assessment in state['ledger'].items():
                expected = {'final': assessment, 'history': [h for h in state['history'] if h['card_id'] == ident]}
                require(S.read(out / 'reviews' / judge / f'{ident}.json') == expected, 'Published review mismatch')
        result['judges'][judge] = {'complete': complete, 'verified_stages': completed,
                                    'verified_scores': len(state['ledger']),
                                    'revisions': len(state['history']) - len(state['ledger'])}
        result['complete'] &= complete
    result['distinct_native_sessions'] = len(sessions)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=S.DEFAULT_OUT)
    args = parser.parse_args()
    print(json.dumps(audit(args.out.resolve()), ensure_ascii=False, indent=2))
