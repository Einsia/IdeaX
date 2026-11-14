#!/usr/bin/env python3
"""Prepare a demo brief with the released single-agent runtime; --run opts into model calls."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'ideax.research-brief.v1'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def validate_request(value):
    if not isinstance(value, dict) or value.get('schema') != SCHEMA:
        raise ValueError('Expected an ideax.research-brief.v1 request from the demo.')
    allowed = {'schema', 'domain', 'access', 'question', 'critique', 'reference_case'}
    if set(value) - allowed:
        raise ValueError('Unknown request fields: ' + ', '.join(sorted(set(value) - allowed)))
    domains = {d['id'] for d in read(ROOT / 'data/domains.json')['domains']}
    if not isinstance(value.get('domain'), str) or value['domain'] not in domains:
        raise ValueError('Choose one of the 38 supported domains.')
    if value.get('access') not in ('api', 'full'):
        raise ValueError('Access must be api or full.')
    clean = {k: value[k] for k in ('schema', 'domain', 'access')}
    for key in ('question', 'critique'):
        text = value.get(key, '')
        if not isinstance(text, str) or len(text) > 4000 or '\x00' in text:
            raise ValueError(key + ' must be text of at most 4,000 characters.')
        clean[key] = text.strip()
    if 'reference_case' in value:
        case = value['reference_case']
        required = {'id', 'title', 'question', 'mechanism', 'previous_work_check',
                    'remaining_contribution', 'source_url', 'process_url', 'source_sha256'}
        if not isinstance(case, dict) or set(case) != required:
            raise ValueError('Reference case has an unexpected shape.')
        if any(not isinstance(v, str) or len(v) > 5000 or '\x00' in v for v in case.values()):
            raise ValueError('Reference-case fields must be bounded text.')
        stories = {s['id']: s for s in read(ROOT / 'demo/stories.json')}
        if case['id'] not in stories:
            raise ValueError('Unknown recorded reference case.')
        folder = ROOT / 'case_studies/model_efficiency' / stories[case['id']]['folder']
        if case['source_sha256'] != digest(folder / 'PROPOSAL.md'):
            raise ValueError('Reference proposal differs from this checkout; refresh the demo or update the checkout.')
        clean['reference_case'] = case
    return clean


def request_text(request):
    text = '\n\n## 用户研究简报（本次自定义任务）\n'
    text += '研究问题：' + (request['question'] or '围绕所选领域自主探索。') + '\n'
    text += '用户的 critique / 约束：' + (request['critique'] or '未指定额外约束。') + '\n'
    if request.get('reference_case'):
        text += '\n用户明确提供的起点案例（尚未验证，不得当作新检索结果；请实质改进或提出独立候选，并重新核查前作）：\n'
        text += json.dumps(request['reference_case'], ensure_ascii=False, indent=2) + '\n'
    text += ('\n仍须交付五个相互有实质区别的完整 idea。区分来源事实、用户提供的观点和新假设，'
             '不要只重述起点案例。记录用户反馈如何影响选题或机制。'
             '本次为自定义探索，不是原论文 benchmark 的复现。\n')
    return text


def runtime_command(condition, *args):
    return [sys.executable, str(ROOT / 'system/run.py'), condition, *map(str, args)]


def prepare(request, output):
    """Add explicit user material only to a fresh run, before its input hashes freeze."""
    condition = 'single-' + request['access']
    if output.exists():
        receipt = output / 'demo_request.json'
        if not receipt.is_file() or read(receipt) != request:
            raise ValueError('This output already belongs to a different request. Use a new --out directory.')
        manifest = read(output / 'manifest.json')
        if manifest.get('demo_customization', {}).get('request_sha256') != digest(receipt):
            raise ValueError('Prepared request integrity check failed.')
        return condition
    subprocess.run(runtime_command(condition, 'prepare', '--domains', request['domain'], '--out', output),
                   cwd=ROOT, check=True)
    run = output / 'runs' / request['domain']
    meta = read(run / 'run.json')
    prompt = run / 'initial_prompt.md'
    original = prompt.read_text()
    if digest(prompt) != meta['input_files'].get(str(prompt)):
        raise ValueError('Prepared base prompt does not match its frozen input hash.')
    original_path = run / 'base_prompt.md'
    original_path.write_text(original)
    material = run / 'work/user_research_brief.json'
    save(material, request)
    prompt.write_text(original + request_text(request))
    receipt = output / 'demo_request.json'
    save(receipt, request)
    customization = {
        'schema': 'ideax.demo-customization.v1',
        'request_sha256': digest(receipt),
        'base_prompt_sha256': digest(original_path),
        'effective_prompt_sha256': digest(prompt),
        'paper_benchmark_reproduction': False,
        'prepared_at': datetime.now(timezone.utc).isoformat(),
    }
    meta['input_files'].update({str(prompt): digest(prompt), str(material): digest(material),
                                str(original_path): digest(original_path), str(receipt): digest(receipt)})
    meta['prompt_sha256'] = digest(prompt)
    meta['demo_customization'] = customization
    save(run / 'run.json', meta)
    manifest = read(output / 'manifest.json')
    manifest['demo_customization'] = customization
    save(output / 'manifest.json', manifest)
    (output / 'README.md').write_text(
        '# Custom IdeaX demo run\n\nThis run includes an explicit user question, critique, and optional '
        'recorded case. It is not a reproduction of the paper benchmark.\n\n'
        'The original prompt, effective prompt, request, and their hashes are retained. '
        'The published system prompt files have not been changed.\n\n'
        'Completed cards: runs/' + request['domain'] + '/accepted/IDEAS.json\n'
        'Reading record: runs/' + request['domain'] + '/work/out/SEARCH_LOG.md\n')
    return condition


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--run', action='store_true', help='Start real model generation with your configured account.')
    parser.add_argument('--external-gpt-reserved', type=int, default=0,
                        help='Declare requests reserved by other jobs on the same account.')
    args = parser.parse_args()
    try:
        if args.request.stat().st_size > 60000:
            raise ValueError('Request is too large.')
        if not 0 <= args.external_gpt_reserved < 300:
            raise ValueError('External GPT reservation must be between 0 and 299.')
        request = validate_request(read(args.request))
        output = args.out.resolve()
        condition = prepare(request, output)
        if not args.run:
            print(json.dumps({'status': 'prepared', 'execution': str(output), 'model_calls': 0,
                              'next': 'Inspect the prepared prompt, then repeat with --run.'}, indent=2))
            return 0
        subprocess.run(runtime_command(condition, 'run', '--execution', output, '--gpt-budget', '1',
                                       '--external-gpt-reserved', args.external_gpt_reserved), cwd=ROOT, check=True)
        status = read(output / 'state.json')
        if status.get('status') != 'completed':
            print('Run needs attention. Inspect state.json and the per-domain records; no failure is treated as completion.', file=sys.stderr)
            return 1
        print('Completed cards: ' + str(output / 'runs' / request['domain'] / 'accepted/IDEAS.json'))
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print('IdeaX demo: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
