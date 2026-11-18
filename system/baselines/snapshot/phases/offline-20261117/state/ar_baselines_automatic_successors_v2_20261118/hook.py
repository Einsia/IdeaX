"""Persistent successor preparation owned by the existing recovery owner, never a second owner."""
from pathlib import Path
import datetime,hashlib,json,os,subprocess,sys,time,traceback
S=Path(__file__).resolve().parent;P=S.parents[1];sys.path.insert(0,str(P));import campaign as C,offline_gates as G
O=P/'state/ar_baselines_normal_recovery_owner_20261118T0020';read=C.read;sha=G.sha
def ref(p):return {'path':str(p),'sha256':sha(p)}
def epoch(at):return datetime.datetime.fromisoformat(at).timestamp()
def launch(command,record,stage):
 log=S/'logs'/f"{record['signature']}-{stage}.log";log.parent.mkdir(exist_ok=True)
 with log.open('ab') as f:p=subprocess.Popen(command,cwd=P,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 record.update(stage=stage,process=C.handle(p.pid),command=command,log=str(log),at=C.now());C.save(S/'active.json',record);return record
def new_attempt_evidence(job,cfg,m,out,owner_record):
 """A new launch alone cannot justify another package or API retry."""
 if job['method']=='insightagents':
  target=out/m['target_directory'];count=len(list(target.glob('physical-*')))
  if count<=m['prior_physical_attempts']:return False,'preparation_or_finalization_repair_requires_revision'
  return True,'new_original_physical_evidence'
 if job['method']=='sciagents':
  events=[json.loads(l) for l in (out/'api_events.jsonl').read_text().splitlines()]
  ends=[e for e in events if e.get('event')=='attempt_end'];previous=Path(m['original_snapshot'])/'api_events.jsonl'
  old=[json.loads(l) for l in previous.read_text().splitlines()];oldids={e.get('attempt_id') for e in old if e.get('event')=='attempt_end'}
  fresh=[e for e in ends if e.get('attempt_id') not in oldids]
  if not fresh:return False,'missing_new_terminal_ledger_requires_evidence_repair'
  if not any(e.get('status')=='infrastructure_failure' for e in fresh):return False,'API_success_finalization_requires_cache_repair'
  return True,'new_actual_API_failure_end'
 if job['method']=='cycleresearcher':
  hr=owner_record.get('health')
  if not hr or sha(hr['path'])!=hr['sha256']:return False,'incomplete_owner_health_requires_evidence_repair'
  health=read(hr['path'])
  if health.get('new_physical_attempts',0)==0:return False,'zero_physical_preparation_requires_revision'
  if not health.get('passed') or health.get('success') is not False:return False,'non_API_terminal_requires_cache_or_evidence_review'
  if not health.get('end',{}).get('at'):return False,'missing_actual_failure_end_requires_evidence_repair'
  return True,'verified_real_API_failure_subset'
 return False,'outside_scope'
def first_attempt_evidence(job,out):
 """Only zero-API diagnosis is admitted here; builder and independent review prove the exact request."""
 if job.get('launches',0)<1:return False,'original_slot_never_launched',{}
 expected=P/'runs'/job['method']/job['domain']/f"slot-{job['slot']:02}"
 if out!=expected:return False,'non_original_output_scope',{}
 if job['method']=='insightagents':
  if (out/'terminal.json').exists():return False,'native_terminal_requires_independent_review',{}
  missing=[q for q in (out/'model_calls').glob('*') if q.is_dir() and (q/'request.json').exists() and not (q/'native_returned.json').exists()]
  if len(missing)!=1:return False,'missing_response_scope_requires_evidence_repair',{}
  physical=sorted(missing[0].glob('physical-*'))
  if not physical:return False,'zero_physical_preparation_requires_revision',{}
  receipt=physical[-1]/'receipt.json';ledger=out/'model_attempts.jsonl'
  if not receipt.exists() or not ledger.exists():return False,'missing_terminal_evidence_requires_repair',{}
  return True,'first_original_failure_requires_strict_builder_classification',{'request':ref(missing[0]/'request.json'),'receipt':ref(receipt),'ledger':ref(ledger)}
 if job['method']=='sciagents':
  ledger=out/'api_events.jsonl'
  if not ledger.exists():return False,'zero_physical_preparation_requires_revision',{}
  events=[json.loads(l) for l in ledger.read_text().splitlines()]
  ends=[e for e in events if e.get('event')=='attempt_end' and e.get('status')=='infrastructure_failure']
  if not ends:return False,'no_failed_API_end_requires_terminal_or_evidence_review',{}
  return True,'first_original_failure_requires_strict_builder_classification',{'ledger':ref(ledger)}
 return False,'outside_first_failure_scope',{}
def finish(active,status,detail=None):
 active.update(stage=status,finished_at=C.now(),detail=detail);C.save(S/'attempts'/f"{active['signature']}.json",active);C.save(S/'active.json',{});return active
def review_command(hp,method):
 if method=='insightagents':
  h=read(hp);root=hp.parents[2];index=root/'owner_single_ready.json';C.save(index,{'model_calls':0,'shared_mutations':False,'ready':[{'job_key':h['job_key'],'handoff':ref(hp)}]});return ['/usr/bin/python3','-B',str(S/'review_insight.py'),str(index),sha(index)]
 return ['/usr/bin/python3','-B',str(S/('review_sci.py' if method=='sciagents' else 'review_cycle.py')),str(hp),sha(hp)]
def tick():
 cfg=read(S/'configuration.json');assert cfg['enabled'];assert all(sha(p)==v for p,v in cfg['bindings'].items());(S/'attempts').mkdir(exist_ok=True);active=read(S/'active.json',{});waiting=read(S/'waiting.json',{});observations=[]
 if active:
  if active['stage']=='waiting_backoff':
   if time.time()>=active['not_before_epoch']:active=launch(review_command(Path(active['handoff']),active['method']),active,'reviewing')
  elif C.alive(active.get('process')):pass
  elif active['stage']=='building':
   lines=Path(active['log']).read_text().splitlines();values=[]
   for line in lines:
    try:v=json.loads(line)
    except ValueError:continue
    if isinstance(v,dict):values.append(v)
   last=values[-1] if values else {};hp=None
   if active['method']=='cycleresearcher' and last.get('owner_config'):hp=Path(last['owner_config']['path']).parent/'handoff.json'
   elif last.get('handoff'):hp=Path(last['handoff']['path']);assert sha(hp)==last['handoff']['sha256']
   if hp and hp.exists():
    h=read(hp);cp=h.get('config') or h['owner_config']['path'];config=read(cp);active.update(handoff=str(hp),not_before_epoch=config['not_before_epoch']);C.save(S/'active.json',active)
    if time.time()<config['not_before_epoch']:
     active.update(stage='waiting_backoff');waiting[active['signature']]=active;C.save(S/'waiting.json',waiting);C.save(S/'active.json',{});active={}
    else:active=launch(review_command(hp,active['method']),active,'reviewing')
   else:finish(active,'requires_evidence_or_implementation_repair',last);active={}
  elif active['stage']=='reviewing':
   q=read(O/'reviewed_queue.json');hp=Path(active['handoff']);h=read(hp);cp=h.get('config') or h['owner_config']['path'];entries=[e for e in q['batches'] if e['config']==cp]
   if len(entries)==1:finish(active,'enqueued_strict_review_passed',entries[0]);active={}
   else:finish(active,'review_withheld_requires_new_revision',{'log':active['log']});active={}
 if not active:
  due=[a for a in waiting.values() if time.time()>=a['not_before_epoch']]
  if due:
   item=min(due,key=lambda a:a['not_before_epoch']);active=launch(review_command(Path(item['handoff']),item['method']),item,'reviewing');waiting.pop(item['signature']);C.save(S/'waiting.json',waiting)
 if not active:
  state=read(P/'state/campaign.json');registry=read(P/'state/generation_recoveries.json');queue=read(O/'reviewed_queue.json')['batches'];byconfig={x['config']:x for x in queue}
  for key in cfg['allowed_keys']:
   job=state['jobs'][key]
   if job['status']!='infrastructure_failure' or C.alive(job.get('process')):continue
   if any(a.get('job_key')==key and a.get('prior_launches')==job['launches'] for a in waiting.values()):continue
   try:
    action=registry.get(key);cp=None;m={};record={};out=C.result_path(job).parent
    if action:
     if action['recovery_id'] not in job.get('executed_recovery_ids',[]):continue
     cmd=action['command'];mp=Path(cmd[cmd.index('--manifest')+1]);m=read(mp);cp=mp.parent/'owner_config.json';assert str(cp) in byconfig;owner_cfg=read(cp);out=Path(owner_cfg['output_dir'])
     candidate=out/m.get('candidate_filename','original_transport_candidate_result.json')
     if (job['method']=='insightagents' and (out/'terminal.json').exists()) or (candidate.exists() and read(candidate).get('status')!='infrastructure_failure'):
      observations.append({'job_key':key,'status':'native_terminal_or_finalization_requires_independent_review'});continue
     record=read(O/(job['method']+'_'+action['recovery_id']+'.json'),{});ok,reason=new_attempt_evidence(job,owner_cfg,m,out,record);evidence={'prior_config':ref(cp)}
    else:ok,reason,evidence=first_attempt_evidence(job,out)
   except Exception as exc:
    observations.append({'job_key':key,'status':'source_evidence_repair_required','error':repr(exc)});continue
   if not ok:observations.append({'job_key':key,'status':reason});continue
   signature=hashlib.sha256(json.dumps({'job_key':key,'launches':job['launches'],'prior_evidence':evidence,'builder_revision':cfg['revision']},sort_keys=True).encode()).hexdigest()[:24]
   if (S/'attempts'/f'{signature}.json').exists() or signature in waiting:continue
   builder=cfg['builders'][job['method']];assert sha(builder['release']['path'])==builder['release']['sha256'];root=P/'state'/('automatic_successor_'+signature);rid=key+'-automatic-'+signature
   if job['method']=='cycleresearcher':
    assert m['stage'] in ['reviewer_continuation','reviewer_checkpoint_successor'];command=builder['command']+['--kind','reviewer','--previous-owner-config',str(cp),'--previous-health',record['health']['path']]
   else:command=builder['command']+['--key',key,'--recovery-id',rid,'--output-root',str(root)]
   active=launch(command,{'signature':signature,'job_key':key,'method':job['method'],'prior_evidence':evidence,'prior_launches':job['launches'],'evidence_classification':reason,'owner':C.handle(os.getpid()),'new_model_calls_by_builder':0},'building');break
 C.save(S/'health.json',{'at':C.now(),'owner':C.handle(os.getpid()),'same_existing_recovery_owner':True,'active':active,'waiting':waiting,'scope_original_keys':len(cfg['allowed_keys']),'first_original_failure_supported':True,'observations':observations,'minimum_actual_failure_backoff_seconds':600,'zero_physical_and_incomplete_evidence_require_repair':True,'successful_requests_never_retried':True,'no_new_sampling':True,'single_preparation_subprocess':True})
