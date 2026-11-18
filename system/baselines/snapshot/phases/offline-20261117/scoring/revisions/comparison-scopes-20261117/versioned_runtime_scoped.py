"""Run frozen scoring unchanged after matching generation and evaluation material identity."""
import json
import os
from pathlib import Path
import sys
import urllib.request
import material_versions_scoped as M
sys.path.insert(0,str(M.ROOT/'scoring'))
import runtime as original


def main():
    command=sys.argv[1:]
    def option(name):return command[command.index(name)+1]
    stage=command[0];method=option('--method');domain=option('--domain')
    index=int(option('--slot')) if '--slot' in command else None
    selected=M.scoring_material(method,domain,index)
    out=M.ROOT/'evaluations'/method/domain/(f'slot-{index:02}' if index is not None else 'novelty')
    out.mkdir(parents=True,exist_ok=True)
    with urllib.request.urlopen('http://127.0.0.1:8766/health',timeout=5) as response:health=json.load(response)
    if health.get('corpus_id')!=selected['corpus_id']:
        raise RuntimeError('Evaluation corpus differs from generation material')
    previous=M.read(out/'evaluation_material_version.json')
    if previous and any(previous.get(k)!=selected.get(k) for k in ('data_version','corpus_id','corpus_sha256','comparison_scope')):
        raise RuntimeError('Cached evaluation belongs to another material version or comparison scope')
    if not previous and any((out/name).exists() for name in ('result.json','inputs','evidence','reviews','01-read','02-score')):
        raise RuntimeError('Existing evaluation without material and comparison scope cannot be adopted')
    for name in ('manifest.json','result.json'):
        cached=M.read(out/name,{})
        if cached and any(cached.get(k)!=selected[k] for k in ('data_version','corpus_id','corpus_sha256','comparison_scope')):
            raise RuntimeError('Cached evaluation artifact has a different or absent comparison scope')
    original.save(out/'evaluation_material_version.json',selected)
    original_collect=original.E.evidence
    def checked_evidence(ident):
        original_collect(ident)
        receipt=M.read(original.E.ROOT/'evidence'/ident/'receipt.json',{})
        if receipt.get('corpus_id')!=selected['corpus_id']:
            raise RuntimeError('Evidence cache differs from generation material')
    original.E.evidence=checked_evidence
    try:
        original.main()
    finally:
        for name in ('manifest.json','result.json'):
            path=out/name
            if path.exists():
                value=M.read(path);value.update({k:selected[k] for k in ('data_version','corpus_id','corpus_sha256','comparison_scope')})
                original.save(path,value)
        original.E.evidence=original_collect


if __name__=='__main__':main()
