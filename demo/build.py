#!/usr/bin/env python3
"""Build a static, source-linked replay. Does not call a model or a service."""
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
SITE = HERE / 'site'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    stories = json.loads((HERE / 'stories.json').read_text())
    case_root = ROOT / 'case_studies/model_efficiency'
    targets = []
    for story in stories:
        folder = case_root / story['folder']
        proposal, process = folder / 'PROPOSAL.md', folder / 'PROCESS.md'
        raw = proposal.read_text()
        refs = []
        for line in raw.splitlines():
            m = re.match(r'\[(\d+)\]\s+\*\*(.+?)\*\*', line)
            if not m:
                continue
            urls = re.findall(r'\]\((https://[^\s)]+)\)', line)
            if urls:
                refs.append({'number': int(m[1]), 'title': m[2], 'url': urls[0],
                             'reading_note': line.split('阅读：', 1)[-1] if '阅读：' in line else
                             'See the source process record for the actual reading scope.'})
        neighbors = []
        for title in story['neighbors']:
            ref = next((r for r in refs if r['title'].casefold() == title.casefold()), None)
            if ref is None:
                raise ValueError(f'Unmatched source citation: {story["id"]}: {title}')
            neighbors.append(ref)
        story['neighbors'] = neighbors
        story['references'] = refs
        trace = process.read_text()
        for insight in story['insights']:
            if insight['id'] not in trace:
                raise ValueError('Entry missing from source process: ' + insight['id'])
        queries = []
        for match in re.finditer(r'\[([^\]\n]+)\]\((https://[^\s)]+/api/v1/search\?[^\s)]+)\)', trace):
            item = {'label': match[1], 'url': match[2]}
            if item['url'] not in [q['url'] for q in queries]:
                queries.append(item)
        story['queries'] = queries[:6]
        story['process_url'] = f'https://github.com/Einsia/IdeaX/blob/main/case_studies/model_efficiency/{story["folder"]}/PROCESS.md'
        story['proposal_url'] = story['process_url'].replace('PROCESS.md', 'PROPOSAL.md')
        story['source_sha256'] = {'proposal': sha(proposal), 'process': sha(process)}
        story['recorded_on'] = '2026-11-13'
        story['scope'] = 'Editorial replay of recorded sources and candidate revisions; not a live model session or a private reasoning transcript.'
        dest = SITE / 'sources' / story['id']
        dest.mkdir(parents=True, exist_ok=True)
        for path in [proposal, process]:
            shutil.copy2(path, dest / path.name)
        targets.append(story)
    domains = json.loads((ROOT / 'data/domains.json').read_text())['domains']
    prompt = (ROOT / 'docs/single_api_copyable_zh.md').read_text()
    start = prompt.index('你是一个独立研究者。')
    prompt = prompt[start:]
    if '```' in prompt:
        prompt = prompt.split('```', 1)[0].rstrip()
    catalog = {
        'schema': 'ideax.demo.catalog.v1',
        'default_case': 'residency',
        'cases': targets,
        'domains': [{'id': d['id'], 'name': d['name'], 'category': d.get('category', '')} for d in domains],
        'api_prompt': prompt,
        'prompt_sha256': sha(ROOT / 'docs/single_api_copyable_zh.md'),
        'source_collection': 'https://github.com/Einsia/IdeaX/tree/main/case_studies/model_efficiency',
    }
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n')
    (SITE / '.nojekyll').touch()
    print(json.dumps({'cases': len(targets), 'domains': len(domains), 'model_calls': 0}))


if __name__ == '__main__':
    build()
