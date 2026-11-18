"""Replay every successful cache and attempt only bound original failed reviewer IDs once."""
from pathlib import Path
import argparse,datetime,fcntl,json,threading,time
import adapter_v5 as A
import checkpoint_utils as U
S=A.S;P=A.P;V=A.V
def check_manifest(path,out,now_epoch=None):
 m=U.read(path);assert m['stage']=='reviewer_checkpoint_successor' and m['selection_semantics_revision']==A.REVISION
 failed=m['missing_request_ids'];assert failed and len(failed)==len(set(failed))==m['physical_attempt_budget']<=10 and m['max_attempts_per_missing_request']==1 and m['minimum_failure_backoff_seconds']>=600
 assert m['not_before_epoch']>=max(U.epoch(r['last_end']['at'])+600 for r in m['failed_requests'])
 assert (time.time() if now_epoch is None else now_epoch)>=m['not_before_epoch'],'Actual failure end + 600 seconds not elapsed'
 for n in ['configuration','deployment']:assert U.sha(m[n]['path'])==m[n]['sha256']
 for p,h in U.read(S/'deployment_manifest.json')['bindings'].items():assert U.sha(p)==h,p
 U.unchanged(out,Path(m['original_snapshot']),m['files']);assert U.sha(out/'result.json')==m['expected_result_sha256'] and U.read(out/'run_binding.json')==m['original_binding']
 assert len(m['planned_requests'])==10
 for i,row in enumerate(m['planned_requests']):
  ident=f'reviewer-{i+1:04}';assert row['request_id']==ident and row['original_index']==i and row['max_attempts']==1
  assert U.sha(row['payload']['path'])==row['payload']['sha256'] and U.sha(row['carrier']['path'])==row['carrier']['sha256']
  assert U.read(row['payload']['path'])==U.read(out/'reviewer/api_requests'/ident/'request.json'),'Original reviewer prompt differs'
  state=U.request_state(out,'reviewer',ident);assert state['completed']==(ident not in failed)
  if ident in failed:assert state==next(x for x in m['failed_requests'] if x['request_id']==ident)
  else:U.cached(out,'reviewer',ident,U.read(row['payload']['path']))
 for i in range(1,11):U.cached(out,'researcher',f'researcher-{i:04}')
 return m
def execute(path,out,client_factory=None,fixture_boundary=False):
 m=check_manifest(path,out,now_epoch=U.read(path)['not_before_epoch'] if fixture_boundary else None);planned={r['request_id']:U.read(r['payload']['path']) for r in m['planned_requests']};missing=set(m['missing_request_ids']);seen=set();lock=threading.Lock();prior=(out/'reviewer/api_events.jsonl').read_bytes()
 class Client:
  def __init__(self,component):self.component=component
  def completion(self,messages,max_tokens,request_id,**kwargs):
   payload=A.payload(messages,max_tokens,kwargs);key=(self.component,request_id)
   with lock:assert key not in seen;seen.add(key)
   if self.component=='reviewer':assert payload==planned[request_id]
   if self.component=='researcher' or request_id not in missing:return U.cached(Path(m['original_snapshot']),self.component,request_id,payload)
   if fixture_boundary:raise V.InfrastructureFailure('Fixture only: failed original reviewer boundary reached without transport')
   return (client_factory or V.AstraClient)(out/'reviewer',max_attempts=1).completion(messages,max_tokens=max_tokens,request_id=request_id,**kwargs)
 result=None;error=None
 try:result=A.run_chain(U.read(V.INPUTS/'ai-control-deception/configuration.json'),out,{c:Client(c) for c in ['researcher','reviewer']})
 except Exception as exc:error={'type':type(exc).__name__,'message':V.safe(exc)}
 after=(out/'reviewer/api_events.jsonl').read_bytes();assert after.startswith(prior);events=[json.loads(x) for x in after[len(prior):].decode().splitlines()];starts=[e for e in events if e['event']=='attempt_start'];ends=[e for e in events if e['event']=='attempt_end']
 assert len(starts)==len(ends)<=len(missing) and len({e['request_id'] for e in starts})==len(starts) and all(e['request_id'] in missing and e['attempt_in_invocation']==1 for e in starts)
 U.unchanged(out,Path(m['original_snapshot']),m['files'],after=True);assert U.sha(out/'result.json')==m['expected_result_sha256']
 checks={'only_failed_original_reviewers_may_call_api':True,'all20_logical_requests_original_order_and_payload':len(seen)==20,'all_successful_cache_files_unchanged':True,'all_original_ledger_prefixes_unchanged':True,'canonical_unchanged':True}
 if fixture_boundary:
  assert m['fixture'] and not starts and result is None and error['type']=='InfrastructureFailure'
  U.save(out/'namespace_fixture_acceptance.json',{'passed':all(checks.values()),'checks':checks,'fixture':True,'model_calls':0,'failed_original_boundaries':sorted(missing)});return {'passed':True}
 failures=[e for e in ends if e.get('status')!='completed'];report={'passed':all(checks.values()),'checks':checks,'fixture':m['fixture'],'stage':m['stage'],'native_terminal':result is not None,'status':'completed' if result else 'checkpoint_waiting_recovery','error':error,'new_physical_attempts':len(starts),'successful_new_requests':sum(e.get('status')=='completed' for e in ends),'cached_researcher_responses':10,'cached_reviewer_responses':10-len(missing),'minimum_backoff_seconds':600,'next_retry_at':datetime.datetime.fromtimestamp(max(U.epoch(e['at']) for e in failures)+600,datetime.timezone.utc).isoformat() if failures else None,'native_zero_eligible':False,'failed_usage_remains_unknown':True,'independent_native_publication_required':True,'selection_semantics_revision':A.REVISION}
 if result is None:result={'status':'infrastructure_failure' if error and error['type']=='InfrastructureFailure' else 'adapter_failure','terminal_reason':error,'proposal_markdown':None,'usage':None,'usd':None,'native_zero_eligible':False,'independent_native_publication_required':True}
 result.update(fixture=m['fixture'],recovery_id=m['recovery_id'],continuation_manifest=str(path),continuation_manifest_sha256=U.sha(path),same_slot=True,new_sample=False)
 U.save(out/m['candidate_filename'],result);U.save(out/m['completion_filename'],report);return report
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--manifest',type=Path,required=True);ap.add_argument('--fixture-boundary',action='store_true');a=ap.parse_args();m=U.read(a.manifest);assert m['fixture'] is a.fixture_boundary;out=Path(m['output_dir']);V.require_offline(out)
 with (out/'run.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);r=execute(a.manifest,out,fixture_boundary=a.fixture_boundary)
 return 0 if r['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
