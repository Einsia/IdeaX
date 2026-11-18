"""One owner for independently reviewed same-input recoveries; queues remain independent."""
from pathlib import Path
import datetime,fcntl,hashlib,json,os,sys,time,importlib.util,traceback
W=Path(__file__).resolve().parent;P=W.parents[1];OWNER=Path(__file__).resolve()
sys.path.insert(0,str(P));import campaign as C,offline_gates as G
B=P/'state/cycle_arc_same_input_successor_20261117T2155_B'
sp=importlib.util.spec_from_file_location('reviewed_transport_evidence',B/'recovery_owner.py');T=importlib.util.module_from_spec(sp);sp.loader.exec_module(T)
TERMINALS={'request_completed_pending_native_terminal_review','request_failed_waiting_reviewed_successor','preparation_failure_waiting_reviewed_successor'}
def ref(p):return {'path':str(p),'sha256':G.sha(p)}
def utc(t):return datetime.datetime.fromtimestamp(t,datetime.timezone.utc).isoformat()
def target_health(cfg):
 v=cfg.get('health_verifier')
 if not v:return T.target_health(cfg)
 assert v['function']=='target_health' and G.sha(v['path'])==v['sha256'],'Reviewed health verifier changed'
 sp=importlib.util.spec_from_file_location('reviewed_multi_request_health',v['path']);module=importlib.util.module_from_spec(sp);sp.loader.exec_module(module)
 return module.target_health(cfg)
def terminal_state(health):
 if health.get('classification')=='preparation_failure_no_new_physical_attempt':
  assert health.get('new_physical_attempts')==0 and health.get('model_calls_for_this_launch')==0
  return 'preparation_failure_waiting_reviewed_successor'
 if health.get('success') is True:return 'request_completed_pending_native_terminal_review'
 return 'request_failed_waiting_reviewed_successor'
def process(entry):
 assert G.sha(entry['review'])==entry['review_sha256'];review=C.read(entry['review'])
 assert review['passed'] and review['approved_normal_admission_same_input_batch']
 cfg=C.read(entry['config']);assert G.sha(entry['config'])==review['config_sha256']
 key,rid=cfg['job_key'],cfg['recovery_id'];record=W/(cfg['method']+'_'+rid+'.json');saved=C.read(record,{})
 if not saved:
  assert G.sha(Path(entry['config']).parent/'source_bindings.json')==review['source_bindings_sha256']
  for p,h in C.read(Path(entry['config']).parent/'source_bindings.json').items():assert G.sha(p)==h,p
  with C.admission_lock():
   state=C.read(P/'state/campaign.json');job=state['jobs'][key];ctl=C.read(P/'state/control.json');methods=C.read(P/'state/methods.json')
   assert ctl['request_concurrency']==250 and ctl['generation_workers']<=230 and ctl['scoring_workers']<=20
   assert all(1<=methods[name]['max_generation_workers']<=230 for name in ['cycleresearcher','sciagents','insightagents'])
   assert ctl['request_concurrency']==250 and ctl['generation_workers']==230 and ctl['scoring_workers']==20
   assert job['launches']==cfg['expected_launches'] and job['status']=='infrastructure_failure' and not C.alive(job.get('process'))
   assert G.sha(C.result_path(job))==cfg['expected_result_sha256'] and rid not in job.get('executed_recovery_ids',[])
   recovery={'approved':True,'ready':True,'recovery_id':rid,'audit_path':entry['review'],'audit_sha256':entry['review_sha256'],'expected_result_sha256':cfg['expected_result_sha256'],'command':cfg['command'],'same_slot':True,'new_sample':False,'same_material':True,'automatic_relaunch':False,'not_before_epoch':cfg['not_before_epoch'],'next_retry_at':utc(cfg['not_before_epoch']),'owner':str(OWNER),'owner_health':str(W/'health.json')}
   C.update_recovery_registry({key:recovery})
   saved={'at':C.now(),'job_key':key,'recovery_id':rid,'status':'registered_waiting_normal_scheduler','next_retry_at':utc(cfg['not_before_epoch']),'expected_launches':cfg['expected_launches']+1,'review':entry,'same_slot':True,'new_sample':False,'physical_attempt_budget':cfg.get('physical_attempt_budget',1),'budget_scope':'One new physical attempt for each original failed request; subsequent original native requests retain original semantics.','permanent_hold':False};C.save(record,saved)
 job=C.read(P/'state/campaign.json')['jobs'][key]
 if rid in job.get('executed_recovery_ids',[]):
  assert job['launches']>=saved['expected_launches']
  if job['launches']==saved['expected_launches']:
   saved.update(process=job.get('process'),started=job.get('started'))
   if C.alive(job.get('process')):saved.update(status='original_scheduler_recovery_running',next_retry_at=None)
   elif saved.get('status') not in TERMINALS:
    try:
     health=target_health(cfg);status=terminal_state(health)
     ended=health.get('end',{}).get('at');assert ended or health['success'],'No real failure timestamp; cannot invent a new backoff'
     due=None if health['success'] else datetime.datetime.fromisoformat(ended).timestamp()+600
     hp=W/(cfg['method']+'_'+rid+'_health.json');C.save(hp,health)
     saved.update(status=status,health=ref(hp),next_retry_at=None if due is None else utc(due),completed_at=C.now(),native_zero_eligible=False,automatic_unreviewed_retry=False)
    except Exception as exc:
     hp=W/(cfg['method']+'_'+rid+'_health_verification_error.json');C.save(hp,{'at':C.now(),'error':repr(exc),'traceback':traceback.format_exc(),'classification':'terminal_verification_unresolved','usage':None,'usd':None,'new_attempt_count':None,'no_retry_registered':True})
     saved.update(status='terminal_verification_unresolved',health_verification_error=ref(hp),next_retry_at=None,native_zero_eligible=False)
 saved['observed_at']=C.now();C.save(record,saved);return saved

def tick():
 queue=C.read(W/'reviewed_queue.json')['batches'];rows=[];errors=[]
 for entry in queue:
  try:rows.append(process(entry))
  except Exception as exc:
   error={'at':C.now(),'config':entry.get('config'),'status':'controller_review_error','error':repr(exc),'traceback':traceback.format_exc(),'next_check_at':utc(time.time()+15),'new_calls':0};errors.append(error);rows.append(error)
 health={'at':C.now(),'process':C.handle(os.getpid()),'owner':str(OWNER),'status':'degraded' if errors else 'running','next_check_at':utc(time.time()+15),'batches':rows,'batch_errors':errors,'normal_queue_control_unmodified':True,'request_cap':250,'minimum_failure_backoff_seconds':600,'worker_signals':0,'permanent_hold':False,'independent_batches_continue_after_one_error':True};C.save(W/'health.json',health)
 if errors:C.save(W/'owner_v2_error.json',{'at':C.now(),'errors':errors,'workers_signaled':0})
def main():
 with (W/'owner.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  while True:
   try:tick()
   except Exception as exc:C.save(W/'owner_v2_error.json',{'at':C.now(),'error':repr(exc),'traceback':traceback.format_exc(),'next_check_at':utc(time.time()+15),'workers_signaled':0})
   time.sleep(15)
if __name__=='__main__':main()
