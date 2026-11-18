"""Review-gated append-only admission and one primary-scheduler refresh."""
import argparse,copy,fcntl,os,shutil,signal,subprocess,sys,time
from pathlib import Path
from contracts import *
from result_export import save
sys.path.insert(0,str(P));sys.path.insert(0,str(P/'scoring/revisions/new-method-accounting-v2-20261117'))
import campaign as C,offline_gates as G,accounting_new_methods as A

def pending_jobs():
 result={}
 for b in plans():
  if b['preserve_existing_completed_slot']:continue
  for kind in ('generation','card'):
   key=f"{METHOD}__{b['domain']}__{b['slot']:02}__{kind}"
   result[key]={'key':key,'kind':kind,'method':METHOD,'domain':b['domain'],'slot':b['slot'],'status':'pending','launches':0}
 return result

def initial_eligibility():
 return {b['domain']:([1,2,3,4,5] if b['domain']=='agent-memory' else [1]) for b in plans()}

def verify_proof(ref,domain,scoring=False):
 proof=bound(ref)
 assert proof.get('passed') is True and proof.get('fixture') is False
 assert proof.get('method')==METHOD and proof.get('domain')==domain and proof.get('comparison_scope')==SCOPE
 assert proof.get('checks') and all(v is True for v in proof['checks'].values())
 assert proof.get('bindings') and all(sha(p)==h for p,h in proof['bindings'].items())
 if not scoring:assert proof.get('slot')==1
 return proof

def validated(plan_path,plan_sha,review_ref):
 plan=bound({'path':str(plan_path),'sha256':plan_sha});review=bound(review_ref)
 assert plan['schema']=='sakana-domain-expansion-plan-v2' and plan['fixture'] is False
 assert plan['new_generation_jobs']==189 and plan['new_card_jobs']==189 and plan['new_novelty_jobs']==0
 assert plan['initial_eligible_slots_by_domain']==initial_eligibility()
 assert plan['capacity']=={'generation':230,'scoring':20,'physical_requests':250}
 assert plan['comparison_scope']==SCOPE and plan['main_comparison_included'] is False
 assert plan['activation_directory']==str(P/'state/ai_scientist_v3_common38_activation_v2_20261117')
 assert review.get('status')=='accepted_v3_domain_runtime_package' and review.get('passed') is True and review.get('fixture') is False and review.get('paid_calls')==0
 assert review.get('reviewer') and review.get('manifest_sha256')==plan['runtime_manifest_sha256'] and review.get('plan_sha256')==plan_sha and review.get('controller_index_sha256')==plan['controller_index']['sha256']
 assert review.get('activation_script_sha256')==sha(__file__)
 verify_manifest(plan['runtime_manifest_sha256'])
 index=bound(plan['controller_index']);receipt=bound(plan['offline_receipt'])
 assert index['schema']=='sakana-domain-controller-index-v2' and index['fixture'] is False and index['runtime_manifest_sha256']==plan['runtime_manifest_sha256']
 assert plan['command']==['/usr/bin/python3','-B',str(D/'host_launch.py'),'--controller-index',plan['controller_index']['path'],'--controller-index-sha256',plan['controller_index']['sha256']]
 assert receipt['command']==plan['command'] and receipt['comparison_scope']==SCOPE
 assert not G.receipt(plan['offline_receipt'],G.METHOD_CHECKS,P)
 assert plan['accounting_implementation']=={'path':str(Path(A.__file__).resolve()),'sha256':sha(A.__file__)}
 expected=[registration(b,stage) for b in plans() if not b['preserve_existing_completed_slot'] for stage in ('native_generation','scoring')]
 assert plan['accounting_registrations']==expected and len(expected)==378
 registry={'schema':'new-method-cost-registration-v1','registrations':expected}
 assert len(index['admissions'])==189
 for b in plans():
  if b['preserve_existing_completed_slot']:continue
  a=bound(index['admissions'][f"{b['domain']}/slot-{b['slot']:02}"])
  validate_admission(a,b,plan['controller_index']['sha256'],plan['runtime_manifest_sha256'],registry,review)
 for row in expected:A.validate_registration(row)
 first=verify_proof(plan['preserved_first_native_acceptance'],'agent-memory')
 score=verify_proof(plan['preserved_first_score_acceptance'],'agent-memory',True)
 assert first['run_id']=='ai-scientist-v3-agent-memory-slot01-native-20261117' and first['admission_id']=='ai-scientist-v3-first-controlled-20261117'
 assert score['scores']=={'C':3,'I':4,'S':3}
 return plan

def method_updates(plan,review_ref,current):
 return dict(enabled=True,status='reviewed_native_domain_first_slots',lifecycle='reviewed_native_domain_first_slots',command=plan['command'],eligible_domains=sorted(initial_eligibility()),eligible_slots=[1,2,3,4,5],eligible_slots_by_domain=initial_eligibility(),max_generation_workers=41,full_native_accepted_domains=['agent-memory'],scoring_approved=True,scoring_approved_domains=['agent-memory'],runtime_independent_review=review_ref,domain_terminal_acceptances={'agent-memory':plan['preserved_first_native_acceptance']},comparison_scope=SCOPE,main_comparison_included=False,controlled_first_slot_only=False,automatic_followup_slots=False,blocker='Other 37 domains admit only their first native slot; remaining four require same-domain independent terminal acceptance.',live_stage_note='Additional official AI-Scientist-v3 first ideation stage only. Agent-memory slot01 stays unchanged; slots02–05 use fresh contexts. Other37 domain first slots await native acceptance. Full raw artifacts and all failed costs remain registered; no novelty expansion.')

def spawn_scheduler(dest,name,command):
 with (dest/name).open('ab') as log:return subprocess.Popen(command,cwd=P,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)

def stop(handle):
 if not C.alive(handle):return
 os.kill(handle['pid'],signal.SIGTERM);deadline=time.monotonic()+8
 while C.alive(handle) and time.monotonic()<deadline:time.sleep(.05)
 if C.alive(handle):raise RuntimeError('Primary scheduler did not stop')

def activate(plan_path,plan_sha,review_ref,execute=False):
 plan=validated(plan_path,plan_sha,review_ref)
 if not execute:return {'passed':True,'activated':False,'paid_calls':0,'new_generation_jobs':189,'new_card_jobs':189,'new_novelty_jobs':0,'initial_runnable_new_generation_slots':41}
 dest=Path(plan['activation_directory']);dest.mkdir(parents=True,exist_ok=False)
 with C.admission_lock():
  with (P/'state/activation.lock').open('a+') as al,(P/'state/methods.lock').open('a+') as ml:
   fcntl.flock(al,fcntl.LOCK_EX);fcntl.flock(ml,fcntl.LOCK_EX)
   validated(plan_path,plan_sha,review_ref)
   control=read(P/'state/control.json');state=read(P/'state/campaign.json');methods=read(P/'state/methods.json');activation=read(P/'state/activation.json')
   assert control['enabled'] is True and control['generation_workers']==230 and control['scoring_workers']==20 and control['request_concurrency']==250
   assert G.check()['passed'],'Original common gate must pass before admission'
   newjobs=pending_jobs();assert not set(newjobs).intersection(state['jobs'])
   existing={k:j for k,j in state['jobs'].items() if j['method']==METHOD}
   assert set(existing)=={f'{METHOD}__agent-memory__01__generation',f'{METHOD}__agent-memory__01__card'} and all(j['status']=='completed' for j in existing.values())
   assert all(not Path(row['root']).exists() for row in plan['accounting_registrations'])
   old=state['scheduler'];assert C.alive(old)
   oldcmd=[s.decode() for s in Path(f"/proc/{old['pid']}/cmdline").read_bytes().split(b'\0') if s]
   assert str(P/'campaign.py') in oldcmd,'Unexpected primary scheduler entry; independent refresh review required'
   before=dest/'before';before.mkdir()
   for name in ('campaign.json','methods.json','activation.json','control.json'):shutil.copy2(P/'state'/name,before/name)
   save(dest/'inflight_before.json',{k:j for k,j in state['jobs'].items() if C.alive(j.get('process'))})
   for row in plan['accounting_registrations']:A.register(row)
   registry=read(A.REGISTRY);assert all(sum(r==row for r in registry['registrations'])==1 for row in plan['accounting_registrations'])
   changed_methods=copy.deepcopy(methods);changed_methods[METHOD].update(method_updates(plan,review_ref,methods[METHOD]))
   changed_activation=copy.deepcopy(activation);changed_activation['method_receipts'][METHOD]=plan['offline_receipt']
   stopped=False;proc=None
   try:
    C.save(P/'state/methods.json',changed_methods);C.save(P/'state/activation.json',changed_activation)
    gate=G.check();save(dest/'gate_before_refresh.json',gate);assert gate['passed'],gate
    stop(old);stopped=True;assert read(P/'state/campaign.json')==state,'Locked state changed'
    newstate=copy.deepcopy(state);newstate['jobs'].update(newjobs);C.save(P/'state/campaign.json',newstate)
    proc=spawn_scheduler(dest,'scheduler.log',['/usr/bin/python3','-B',str(D/'scheduler_entry.py')]);newhandle=C.handle(proc.pid)
    deadline=time.monotonic()+20;started=False
    while time.monotonic()<deadline:
     assert C.alive(newhandle),'Refreshed scheduler exited'
     with (P/'state/scheduler.lock').open('a+') as lock:
      try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
      except BlockingIOError:started=True
     if started:break
     time.sleep(.05)
    assert started,'Refreshed scheduler did not own original lock'
   except BaseException as exc:
    if proc is not None:stop(C.handle(proc.pid))
    C.save(P/'state/methods.json',methods);C.save(P/'state/activation.json',activation);C.save(P/'state/campaign.json',state)
    recovered=C.handle(spawn_scheduler(dest,'rollback_scheduler.log',oldcmd).pid) if stopped and not C.alive(old) else None
    save(dest/'failed_activation_preserved.json',{'error':str(exc),'old_jobs_and_methods_restored':True,'unstarted_accounting_rows_preserved':True,'restored_scheduler':recovered,'worker_signals':0});raise
   result={'at':C.now(),'passed':True,'old_scheduler':old,'new_scheduler':newhandle,'plan_sha256':plan_sha,'independent_review':review_ref,'new_generation_jobs':189,'new_card_jobs':189,'new_novelty_jobs':0,'existing_jobs_identical':all(newstate['jobs'][k]==j for k,j in state['jobs'].items()),'retained_existing_jobs':len(state['jobs']),'worker_signals':0,'controller_paid_calls':0,'accounting_registered_before_launch':True,'shared_capacity_unchanged':True,'initial_eligible_slots_by_domain':initial_eligibility()}
   save(dest/'activation.json',result)
 return result

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--plan',required=True);ap.add_argument('--plan-sha256',required=True);ap.add_argument('--independent-review',required=True);ap.add_argument('--review-sha256',required=True);ap.add_argument('--execute',action='store_true');args=ap.parse_args()
 print(__import__('json').dumps(activate(args.plan,args.plan_sha256,{'path':str(Path(args.independent_review).resolve()),'sha256':args.review_sha256},args.execute)))
if __name__=='__main__':main()
