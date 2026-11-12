#!/usr/bin/env python3
"""Check portable source, frozen prompts, domain contexts and repository assets."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CONDITIONS=('single-full','single-api','multi-full','multi-api')
SKIP={'.git','.venv','.scratch','.state','__pycache__','runs','outputs'}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def files():
    for p in ROOT.rglob('*'):
        if any(x in SKIP for x in p.relative_to(ROOT).parts):continue
        if p.is_file():yield p

def main():
    count=0
    for p in files():
        if p.is_symlink() and not p.resolve().is_relative_to(ROOT):raise ValueError('External symlink: '+str(p))
        if p.suffix=='.py':ast.parse(p.read_text(),filename=str(p));count+=1
    total=0
    for name in CONDITIONS:
        folder=ROOT/'system'/name;release=json.loads((folder/'release.json').read_text())
        assert len(release['domains'])==38
        for filename,expected in release['prompt_files'].items():
            assert sha(folder/'prompts'/filename)==expected,(name,filename)
        assert sha(folder/'prompts/generation.md')==release['template_sha256']
        for domain in release['domains']:
            path=folder/'domains'/domain['id']/'full_context.jsonl'
            task=json.loads((path.parent/'task.json').read_text())
            assert task['litgraph_domain_ids']
            if release['access']=='api':
                assert not path.exists();continue
            assert sha(path)==domain['context_sha256']
            rows=[json.loads(s) for s in path.read_text().splitlines() if s.strip()]
            assert len({x['id'] for x in rows})==len(rows)
            counts=Counter(x['kind'] for x in rows)
            assert counts['insight']==domain['insights'] and counts['problem']==domain['problems']
            if name=='single-full':total+=len(rows)
    manifest=ROOT/'provenance/release_files.json'
    if manifest.exists():
        for filename,expected in json.loads(manifest.read_text()).items():
            assert sha(ROOT/filename)==expected,filename
    print(json.dumps({'ok':True,'python_files':count,'systems':4,'domains':38,'full_entries':total,'model_calls':0}))

if __name__=='__main__':main()
