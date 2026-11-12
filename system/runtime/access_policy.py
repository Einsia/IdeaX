"""Condition checks use only evidence actually supplied to or fetched by this run."""
import json
import os
import re
from urllib.parse import urlsplit
from common import ACCESS, SYSTEM, read, save, sha, now
from log_evidence import collect

ENTRY = re.compile(r'(?<![\w-])[A-Za-z0-9_-]+-[IP]\d+(?:-s\d+)?')

def denied_hosts():
    if ACCESS != 'web': return []
    hosts = {urlsplit(os.environ['LITGRAPH_API_BASE_URL']).hostname,
             'loc-serves-annotation-tomatoes.trycloudflare.com'}
    return sorted(h for h in hosts if h)

def rows(path):
    if not path.exists(): return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

def evidence_entries(run):
    entries = {r['id']: r for r in rows(run/'work/full_domain_context.jsonl')}
    if ACCESS == 'web': return entries
    base = read(run/'work/library_api.json')['base_url']
    logs, _ = collect(run/'work/out', base)
    observed = {r['sha256'] for r in logs if r.get('status') == 200}
    def visit(value):
        if isinstance(value, dict):
            if value.get('kind') in ('insight', 'problem') and isinstance(value.get('id'), str):
                entries[value['id']] = value
            for child in value.values(): visit(child)
        elif isinstance(value, list):
            for child in value: visit(child)
    for path in (run/'work/out').rglob('api_responses/*.json'):
        if path.stem not in observed: continue
        if sha(path) != path.stem: raise ValueError('Retrieved API evidence changed: '+str(path))
        visit(read(path))
    return entries

def check_sources(item, run):
    errors = []
    problem_ids = set(ENTRY.findall(json.dumps(item.get('problem'), ensure_ascii=False)))
    insight_ids = set(ENTRY.findall(json.dumps(item.get('mechanism'), ensure_ascii=False)))
    if ACCESS == 'web':
        if problem_ids or insight_ids: errors.append('Web condition must cite public literature, not LitGraph entry IDs')
        return errors
    entries = evidence_entries(run)
    domain = read(run/'run.json')['domain_id']
    domains = set(read(SYSTEM/'domains'/domain/'task.json')['litgraph_domain_ids'])
    problems = {k for k,v in entries.items() if v.get('kind') == 'problem' and v.get('unit', v.get('domain_id')) in domains}
    insights = {k for k,v in entries.items() if v.get('kind') == 'insight'}
    if not problems & problem_ids:
        errors.append('Cite an actual target-domain problem from this run’s supplied or retrieved evidence; use the provided API client to preserve retrieved sources')
    if not insights & insight_ids:
        errors.append('Cite an actual insight present in this run’s supplied or retrieved evidence')
    unknown = (problem_ids | insight_ids) - entries.keys()
    if unknown: errors.append('Entry IDs lack saved evidence in this run: '+', '.join(sorted(unknown)))
    return errors

def check_network(run):
    errors = []
    connections = [r for r in rows(run/'gate/egress.log') if r.get('method') == 'CONNECT' and r.get('allowed') is True and not r.get('error')]
    library_host = urlsplit(os.environ['LITGRAPH_API_BASE_URL']).hostname
    if ACCESS != 'api' and not any(r.get('target','').rsplit(':',1)[0] != library_host for r in connections):
        errors.append('No observed public HTTPS access')
    if ACCESS == 'web':
        for rel in ('full_domain_context.jsonl','library_api.json','tools/library_client.py','lit.db'):
            if (run/'work'/rel).exists(): errors.append('Forbidden Web material: '+rel)
        if any(r.get('target','').rsplit(':',1)[0].lower().rstrip('.') in denied_hosts() for r in connections):
            errors.append('Web condition accessed LitGraph')
    else:
        logs, sources = collect(run/'work/out', read(run/'work/library_api.json')['base_url'])
        count = sum(r.get('status') == 200 for r in logs)
        if not count: errors.append('No observed successful LitGraph request')
        save(run/'api_log_audit.json', {'at':now(),'sources':sources,'successful_requests':count})
    return errors
