"""Enable an existing domain's other four jobs only after exact terminal acceptance."""
import argparse,fcntl
from contracts import *
from activate import C,G,verify_proof,validated

def validate_terminal(domain,reference,state,methods,registry):
 assert domain!='agent-memory','Agent-memory was already accepted in the original plan'
 b=slot_plan(domain,1);proof=verify_proof(reference,domain)
 assert proof['run_id']==b['run_id'] and proof['admission_id']==b['admission_id']
 assert registry.get(b['run_id'])==reference,'Canonical independent acceptance is not registered'
 path=Path(b['output'])/'result.json';result=read(path)
 assert proof['bindings'].get(str(path))==sha(path)
 assert all(result.get(k)==v for k,v in {'status':'completed','fixture':False,'method':METHOD,'domain':domain,'run_id':b['run_id'],'admission_id':b['admission_id'],'comparison_scope':SCOPE}.items())
 job=state['jobs'][f'{METHOD}__{domain}__01__generation']
 assert job['status']=='completed' and not C.alive(job.get('process'))
 assert methods[METHOD]['eligible_slots_by_domain'].get(domain)==[1]
 for slot in range(2,6):
  for kind in ('generation','card'):
   item=state['jobs'][f'{METHOD}__{domain}__{slot:02}__{kind}'];assert item['status']=='pending' and item['launches']==0 and not item.get('process')
  assert not Path(slot_plan(domain,slot)['output']).exists()
 return True

def release(domain,reference,execute=False):
 with C.admission_lock():
  with (P/'state/methods.lock').open('a+') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX)
   state=read(P/'state/campaign.json');methods=read(P/'state/methods.json');registry=read(P/'state/new_method_accounting/accepted_terminals.json')
   plan_path=D/'activation_plan.json';review_ref=methods[METHOD]['runtime_independent_review'];validated(plan_path,sha(plan_path),review_ref)
   validate_terminal(domain,reference,state,methods,registry)
   assert G.check()['passed']
   if not execute:return {'passed':True,'activated':False,'domain':domain,'paid_calls':0}
   spec=methods[METHOD];spec['eligible_slots_by_domain'][domain]=[1,2,3,4,5]
   spec['full_native_accepted_domains']=sorted(set(spec['full_native_accepted_domains'])|{domain})
   spec['scoring_approved_domains']=sorted(set(spec['scoring_approved_domains'])|{domain})
   spec.setdefault('domain_terminal_acceptances',{})[domain]=reference
   spec['max_generation_workers']=min(230,41+4*(len(spec['full_native_accepted_domains'])-1))
   C.save(P/'state/methods.json',methods)
   receipt=P/'state/ai_scientist_v3_common38_activation_v2_20261117'/f'{domain}_remaining_four_release.json'
   C.save(receipt,{'passed':True,'domain':domain,'native_acceptance':reference,'enabled_slots':[2,3,4,5],'scheduler_refresh':False,'jobs_added':0,'worker_signals':0,'paid_calls_by_controller':0,'at':C.now()})
   return read(receipt)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--domain',required=True);ap.add_argument('--native-acceptance',required=True);ap.add_argument('--acceptance-sha256',required=True);ap.add_argument('--execute',action='store_true');a=ap.parse_args()
 print(__import__('json').dumps(release(a.domain,{'path':str(Path(a.native_acceptance).resolve()),'sha256':a.acceptance_sha256},a.execute)))
if __name__=='__main__':main()
