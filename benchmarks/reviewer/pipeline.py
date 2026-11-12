"""Independent acquisition and one independent review per judge of the same evidence.

The existing one-repeat pilot is immutable. New batches do not import its scores.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent.parent/'system/single-full/litgraph/tools'), str(HERE.parent/'shared')]
BENCH = HERE.parent
VERSION = 'three-axis-v1-ni-priority'
MODELS = {'astra': 'gpt-6-astra', 'opus': 'claude-opus-5-5'}
POLICY = 'same_frozen_evidence_one_independent_review_per_judge_v1'


def now(): return datetime.now(timezone.utc).isoformat()
def read(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f'.{os.getpid()}.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


def engine(out, isolated=False):
    spec = importlib.util.spec_from_file_location('three_axis_engine', HERE / 'vendor/evaluate.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.ROOT = Path(out)
    return module


def implementation():
    paths = [HERE / 'pipeline.py', HERE / 'reviewer_prompt.md', *sorted((HERE / 'vendor').glob('*.py'))]
    return {os.path.relpath(p,HERE): sha(p) for p in paths+[BENCH/'shared/native_judge.py',BENCH/'shared/zero_outcomes.py']}


def prepare(out, source=None, from_evaluation=None):
    out = Path(out).resolve()
    if out.exists(): raise ValueError('Use a new output directory; existing evidence and reviews are immutable')
    e = engine(out); items = []; packets = {}; provenance = {}; frozen = {}
    import zero_outcomes
    zeros = zero_outcomes.load(source) if source else read(Path(from_evaluation)/'manifest.json').get('zero_outcomes',[])
    zero_outcomes.verify(zeros)
    if from_evaluation:
        old = Path(from_evaluation).resolve(); manifest = read(old / 'manifest.json')
        if manifest['reviewer_version'] != VERSION: raise ValueError('Different source rubric')
        if sha(old / 'reviewer_prompt.md') != sha(HERE / 'reviewer_prompt.md'): raise ValueError('Source prompt mismatch')
        for item in manifest['items']:
            ident = item['id']; path = old / 'inputs' / f'{ident}.json'
            if sha(path) != item['input_sha256']: raise ValueError('Source input changed: ' + ident)
            packet_path = old / 'evidence' / ident / 'packet.json'
            receipt = read(packet_path.with_name('receipt.json'))
            if sha(packet_path) != receipt['packet_sha256']: raise ValueError('Frozen evidence changed: ' + ident)
            if receipt['input_sha256'] != item['input_sha256']: raise ValueError('Evidence/input mismatch')
            packets[ident] = read(path)
            items.append({**{k: item[k] for k in ('id', 'group', 'group_label', 'domain', 'domain_name', 'source_idea_id')},
                          'selector_top1': item.get('selector_top1', False)})
            frozen[ident] = packet_path.parent
            provenance[str(path)] = sha(path); provenance[str(packet_path)] = sha(packet_path)
    else:
        source = Path(source).resolve(); rows = read(source)
        if not isinstance(rows, list) or not rows: raise ValueError('Input must be a nonempty card array')
        provenance[str(source)] = sha(source)
        domain_map = {d['id']: d for d in read(BENCH.parent / 'data/domains.json')['domains']}
        seen = set()
        for row in rows:
            key = (row.get('system', 'unspecified'), row['task_id'], row['idea_id'])
            if key in seen: raise ValueError('Duplicate idea identity: ' + str(key))
            seen.add(key); ident = 'idea_' + e.digest(key)[:20]
            domain = row['task_id']; known = domain_map.get(domain, {})
            domain_ids = row.get('domain_ids') or [d['id'] for d in known.get('litgraph_support', {}).get('subdomains', [])]
            if not domain_ids: raise ValueError('Supply real domain_ids for domain ' + domain)
            if not isinstance(row['idea_text'], str) or not row['idea_text'].strip(): raise ValueError('Empty idea_text')
            packet = {k: row[k] for k in ('idea_text', 'task_context', 'knowledge_cutoff') if k in row}
            packet.update(idea_id=ident, domain_id=domain, domain_ids=domain_ids,
                          domain=row.get('domain', known.get('name', domain)),
                          provided_reference_texts=row.get('provided_reference_texts', []))
            packets[ident] = packet
            items.append(dict(id=ident, group=key[0], group_label=row.get('system_label', key[0]),
                              domain=domain, domain_name=packet['domain'], source_idea_id=row['idea_id'], selector_top1=row.get('selector_top1',False)))
    if not items: raise ValueError('No accepted cards')
    out.mkdir(parents=True)
    for item in items:
        ident = item['id']; save(out / 'inputs' / f'{ident}.json', packets[ident])
        item['input_sha256'] = sha(out / 'inputs' / f'{ident}.json')
        if ident in frozen:
            shutil.copytree(frozen[ident], out / 'evidence' / ident)
            receipt_path = out / 'evidence' / ident / 'receipt.json'; receipt = read(receipt_path)
            receipt.update(imported_from=str(frozen[ident]), imported_at=now(), input_sha256=item['input_sha256'])
            save(receipt_path, receipt)
            item['frozen_packet_sha256'] = sha(out / 'evidence' / ident / 'packet.json')
    shutil.copy2(HERE / 'reviewer_prompt.md', out / 'reviewer_prompt.md')
    (out / 'score_prompt.md').write_text((out / 'reviewer_prompt.md').read_text() + e.OUTPUT_CONTRACT)
    (out / 'planner_prompt.md').write_text(e.PLANNER); (out / 'selector_prompt.md').write_text(e.SELECTOR)
    save(out / 'manifest.json', dict(created=now(), reviewer_version=VERSION, benchmark='reviewer-three-axis-v1',
        weights={'N': .4, 'I': .4, 'S': .2}, models=MODELS, effort='xhigh', repetitions=1,
        expected_reviews=len(items)*2, expected_ideas=len(items), expected_domains=len({i['domain'] for i in items}),
        aggregation_policy=POLICY,
        litgraph_base_url=os.environ.get('LITGRAPH_API_BASE_URL', ''),
        evidence_policy='independent_astra_acquisition_then_same_frozen_packet_for_both_reviews',
        source_files=provenance, items=items, zero_outcomes=zeros, implementation=implementation(),
        prompts={p: sha(out / p) for p in ('reviewer_prompt.md', 'score_prompt.md', 'planner_prompt.md', 'selector_prompt.md')}))
    result = report(out)
    return {'prepared': str(out), 'cards': len(items), 'expected_reviews': len(items)*2,
            'repetitions': 1, 'evidence_ready': result['evidence_ready'], 'model_calls': 0}


def verify(out):
    out = Path(out); m = read(out / 'manifest.json')
    if (m['reviewer_version'], m['repetitions'], m['models'], m['aggregation_policy']) != (VERSION, 1, MODELS, POLICY):
        raise ValueError('Unsupported benchmark identity or aggregation policy')
    for name, expected in m['implementation'].items():
        if sha(HERE / name) != expected: raise ValueError('Implementation changed: ' + name)
    for name, expected in m['prompts'].items():
        if sha(out / name) != expected: raise ValueError('Prompt changed: ' + name)
    for name, expected in m['source_files'].items():
        if sha(name) != expected: raise ValueError('Source changed: ' + name)
    for item in m['items']:
        if sha(out / 'inputs' / (item['id'] + '.json')) != item['input_sha256']: raise ValueError('Input changed')
        packet = out / 'evidence' / item['id'] / 'packet.json'; receipt = packet.with_name('receipt.json')
        if receipt.exists():
            value = read(receipt)
            if sha(packet) != value['packet_sha256'] or value['input_sha256'] != item['input_sha256']:
                raise ValueError('Evidence integrity failure: ' + item['id'])
            if item.get('frozen_packet_sha256', value['packet_sha256']) != value['packet_sha256']:
                raise ValueError('Imported packet changed')
    return m


def review_dir(out, ident, judge, rep): return Path(out) / 'reviews' / ident / judge / f'r{rep}'


def worker(out, ident, stage, rep=None):
    m = verify(out)
    if ident not in {i['id'] for i in m['items']}: raise ValueError('Unknown card')
    e = engine(out, isolated=True)
    if stage == 'evidence': e.evidence(ident); return
    if stage not in MODELS or rep not in (1,): raise ValueError('Invalid judge or repetition')
    packet_path = Path(out) / 'evidence' / ident / 'packet.json'; packet = read(packet_path); expected = sha(packet_path)
    dest = review_dir(out, ident, stage, rep); dest.mkdir(parents=True, exist_ok=True)
    if (dest / 'receipt.json').exists():
        r = read(dest / 'receipt.json')
        if r['packet_sha256'] != expected or r['assessment_sha256'] != sha(dest / 'assessment.json'):
            raise ValueError('Accepted result changed')
        return
    value, receipt = e.cached_call(dest, 'review', stage, (Path(out) / 'score_prompt.md').read_text(), packet,
                                   lambda value: e.validate_review(value, packet))
    normalized = json.loads(json.dumps(value)); calculated = e.calculated_overall(value)
    corrections = {k: {'reported': value['overall'].get(k), 'calculated': v}
                   for k, v in calculated.items() if value['overall'].get(k) != v}
    normalized['overall'].update(calculated); save(dest / 'assessment.json', normalized)
    save(dest / 'receipt.json', dict(at=now(), **receipt, repeat=rep, packet_sha256=expected,
        assessment_sha256=sha(dest / 'assessment.json'), arithmetic_or_status_corrections=corrections))


def aggregate_repeats(reviews):
    result = {'returned': len(reviews), 'numeric': 0, 'complete': False}; values = {}
    for dim in ('N', 'I', 'S', 'total'):
        scores = [r['overall']['score_100'] if dim == 'total' else r[dim]['score'] for r in reviews]
        valid = [v for v in scores if type(v) in (int, float) and math.isfinite(v)]
        values[dim] = dict(valid=len(valid), mean=statistics.mean(valid) if len(valid) == 1 else None,
                           sample_sd=None, raw=scores)
    result.update(numeric=values['total']['valid'], complete=len(reviews)==1 and values['total']['valid']==1,
                  all_returned=len(reviews)==1, dimensions=values)
    return result


def report(out):
    out = Path(out); m = read(out / 'manifest.json'); e = engine(out)
    rows = []; sessions = set(); evidence_ready = 0
    for item in m['items']:
        ident = item['id']; er = out / 'evidence' / ident / 'receipt.json'; evidence_ready += er.exists()
        for judge in MODELS:
            reviews = []
            for rep in (1,):
                dest = review_dir(out, ident, judge, rep)
                if not (dest / 'receipt.json').exists(): continue
                r = read(dest / 'receipt.json')
                if r['repeat'] != rep or r['model'] != MODELS[judge] or r['effort'] != 'xhigh': raise ValueError('Judge/repeat mismatch')
                if r['packet_sha256'] != sha(er.with_name('packet.json')): raise ValueError('Different evidence across repeats')
                if sha(dest / 'assessment.json') != r['assessment_sha256']: raise ValueError('Changed assessment')
                session = (judge, r['native_session'])
                if session in sessions: raise ValueError('Native judge session reused across reviews')
                sessions.add(session)
                v = read(dest / 'assessment.json'); e.validate_review(v, read(er.with_name('packet.json')))
                v['overall'].update(e.calculated_overall(v)); reviews.append(v)
            rows.append({**{k: item[k] for k in ('id', 'group', 'group_label', 'domain', 'domain_name')},
                         'judge': judge, 'source_idea_id':item['source_idea_id'], 'selector_top1':item.get('selector_top1',False), **aggregate_repeats(reviews)})
    for row in rows:
        for dim in ('N','I','S','total'): row[dim]=row['dimensions'][dim]['mean']
    groups = []; grouped = defaultdict(list)
    for row in rows: grouped[(row['group'], row['judge'])].append(row)
    for (group, judge), members in sorted(grouped.items()):
        complete = all(r['complete'] for r in members)
        groups.append(dict(group=group, label=members[0]['group_label'], judge=judge, expected=len(members),
            returned=sum(r['returned'] for r in members), numeric=sum(r['numeric'] for r in members), expected_reviews=len(members),
            complete_ideas=sum(r['complete'] for r in members), complete=complete,
            **{d: statistics.mean(r['dimensions'][d]['mean'] for r in members) if complete else None for d in ('N','I','S','total')}))
    for g in groups:
        members=grouped[(g['group'],g['judge'])]
        top=[x for x in members if x.get('selector_top1')]
        domains={x['domain'] for x in members}
        valid_top=bool(top) and len(top)==len(domains) and {x['domain'] for x in top}==domains and all(x['complete'] for x in top)
        g['selector_top1_count']=len(top)
        g['selector_top1_means']={d:statistics.mean(x[d] for x in top) if valid_top else None for d in ('N','I','S','total')}
    result = dict(at=now(), reviewer_version=VERSION, repetitions=1, aggregation_policy=POLICY,
        expected_ideas=len(m['items']), expected_reviews=m['expected_reviews'], evidence_ready=evidence_ready,
        returned=sum(r['returned'] for r in rows), numeric=sum(r['numeric'] for r in rows),
        all_returned=all(r['all_returned'] for r in rows), complete=all(r['complete'] for r in rows), groups=groups, cards=rows)
    import zero_outcomes
    result['end_to_end'] = zero_outcomes.adjusted([
        {'system':g['group'],'judge':g['judge'],'count':g['expected'],
         'means':{d:g[d] for d in ('N','I','S','total')}} for g in groups],m.get('zero_outcomes',[]),result['complete'])
    save(out / 'results.json', result)
    lines = ['# 新版 Reviewer · 每裁判一次独立评审', '', f'版本：{VERSION}；40/40/20。相同冻结证据；Astra 与 Opus 各一次。',
             f'返回 {result["returned"]}/{m["expected_reviews"]}；有效数值 {result["numeric"]}；完整单评：{result["complete"]}。', '',
             '|系统|裁判|完整单评 idea|N|I|S|总分|', '|---|---|---|---:|---:|---:|---:|']
    for g in groups:
        nums = ['待完整单评' if g[d] is None else f'{g[d]:.2f}' for d in ('N','I','S','total')]
        lines.append(f'|{g["label"]}|{g["judge"]}|{g["complete_ideas"]}/{g["expected"]}|' + '|'.join(nums) + '|')
    lines += ['', '各卡原始单次分数（不计算复评标准差）保存在 results.json。任一次综合分为 null，不补零，不给完整单评综合均值。',
              '分组总分仅在该组全部卡片具备有效总分后展示。旧版结果不进入此表。']
    (out / 'REPORT.md').write_text('\n'.join(lines)+'\n'); return result


def run(out, astra_limit=64, opus_limit=64):
    if not 1 <= astra_limit <= 300 or not 1 <= opus_limit <= 300: raise ValueError('Concurrency must be 1–300')
    out = Path(out); m = verify(out); e = engine(out)
    with (out / 'scheduler.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state_path = out / 'state.json'; state = read(state_path) if state_path.exists() else {'created': now(), 'jobs': {}}
        jobs = state['jobs']; active = {}; children = {}
        for item in m['items']:
            ident = item['id']; jobs.setdefault(ident+'__evidence', dict(id=ident, stage='evidence', status='pending', launches=0))
            for judge in MODELS:
                for rep in (1,):
                    jobs.setdefault(f'{ident}__{judge}__r{rep}', dict(id=ident, stage=judge, repeat=rep, status='pending', launches=0))
        def dest(job):
            return out/'evidence'/job['id'] if job['stage']=='evidence' else review_dir(out, job['id'], job['stage'], job['repeat'])
        for key, job in jobs.items():
            if (dest(job)/'receipt.json').exists(): job['status']='complete'
            elif e.alive(job.get('process')): active[key]=job['process']
            else: job['status']='pending'
        last_report=0
        while True:
            for key, handle in list(active.items()):
                if key in children: children[key].poll()
                if e.alive(handle): continue
                job=jobs[key]; job['status']='complete' if (dest(job)/'receipt.json').exists() else 'needs_attention'; job['finished']=now()
                error=dest(job)/'job_error.json'
                if error.exists() and job['status']!='complete':job['error']=read(error)['error']
                active.pop(key)
            counts=Counter('opus' if jobs[k]['stage']=='opus' else 'astra' for k in active)
            for key, job in sorted(jobs.items(), key=lambda kv:(kv[1]['stage']=='evidence',kv[0])):
                if job['status']!='pending':continue
                pool='opus' if job['stage']=='opus' else 'astra'
                if counts[pool] >= (opus_limit if pool=='opus' else astra_limit):continue
                if job['stage']!='evidence' and jobs[job['id']+'__evidence']['status']!='complete':continue
                log=out/'logs'/f'{key}-{job["launches"]+1}.log';log.parent.mkdir(exist_ok=True)
                cmd=[sys.executable,'-B',str(HERE/'pipeline.py'),'worker','--out',str(out),'--id',job['id'],'--stage',job['stage']]
                if job.get('repeat'):cmd+=['--repeat',str(job['repeat'])]
                with log.open('wb') as stream:
                    proc=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
                job.update(status='running', launches=job['launches']+1, started=now(), process=e.process_handle(proc.pid))
                active[key]=job['process'];children[key]=proc;counts[pool]+=1
            state.update(at=now(),scheduler_handle=e.process_handle(os.getpid()),active=dict(counts),
                         limits={'astra':astra_limit,'opus':opus_limit},counts=dict(Counter(j['status'] for j in jobs.values())))
            save(state_path,state)
            if time.time()-last_report>30: report(out);last_report=time.time()
            if not active:break
            time.sleep(2)
        return report(out)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','check','run','report','worker'))
    parser.add_argument('--out',type=Path,required=True); parser.add_argument('--input',type=Path); parser.add_argument('--from-evaluation',type=Path)
    parser.add_argument('--astra-concurrency',type=int,default=64);parser.add_argument('--opus-concurrency',type=int,default=64)
    parser.add_argument('--id');parser.add_argument('--stage',choices=('evidence','astra','opus'));parser.add_argument('--repeat',type=int,choices=(1,))
    args=parser.parse_args(argv);out=args.out.resolve()
    if args.action=='prepare':
        if bool(args.input)==bool(args.from_evaluation):parser.error('Choose exactly one of --input or --from-evaluation')
        result=prepare(out,args.input,args.from_evaluation)
    elif args.action=='check':
        m=verify(out);result={'ok':True,'version':VERSION,'repetitions':1,'cards':len(m['items']),'model_calls':0}
    elif args.action=='run': result=run(out,args.astra_concurrency,args.opus_concurrency)
    elif args.action=='report':verify(out);result=report(out)
    else:
        if not args.id or not args.stage:parser.error('worker requires --id and --stage')
        try:worker(out,args.id,args.stage,args.repeat)
        except Exception as exc:
            dest=out/'evidence'/args.id if args.stage=='evidence' else review_dir(out,args.id,args.stage,args.repeat)
            message=re.sub(r'\bsk-[A-Za-z0-9_-]{12,}','[REDACTED]',f'{type(exc).__name__}: {exc}')[:1200]
            save(dest/'job_error.json',{'at':now(),'error':message});raise
        result={'ok':True,'id':args.id,'stage':args.stage,'repeat':args.repeat}
    print(json.dumps({k:v for k,v in result.items() if k!='cards' or not isinstance(v,list)},ensure_ascii=False))
    return 1 if args.action=='run' and not result.get('complete') else 0


if __name__=='__main__':raise SystemExit(main())
