"""One continuous independent research session per domain; original single schema."""
from collections import Counter
from pathlib import Path
import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from common import *
sys.path[:0] = [str(HERE/'transport'), str(SYSTEM/'litgraph/tools')]
import isolate
import recovery as R
from retry_runtime_audit import audit as runtime_audit
from log_evidence import collect
from access_policy import check_sources, check_network, denied_hosts

REQUIRED = ('title', 'problem', 'mechanism', 'previous_work', 'novelty_check',
            'experiment', 'failure_conditions', 'scientific_potential')
NOVELTY = ('search_queries', 'closest_work', 'already_done_test', 'remaining_contribution', 'unresolved_risks')

def configure():
    if getattr(configure, 'done', False): return
    configure.done = True
    cfg = isolate.sub2api_env()
    if cfg.get('SUB2API_BASE_URL', '').rstrip('/') != PROVIDER or not cfg.get('SUB2API_API_KEY'):
        raise ValueError('Configured sbtunnel profile is required')
    isolate.CODEX_DIR = str(Path(os.environ['IDEAX_CODEX_RAW_BIN']).parent)
    isolate.CODEX_CONFIG = 'model_context_window = 1050000\nmodel_auto_compact_token_limit = 900000\n' + isolate.CODEX_CONFIG
    os.environ.update(LITGRAPH_CODEX_NATIVE_WEB='0', LITGRAPH_CODEX_REQUIRE_CLEAN_TRANSPORT='1',
                      LITGRAPH_CODEX_ATOMIC_RESPONSES='1', LITGRAPH_WEB_DENY_HOSTS=','.join(denied_hosts()))
    original = isolate.agent_env
    def clean_env():
        env = original()
        for key in ('LITGRAPH_DB', 'LITGRAPH_TEMPLATES', 'LITGRAPH_MAIL'): env.pop(key, None)
        return env
    isolate.agent_env = clean_env

def records(path):
    if not path.exists(): return []
    rows=[]
    for line in path.read_text(errors='replace').splitlines():
        try: rows.append(json.loads(line))
        except ValueError: pass
    return rows

def artifact_errors(run, result, network=True):
    errors = []
    if not result.get('ok'): errors.append('Model turn incomplete')
    out = run/'work/out'; items = read(out/'IDEAS.json', [])
    if not isinstance(items, list) or len(items) != 5: return errors+['IDEAS.json must contain exactly five objects'], []
    titles=[]
    for i, item in enumerate(items,1):
        if not isinstance(item,dict): errors.append(f'idea {i}: not an object');continue
        titles.append(item.get('title'))
        for key in REQUIRED:
            if not item.get(key): errors.append(f'idea {i}: missing {key}')
        refs=item.get('previous_work')
        if not isinstance(refs,list) or len(refs)<3: errors.append(f'idea {i}: at least three previous works required')
        elif any(not isinstance(r,dict) or not all(r.get(k) for k in ('title','url','read_depth','source_location','overlap','difference')) for r in refs):
            errors.append(f'idea {i}: incomplete previous work')
        novelty=item.get('novelty_check')
        if not isinstance(novelty,dict) or any(k not in novelty for k in NOVELTY): errors.append(f'idea {i}: incomplete novelty_check')
        errors.extend(f'idea {i}: '+e for e in check_sources(item,run))
    if len(set(str(x) for x in titles))!=5: errors.append('Five distinct idea titles required')
    for name in ('IDEA.md','SEARCH_LOG.md'):
        path=out/name
        if not path.is_file() or path.stat().st_size<200: errors.append('Missing/empty '+name)
    if network: errors.extend(check_network(run))
    return errors,items

def audit(run):
    runtime=runtime_audit(run); recovery=R.audit_recovery(run,runtime)
    save(run/'runtime_audit.json',runtime);save(run/'recovery_audit.json',recovery)
    if not recovery['ok']: raise ValueError('; '.join(recovery['errors']))

def accept(run, items):
    meta=read(run/'run.json');out=run/'accepted';out.mkdir(exist_ok=True)
    shutil.copy2(run/'work/out/IDEAS.json',out/'IDEAS.json')
    files={str(p):sha(p) for p in [run/'run.json',run/'verification.json',run/'work/out/IDEAS.json',run/'work/out/IDEA.md',run/'work/out/SEARCH_LOG.md']}
    selected=[]
    for i,card in enumerate(items,1):
        path=out/f'idea-{i:02d}.json';save(path,card);files[str(path)]=sha(path)
        selected.append({'rank':i,'path':str(path),'sha256':sha(path)})
    receipt=out/'acceptance.json';save(receipt,{'source_kind':'single-original','source_files':files,'selected':selected,'ideas_sha256':sha(out/'IDEAS.json')})
    source={'source_kind':'single-original','domain':meta['domain_id'],'condition':CONDITION,'run':str(run),
        'ideas':str(out/'IDEAS.json'),'ideas_sha256':sha(out/'IDEAS.json'),'source_files':files,
        'acceptance_file':str(receipt),'acceptance_sha256':sha(receipt),'accepted_at':now(),'provider':PROVIDER}
    from multi_source import validate_source
    validate_source(source);save(run/'evaluation_source.json',source)


def prepare_work(run, domain):
    """A separate filesystem and native home for every author or selector."""
    source = SYSTEM/'domains'/domain
    for name in ('work/tools','work/out','work/ideas/pool','homes/single_agent','stages/1'):
        (run/name).mkdir(parents=True,exist_ok=True)
    if ACCESS=='full': shutil.copy2(source/'full_context.jsonl',run/'work/full_domain_context.jsonl')
    if ACCESS!='web':
        for name in ('library_client.py','idea_provenance.py'):
            shutil.copy2(SYSTEM/'litgraph/tools'/name,run/'work/tools'/name)
    shutil.copy2(SYSTEM/'ideax/scripts/single_web_search.py',run/'work/tools/web_search.py')
    if ACCESS!='web': save(run/'work/library_api.json',{'base_url':os.environ['LITGRAPH_API_BASE_URL'],'request_log':'out/api_requests.jsonl'})


def prepare(run, domain):
    if run.exists(): raise ValueError('Use a fresh run directory: '+str(run))
    release=read(SYSTEM/'release.json')
    entry=next(d for d in release['domains'] if d['id']==domain)
    template=SYSTEM/'prompts/generation.md'; source=SYSTEM/'domains'/domain/'full_context.jsonl'
    verify({template:release['template_sha256']})
    if ACCESS=='full': verify({source:entry['context_sha256']})
    context=source.read_text() if ACCESS=='full' else ''; rows=records(source) if ACCESS=='full' else []
    counts=Counter(r['kind'] for r in rows)
    if len({r['id'] for r in rows})!=len(rows): raise ValueError('Duplicate context entries')
    if ACCESS=='full' and (counts['insight']!=entry['insights'] or counts['problem']!=entry['problems']):
        raise ValueError('Incomplete domain context')
    values=dict(current_date=now()[:10],domain_name=entry['name'],domain_id=domain,
                api_base=os.environ['LITGRAPH_API_BASE_URL'] if ACCESS!='web' else None,entries=len(rows),
                insights=counts['insight'],problems=counts['problem'],context_chars=len(context),
                full_domain_context_jsonl=context)
    prompt=template.read_text()
    # Literal API route braces such as {id} are not template variables.
    for key,value in values.items(): prompt=prompt.replace('{'+key+'}',str(value))
    prepare_work(run,domain);(run/'initial_prompt.md').write_text(prompt)
    inputs={str(p):sha(p) for p in (run/'work').rglob('*') if p.is_file()}
    inputs[str(run/'initial_prompt.md')]=sha(run/'initial_prompt.md')
    implementation={str(p):sha(p) for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py','.sh')}
    save(run/'run.json',dict(created=now(),domain_id=domain,domain_name=entry['name'],
        condition=CONDITION,matrix_condition=CONDITION,matrix_domain=domain,
        model='gpt-6-astra',effort='xhigh',runner='codex',provider=PROVIDER,
        scouts=['single_agent'],ideas_per_agent=5,stages=1,workflow='single-autonomous-new-v4',
        prompt_version=release['prompt_version'],prompt_sha256=sha(run/'initial_prompt.md'),
        prompt_template_sha256=release['template_sha256'],library_api=values['api_base'],
        input_files=inputs,implementation=implementation,access=ACCESS,context_sha256=sha(source) if ACCESS=='full' else None,
        injected_insights=counts['insight'],injected_problems=counts['problem']))
    save(run/'session.json',dict(status='prepared',stages={}))
    save(run/'work/research_phase.json',{'phase':'single-new-v4-generation'})
    save(run/'work/ideas/idea_run_state.json',{'single_agent':{'search_done':False}})


def validate_cards(path, run):
    """Collaboration preserves the full new schema; identity lives in card_id."""
    items=read(path)
    if not isinstance(items,list) or len(items)!=5: raise ValueError('Exactly five complete cards required')
    if len({str(i.get('title')) for i in items if isinstance(i,dict)})!=5: raise ValueError('Five distinct titles required')
    for item in items:
        if not isinstance(item,dict) or not all(item.get(k) for k in REQUIRED): raise ValueError('Incomplete new single schema')
        refs=item['previous_work']; novelty=item['novelty_check']
        if not isinstance(refs,list) or len(refs)<3 or any(not isinstance(r,dict) or not all(r.get(k) for k in ('title','url','read_depth','source_location','overlap','difference')) for r in refs):
            raise ValueError('Missing previous-work evidence')
        if not isinstance(novelty,dict) or not all(k in novelty for k in NOVELTY): raise ValueError('Missing novelty self-review')
        errors=check_sources(item,run)
        if errors: raise ValueError('; '.join(errors))
    return items


def worker(run):
    configure(); meta=read(run/'run.json'); verify(meta['input_files']);verify(meta['implementation'])
    with (run/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if read(run/'verification.json',{}).get('ok') and (run/'evaluation_source.json').exists():
            from multi_source import validate_source
            validate_source(read(run/'evaluation_source.json'));return 0
        state=read(run/'session.json');thread=state.get('session_id')
        # Recover a recorded session after a coordinator interruption; never silently restart it.
        if not thread:
            prior=[read(p).get('session') for p in sorted((run/'stages/1').glob('attempt-*/model_result.json'))]
            identities={s for s in prior if s}
            if len(identities)>1: raise ValueError('Ambiguous native identity')
            thread=next(iter(identities),None)
        if not thread and list((run/'homes/single_agent/.codex/sessions').glob('**/*.jsonl')):
            raise ValueError('Interrupted session needs identity reconciliation; no new session launched')
        if (run/'recovery_blocked.json').exists(): raise ValueError('Unresolved transport blocker; inspect evidence before continuing')
        state.update(status='running',worker_pid=os.getpid(),process_handle=handle(os.getpid()),current_phase=1)
        save(run/'session.json',state)
        original=(run/'initial_prompt.md').read_text();error=''
        previous=len(list((run/'stages/1').glob('attempt-*')))
        try:
            with isolate.Gate(str(run),['single_agent'],allow_web=True):
                for repair in range(3):
                    attempt=run/f'stages/1/attempt-{previous+repair+1:03d}'
                    prompt=original if not thread else ('继续同一研究会话，保留研究内容，完成 /work/out 的原定五卡交付。不要重启研究或调用子代理。\n'+(error or '请检查并完成原任务。'))
                    save(attempt/'request.json',dict(at=now(),phase=1,repair=repair,prompt_sha256=__import__('hashlib').sha256(prompt.encode()).hexdigest()))
                    result=R.recover_call(isolate.run_codex,run,run.name,'single_agent',prompt,
                        thread_id=thread,resume=bool(thread),model='gpt-6-astra',effort='xhigh',web=True,timeout=14400)
                    result['provider_configured_cost_estimate_usd']=result.pop('cost',None);save(attempt/'model_result.json',result)
                    if thread and result.get('session') and thread!=result['session']: raise ValueError('Native session identity changed')
                    thread=result.get('session') or thread;state.update(session_id=thread,updated_at=now());save(run/'session.json',state)
                    if not result.get('ok') or not thread: raise ValueError('Native turn incomplete: '+str(result.get('error')))
                    audit(run);errors,items=artifact_errors(run,result)
                    if errors:
                        error='\n'.join(errors);save(attempt/'validation.json',dict(ok=False,errors=errors))
                        shutil.copytree(run/'work/out',attempt/'output')
                        if repair==2: raise ValueError(error)
                        state['validation_retry']=dict(phase=1,attempt=repair+1,reason=error);save(run/'session.json',state)
                        continue
                    save(attempt/'validation.json',dict(ok=True,errors=[]));break
            verify(meta['input_files']);audit(run)
            save(run/'verification.json',dict(ok=True,at=now(),errors=[],scope='Output schema, source IDs and clean transport; not scientific novelty proof'))
            accept(run,items)
            state.pop('validation_retry',None);state.update(status='completed',finished_at=now(),stages={'1':dict(status='completed',session_id=thread)})
            save(run/'session.json',state);return 0
        except Exception as exc:
            state.update(status='needs_review',error=f'{type(exc).__name__}: {exc}',finished_at=now());save(run/'session.json',state)
            save(run/'verification.json',dict(ok=False,errors=[state['error']]));return 1
