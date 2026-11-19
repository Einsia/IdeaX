"""Paper-facing labels and dual-judge coverage; never alter accepted reviews."""
from collections import Counter, defaultdict
import math
import statistics

JUDGES = {'astra': 'GPT', 'opus': 'Claude'}
GENERATION = ('C', 'N', 'S', 'I')
QUALITY = ('actionability', 'specificity', 'clarity', 'impact', 'soundness', 'relevance')


def numeric(value):
    return type(value) in (int, float) and math.isfinite(value)


def metric(values, expected, native_zeros=0):
    valid = [v for v in values if numeric(v)]
    covered = len(valid) + native_zeros
    if expected <= 0 or covered > expected:
        raise ValueError('Coverage exceeds the declared target denominator')
    return {
        'expected': expected, 'judged': len(valid), 'confirmed_native_zero': native_zeros,
        'missing': expected - covered,
        'successful_mean': statistics.mean(valid) if valid else None,
        'covered_mean': sum(valid) / covered if covered else None,
        'full_mean': (sum(valid) / expected) if covered == expected else None,
    }


def generation(reviewer, novelty, expected=190, zeros=()):
    """Reviewer raw N is Contribution; Interesting / 20 is paper Novelty."""
    values = defaultdict(lambda: defaultdict(list))
    systems = set()
    seen = set()
    for row in reviewer['cards']:
        key = (row['group'], row['domain'], row['source_idea_id'], row['judge'])
        if key in seen or row['judge'] not in JUDGES:
            raise ValueError('Duplicate or unknown Reviewer identity')
        seen.add(key); systems.add(row['group'])
        for displayed, raw in [('C', 'N'), ('S', 'S'), ('I', 'I')]:
            value = row.get(raw)
            if value is not None and (not numeric(value) or not 1 <= value <= 5):
                raise ValueError('Invalid Reviewer score')
            values[(row['group'], row['judge'])][displayed].append(value)
    seen = set()
    for row in novelty['rows']:
        key = (row['system'], row['domain'], row['idea_id'], row['judge'])
        if key in seen or row['judge'] not in JUDGES:
            raise ValueError('Duplicate or unknown Novelty identity')
        seen.add(key); systems.add(row['system'])
        value = row.get('interesting')
        if value is not None and (not numeric(value) or not 0 <= value <= 100):
            raise ValueError('Invalid Novelty score')
        values[(row['system'], row['judge'])]['N'].append(value / 20 if value is not None else None)
    zero_counts = Counter(row['system'] for row in zeros)
    systems.update(zero_counts)
    return [{'system': system, 'judge': JUDGES[judge], 'judge_id': judge,
             'metrics': {name: metric(values[(system, judge)][name], expected, zero_counts[system])
                         for name in GENERATION}}
            for system in sorted(systems) for judge in JUDGES]


def reconstruction(result, manifest, targets):
    """Keep target-weighted historical scores beside domain-weighted scores."""
    main = [t for t in targets if not t.get('supplementary')]
    target_map = {(t['task_id'], str(t['founder_paper_id'])): t['task_id'].split(':', 1)[1] for t in main}
    expected_domains = set(target_map.values())
    systems = set()
    # Expected systems include jobs with no accepted judge response.
    for payload in manifest['payloads']:
        systems.update(payload['labels'])
    groups = defaultdict(list)
    seen = set()
    for row in result['rows']:
        identity = (row['system'], row['judge'], row['domain'], str(row['target']))
        if identity in seen or row['judge'] not in JUDGES:
            raise ValueError('Duplicate or unknown reconstruction identity')
        seen.add(identity)
        key = (row['domain'], str(row['target']))
        if key not in target_map:
            raise ValueError('Result is outside the frozen main target set')
        groups[(row['system'], row['judge'])].append((target_map[key], row))
    output = []
    for system in sorted(systems):
        for judge in JUDGES:
            rows = groups[(system, judge)]
            metrics = {}
            for shown, raw in [('Grade', 'best_level'), ('direction_hit', 'direction_hit'), ('mechanism_hit', 'mechanism_hit')]:
                by_domain = defaultdict(list)
                for domain, row in rows:
                    value = row[raw]
                    if not numeric(value) or value not in (range(4) if raw == 'best_level' else (0, 1)):
                        raise ValueError('Invalid reconstruction score')
                    by_domain[domain].append(value)
                per_domain = {d: statistics.mean(v) for d, v in by_domain.items()}
                all_targets = len(rows) == len(target_map)
                metrics[shown] = {
                    'expected_targets': len(target_map), 'judged_targets': len(rows),
                    'expected_domains': len(expected_domains), 'covered_domains': len(per_domain),
                    'domain_mean': statistics.mean(per_domain.values()) if all_targets else None,
                    'available_domain_mean': statistics.mean(per_domain.values()) if per_domain else None,
                    'historical_target_mean': statistics.mean(row[raw] for _, row in rows) if all_targets else None,
                    'per_domain': per_domain,
                }
            output.append({'system': system, 'judge': JUDGES[judge], 'judge_id': judge, 'metrics': metrics})
    return output


def is_benchmark(result, manifest, expected=190):
    groups = defaultdict(list)
    seen = set()
    systems = {job['system'] for job in manifest['jobs']}
    zero_counts = Counter(row['system'] for row in manifest.get('zero_outcomes', []))
    systems.update(zero_counts)
    for row in result['rows']:
        key = (row['system'], row['domain'], row['idea_id'], row['judge'])
        if key in seen or row['judge'] not in JUDGES:
            raise ValueError('Duplicate or unknown IS identity')
        seen.add(key)
        groups[(row['system'], row['judge'])].append(row)
    output = []
    for system in sorted(systems):
        for judge in JUDGES:
            rows = groups[(system, judge)]
            dimensions = {}
            for name in (*QUALITY, 'novelty', 'transfer'):
                vals = [r.get(name) for r in rows]
                lower, upper = (0, 1) if name == 'transfer' else (1, 10)
                if any(v is not None and (not numeric(v) or not lower <= v <= upper) for v in vals):
                    raise ValueError('Invalid IS dimension')
                dimensions[name] = metric(vals, expected, zero_counts[system])
            quality = [statistics.mean(r[d] for d in QUALITY) if all(numeric(r.get(d)) for d in QUALITY) else None for r in rows]
            dimensions['quality_mean'] = metric(quality, expected, zero_counts[system])
            output.append({'system': system, 'judge': JUDGES[judge], 'judge_id': judge,
                           'metrics': dimensions, 'Overall': None,
                           'Overall_status': 'not_defined_for_existing_output_adaptation'})
    return output
