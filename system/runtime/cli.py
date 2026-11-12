"""Current single/light releases. Preparation is offline; run is explicit."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import threading

from common import *


def release(): return read(SYSTEM/'release.json')


def check():
    r=release();verify({SYSTEM/'prompts/generation.md':r['template_sha256']})
    import single
    total=0
    for d in r['domains']:
        if ACCESS!='full':
            if (SYSTEM/'domains'/d['id']/'full_context.jsonl').exists():raise ValueError('Ablation must not carry injected full context')
            continue
        path=SYSTEM/'domains'/d['id']/'full_context.jsonl'
        verify({path:d['context_sha256']});rows=single.records(path)
        counts=Counter(x['kind'] for x in rows)
        if counts['insight']!=d['insights'] or counts['problem']!=d['problems'] or len({x['id'] for x in rows})!=len(rows):
            raise ValueError('Domain material incomplete: '+d['id'])
        total+=len(rows)
    for path in (os.environ['IDEAX_CODEX_RAW_BIN'],single.isolate.PY_PREFIX):
        if not Path(path).exists(): raise ValueError('Runtime dependency missing: '+str(path))
    if not shutil.which('bwrap'): raise ValueError('bubblewrap is required')
    import light
    for name in ('DISCUSS','RESPOND','SELECT'):
        getattr(light.prompts,name).format(author='author-01',own='c-001',domain='Efficiency')
        if r['kind']=='light-multi' and (SYSTEM/'prompts'/f'{name.lower()}.md').read_text()!=getattr(light.prompts,name):
            raise ValueError('Published collaboration prompt differs from runtime: '+name)
    return dict(ok=True,version=r['version'],domain_count=len(r['domains']),context_entries=total,
                author_prompt_sha256=r['template_sha256'],benchmark=r['benchmark'],model_calls=0)


def initialize(out, domains):
    check();r=release();known={d['id'] for d in r['domains']}
    requested=list(known) if domains==['all'] else domains
    if not requested or len(set(requested))!=len(requested) or not set(requested)<=known:
        raise ValueError('Supply unique supported domains, or all')
    if out.exists(): raise ValueError('Use a new execution directory')
    import single
    jobs={};out.mkdir(parents=True)
    for domain in sorted(requested):
        root=out/'runs'/domain
        if r['kind']=='single': single.prepare(root,domain)
        else:
            (root/'logs').mkdir(parents=True)
            for author in AUTHORS: single.prepare(root/'authors'/author,domain)
            save(root/'domain_state.json',dict(status='prepared',phase='generate',stages={},authors={}))
        jobs[domain]=dict(domain=domain,run=str(root),status='prepared')
    impl={str(p):sha(p) for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py','.sh')}
    save(out/'manifest.json',dict(version=r['version'],kind=r['kind'],system=str(SYSTEM),created=now(),
         domains=sorted(requested),authors_per_domain=r['authors_per_domain'],ideas_per_domain=5,
         discussion_rounds=r['discussion_rounds'],prompt_version=r['prompt_version'],
         prompt_sha256=r['template_sha256'],benchmark=r['benchmark'],implementation=impl))
    save(out/'state.json',dict(status='prepared',jobs=jobs,model_calls=0))
    return dict(prepared=str(out),domains=len(jobs),authors=len(jobs)*r['authors_per_domain'],model_calls=0)


def checked_manifest(out):
    m=read(out/'manifest.json')
    if m['version']!=release()['version'] or Path(m['system']).resolve()!=SYSTEM:
        raise ValueError('Execution belongs to a different system release')
    verify(m['implementation']);return m


@contextmanager
def reserve(slots, external):
    """Reserve whole runs across both current systems. Legacy usage is declared explicitly."""
    if slots<=0 or external<0 or slots+external>300: raise ValueError('GPT reservations must fit within 300')
    path=HERE/'admission.json';lockpath=HERE/'admission.lock';ident=str(os.getpid())
    with lockpath.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        active={k:v for k,v in read(path,{}).items() if alive(v['handle'])}
        other=max([external]+[v['external'] for v in active.values()])
        if other+sum(v['slots'] for v in active.values())+slots>300:
            raise ValueError('Insufficient GPT capacity; no split run or model call admitted')
        active[ident]=dict(handle=handle(os.getpid()),slots=slots,external=external,system=str(SYSTEM))
        save(path,active)
    try: yield
    finally:
        with lockpath.open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);active=read(path,{})
            active.pop(ident,None);save(path,active)


def run_batch(out, limit, external):
    m=checked_manifest(out);weight=m['authors_per_domain'];parallel=limit//weight
    if parallel<1: raise ValueError('Budget must fit at least one complete run')
    with (out/'scheduler.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=read(out/'state.json')
        pending=[(d,j) for d,j in state['jobs'].items() if j['status']!='completed']
        if not pending: return export(out,out/'benchmark_input.json')
        parallel=min(parallel,len(pending))
        with reserve(parallel*weight,external):
            state_guard=threading.Lock()
            state.update(status='running',scheduler_handle=handle(os.getpid()),reserved_gpt=parallel*weight,external_gpt_reserved=external)
            save(out/'state.json',state)
            def one(pair):
                domain,job=pair;root=Path(job['run']);(out/'logs').mkdir(exist_ok=True)
                with state_guard: job.update(status='running',started=now())
                with (out/'logs'/f'{domain}.log').open('ab') as log:
                    proc=subprocess.Popen([sys.executable,'-B',str(HERE/'cli.py'),'domain','--root',str(root),'--domain',domain],
                        stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
                    with state_guard: job['handle']=handle(proc.pid)
                    code=proc.wait()
                detail=read(root/('session.json' if m['kind']=='single' else 'domain_state.json'),{})
                with state_guard: job.update(status='completed' if code==0 else 'needs_review',exit_code=code,error=detail.get('error'),finished=now())
            with ThreadPoolExecutor(max_workers=parallel) as pool:
                futures=[pool.submit(one,j) for j in pending]
                while not all(f.done() for f in futures):
                    with state_guard:
                        state['counts']=dict(Counter(j['status'] for j in state['jobs'].values()))
                        save(out/'state.json',state)
                    time.sleep(2)
                for f in futures: f.result()
            state.update(status='completed' if all(j['status']=='completed' for j in state['jobs'].values()) else 'needs_review',finished=now())
            save(out/'state.json',state)
        if state['status']=='completed': return export(out,out/'benchmark_input.json')
        return dict(status='needs_review',errors={d:j.get('error') for d,j in state['jobs'].items() if j['status']!='completed'})


def export(out, dest):
    m=checked_manifest(out);cards=[];sources={}
    from multi_source import validate_source
    for domain in m['domains']:
        root=out/'runs'/domain;source=read(root/'evaluation_source.json')
        validate_source(source)
        if m['kind']=='light-multi' and not read(root/'completion_check.json').get('ok'):
            raise ValueError('Light pipeline has not completed')
        items=read(source['ideas'])
        if len(items)!=5: raise ValueError('Five accepted ideas per domain required')
        task=read(SYSTEM/'domains'/domain/'task.json')
        for i,idea in enumerate(items,1):
            cards.append(dict(task_id=domain,domain=task['name'],idea_id=f'{domain}-{i:02d}',
                system=m['version'],idea_text=json.dumps({k:v for k,v in idea.items() if k not in ('author','id')},ensure_ascii=False,indent=2),
                domain_ids=task['litgraph_domain_ids'],
                selector_top1=(read(root/'selector_top1.json')['original_rank']==i) if m['kind']=='single' else i==1))
        sources[str(root/'evaluation_source.json')]=sha(root/'evaluation_source.json')
    freeze(dest,cards);freeze(dest.with_suffix('.provenance.json'),dict(sources=sources,benchmark=m['benchmark']))
    return dict(exported=str(dest),cards=len(cards),benchmark=m['benchmark'],model_calls=0)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('check','domains','prepare','run','status','export','prepare-review','domain','author'))
    p.add_argument('--execution',type=Path);p.add_argument('--out',type=Path)
    p.add_argument('--domains',nargs='+',default=['all']);p.add_argument('--gpt-budget',type=int,default=38)
    p.add_argument('--external-gpt-reserved',type=int)
    p.add_argument('--root',type=Path);p.add_argument('--domain');p.add_argument('--author',choices=AUTHORS)
    p.add_argument('--phase',choices=('generate','discuss','respond'));a=p.parse_args()
    os.umask(0o007)
    if a.execution: a.execution=a.execution.resolve()
    if a.out: a.out=a.out.resolve()
    if a.action=='check': result=check()
    elif a.action=='domains': result=[dict(id=d['id'],name=d['name']) for d in release()['domains']]
    elif a.action=='prepare':
        if not a.out: p.error('prepare requires --out')
        result=initialize(a.out,a.domains)
    elif a.action in ('domain','author'):
        if not a.root or not a.domain: p.error('Internal worker requires root and domain')
        if a.action=='author':
            if not a.author or not a.phase: p.error('Author and phase required')
            import light
            light.author_worker(a.root,a.author,a.phase)
        elif release()['kind']=='single':
            import single
            code=single.worker(a.root)
            if code: sys.exit(code)
            from single_selector import select
            select(a.root,a.domain)
        else:
            import light
            with (a.root/'domain.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);light.domain_worker(a.root,a.domain)
        result={'ok':True}
    else:
        if not a.execution: p.error('This action requires --execution')
        checked_manifest(a.execution)
        if a.action=='run':
            if a.external_gpt_reserved is None: p.error('Declare current external GPT reservation with --external-gpt-reserved')
            result=run_batch(a.execution,a.gpt_budget,a.external_gpt_reserved)
        elif a.action=='status':
            result=read(a.execution/'state.json')
            for j in result['jobs'].values():
                root=Path(j['run']);j['detail']=read(root/('session.json' if release()['kind']=='single' else 'domain_state.json'),{})
                if release()['kind']=='light-multi':
                    j['detail']['authors']={author:dict(generation=read(root/'authors'/author/'session.json',{}),
                        collaboration=read(root/'authors'/author/'collaboration/state.json',{}),
                        recovery_blocker=read(root/'authors'/author/'recovery_blocked.json',{})) for author in AUTHORS}
        elif a.action=='export': result=export(a.execution,a.out or a.execution/'benchmark_input.json')
        else:
            if not a.out: p.error('prepare-review requires a new --out')
            export(a.execution,a.execution/'benchmark_input.json')
            subprocess.run([sys.executable,str(HERE.parents[1]/'benchmarks/reviewer/pipeline.py'),'prepare','--input',str(a.execution/'benchmark_input.json'),'--out',str(a.out)],check=True)
            result={'prepared_review':str(a.out),'model_calls':0}
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
