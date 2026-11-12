"""Run the original post-selection Blueprint writer with preserved source evidence."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import blueprint
import cli
from common import read,save,SYSTEM

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('prepare','run','status','worker','export'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--execution',type=Path)
    p.add_argument('--workers',type=int,default=2);p.add_argument('--domain');p.add_argument('--id')
    a=p.parse_args();a.out=a.out.resolve()
    if a.workers<1:p.error('workers must be positive')
    if a.action=='prepare':
        if not a.execution:p.error('prepare needs --execution')
        source=a.execution.resolve();m=cli.checked_manifest(source)
        a.out.mkdir(parents=True,exist_ok=False)
        for domain in m['domains']:
            blueprint.prepare_domain(source/'runs'/domain,a.out/domain,domain)
        save(a.out/'manifest.json',{'system':str(SYSTEM),'domains':m['domains'],'source_execution':str(source)})
    else:
        m=read(a.out/'manifest.json')
        if m['system']!=str(SYSTEM):raise ValueError('Different source condition')
        if a.action=='worker':
            blueprint.worker(a.out/a.domain,a.id);return
        if a.action=='run':
            jobs=[(d,item['id']) for d in m['domains'] for item in read(a.out/d/'manifest.json')['items']]
            def one(job):
                return subprocess.call([sys.executable,__file__,'worker','--out',str(a.out),'--domain',job[0],'--id',job[1]])
            with ThreadPoolExecutor(max_workers=a.workers) as pool:codes=list(pool.map(one,jobs))
            if any(codes):raise SystemExit('Some Blueprint writers need review; original cards remain preserved')
    rows=[];mechanisms={};ready=0;expected=0
    m=read(a.out/'manifest.json')
    for domain in m['domains']:
        dm=read(a.out/domain/'manifest.json')
        task=read(SYSTEM/'domains'/domain/'task.json')
        for item in dm['items']:
            expected+=1;valid=blueprint.valid(a.out/domain,item);ready+=int(valid)
            if a.action=='export':
                if not valid:raise ValueError('Incomplete Blueprint '+item['id'])
                dest=a.out/domain/'deliveries'/f"idea-{item['rank']:02}"
                rows.append({'system':SYSTEM.name+'-blueprint','task_id':domain,'domain':task['name'],
                    'domain_ids':task['litgraph_domain_ids'],'idea_id':item['id'],'selector_top1':item['selector_top1'],
                    'task_context':'Generate research ideas in '+task['name'],
                    'idea_text':(dest/'RESEARCH_BLUEPRINT.md').read_text(),
                    'provided_reference_texts':[]})
                card=read(dest/'IDEA_CARD.json')
                mechanisms[item['id']]=json.dumps({k:card[k] for k in ('title','problem','mechanism') if k in card},ensure_ascii=False)
    if a.action=='export':
        save(a.out/'benchmark_input.json',rows)
        save(a.out/'mechanisms.json',mechanisms)
    print(json.dumps({'ready':ready,'expected':expected,'complete':ready==expected,'out':str(a.out)}))

if __name__=='__main__':main()
