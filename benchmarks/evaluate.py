#!/usr/bin/env python3
"""Generation (C/N/S/I), Reconstruction, and IS, each with GPT and Claude."""
import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE / 'shared'), str(HERE / 'interesting')]
import paper_report
from native_judge import digest, save


def read(path):
    return json.loads(Path(path).read_text())


def run_legacy(benchmark, args):
    subprocess.run([sys.executable, str(HERE / 'run.py'), benchmark, *args], check=True)


def argument(args, name, default=None):
    if name in args:
        return args[args.index(name) + 1]
    return next((s.split('=', 1)[1] for s in args if s.startswith(name + '=')), default)


def validate_proposals(source):
    groups = defaultdict(list)
    identities = set()
    models = set()
    for row in read(source):
        key = (row['system'], row['task_id'], row['idea_id'])
        if key in identities:
            raise ValueError('Duplicate proposal identity')
        identities.add(key)
        groups[key[:2]].append(row)
        models.add(row.get('generation_model'))
    if not groups:
        raise ValueError('Novelty requires original proposals')
    if len(models) != 1:
        raise ValueError('Use separate evaluation directories for different generation models')


def generation_report(args):
    parser = argparse.ArgumentParser(description='Verified C/N/S/I report; fixed target, both judges, no API calls')
    parser.add_argument('--reviewer', type=Path, required=True)
    parser.add_argument('--novelty', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--generation-model', required=True)
    parser.add_argument('--expected-slots', type=int, default=190)
    a = parser.parse_args(args)
    run_legacy('reviewer', ['report', '--out', str(a.reviewer)])
    run_legacy('interesting', ['report', '--out', str(a.novelty)])
    rm, nm = read(a.reviewer / 'manifest.json'), read(a.novelty / 'manifest.json')
    require_independent_novelty(nm)
    from idea_benchmark.core import blind_text
    original = {}
    for item in rm['items']:
        text = blind_text(read(a.reviewer / 'inputs' / (item['id'] + '.json'))['idea_text'])
        original[(item['group'], item['domain'], item['source_idea_id'])] = '\n'.join(f'L{i}: {line}' for i, line in enumerate(text.splitlines(), 1))
    for job in nm['jobs']:
        payload = read(a.novelty / 'inputs' / (job['id'] + '.json'))
        cards = {c['card_id']: c for c in payload['cards']}
        if len(payload['mapping']) != 1 or len(cards) != 1:
            raise ValueError('Independent Novelty must contain exactly one original proposal')
        for card in payload['mapping']:
            key = (job['system'], job['domain'], card['idea_id'])
            if key not in original or original[key] != cards[card['card_id']]['idea_text']:
                raise ValueError('CIS and Novelty proposal inputs differ')
    if rm.get('zero_outcomes', []) != nm.get('zero_outcomes', []):
        raise ValueError('Native-zero provenance differs between the two evaluations')
    report = {'benchmark': 'Generation', 'generation_model': a.generation_model,
              'novelty_protocol': nm['protocol'],
              'metric_order': list(paper_report.GENERATION),
              'raw_mapping': {'C': 'Reviewer.N', 'N': 'Interesting.score / 20', 'S': 'Reviewer.S', 'I': 'Reviewer.I'},
              'manifest_sha256': {'reviewer': digest(rm), 'novelty': digest(nm)},
              'rows': paper_report.generation(read(a.reviewer / 'results.json'), read(a.novelty / 'results.json'), a.expected_slots, rm.get('zero_outcomes', []))}
    save(a.out / 'scores.json', report)
    lines = ['# Generation — GPT / Claude', '', 'Each cell is the full target mean, in GPT / Claude order. Missing means remain unknown; coverage and successful means are in scores.json.', '', '| System | C | N | S | I |', '|---|---:|---:|---:|---:|']
    for system in sorted({r['system'] for r in report['rows']}):
        judges = {r['judge_id']: r for r in report['rows'] if r['system'] == system}
        cells = []
        for name in paper_report.GENERATION:
            vals = [judges[j]['metrics'][name]['full_mean'] for j in paper_report.JUDGES]
            cells.append(' / '.join('pending' if v is None else f'{v:.2f}' for v in vals))
        lines.append('| ' + system + ' | ' + ' | '.join(cells) + ' |')
    (a.out / 'REPORT.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({'report': str(a.out / 'scores.json'), 'model_calls': 0}))


def require_independent_novelty(manifest):
    if (manifest.get('protocol') != 'interesting-independent-single-card-v1'
            or manifest.get('scope') != 'per_proposal_independent_context'):
        raise ValueError('Generation N requires the independent single-proposal version; old panel scores stay separate')


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ('-h', '--help'):
        print(__doc__ + '\n\n  generation cis <prepare|check|run|report> [Reviewer options]\n  generation novelty <prepare|run|report> [panel options]\n  generation report --reviewer DIR --novelty DIR --generation-model MODEL --out DIR\n  reconstruction <prepare|run|report> [Founder options]\n  is <prepare|run|report> [IS options]')
        return
    benchmark = args.pop(0)
    if benchmark == 'generation':
        stage = args.pop(0) if args else ''
        if stage == 'report':
            generation_report(args); return
        if stage not in ('cis', 'novelty'):
            raise ValueError('Generation stage must be cis, novelty, or report')
        legacy = 'reviewer' if stage == 'cis' else 'interesting'
        if args and stage == 'novelty':
            if args[0] == 'prepare':
                validate_proposals(argument(args, '--input'))
                if argument(args, '--novelty-unit') not in (None, 'single'):
                    raise ValueError('Generation N uses independent single-proposal contexts')
                if argument(args, '--novelty-unit') is None:
                    args.extend(['--novelty-unit', 'single'])
            else:
                require_independent_novelty(read(Path(argument(args, '--out')) / 'manifest.json'))
    elif benchmark in ('reconstruction', 'is'):
        legacy = {'reconstruction': 'founder', 'is': 'ideascientist'}[benchmark]
    else:
        raise ValueError('Unknown benchmark')
    if args and args[0] == 'run':
        if legacy == 'reviewer':
            astra = int(argument(args, '--astra-concurrency', '8'))
            opus = int(argument(args, '--opus-concurrency', '8'))
            if astra < 1 or opus < 1 or astra + opus > 20:
                raise ValueError('Combined scoring workers must be within 20')
            for name, value in [('--astra-concurrency', astra), ('--opus-concurrency', opus)]:
                if argument(args, name) is None: args.extend([name, str(value)])
            out = Path(argument(args, '--out'))
            m = read(out / 'manifest.json')
            needs_acquisition = any(not (out / 'evidence' / i['id'] / 'receipt.json').exists() for i in m['items'])
            if needs_acquisition and urlparse(os.environ.get('LITGRAPH_API_BASE_URL', '')).hostname not in ('127.0.0.1', 'localhost', '::1'):
                raise ValueError('Use frozen evidence or a local offline literature service')
        elif not 1 <= int(argument(args, '--workers', '8')) <= 20:
            raise ValueError('Scoring workers must be within 20')
    run_legacy(legacy, args)
    if args and args[0] in ('run', 'report') and benchmark in ('reconstruction', 'is'):
        out = Path(argument(args, '--out'))
        result, manifest = read(out / 'results.json'), read(out / 'manifest.json')
        if benchmark == 'reconstruction':
            enriched = dict(manifest, payloads=[read(out / 'inputs' / (j['id'] + '.json')) for j in manifest['jobs']])
            targets = [json.loads(s) for s in (HERE / 'founder/data/targets.jsonl').read_text().splitlines() if s.strip()]
            rows = paper_report.reconstruction(result, enriched, targets)
        else:
            # The planned denominator remains 190 even for an incomplete input export.
            rows = paper_report.is_benchmark(result, manifest)
        save(out / 'paper_scores.json', {'benchmark': benchmark, 'manifest_sha256': digest(manifest), 'rows': rows})


if __name__ == '__main__':
    main()
