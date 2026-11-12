"""Six new single sessions, one discussion/response round, independent exact Top5."""
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from pathlib import Path
import argparse
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time

from common import *
import prompts

def engine(configure=True):
    import single as E
    if configure: E.configure()
    return E

def author_path(root, author): return root/'authors'/author

def validate_discussion(data, author, pool):
    if data.get('author') != author: raise ValueError('Discussion author mismatch')
    notes = data.get('peer_notes', [])
    peers = set(AUTHORS) - {author}
    if len(notes)!=5 or {n.get('peer') for n in notes} != peers: raise ValueError('Discussion must cover all five peers exactly once')
    cards = {c['card_id']: c for c in pool}
    for note in notes:
        ids = note.get('card_ids', [])
        if not ids or len(ids) != len(set(ids)): raise ValueError('Missing/duplicate discussed card IDs')
        if any(i not in cards or cards[i]['author'] != note['peer'] for i in ids): raise ValueError('Feedback refers to wrong author/card')
        if not str(note.get('assessment', '')).strip() or not str(note.get('suggestion', '')).strip(): raise ValueError('Empty peer feedback')

def validate_response(data, author, pool, five_cards=None, scratch=None):
    own = {c['card_id']: c['idea'] for c in pool if c['author'] == author}
    if data.get('author') != author: raise ValueError('Response author mismatch')
    replies = data.get('responses', [])
    if len(replies) != 5 or {r.get('critic') for r in replies} != set(AUTHORS)-{author}: raise ValueError('Respond to all five critics')
    if any(not str(r.get('response', '')).strip() for r in replies): raise ValueError('Empty response')
    decisions = data.get('decisions', [])
    if len(decisions) != 5 or {d.get('card_id') for d in decisions} != set(own): raise ValueError('Only own five cards may be finalized')
    for row in decisions:
        cid, action, idea = row['card_id'], row.get('action'), row.get('idea')
        if action not in ('retain','revise','withdraw') or not str(row.get('reason','')).strip(): raise ValueError('Missing action/reason')
        if not isinstance(idea, dict): raise ValueError('Complete idea object required')
        if action in ('retain','withdraw') and idea != own[cid]: raise ValueError('Retained/withdrawn original changed')
    if five_cards:
        save(scratch, [d['idea'] for d in decisions]); five_cards(scratch)

def validate_selection(data, pool):
    rows = data.get('top5', [])
    ids = {c['id'] for c in pool}
    if len(rows) != 5 or [r.get('rank') for r in rows] != [1,2,3,4,5]: raise ValueError('Exactly five ranked selections required')
    selected = [r.get('card') for r in rows]
    if len(set(selected)) != 5 or not set(selected) <= ids: raise ValueError('Duplicate/invented/withdrawn selection')
    if any(not str(r.get('reason','')).strip() for r in rows): raise ValueError('Selection reasons missing')

def readonly_generation(E, run):
    """Add real read-only mounts for accepted artifacts, leaving only debate output writable."""
    original = E.isolate.bwrap
    frozen = [p for p in (run/'work/out').iterdir() if p.name != 'debate']
    if (run/'work/out/debate/DISCUSSION.json').exists():frozen.append(run/'work/out/debate/DISCUSSION.json')
    overrides=run/'collaboration/tool-config';overrides.mkdir(parents=True,exist_ok=True)
    if ACCESS!='web':
        config=read(run/'work/library_api.json');config['request_log']='out/debate/lookups/api_requests.jsonl'
        freeze(overrides/'library_api.json',config)
    web=(run/'work/tools/web_search.py').read_text()
    if '/work/out/web_requests.jsonl' not in web:raise ValueError('Unrecognized web logging contract')
    patched=web.replace('/work/out/web_requests.jsonl','/work/out/debate/lookups/web_requests.jsonl')
    (overrides/'web_search.py').write_text(patched)
    (run/'work/out/debate/lookups').mkdir(parents=True,exist_ok=True)
    def bwrap(*args, **kwargs):
        command = original(*args, **kwargs); index = command.index('--chdir')
        binds = ['--ro-bind', str(run/'work/ideas/pool'), '/work/ideas/pool']
        for p in frozen: binds += ['--ro-bind', str(p), '/work/out/'+str(p.relative_to(run/'work/out'))]
        if ACCESS!='web': binds += ['--ro-bind',str(overrides/'library_api.json'),'/work/library_api.json']
        binds += ['--ro-bind',str(overrides/'web_search.py'),'/work/tools/web_search.py']
        command[index:index] = binds
        return command
    E.isolate.bwrap = bwrap

def invoke(run, phase, prompt, output, validator, session=None):
    E = engine(); R = E.R
    protected = read(run/'generation_seal.json', {}).get('files', {})
    protected.update({str(p):sha(p) for p in (run/'work/debate').rglob('*') if p.is_file()})
    if phase=='respond':
        discussion=run/'work/out/debate/DISCUSSION.json'
        protected[str(discussion)]=read(run/'collaboration/discuss/accepted.json')['output_sha256']
    if (run/'generation_seal.json').exists(): readonly_generation(E, run)
    root = run/'collaboration'/phase
    accepted = root/'accepted.json'
    if accepted.exists():
        receipt = read(accepted); verify(receipt['protected']); verify({str(output):receipt['output_sha256']})
        validator(read(output)); return receipt
    history = sorted(root.glob('attempt-*/result.json'))
    if history:
        prior = read(history[-1]); prior_id = prior.get('session')
        if session and prior_id and session != prior_id: raise ValueError('Native session changed')
        session = session or prior_id
    save(run/'work/research_phase.json', {'phase':'light-'+phase})
    state = {'phase':phase,'status':'running','started':now(),'process_handle':handle(os.getpid())}
    save(run/'collaboration/state.json', state)
    error = ''
    with E.isolate.Gate(str(run), ['single_agent'], allow_web=True):
        for number in range(len(history)+1, len(history)+4):
            attempt = root/f'attempt-{number:02d}'; attempt.mkdir(parents=True)
            current = prompt if not error else '继续当前阶段，修复以下已定位的产物问题，保留其余研究内容：\n'+error+'\n原任务：\n'+prompt
            (attempt/'prompt.md').write_text(current)
            result = R.recover_call(E.isolate.run_codex, run, run.name, 'single_agent', current,
                thread_id=session, resume=bool(session), model='gpt-6-astra', effort='xhigh', web=True, timeout=14400)
            result['provider_configured_cost_estimate_usd'] = result.pop('cost',None); save(attempt/'result.json',result)
            verify(protected)
            if not result.get('ok') or not result.get('session'): raise ValueError('Incomplete native turn: '+str(result.get('error')))
            if session and session != result['session']: raise ValueError('Native session changed')
            session = result['session']; E.audit(run)
            try:
                validator(read(output))
            except (ValueError,KeyError,TypeError,OSError) as exc:
                error = f'{type(exc).__name__}: {exc}'
                save(attempt/'validation.json', {'ok':False,'error':error})
                if output.exists(): shutil.copy2(output,attempt/'output.json')
                if number == len(history)+3: raise
                continue
            receipt = {'ok':True,'phase':phase,'at':now(),'session':session,'protected':protected,'output_sha256':sha(output)}
            save(accepted,receipt); state.update(status='completed',finished=now()); save(run/'collaboration/state.json',state)
            return receipt

def author_worker(root, author, phase):
    run = author_path(root,author); E = engine()
    if phase == 'generate':
        if read(run/'verification.json',{}).get('ok') is True: return
        code = E.worker(run)
        if code: raise ValueError(read(run/'session.json').get('error','Generation failed'))
        return
    pool = read(run/'work/debate/generation.json'); own = [c['card_id'] for c in pool if c['author'] == author]
    session = read(run/'session.json')['session_id']
    if phase == 'discuss':
        prompt = prompts.DISCUSS.format(author=author,own=', '.join(own))
        output = run/'work/out/debate/DISCUSSION.json'
        validator = lambda value:validate_discussion(value,author,pool)
    else:
        assert phase == 'respond'
        discussion_receipt = read(run/'collaboration/discuss/accepted.json')
        assert discussion_receipt['session'] == session
        prompt = prompts.RESPOND.format(author=author,own=', '.join(own))
        output = run/'work/out/debate/FINAL.json'
        validator = lambda value:validate_response(value,author,pool,lambda path:E.validate_cards(path,run),run/'collaboration/validation-cards.json')
    invoke(run,phase,prompt,output,validator,session)

def accepted_generation(root):
    pool = []
    for ai,author in enumerate(AUTHORS):
        run = author_path(root,author)
        if not read(run/'verification.json',{}).get('ok'): raise ValueError('Six-author generation barrier not met')
        session = read(run/'session.json')
        if set(session.get('stages',{})) != {'1'}: raise ValueError('Missing accepted generation stage')
        if session.get('status')!='completed' or session['stages']['1'].get('status')!='completed' or not session.get('session_id'):
            raise ValueError('Author generation session incomplete')
        from multi_source import validate_source
        validate_source(read(run/'evaluation_source.json'))
        cards = read(run/'work/out/IDEAS.json')
        if len(cards) != 5: raise ValueError('Author did not generate five cards')
        if (run/'generation_seal.json').exists():
            seal=read(run/'generation_seal.json');verify(seal['files'])
            if seal['session']!=session['session_id']:raise ValueError('Original generation session changed')
        else:
            files = {str(p):sha(p) for folder in ['work/out','stages','implementation'] for p in (run/folder).rglob('*') if p.is_file()}
            files.update({str(run/n):sha(run/n) for n in ['run.json','verification.json','session.json']})
            freeze(run/'generation_seal.json',{'files':files,'session':session['session_id']})
        for i,idea in enumerate(cards,1): pool.append({'card_id':f'c-{ai*5+i:03d}','author':author,'idea':idea})
    freeze(root/'generation.json',pool)
    for author in AUTHORS:
        run = author_path(root,author)
        freeze(run/'work/debate/generation.json',pool)
        (run/'work/out/debate').mkdir(exist_ok=True)
    return pool

def collect_discussions(root):
    pool = read(root/'generation.json'); rows = []
    for author in AUTHORS:
        run = author_path(root,author); receipt = read(run/'collaboration/discuss/accepted.json')
        output = run/'work/out/debate/DISCUSSION.json'
        verify(receipt['protected']); verify({str(output):receipt['output_sha256']})
        data = read(output); validate_discussion(data,author,pool); rows.append(data)
    freeze(root/'discussions.json',rows)
    for author in AUTHORS: freeze(author_path(root,author)/'work/debate/discussions.json',rows)

def collect_responses(root):
    pool = read(root/'generation.json'); rows = []; final = []
    for author in AUTHORS:
        run = author_path(root,author); receipt = read(run/'collaboration/respond/accepted.json')
        output = run/'work/out/debate/FINAL.json'
        verify(receipt['protected']); verify({str(output):receipt['output_sha256']})
        data = read(output); validate_response(data,author,pool); rows.append(data)
        for d in data['decisions']:
            if d['action'] != 'withdraw': final.append(dict(d['idea'],id=d['card_id'],author=author))
    if len(final) < 5: raise ValueError('Fewer than five active cards after discussion; no automatic filling')
    freeze(root/'responses.json',rows); freeze(root/'final_pool.json',final)
    return final

def selection(root, domain):
    E = engine(); run = root/'selector'; pool = read(root/'final_pool.json')
    if not (run/'run.json').exists():
        E.prepare_work(run,domain)
        (run/'work/ideas/pool').mkdir(parents=True,exist_ok=True)
        for name in ['final_pool.json','discussions.json','responses.json']: freeze(run/'work/debate'/name,read(root/name))
        save(run/'run.json',{'created':now(),'domain':domain,'model':'gpt-6-astra','effort':'xhigh','provider':E.PROVIDER})
    prompt = prompts.SELECT.format(domain=read(SYSTEM/'domains'/domain/'task.json')['name'])
    output = run/'work/out/TOP5.json'
    receipt = invoke(run,'select',prompt,output,lambda x:validate_selection(x,pool))
    all_sessions = {read(author_path(root,a)/'session.json')['session_id'] for a in AUTHORS}
    if receipt['session'] in all_sessions: raise ValueError('Selector reused an author session')
    selected = read(output)['top5']; byid = {c['id']:c for c in pool}
    files = {str(root/n):sha(root/n) for n in ['generation.json','discussions.json','responses.json','final_pool.json']}
    files.update({str(output):sha(output)})
    for author in AUTHORS:
        arun = author_path(root,author)
        verify(read(arun/'generation_seal.json')['files'])
        for phase in ['discuss','respond']:
            receipt_path = arun/f'collaboration/{phase}/accepted.json'; r = read(receipt_path)
            verify(r['protected']); files[str(receipt_path)] = sha(receipt_path)
            output=arun/'work/out/debate'/('DISCUSSION.json' if phase=='discuss' else 'FINAL.json')
            verify({str(output):r['output_sha256']});files[str(output)]=r['output_sha256']
    exported = []
    for row in selected:
        p = root/'selected'/f'{row["card"]}.json'; freeze(p,byid[row['card']]); files[str(p)] = sha(p)
        exported.append({'rank':row['rank'],'card':row['card'],'path':str(p),'sha256':sha(p)})
    ideas = root/'selected/IDEAS.json'; freeze(ideas,[byid[r['card']] for r in selected])
    acceptance = root/'selected/acceptance.json'
    freeze(acceptance,{'source_kind':'multi','run':str(root),'selected':exported,'source_files':files,'ideas_sha256':sha(ideas)})
    source = {'source_kind':'multi','domain':domain,'condition':CONDITION,'run':str(root),'ideas':str(ideas),
        'ideas_sha256':sha(ideas),'source_files':files,'acceptance_file':str(acceptance),'acceptance_sha256':sha(acceptance),
        'accepted_at':now(),'provider':E.PROVIDER}
    from multi_source import validate_source
    validate_source(source); save(root/'evaluation_source.json',source)
    save(root/'completion_check.json',{'ok':True,'at':now(),'errors':[],'generation_authors':6,'generation_cards':30,
        'discussion_rounds':1,'active_cards':len(pool),'selected':5,'independent_selection_session':receipt['session']})

def domain_worker(root, domain):
    state = read(root/'domain_state.json',{'phase':'generate','stages':{},'authors':{}})
    state.update(status='running',process_handle=handle(os.getpid()))
    save(root/'domain_state.json',state)
    try:
        for phase in ['generate','discuss','respond']:
            if state['stages'].get(phase)=='completed': continue
            state.update(phase=phase,at=now());save(root/'domain_state.json',state)
            if phase=='discuss': accepted_generation(root)
            if phase=='respond': collect_discussions(root)
            def worker(author):
                run=author_path(root,author)
                if phase=='generate' and read(run/'verification.json',{}).get('ok'): return 0
                if phase!='generate' and (run/f'collaboration/{phase}/accepted.json').exists(): return 0
                with (root/'logs'/f'{author}-{phase}.log').open('ab') as log:
                    return subprocess.call([sys.executable,'-B',str(HERE/'cli.py'),'author','--root',str(root),'--domain',domain,'--author',author,'--phase',phase],
                        stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
            with ThreadPoolExecutor(max_workers=6) as executor: codes = list(executor.map(worker,AUTHORS))
            if any(codes): raise ValueError(f'{phase} incomplete: '+str(dict(zip(AUTHORS,codes))))
            state['stages'][phase]='completed';save(root/'domain_state.json',state)
        collect_responses(root)
        state.update(phase='select',at=now());save(root/'domain_state.json',state)
        selection(root,domain)
        state['stages']['select']='completed';state.update(status='selected',finished=now());save(root/'domain_state.json',state)
    except Exception as exc:
        state.update(status='needs_review',error=f'{type(exc).__name__}: {exc}',at=now());save(root/'domain_state.json',state)
        raise
