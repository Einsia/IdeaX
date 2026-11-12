"""CoI focused60: Astra-only application of the frozen sequential rubric."""
import argparse
import fcntl
import importlib.util
import statistics
from pathlib import Path

from . import interesting_sequential as base
from .interesting_sequential import (
    ROOT, RULE, PROTOCOL, read, write, sha, canonical, now, stages,
    initial_state, payload_for, validate_result, advance, strip, lane,
)
from ..core import judge_packet

DEFAULT_OUT = ROOT / 'idea_benchmark/evaluations/focused60-coi-interesting-panel-20261102'
GEN = ROOT / 'idea_runs/focused60-coi-astra-20261101'
IDEAX = ROOT / 'idea_benchmark/evaluations/focused60-interesting-panel-20261031'
MODELS = {'astra': 'gpt-6-astra'}


def generation_audit():
    path = GEN / 'tools/batch.py'
    spec = importlib.util.spec_from_file_location('coi_focused_generation_audit', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tasks = mod.verify()
    result = mod.report(tasks)
    if not result['complete'] or result['accepted'] != 60:
        raise ValueError('All 60 native CoI ideas must pass generation validation')
    preserved = read(GEN / 'execution_revisions/retry-failed-20261101/preservation_audit.json')
    if preserved['successes_unchanged'] != 45:
        raise ValueError('Original success preservation was not verified')
    return tasks, result


def prepare(out):
    if out.exists():
        raise ValueError('Existing scoring batch is immutable')
    tasks, generation = generation_audit()
    tasks = {t['task_id']: t for t in tasks}
    accepted = {a['task_id']: a for a in generation['items']}
    order = read(IDEAX / 'mapping.json')
    if len(order) != 60 or {m['task_id'] for m in order} != set(tasks):
        raise ValueError('IdeaX paired task order does not cover these 60 tasks')
    if (IDEAX / 'prompt.txt').read_text() != RULE + '\n' + PROTOCOL:
        raise ValueError('Rubric changed relative to IdeaX')
    out.mkdir(parents=True)
    cards, mapping, provenance = [], [], []
    old_cards = {c['card_id']: c for c in read(IDEAX / 'cards.json')}
    for m in order:
        ident, task_id = m['card_id'], m['task_id']
        t, a = tasks[task_id], accepted[task_id]
        raw = Path(a['card']).read_text()
        context = Path(t['coi_prompt']).read_text()
        if old_cards[ident]['task_context'] != context:
            raise ValueError('Task input differs from paired IdeaX input')
        packet = judge_packet({'idea_text': raw, 'task_context': context, 'domain': t['domain']}, ident)
        packet['card_id'] = packet.pop('item_id')
        cards.append(packet)
        dest = out / 'cards' / f'{ident}.md'
        dest.parent.mkdir(exist_ok=True)
        dest.write_text(raw)
        mapping.append({'card_id': ident, 'task_id': task_id, 'domain': t['domain'], 'text_path': str(dest)})
        provenance.append({'card_id': ident, 'generation': a, 'prompt_sha256': t['prompt_sha256'],
                           'source_result': str(GEN / 'runs' / task_id / 'result.json')})
    write(out / 'cards.json', cards)
    write(out / 'mapping.json', mapping)
    write(out / 'provenance.json', provenance)
    write(out / 'generation_audit.json', generation)
    write(out / 'stages.json', stages([c['card_id'] for c in cards]))
    (out / 'prompt.txt').write_text(RULE + '\n' + PROTOCOL)
    write(out / 'config.json', {'protocol': 'interesting-sequential-v1-coi-astra', 'models': MODELS,
                               'effort': 'high', 'read_seconds': 2700, 'score_seconds': 5400,
                               'order_source': str(IDEAX / 'mapping.json'),
                               'scope': 'Astra only; Opus not requested'})
    # Comparison is offline: the judge never receives these previous scores.
    write(out / 'comparison_baseline.json', {'scores': read(IDEAX / 'scores.json'),
                                           'mapping': order, 'report': str(IDEAX / 'REPORT.md')})
    files = [Path(__file__), Path(base.__file__), Path(__file__).with_name('audit_focused60_coi.py'),
             Path(__file__).with_name('sequential.py'), Path(__file__).with_name('pilot.py'),
             ROOT / 'idea_benchmark/core.py', ROOT / 'idea_benchmark/runner.py', GEN / 'tools/batch.py']
    write(out / 'manifest.json', {'created_at': now(),
          'implementation': {str(p.resolve()): sha(p.read_bytes()) for p in files},
          'assets': {str(p.relative_to(out)): sha(p.read_bytes()) for p in out.rglob('*') if p.is_file()}})
    report(out)


def verify(out):
    m = read(out / 'manifest.json')
    for name, digest in m['assets'].items():
        if sha((out / name).read_bytes()) != digest:
            raise ValueError(f'Frozen asset changed: {name}')
    for name, digest in m['implementation'].items():
        if sha(Path(name).read_bytes()) != digest:
            raise ValueError(f'Frozen implementation changed: {name}')
    cfg = read(out / 'config.json')
    if cfg['models'] != MODELS or cfg['effort'] != 'high':
        raise ValueError('Expected Astra/high only')
    if (out / 'prompt.txt').read_text() != RULE + '\n' + PROTOCOL:
        raise ValueError('Rubric changed')


def report(out):
    state_path = out / 'runs/astra/state.json'
    state = read(state_path) if state_path.exists() else initial_state()
    mapping = read(out / 'mapping.json')
    rows = []
    lines = ['# CoI-Agent focused60：多卡 Interesting 评分', '',
             'Astra/high，0–100分。先预读10张不打分，此后每5张评分，每轮最多回改1张旧卡，末尾补评前10张。', '',
             f'已评分 {len(state["ledger"])}/60；仅评价 Interesting。', '',
             '|卡片|任务|Interesting / 完整理由|', '|---|---|---:|']
    for m in mapping:
        ident = m['card_id']
        a = state['ledger'].get(ident)
        cell = '待评分'
        if a:
            history = [h for h in state['history'] if h['card_id'] == ident]
            dest = out / 'reviews/astra' / f'{ident}.json'
            write(dest, {'final': a, 'history': history})
            v = a['score']
            cell = f'[{v if v is not None else "不可评"}]({dest})'
            rows.append({'card_id': ident, 'task_id': m['task_id'], 'domain': m['domain'], 'judge': 'astra',
                         'initial_score': history[0]['new']['score'], 'final_score': v, 'revisions': len(history) - 1})
        lines.append(f'|[{ident}]({m["text_path"]})|{m["task_id"]}|{cell}|')
    lines += ['', '缺评不作零分。完整理由链接包括首次评分及改分记录。依据提供材料，未独立联网查新。', '',
              '与IdeaX使用相同任务顺序及rubric，两个批次独立校准；同题分差不等于已证明框架因果效果。']
    (out / 'REPORT.md').write_text('\n'.join(lines) + '\n')
    write(out / 'scores.json', rows)
    if len(rows) == 60:
        baseline = read(out / 'comparison_baseline.json')
        old = {r['task_id']: r for r in baseline['scores'] if r['judge'] == 'astra'}
        paired = [r for r in rows if r['final_score'] is not None and old[r['task_id']]['final_score'] is not None]
        summary = []
        for domain in sorted({r['domain'] for r in rows}) + ['all']:
            selected = [r for r in paired if domain == 'all' or r['domain'] == domain]
            summary.append({'domain': domain, 'paired_numeric': len(selected),
                            'ideax_mean': statistics.mean(old[r['task_id']]['final_score'] for r in selected) if selected else None,
                            'coi_mean': statistics.mean(r['final_score'] for r in selected) if selected else None})
        write(out / 'comparison.json', summary)
        lines = ['# 同输入60题：IdeaX 与 CoI Interesting', '',
                 '相同Astra/high、多卡百分制rubric及任务顺序；两批独立校准，不是混合盲评，不能单独归因框架优劣。', '',
                 '|领域|共同数值评分|IdeaX|CoI|', '|---|---:|---:|---:|']
        for r in summary:
            cells = [f'{r[k]:.2f}' if r[k] is not None else '—' for k in ['ideax_mean', 'coi_mean']]
            lines.append(f'|{r["domain"]}|{r["paired_numeric"]}|{cells[0]}|{cells[1]}|')
        lines += ['', f'[CoI逐卡评分与理由]({out}/REPORT.md)', f'[IdeaX逐卡评分与理由]({baseline["report"]})']
        (out / 'COMPARISON.md').write_text('\n'.join(lines) + '\n')


def run(out, retry_failed=False):
    from .audit_focused60_coi import audit
    verify(out)
    with (out / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        def caller(*args):
            report(out)  # Publish preceding accepted stages before the next model call.
            return base.transport(*args)
        try:
            lane(out, 'astra', retry_failed, caller)
        except Exception as exc:
            write(out / 'runs/astra/status.json', {'state': 'needs_inspection', 'error_type': type(exc).__name__, 'updated_at': now()})
            raise
        finally:
            report(out)
            write(out / 'audit.json', audit(out))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['prepare', 'run', 'report', 'audit'])
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT)
    ap.add_argument('--retry-failed', action='store_true')
    args = ap.parse_args()
    out = args.out.resolve()
    if args.command == 'prepare':
        prepare(out)
    elif args.command == 'run':
        run(out, args.retry_failed)
    else:
        verify(out)
        report(out)
        if args.command == 'audit':
            from .audit_focused60_coi import audit
            result = audit(out)
            write(out / 'audit.json', result)
            print(result)


if __name__ == '__main__':
    main()
