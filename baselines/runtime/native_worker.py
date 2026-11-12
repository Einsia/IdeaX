"""One isolated domain run, preserving the selected baseline's native workflow."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

from common import *

def update(run, **values):
    state = read(run/'status.json'); state.update(updated_at=now(), **values)
    save(run/'status.json', state)

def aggregate(run):
    cards = [read(path) for path in sorted(run.glob('native/run-*/idea_card.json'))]
    save(run/'idea_cards.json', cards)
    update(run, completed_cards=len(cards))
    return cards

def init_credentials():
    base, key = provider()
    for name in ('AGENT_LOOP_BASE_URL','IDEASCIENTIST_ROLE_BASE_URL','IDEASCIENTIST_ROLE_MODEL',
                 'COI_RETRIEVAL_CACHE','COI_ATTEMPT_LEDGER','COI_API_LOG'):
        os.environ.pop(name, None)
    os.environ.update(OPENAI_BASE_URL=base, OPENAI_API_KEY=key,
                      IDEASCIENTIST_BASE_URL=base, IDEASCIENTIST_API_KEY=key,
                      PYTHONUNBUFFERED='1', PYTHONDONTWRITEBYTECODE='1',
                      TMPDIR=os.environ['IDEAX_SCRATCH'])
    return base, key

def coi_export(native, domain, index):
    normalizer = load_module('coi_normalize', REPO/'baselines/coi/normalize.py')
    result = read(native/'result.json')
    valid, error = normalizer.validate_native(result)
    if not valid: raise ValueError(error)
    for name in ('idea','experiment','review_0'):
        if not (native/'.stage_cache'/f'{name}.json').exists():
            raise ValueError('Missing native completion checkpoint: '+name)
    reviews = read(native/'saves/review_logs/review_experiment_suggestions.json', [])
    experiments = read(native/'saves/deep_logs/experiments.json', [])
    if not reviews or not all(r.get('suggestions') for r in reviews): raise ValueError('Missing native ReviewAgent suggestions')
    if len(experiments)<2 or result['experiment']!=experiments[-1]: raise ValueError('Native experiment refinement is incomplete')
    logs = '\n'.join(p.read_text(errors='replace') for p in sorted(native.glob('attempt-*.log')))
    if 'successfully check novel' not in logs: raise ValueError('Native novelty screening completion is absent')
    chains = re.findall(r'(?m)^\d+\.Paper:', result.get('idea_chain',''))
    if not 2<=len(chains)<=3: raise ValueError('Native chain did not contain 2–3 papers')
    trace, warnings = normalizer.load_trace(native/'retrieval_trace.jsonl')
    refs = normalizer.sources_from_trace(trace)
    title = normalizer.title_from_idea(result['idea']) or next(line.strip() for line in result['idea'].splitlines() if line.strip())[:180]
    md = '# '+title+'\n\n'+result['idea']+'\n\n## 实验方案\n\n'+result['experiment']
    card = dict(schema_version='research.idea_card.v1', method_id='coi', domain_id=domain,
                card_id=f'coi-{domain}-{index:02}', title=title, idea_card_md=md,
                native_artifact=str(native/'result.json'), native_sha256=sha(native/'result.json'),
                source_refs=refs, validation=dict(native_workflow_complete=True, novelty_screen_complete=True,
                review_refinement_complete=True, experiments_run=False, scientific_validity_verified=False,
                trace_warnings=warnings))
    save(native/'idea_card.json', card); (native/'idea_card.md').write_text(md+'\n')

def run_coi(run, domain):
    source = REPO/'baselines/coi/source'
    prompt = (ROOT/'inputs'/domain/'task-one.md').read_text()+(
        '\nCoI 原生运行约定：本次独立流程只生成一个最终研究提案，完整执行论文链、趋势、构思、'
        '新颖性核查、实验设计和至少一次 ReviewAgent 实验改进。论文链长度 2–3 篇、链数 1。'
        '保留原生 result.json，idea 与 experiment 均须非空完整。不得访问其他运行或历史候选。\n')
    (run/'prompt_effective.md').write_text(prompt)
    config = dict(is_azure=False, OPENAI_BASE_URL=PROVIDER, OPENAI_WIRE_API='responses',
        COI_HTTP_USER_AGENT='codex_cli_rs/0.114.0', COI_REASONING_EFFORT='xhigh', COI_REQUIRE_MODEL_MATCH=True,
        COI_REQUEST_ATTEMPTS=4, COI_RETRY_BASE_SECONDS=10, COI_RETRY_MAX_SECONDS=45,
        COI_LLM_TIMEOUT_SECONDS=1200, COI_CONNECT_TIMEOUT_SECONDS=30, COI_MAX_NOVELTY_ATTEMPTS=3,
        COI_RETRIEVAL_BACKEND='arxiv_openalex', COI_PAPER_PARSER='pymupdf', COI_RERANKER='lexical',
        MAIN_LLM_MODEL=MODEL, CHEAP_LLM_MODEL=MODEL, COI_ATTEMPT_LEDGER_ENABLED='1')
    for index in range(1,6):
        native = run/'native'/f'run-{index:02}'; native.mkdir(parents=True,exist_ok=True)
        if (native/'idea_card.json').exists(): continue
        save(native/'config.yaml', config)
        (native/'effective_topic.txt').write_text(prompt)
        save(native/'run_config.json', dict(model=MODEL,effort='xhigh',base_url=PROVIDER,
             credential_source=os.environ.get('IDEAX_GPT_PROFILE_FILE','environment'),domain_id=domain,index=index,
             task_sha256=sha(run/'prompt_effective.md'),source=str(source),
             retrieval='arxiv_openalex',chain_length=[2,3],chain_count=1,review_improvements=1))
        update(run, phase='coi_native_workflow', active_idea_index=index, native_run=str(native))
        cmd=[COI_PYTHON,str(source/'main.py'),'--topic_file',str(native/'effective_topic.txt'),
             '--save_file',str(native/'saves'),'--improve_cnt','1','--min_chain_length','2',
             '--max_chain_length','3','--max_chain_numbers','1']
        env=dict(os.environ,**{k:str(v) for k,v in config.items()},
                 PYTHONPATH=str(source)+os.pathsep+str(REPO/'baselines/runtime'),
                 BASELINES38_RUNTIME=str(REPO/'baselines/runtime'),BASELINES38_LABEL=f'coi/{domain}/{index}')
        existing=len(list(native.glob('attempt-*.log')))
        if existing>=4: raise RuntimeError('Native CoI recovery attempts exhausted')
        for attempt in range(existing+1,5):
            update(run, native_attempt=attempt)
            with (native/f'attempt-{attempt}.log').open('w') as log:
                child=subprocess.Popen(cmd,cwd=native,env=env,stdout=log,stderr=subprocess.STDOUT)
                update(run,child_handle=process_handle(child.pid))
                code=child.wait()
            if code==0:
                coi_export(native,domain,index); break
            text=(native/f'attempt-{attempt}.log').read_text(errors='replace')
            retryable=any(t in text for t in ('TransientGatewayError','RemoteProtocolError','ConnectError',
                'ReadTimeout','ConnectTimeout','TimeoutError','ConnectionError','429','502','503','504'))
            event(run/'events.jsonl','native_failed',index=index,attempt=attempt,exit_code=code,retryable=retryable)
            if not retryable or attempt==4:
                raise RuntimeError('CoI native run failed: '+safe(text[-2500:]))
            update(run, phase='retry_wait', last_error=safe(text[-1000:])); time.sleep(20)
        aggregate(run)

def isci_one(run, domain, index):
    """A fresh process per independent proposal keeps the native caches isolated."""
    native=run/'native'/f'run-{index:02}';native.mkdir(parents=True,exist_ok=True)
    source=REPO/'baselines/ideascientist/source';sys.path.insert(0,str(source))
    entry=load_module('native_isci_entry',source/'scripts/run_gpt_ideation.py')
    opts=entry.parser().parse_args(['--model',MODEL,'--base-url',PROVIDER,'--reasoning-effort','xhigh',
        '--vault-api-url',os.environ.get('IDEASCIENTIST_VAULT_API_URL','http://127.0.0.1:8901'),'--cutoff-date','2027-01-01',
        '--max-turns','100','--max-sub-turns','40','--max-output-tokens','24576'])
    config=entry.configure(opts)
    os.environ.update(IDEASCIENTIST_HTTP_TIMEOUT='1200',IDEASCIENTIST_MAX_RETRIES='6',CONTEXT_WINDOW='828400',
        IDEASCIENTIST_EVIDENCE_DIR=str(native/'evidence'),IDEASCIENTIST_CALL_CACHE=str(native/'request_cache'),
        IDEASCIENTIST_PUBLIC_READER_CHAR_CAP='180000')
    config.update(recovery_version='retrieval-v2', credential_source=os.environ.get('IDEAX_GPT_PROFILE_FILE','environment'),
        reader_source='public_original_with_explicit_structured_fallback',full_text_available='per_source_provenance',
        independent_run_index=index,domain_id=domain,transport_recovery_cycles=3)
    prompt=(ROOT/'inputs'/domain/'task-one.md').read_text()+(
        '\n本轮只完成一个最终提案。使用完整原生 gap_finder → innovator → reviewer → report_writer 流程，'
        '经过真实 reviewer 后输出一份完整 report.json。不得读取其他运行或其他方法的候选。'
        '保留原生内部 revise/reject/survive 判断，不强制放行。\n')
    (native/'prompt_effective.md').write_text(prompt);save(native/'run_config.json',config)
    from ideascientist.harness.resilience import install
    from ideascientist.harness.client import AgenticLLMClient, LoggedLLMClient
    # Every role and paper reader must acquire the same process-shared budget.
    original_chat=AgenticLLMClient.chat; original_call=LoggedLLMClient.call
    def bounded_chat(self,*args,**kwargs):
        label=f'ideascientist/{domain}/{index}/'+str(getattr(self,'_step_name','agent'))
        with slot(label=label): return original_chat(self,*args,**kwargs)
    def bounded_call(self,*args,**kwargs):
        label=f'ideascientist/{domain}/{index}/'+str(getattr(self,'_step_name','reader'))
        with slot(label=label): return original_call(self,*args,**kwargs)
    AgenticLLMClient.chat=bounded_chat;LoggedLLMClient.call=bounded_call
    install()
    from retrieval_recovery import install_isci
    install_isci()
    from replay_recovery import install as install_replay
    install_replay(native)
    from ideascientist.harness import run_ideation
    if (native/'continuation-v6.json').exists():
        run_ideation=load_module('isci_continuation_runner',Path(__file__).parent/'continuation_runner.py').run_ideation
    save(native/'status.json',dict(state='running',started_at=now(),handle=process_handle(os.getpid())))
    summary=asyncio.run(run_ideation(prompt,native,model=MODEL,max_turns=100,max_sub_turns=40))
    save(native/'logs/summary.json',summary)
    validator=load_module('isci_native_delivery_v9',Path(__file__).parent/'native_delivery.py')
    delivery=validator.validate_delivery(native,config)
    if delivery['status']!='passed': raise ValueError('Native IdeaScientist delivery incomplete: '+safe(delivery['errors']))
    report=read(native/'outputs/report.json');refs=[]
    for item in read(native/'outputs/bibliography.json',[]):
        refs.append(dict(item,reading_depth=read(native/'evidence'/f"{item['paper_id']}.json",{'source':'unknown'})))
    md='# '+report['title']+'\n\n'+render({k:v for k,v in report.items() if k!='title'})
    card=dict(schema_version='research.idea_card.v1',method_id='ideascientist',domain_id=domain,
        card_id=f'ideascientist-{domain}-{index:02}',title=report['title'],idea_card_md=md,
        native_artifact=str(native/'outputs/report.json'),native_sha256=sha(native/'outputs/report.json'),
        source_refs=refs,validation=dict(native_delivery=delivery,experiments_run=False,scientific_validity_verified=False))
    save(native/'idea_card.json',card);(native/'idea_card.md').write_text(md+'\n')
    save(native/'status.json',dict(state='completed',finished_at=now(),card=str(native/'idea_card.json')))

def run_isci(run, domain):
    for index in range(1,6):
        native=run/'native'/f'run-{index:02}'
        if (native/'idea_card.json').exists(): continue
        # Native requests retry inside the same conversation; never regenerate
        # an entire rejected/incomplete proposal to select a more favorable one.
        if (native/'status.json').exists() and not (native/'recovery-ready-v2.json').exists(): raise RuntimeError('Existing incomplete native proposal requires checkpoint recovery')
        update(run,phase='continuing_original_history' if (native/'continuation-v6.json').exists() else 'ideascientist_native_workflow',active_idea_index=index,native_run=str(native))
        with (run/f'idea-{index:02}.log').open('a') as log:
            child=subprocess.Popen([ISCI_PYTHON,str(Path(__file__)),'isci-one',domain,'--index',str(index)],
                cwd=run,env=dict(os.environ,PYTHONPATH=str(REPO/'baselines/runtime')),stdout=log,stderr=subprocess.STDOUT)
            update(run,child_handle=process_handle(child.pid));code=child.wait()
        if code:
            error=(run/f'idea-{index:02}.log').read_text(errors='replace')[-2500:]
            raise RuntimeError('IdeaScientist native run failed: '+safe(error))
        aggregate(run)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('method',choices=(*METHODS,'isci-one'))
    parser.add_argument('domain');parser.add_argument('--index',type=int);args=parser.parse_args()
    method='ideascientist' if args.method=='isci-one' else args.method
    run=ROOT/'runs'/method/args.domain
    if not (ROOT/'inputs'/args.domain/'domain.json').exists(): raise ValueError('Unknown domain')
    run.mkdir(parents=True,exist_ok=True)
    lock=(run/('worker.lock' if args.method!='isci-one' else f'idea-{args.index:02}.lock')).open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    init_credentials()
    if args.method=='isci-one':
        try: isci_one(run,args.domain,args.index)
        except Exception as exc:
            save(run/'native'/f'run-{args.index:02}'/'status.json',dict(state='needs_review',finished_at=now(),error_type=type(exc).__name__,error=safe(exc)))
            print(safe(exc),flush=True);return 2
        return 0
    if len(read(run/'idea_cards.json',[]))==5: return 0
    update(run,state='running',started_at=now(),method=method,domain_id=args.domain,
           expected_cards=5,handle=process_handle(os.getpid()),model=MODEL,effort='xhigh',last_error=None,error_type=None)
    try:
        {'coi':run_coi,'ideascientist':run_isci}[method](run,args.domain)
        if len(read(run/'idea_cards.json',[]))!=5: raise ValueError('Final delivery must contain exactly five cards')
        update(run,state='completed',phase='completed',completed_cards=5,finished_at=now(),last_error=None)
        return 0
    except Exception as exc:
        update(run,state='needs_review',phase='failed',error_type=type(exc).__name__,last_error=safe(exc),finished_at=now())
        event(run/'events.jsonl','worker_failed',error_type=type(exc).__name__,error=safe(exc))
        print(safe(exc),flush=True);return 2

if __name__=='__main__': raise SystemExit(main())
