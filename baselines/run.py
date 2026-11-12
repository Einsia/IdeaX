#!/usr/bin/env python3
"""Prepare or run five independent native baseline proposals per domain."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parent.parent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('prepare','run','status','export'))
    p.add_argument('--method',choices=('coi','ideascientist'),required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--domains',nargs='+',default=['all'])
    p.add_argument('--workers',type=int,default=4)
    a=p.parse_args();out=a.out.resolve()
    if a.workers<1:p.error('--workers must be positive')
    if a.action=='prepare':
        known={d.name for d in (ROOT/'baselines/tasks').iterdir() if d.is_dir()}
        domains=sorted(known) if a.domains==['all'] else a.domains
        if not domains or len(set(domains))!=len(domains) or not set(domains)<=known:p.error('Unknown or duplicate domains')
        out.mkdir(parents=True,exist_ok=False)
        for d in domains:shutil.copytree(ROOT/'baselines/tasks'/d,out/'inputs'/d)
        (out/'manifest.json').write_text(json.dumps({'method':a.method,'domains':domains,'ideas_per_domain':5,
              'model':'gpt-6-astra','effort':'xhigh','source':'portable-native-baselines-v1'},ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'prepared':str(out),'domains':len(domains),'model_calls':0}));return
    m=json.loads((out/'manifest.json').read_text())
    if m['method']!=a.method:raise ValueError('Wrong method for this execution')
    if a.action=='run':
        env=dict(os.environ,IDEAX_BASELINE_STATE=str(out),PYTHONPATH=str(ROOT/'baselines/runtime'))
        env.setdefault('IDEAX_SCRATCH',str(ROOT/'.scratch'));Path(env['IDEAX_SCRATCH']).mkdir(parents=True,exist_ok=True)
        (out/'concurrency').mkdir(exist_ok=True)
        def run(d):
            entry='coi_worker.py' if a.method=='coi' else 'delivery_worker.py'
            return subprocess.call([sys.executable,str(ROOT/'baselines/runtime'/entry),a.method,d],env=env)
        with ThreadPoolExecutor(max_workers=a.workers) as pool:codes=list(pool.map(run,m['domains']))
        if any(codes):raise SystemExit('Some native proposals need review; see per-domain status.json')
    rows=[];status={};zeros=[];mechanisms={}
    for d in m['domains']:
        native=out/'runs'/a.method/d
        status[d]=json.loads((native/'status.json').read_text()) if (native/'status.json').exists() else {'state':'prepared'}
        if a.action=='export':
            cards=json.loads((native/'idea_cards.json').read_text())
            outcomes=json.loads((native/'idea_outcomes.json').read_text()) if (native/'idea_outcomes.json').exists() else []
            rejected=[o for o in outcomes if o['status']=='rejected_novelty']
            if len(cards)+len(rejected)!=5 or status[d].get('state')!='completed':raise ValueError('Incomplete domain '+d)
            for o in rejected:zeros.append(dict(o,system=a.method,task_id=d))
            task=json.loads((ROOT/'system/single-api/domains'/d/'task.json').read_text())
            for c in cards:
                rows.append({'system':a.method,'task_id':d,'idea_id':c['card_id'],'domain':task['name'],
                     'domain_ids':task['litgraph_domain_ids'],'idea_text':c['idea_card_md'],
                     'task_context':(out/'inputs'/d/'task-one.md').read_text(),
                     'provided_reference_texts':c.get('source_refs',[])})
                original=json.loads(Path(c['native_artifact']).read_text())
                if a.method=='coi':mechanisms[c['card_id']]=original['idea']
                else:
                    source=original.get('proposal',original)
                    keys=('title','one_sentence_thesis','core_problem','key_novelty','method')
                    selected={k:source[k] for k in keys if source.get(k)}
                    if not selected.get('method'):raise ValueError('Missing native method for transfer scoring')
                    mechanisms[c['card_id']]=json.dumps(selected,ensure_ascii=False,indent=2)
    if a.action=='export':
        path=out/'benchmark_input.json';path.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
        (out/'zero_score_outcomes.json').write_text(json.dumps(zeros,ensure_ascii=False,indent=2)+'\n')
        (out/'mechanisms.json').write_text(json.dumps(mechanisms,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'exported':str(path),'cards':len(rows),'native_novelty_rejections':len(zeros)}))
    else:print(json.dumps(status,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
