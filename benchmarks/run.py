#!/usr/bin/env python3
"""Portable entry points for the four benchmark protocols."""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib.util
import json
from pathlib import Path
import random
import statistics
import subprocess
import sys

HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE/'shared'),str(HERE/'interesting')]
from native_judge import digest,save,MODELS
import zero_outcomes

def read(p):return json.loads(Path(p).read_text())
def load(name,p):
    spec=importlib.util.spec_from_file_location(name,p)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def engine():return load('score_engine',HERE/'reviewer/vendor/evaluate.py')
def scientific_hashes(bench):
    import hashlib
    paths=[Path(__file__),HERE/'shared/native_judge.py',HERE/'shared/zero_outcomes.py',HERE/'reviewer/vendor/evaluate.py']
    folder=HERE/bench
    paths += [p for p in folder.rglob('*') if p.is_file() and p.suffix in ('.py','.md') and '__pycache__' not in p.parts]
    return {str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

def prepare(a):
    if a.out.exists():raise ValueError('Use a fresh output directory')
    if not a.input:raise ValueError('prepare requires --input')
    jobs=[];m={'benchmark':a.benchmark,'protocol':'portable-native-v1','models':MODELS,'effort':'xhigh',
        'repetitions':1,'implementation':scientific_hashes(a.benchmark)}
    if a.benchmark=='interesting':
        m['zero_outcomes']=zero_outcomes.load(a.input)
        from idea_benchmark.core import judge_packet
        from idea_benchmark.panel.interesting_sequential import RULE
        rules=load('read_all',HERE/'interesting/read_all.py')
        rows=read(a.input);panels=defaultdict(list)
        identities=set()
        domains={d['id']:d for d in read(HERE.parent/'data/domains.json')['domains']}
        for row in rows:
            key=(row['system'],row['task_id'],row['idea_id'])
            if key in identities:raise ValueError('Duplicate idea identity')
            identities.add(key)
            panels[(row['system'],row['task_id'])].append(row)
        for key,rows in sorted(panels.items()):
            random.Random(int(digest(key)[:16],16)).shuffle(rows)
            cards=[];mapping=[]
            for index,row in enumerate(rows,1):
                row=dict(row);row.setdefault('task_context',domains.get(row['task_id'],{}).get('prompt',''))
                packet=judge_packet(row,f'card_{index:02}')
                packet['card_id']=packet.pop('item_id');cards.append(packet)
                mapping.append({'card_id':packet['card_id'],'idea_id':row['idea_id'],
                    'selector_top1':row.get('selector_top1',False)})
            payload={'cards':cards,'mapping':mapping,'stages':rules.stages([c['card_id'] for c in cards]),
                     'prompt':RULE+'\n'+rules.PROTOCOL}
            jobs.append({'id':'panel_'+digest(key)[:20],'system':key[0],'domain':key[1],'payload':payload})
        m['protocol']='interesting-read-all-then-score-v2';m['scope']='per_system_per_domain'
    elif a.benchmark=='ideascientist':
        # Reuse exactly the independent frozen evidence from Reviewer.
        source=read(a.input/'manifest.json');m['zero_outcomes']=source.get('zero_outcomes',[]);r=load('isci_rubric',HERE/'ideascientist/rescore.py')
        pipeline=load('reviewer_pipeline',HERE/'reviewer/pipeline.py');pipeline.verify(a.input)
        domains={d['id']:d for d in read(HERE.parent/'data/domains.json')['domains']}
        mechanisms=read(a.mechanisms) if a.mechanisms else {}
        for item in source['items']:
            packet_path=a.input/'evidence'/item['id']/'packet.json'
            packet=read(packet_path);original_text=packet['idea_text']
            if item['source_idea_id'] in mechanisms:
                mechanism=mechanisms[item['source_idea_id']]
                if not isinstance(mechanism,str) or not mechanism.strip():raise ValueError('Empty mechanism')
                # Only transfer receives this declared mechanism; the other prompts see the full frozen card.
                packet=dict(packet,idea_text=json.dumps({'mechanism':mechanism},ensure_ascii=False))
                req=r.requests(packet,domains[item['domain']])
                req['quality']={'system':r.P.proposal_quality_system(),'user':r.P.proposal_quality_user(original_text)}
                domain=domains[item['domain']]
                challenge='Specific research problem is chosen by the author within this assigned domain; no narrower challenge was assigned.\n'+domain.get('scope_boundary','')
                req['relevance']={'system':r.P.relevance_system(),'user':r.P.relevance_user(domain['prompt'],challenge,original_text)}
                refs,count=r.reference_block(packet)
                req['novelty_current']={'system':r.P.novelty_system(),'user':r.P.novelty_user(original_text,refs),'reference_count':count}
            else:req=r.requests(packet,domains[item['domain']])
            jobs.append({'id':item['id'],'system':item['group'],'domain':item['domain'],
                'idea_id':item['source_idea_id'],'selector_top1':item.get('selector_top1',False),'payload':req})
        m['protocol']=r.VERSION
        m['source_reviewer_manifest']=digest(source)
        m['omitted_metrics']=['historical_cutoff_novelty','paper_overall']
    else:
        rubric=load('founder_rubric',HERE/'founder/rubric.py')
        targets=[json.loads(x) for x in (HERE/'founder/data/targets.jsonl').read_text().splitlines() if x.strip()]
        targets=[t for t in targets if not t.get('supplementary')]
        tasks=defaultdict(list)
        for target in targets:tasks[target['task_id']].append(target)
        entries=read(a.input);by_task=defaultdict(dict)
        for entry in entries:
            task=entry['task_id'];system=entry['system'];cards=entry['cards']
            if task not in tasks or system in by_task[task]:raise ValueError('Unknown or repeated system/task')
            if len(cards)!=10:raise ValueError('Main Founder protocol requires exactly ten ranked cards per task')
            meta=entry['generation_protocol'];cutoff=task.split(':')[0]
            if meta.get('web_access') is not False or meta.get('literature_before')!=cutoff:
                raise ValueError('Founder generation must be offline with the declared cutoff library')
            if not meta.get('generator_training_before') or meta['generator_training_before']>=cutoff:
                raise ValueError('Generator training cutoff must precede the task cutoff')
            by_task[task][system]=cards
        for task,systems in sorted(by_task.items()):
            prompt,labels,truth=rubric.build_prompt(task,tasks[task],systems,11)
            expected=[(f'{label}{i}',t['target']) for name,label in labels.items()
                      for i in range(1,len(systems[name])+1) for t in truth]
            jobs.append({'id':'task_'+digest(task)[:20],'domain':task,'system':'blinded',
                'payload':{'prompt':prompt+'\nReturn one JSON object: {"matches":[{"card":"A1","target":"T1","level":0,"rationale":"..."}]}',
                           'labels':labels,'truth':truth,'expected_pairs':expected}})
        m['protocol']='founder-v2-ten-card-best-level';m['expected_main_tasks']=len(tasks)
        m['expected_main_targets']=len(targets)
    if not jobs:raise ValueError('Empty benchmark input')
    a.out.mkdir(parents=True)
    for job in jobs:
        payload=job.pop('payload');save(a.out/'inputs'/f"{job['id']}.json",payload)
        job['input_sha256']=digest(payload)
    m['jobs']=jobs;save(a.out/'manifest.json',m)
    print(json.dumps({'prepared':str(a.out),'jobs':len(jobs),'model_calls':0}))

def validate_founder(value,payload):
    expected={tuple(x) for x in payload['expected_pairs']};seen=set()
    for match in value.get('matches',[]):
        pair=(match.get('card'),match.get('target'))
        if pair in seen or pair not in expected:raise ValueError('Duplicate or unexpected Founder pair')
        if type(match.get('level')) is not int or match['level'] not in range(4) or not match.get('rationale'):
            raise ValueError('Invalid Founder judgment')
        seen.add(pair)
    if seen!=expected:raise ValueError('Incomplete candidate × target coverage; missing pairs are not zero')

def worker(a,job,judge):
    root=a.out/'reviews'/job['id']/judge;root.mkdir(parents=True,exist_ok=True)
    payload=read(a.out/'inputs'/f"{job['id']}.json")
    if digest(payload)!=job['input_sha256']:raise ValueError('Frozen input changed')
    e=engine()
    if a.benchmark=='interesting':
        from idea_benchmark.panel import sequential as seq, interesting_sequential as panel
        cards={c['card_id']:c for c in payload['cards']};state=seq.initial_state();seen=set()
        for stage in payload['stages']:
            if stage['kind']=='score' and seen!=set(cards):raise ValueError('Scoring before all cards were read')
            path=root/stage['stage_id'];path.mkdir(exist_ok=True)
            value,_=e.cached_call(path,'panel',judge,payload['prompt'],seq.payload_for(stage,cards,state),
                lambda v:panel.validate_result(v,stage,cards,state))
            if stage['kind']=='read':seen.update(stage['card_ids'])
            state=seq.advance(state,value,stage)
        if set(state['ledger'])!=set(cards):raise ValueError('Incomplete panel')
        result=state
    elif a.benchmark=='ideascientist':
        r=load('isci_rubric',HERE/'ideascientist/rescore.py');result={}
        for metric,req in payload.items():
            path=root/metric;path.mkdir(exist_ok=True)
            value,_=e.cached_call(path,'score',judge,req['system'],{'benchmark_input':req['user']},
                lambda v:r.validate(metric,v,req))
            result[metric]=r.validate(metric,value,req)
    else:
        result,_=e.cached_call(root,'match',judge,payload['prompt'],{},lambda v:validate_founder(v,payload))
    save(root/'assessment.json',result)
    save(root/'receipt.json',{'input_sha256':job['input_sha256'],'assessment_sha256':digest(result)})

def report(a,m):
    rows=[];missing=[]
    for job in m['jobs']:
        payload=read(a.out/'inputs'/f"{job['id']}.json")
        if digest(payload)!=job['input_sha256']:raise ValueError('Frozen input changed')
        for judge in MODELS:
            path=a.out/'reviews'/job['id']/judge
            if not (path/'receipt.json').exists():missing.append([job['id'],judge]);continue
            result=read(path/'assessment.json');receipt=read(path/'receipt.json')
            if receipt!={'input_sha256':job['input_sha256'],'assessment_sha256':digest(result)}:
                raise ValueError('Accepted result changed')
            if a.benchmark=='interesting':
                for mapping in payload['mapping']:
                    rows.append({'system':job['system'],'domain':job['domain'],'judge':judge,**mapping,
                                 'interesting':result['ledger'][mapping['card_id']]['score']})
            elif a.benchmark=='ideascientist':
                scores={k:v['score'] for k,v in result['quality'].items()}
                scores.update(relevance=result['relevance']['relevance']['score'],
                    novelty=result['novelty_current']['novelty']['score'],transfer=result['transfer']['score'])
                rows.append({'system':job['system'],'domain':job['domain'],'judge':judge,'idea_id':job['idea_id'],'selector_top1':job.get('selector_top1',False),**scores})
            else:
                validate_founder(result,payload)
                for system,label in payload['labels'].items():
                    for target in payload['truth']:
                        values=[x['level'] for x in result['matches'] if x['card'].startswith(label) and x['target']==target['target']]
                        best=max(values)
                        rows.append({'system':system,'domain':job['domain'],'judge':judge,'target':target['paper_id'],
                            'best_level':best,'direction_hit':int(best>=1),'mechanism_hit':int(best>=2)})
    metadata={'system','domain','judge','card_id','idea_id','selector_top1','target'}
    groups=defaultdict(list)
    for row in rows:groups[(row['system'],row['judge'])].append(row)
    summary=[]
    for (system,judge),values in sorted(groups.items()):
        dims=set().union(*(v.keys() for v in values))-metadata
        scores={d:statistics.mean(v[d] for v in values) if all(type(v.get(d)) in (int,float) for v in values) else None for d in dims}
        top=[v for v in values if v.get('selector_top1')]
        domains={j['domain'] for j in m['jobs'] if j['system']==system}
        if a.benchmark=='founder':domains={v['domain'] for v in values}
        valid_top=bool(top) and len(top)==len(domains) and {v['domain'] for v in top}==domains
        top_scores={d:statistics.mean(v[d] for v in top) if valid_top and all(type(v.get(d)) in (int,float) for v in top) else None for d in dims}
        summary.append({'system':system,'judge':judge,'count':len(values),'means':scores,
                        'expected_domains':len(domains),'selector_top1_count':len(top),'selector_top1_means':top_scores})
    numeric_complete=not missing and all(all(v is not None for v in g['means'].values()) for g in summary)
    result={'protocol':m['protocol'],'complete':numeric_complete,'missing':missing,'summary':summary,'rows':rows,
            'end_to_end':zero_outcomes.adjusted(summary,m.get('zero_outcomes',[]),numeric_complete)}
    if a.benchmark=='founder':
        result['main_task_coverage']={'scored_input_tasks':len(m['jobs']),'expected_tasks':m['expected_main_tasks']}
        result['main_benchmark_complete']=numeric_complete and len(m['jobs'])==m['expected_main_tasks'] and all(
            g['count']==m['expected_main_targets'] and g['expected_domains']==m['expected_main_tasks'] for g in summary)
    save(a.out/'results.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False,indent=2))

def main():
    if len(sys.argv)>1 and sys.argv[1]=='reviewer':
        raise SystemExit(subprocess.call([sys.executable,str(HERE/'reviewer/pipeline.py'),*sys.argv[2:]]))
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('benchmark',choices=('interesting','ideascientist','founder'))
    p.add_argument('action',choices=('prepare','run','report'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--input',type=Path)
    p.add_argument('--mechanisms',type=Path,help='Optional idea_id -> native mechanism text for non-JSON cards')
    p.add_argument('--judges',nargs='+',choices=tuple(MODELS),default=list(MODELS))
    p.add_argument('--workers',type=int,default=8)
    a=p.parse_args();a.out=a.out.resolve()
    if a.input:a.input=a.input.resolve()
    if a.workers<1:p.error('--workers must be positive')
    if a.action=='prepare':prepare(a);return
    m=read(a.out/'manifest.json')
    if m['benchmark']!=a.benchmark or m['implementation']!=scientific_hashes(a.benchmark):
        raise ValueError('Benchmark implementation changed; use a new evaluation')
    if a.action=='run':
        errors=[]
        with ThreadPoolExecutor(max_workers=a.workers) as pool:
            futures={pool.submit(worker,a,j,judge):(j['id'],judge) for j in m['jobs'] for judge in a.judges}
            for f in as_completed(futures):
                try:f.result()
                except Exception as exc:errors.append({'job':futures[f],'error':str(exc)})
        save(a.out/'errors.json',errors)
        if errors:print(json.dumps({'failed_jobs':len(errors)}))
    report(a,m)

if __name__=='__main__':main()
