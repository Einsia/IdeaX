"""Durable native generation/scoring supervisor. A slot is never replaced after native refusal."""
import argparse,collections,fcntl,hashlib,json,os,subprocess,sys,time
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'adapters'))
from common import save,read,now,safe
METHODS=['autoresearchclaw','dr_claw','researchagent','cycleresearcher','sciagents','ai_researcher','deepscientist']
SCORING_PY=ROOT.parents[1]/'state/venv_scoring/bin/python'
TERMINAL={'success','completed','native_failure','unsupported'}
@contextmanager
def admission_lock():
    """Serialize control reads, worker launches, and durable state across schedulers."""
    with (ROOT/'state/shared_worker_admission.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        yield

def handle(pid):
    try:
        p=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split();return {'pid':pid,'start':p[19],'state':p[0]}
    except (OSError,IndexError):return None

def alive(h):
    c=handle(h['pid']) if h else None
    return c and c['start']==h['start'] and c['state'] not in ('Z','X')

def update_recovery_registry(updates):
    with (ROOT/'state/generation_recoveries.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        current=read(ROOT/'state/generation_recoveries.json',{});current.update(updates)
        save(ROOT/'state/generation_recoveries.json',current)
    return current

def update_method_registry(method,changes):
    with (ROOT/'state/methods.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        current=read(ROOT/'state/methods.json');current[method].update(changes)
        save(ROOT/'state/methods.json',current)
    return current[method]

def commands(method,domain,index):
    spec=read(ROOT/'state/methods.json')[method];out=ROOT/'runs'/method/domain/f'slot-{index:02}'
    return [str(c).replace('{output}',str(out)) for c in spec['command']]+['--domain-json',str(ROOT/'inputs'/domain/'domain.json'),'--output-dir',str(out)]

def result_path(job):
    if job['kind']=='generation':return ROOT/'runs'/job['method']/job['domain']/f'slot-{job["slot"]:02}'/'result.json'
    if job['kind']=='card':return ROOT/'evaluations'/job['method']/job['domain']/f'slot-{job["slot"]:02}'/'result.json'
    return ROOT/'evaluations'/job['method']/job['domain']/'novelty'/'result.json'

def terminal_exclusion(job):
    """A bound exclusion can release the next original slot, never this slot."""
    if job.get('kind')!='generation' or job.get('method')!='autoresearchclaw':return None
    if alive(job.get('process')):return None
    spec=read(ROOT/'state/generation_exclusions.json',{}).get(job['key'])
    if not spec or spec.get('classification')!='infrastructure_excluded' or spec.get('approved') is not True:return None
    receipt=result_path(job);out=receipt.parent
    value=read(receipt,{})
    if value.get('status')!='infrastructure_failure':return None
    retrieval=value.get('native_retrieval',{})
    if not (retrieval.get('retrieval_degraded') and retrieval.get('real_candidate_papers')==0 and retrieval.get('web_scholar_crawl_results')==0):return None
    bound=spec.get('preserved_sha256',{})
    required={'result.json','proposal.md','native/stage-08/hypotheses.md','native/stage-09/exp_plan.yaml'}
    if not required.issubset(bound):return None
    for relative,digest in bound.items():
        path=(out/relative).resolve()
        if not path.is_relative_to(out.resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:return None
    if not spec.get('audit_path'):return None
    return spec

def manifest():
    domains=read(ROOT/'inputs/domains.json');old=read(ROOT/'state/campaign.json',{})
    jobs=old.get('jobs',{})
    for method in METHODS:
        for domain in domains:
            for slot in range(1,6):
                key=f'{method}__{domain["id"]}__{slot:02}'
                for kind in ('generation','card'):
                    jobs.setdefault(key+'__'+kind,{'key':key+'__'+kind,'kind':kind,'method':method,'domain':domain['id'],'slot':slot,'status':'pending','launches':0})
            key=f'{method}__{domain["id"]}__novelty'
            jobs.setdefault(key,{'key':key,'kind':'novelty','method':method,'domain':domain['id'],'status':'pending','launches':0})
    old.update(jobs=jobs,created=old.get('created',now()),expected_generation_slots=1330,expected_domains=38,expected_slots_per_method=190)
    return old

def refresh(job):
    if job.get('process') and alive(job['process']):job['status']='running';return
    value=read(result_path(job),{});status=value.get('status')
    if status in ('success','completed'):job['status']='completed';return
    if status in ('native_failure','unsupported','input_preparation_blocker','adapter_failure'):job['status']=status;job['reason']=value.get('terminal_reason');return
    if status=='infrastructure_failure':
        job['status']='infrastructure_failure';job['reason']=value.get('terminal_reason')
        exclusion=terminal_exclusion(job)
        job['terminal_infrastructure_exclusion']=bool(exclusion)
        job['exclusion_audit']=exclusion.get('audit_path') if exclusion else None
        return
    if job.get('process') and alive(job['process']):job['status']='running';return
    if job['status']=='running':
        job['status']='infrastructure_failure';job['reason']='Process ended without terminal receipt';job['failed_at_epoch']=time.time()
        error=read(result_path(job).parent/'job_error.json',{})
        if error:job['reason']=error.get('error');job['status']=error.get('status','evaluation_failure')

def ready(job,jobs,methods):
    if job['status']!='pending':return False
    spec=methods[job['method']]
    if job['kind']=='generation':
        if not spec.get('enabled'):return False
        if spec.get('eligible_domains') is not None and job['domain'] not in spec['eligible_domains']:return False
        if spec.get('eligible_slots') is not None and job['slot'] not in spec['eligible_slots']:return False
        domain_slots=spec.get('eligible_slots_by_domain')
        if domain_slots is not None and job['slot'] not in domain_slots.get(job['domain'],[]):return False
        if job['slot']>1 and spec.get('status')!='offline_native_full' and job['domain'] not in spec.get('full_native_accepted_domains',[]):
            prev=jobs[f'{job["method"]}__{job["domain"]}__{job["slot"]-1:02}__generation']
            if prev['status'] not in ('completed','native_failure') and not terminal_exclusion(prev):return False
        return True
    if not spec.get('scoring_approved',True):return False
    if spec.get('scoring_approved_domains') is not None and job['domain'] not in spec['scoring_approved_domains']:return False
    if job['kind']=='card':return jobs[job['key'].replace('__card','__generation')]['status']=='completed'
    return all(jobs[f'{job["method"]}__{job["domain"]}__{n:02}__generation']['status']=='completed' for n in range(1,6))

def existing_workspace_needs_adoption(job,out,recovery=None):
    """New independent slots cannot silently reuse an existing native workspace."""
    return (job['kind']=='generation' and not recovery and out.exists()
            and any(out.iterdir()) and not job.get('process'))

def record_scoring_readiness(jobs,methods):
    """Bind queue age to completed inputs and their acceptance gate, never slot order."""
    for job in jobs.values():
        if job['kind']=='generation' or not ready(job,jobs,methods):continue
        if job.get('scoring_ready_since_epoch') is not None:continue
        slots=[job['slot']] if job['kind']=='card' else range(1,6)
        dependencies=[result_path(jobs[f'{job["method"]}__{job["domain"]}__{slot:02}__generation']) for slot in slots]
        sources=[{'path':str(p),'available_epoch':p.stat().st_mtime,'basis':'accepted_generation_result_mtime'} for p in dependencies]
        spec=methods[job['method']]
        reference=spec.get('domain_terminal_acceptances',{}).get(job['domain']) or spec.get('offline_smoke_acceptance')
        path=Path(reference['path'] if isinstance(reference,dict) else reference) if reference else None
        if path and path.is_file():
            receipt=read(path,{})
            try:accepted=datetime.fromisoformat(receipt['at'].replace('Z','+00:00')).timestamp()
            except (KeyError,ValueError,TypeError):accepted=path.stat().st_mtime
            sources.append({'path':str(path),'available_epoch':accepted,'basis':'native_acceptance_gate'})
        epoch=max(row['available_epoch'] for row in sources)
        job.update(scoring_ready_since_epoch=epoch,scoring_ready_since=datetime.fromtimestamp(epoch,timezone.utc).isoformat(),scoring_ready_first_observed=now(),scoring_ready_sources=sources)

def admission_order(job,recovery_specs):
    if job['kind']=='generation':
        return (True,not bool(recovery_specs.get(job['key'])),job.get('slot',0),0,job['key'])
    return (False,True,0 if job['kind']=='novelty' else 1,job.get('scoring_ready_since_epoch',float('inf')),job['key'])

def ready_recovery(job,recoveries,methods):
    """Only explicitly audited same-run infrastructure continuations may launch."""
    spec=recoveries.get(job['key'])
    if not spec or job['kind']!='generation' or job['status']!='infrastructure_failure':return None
    if terminal_exclusion(job):return None
    if not methods[job['method']].get('enabled') or spec.get('approved') is not True or spec.get('ready') is not True:return None
    if spec.get('recovery_id') in job.get('executed_recovery_ids',[]):return None
    if time.time()<spec.get('not_before_epoch',0):return None
    if not spec.get('command') or not spec.get('recovery_id') or not spec.get('audit_path'):return None
    receipt=result_path(job)
    if not receipt.exists() or hashlib.sha256(receipt.read_bytes()).hexdigest()!=spec.get('expected_result_sha256'):return None
    if job.get('process') and alive(job['process']):return None
    return spec

def report(state):
    methods=read(ROOT/'state/methods.json');rows=[]
    for method in METHODS:
        gen=[j for j in state['jobs'].values() if j['method']==method and j['kind']=='generation'];count=collections.Counter(j['status'] for j in gen)
        rows.append({'method':method,'source_status':methods[method]['status'],'enabled':methods[method]['enabled'],'generation':dict(count),'terminal_infrastructure_exclusions':sum(bool(j.get('terminal_infrastructure_exclusion')) for j in gen),'target':190,'cis_completed':sum(j['status']=='completed' for j in state['jobs'].values() if j['method']==method and j['kind']=='card'),'novelty_panels_completed':sum(j['status']=='completed' for j in state['jobs'].values() if j['method']==method and j['kind']=='novelty')})
    save(ROOT/'state/progress.json',{'at':now(),'protocol_id':'offline-common-corpus-20261117','methods':rows,'scheduler':state.get('scheduler'),'expected_slots':1330})
    lines=['# Offline AR baselines: 38 domains × 5 slots','',f'Updated UTC: {now()}. Astra / xhigh for generation and one independent scoring pass.','', '|Method|Source/integration state|Completed|Running|Native failures|Infrastructure failures|C/I/S|Novelty panels|','|---|---|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        c=r['generation'];lines.append(f'|{r["method"]}|{r["source_status"]}|{c.get("completed",0)}/190|{c.get("running",0)}|{c.get("native_failure",0)}|{c.get("infrastructure_failure",0)}|{r["cis_completed"]}|{r["novelty_panels_completed"]}/38|')
    for method,spec in methods.items():
        if spec.get('live_stage_note'):lines+=['',f'{method}: {spec["live_stage_note"]}']
    exclusions=sum(r['terminal_infrastructure_exclusions'] for r in rows)
    if exclusions:lines+=['',f'{exclusions} infrastructure failures are permanently excluded by preserved-file hashes. Only the next distinct original slot may proceed; these slots remain unscored and prevent a complete own-five Novelty panel.']
    lines+=['','Official sources and native prompts are frozen under `sources/`; each necessary input/API adaptation is recorded in `reports/*_audit.md`. `state/methods.json` stores exact launch commands. Unsupported methods remain explicit, with blockers; they are not replaced by generic prompts.','', 'Five independent native proposal outputs are requested per domain. Native candidate pools, critique, and selection are preserved. Native terminal failures are not regenerated. Transport/retrieval failures are not scored zero; recovery requires an audited same-run continuation.','', 'The frozen existing Reviewer rubric maps raw N/I/S to paper C/I/S (1–5). Novelty uses each system’s own five proposals per domain, reads all five before scoring, and divides raw 0–100 scores by 20. No mixed-panel substitution or post-score selection.','', 'Research tools use the common frozen raw corpus. Public research access and old online histories are hidden. Native offline input/API adaptations and their verification receipts are recorded in this phase; the raw-evidence collector is verified and scoring is enabled for accepted proposals; scoring waits for a complete native output.','', 'This phase starts fresh native contexts. Its offline results and uncapped Dr. Claw runs are reported separately from frozen online history.','']
    (ROOT/'STATUS.md').write_text('\n'.join(lines))
    return rows

def supervise():
    import offline_gates
    gate=offline_gates.check()
    save(ROOT/'state/activation_gate_state.json',gate)
    if not gate['passed']:raise RuntimeError('Offline activation gates have not passed: '+str(gate['errors']))
    with (ROOT/'state/scheduler.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=manifest();children={};state['scheduler']=handle(os.getpid());last_report=0;last_gate_check=0
        while True:
            with admission_lock():
                methods=read(ROOT/'state/methods.json');control=read(ROOT/'state/control.json',{});jobs=state['jobs']
                if control.get('enabled') and time.time()-last_gate_check>=30:
                    gate=offline_gates.check();save(ROOT/'state/activation_gate_state.json',gate);last_gate_check=time.time()
                    if not gate['passed']:
                        control.update(enabled=False,pause_reason='Offline activation binding failed; unstarted jobs withheld.',gate_errors=gate['errors'])
                        save(ROOT/'state/control.json',control)
                for key,adoption in read(ROOT/'state/adoptions.json',{}).items():
                    if key in jobs and adoption['at']>jobs[key].get('adopted','') and alive(adoption['process']):
                        jobs[key].update(status='running',process=adoption['process'],launches=1,adopted=adoption['at'])
                        if adoption.get('log') and adoption['log']!=jobs[key].get('log'):
                            jobs[key].setdefault('prior_logs',[]).append(jobs[key].get('log'))
                            jobs[key]['log']=adoption['log']
                for key,p in list(children.items()):
                    if p.poll() is not None:children.pop(key)
                for job in jobs.values():
                    if methods[job['method']]['status'].startswith('unsupported') and job['kind']=='generation' and job['status']=='pending':job.update(status='unsupported',reason=methods[job['method']].get('blocker'))
                    refresh(job)
                    if job['kind']!='generation' and job['status']=='infrastructure_failure' and job.get('launches',0)<3 and time.time()-job.get('failed_at_epoch',time.time())>=60:
                        job.update(status='pending',retry_reason='Same frozen scoring input; accepted prior stages cached')
                active=collections.Counter('generation' if j['kind']=='generation' else 'scoring' for j in jobs.values() if j['status']=='running')
                active_method=collections.Counter(j['method'] for j in jobs.values() if j['kind']=='generation' and j['status']=='running')
                if control.get('enabled',True):
                    recoveries=read(ROOT/'state/generation_recoveries.json',{})
                    recovery_specs={key:ready_recovery(job,recoveries,methods) for key,job in jobs.items() if key in recoveries}
                    record_scoring_readiness(jobs,methods)
                    ordered=sorted(jobs.values(),key=lambda j:admission_order(j,recovery_specs))
                    for job in ordered:
                        kind='generation' if job['kind']=='generation' else 'scoring';limit=control.get('generation_workers',76) if kind=='generation' else control.get('scoring_workers',20)
                        recovery=recovery_specs.get(job['key'])
                        if active[kind]>=limit or not (recovery or ready(job,jobs,methods)):continue
                        if kind=='generation' and active_method[job['method']]>=methods[job['method']].get('max_generation_workers',230):continue
                        # Do not adopt an existing native workspace without a reviewed completion/continuation contract.
                        out=result_path(job).parent
                        if existing_workspace_needs_adoption(job,out,recovery):
                            job.update(status='needs_adoption',reason='Existing native workspace; live smoke requires explicit process adoption');continue
                        if recovery:cmd=recovery['command']
                        elif kind=='generation':cmd=commands(job['method'],job['domain'],job['slot'])
                        else:
                            cmd=[str(SCORING_PY),str(ROOT/'scoring/runtime.py'),'card' if job['kind']=='card' else 'novelty','--method',job['method'],'--domain',job['domain']]
                            if job['kind']=='card':cmd+=['--slot',str(job['slot'])]
                            sources=ROOT/'runs'/job['method']/job['domain']
                            if job['kind']=='card':sources=sources/f'slot-{job["slot"]:02}'
                            cmd=['/usr/bin/python3',str(ROOT/'runtime/offline_exec.py'),'--output',str(out),
                                 '--model-socket','/tmp/insightpro-offline-model-20261117.sock',
                                 '--read-only',str(ROOT/'scoring'),'--read-only',str(sources),'--',*cmd]
                        log=ROOT/'logs'/f'{job["key"]}-{job["launches"]+1}.log'
                        with log.open('wb') as stream:proc=subprocess.Popen(cmd,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
                        job.update(status='running',started=now(),process=handle(proc.pid),command=cmd,log=str(log),launches=job['launches']+1);children[job['key']]=proc;active[kind]+=1
                        if recovery:
                            job.setdefault('executed_recovery_ids',[]).append(recovery['recovery_id'])
                            job.setdefault('recovery_launches',[]).append({'at':now(),'recovery_id':recovery['recovery_id'],'process':handle(proc.pid),'audit_path':recovery['audit_path'],'command':cmd})
                        if kind=='generation':active_method[job['method']]+=1
                        state.update(at=now(),active=dict(active));save(ROOT/'state/campaign.json',state)
                state.update(at=now(),active=dict(active));save(ROOT/'state/campaign.json',state)
            if time.time()-last_report>20:report(state);last_report=time.time()
            time.sleep(3)

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['run','report','adopt']);p.add_argument('--method');p.add_argument('--domain');p.add_argument('--slot',type=int);p.add_argument('--pid',type=int);a=p.parse_args()
    if a.action=='run':supervise()
    elif a.action=='report':
        state=manifest()
        for j in state['jobs'].values():refresh(j)
        save(ROOT/'state/campaign.json',state);print(json.dumps(report(state),indent=2))
    else:
        state=manifest();key=f'{a.method}__{a.domain}__{a.slot:02}__generation';h=handle(a.pid)
        if not h or not alive(h):raise ValueError('Process not running')
        state['jobs'][key].update(status='running',process=h,launches=1,adopted=now());save(ROOT/'state/campaign.json',state);print(key)
if __name__=='__main__':main()
