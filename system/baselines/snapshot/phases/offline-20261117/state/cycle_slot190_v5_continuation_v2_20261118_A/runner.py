"""Bound native reviewer continuation; each missing payload may be attempted once."""
from pathlib import Path
import argparse,datetime,fcntl,hashlib,json,threading,time
import adapter_v5 as A
S=A.S;P=A.P;V=A.V
def check_manifest(path,out):
 m=A.read(path);assert m['stage']=='reviewer_continuation' and m['selection_semantics_revision']==A.REVISION
 assert m['physical_attempt_budget']==10 and m['max_attempts_per_missing_request']==1 and m['minimum_failure_backoff_seconds']>=600
 for name in ['configuration','deployment']:
  assert A.sha(m[name]['path'])==m[name]['sha256']
 for f,h in A.read(S/'deployment_manifest.json')['bindings'].items():assert A.sha(f)==h
 assert A.sha(out/'result.json')==m['expected_result_sha256'] and A.read(out/'run_binding.json')==m['original_binding']
 for name,h in m['files'].items():
  assert A.sha(Path(m['original_snapshot'])/name)==h
  if name not in V.RUNTIME_FILES:assert A.sha(out/name)==h
 assert not list((out/'reviewer/api_requests').glob('*/request.json')),'A previous attempt needs an immutable successor checkpoint'
 assert len(m['planned_requests'])==10
 for i,row in enumerate(m['planned_requests']):
  assert row['component']=='reviewer' and row['request_id']==f'reviewer-{i+1:04}' and row['original_index']==i and row['max_attempts']==1
  assert A.sha(row['payload']['path'])==row['payload']['sha256'] and A.sha(row['carrier']['path'])==row['carrier']['sha256']
 return m
def execute(path,out,client_factory=None):
 m=check_manifest(path,out);planned={r['request_id']:A.read(r['payload']['path']) for r in m['planned_requests']};seen=set();lock=threading.Lock()
 class Client:
  def __init__(self,component):self.component=component;self.native=None
  def completion(self,messages,max_tokens,request_id,**kwargs):
   payload=A.payload(messages,max_tokens,kwargs);key=(self.component,request_id)
   with lock:assert key not in seen;seen.add(key)
   if self.component=='researcher':
    q=Path(m['original_snapshot'])/'researcher/api_requests'/request_id;assert payload==A.read(q/'request.json');r=A.read(q/'response.json');receipt=A.read(q/'receipt.json');assert receipt['status']=='completed' and r['choices'][0]['finish_reason']=='stop';return r
   assert request_id in planned and payload==planned[request_id],'Unadmitted reviewer payload'
   # One client per request ensures bounded attempts; no implicit retries.
   native=(client_factory or V.AstraClient)(out/'reviewer',max_attempts=1)
   return native.completion(messages,max_tokens=max_tokens,request_id=request_id,**kwargs)
 result=None;error=None
 try:result=A.run_chain(A.read(V.INPUTS/'ai-control-deception/configuration.json'),out,{c:Client(c) for c in ['researcher','reviewer']})
 except Exception as exc:error={'type':type(exc).__name__,'message':V.safe(exc)}
 events=[json.loads(x) for x in (out/'reviewer/api_events.jsonl').read_text().splitlines()] if (out/'reviewer/api_events.jsonl').exists() else []
 starts=[e for e in events if e['event']=='attempt_start'];ends=[e for e in events if e['event']=='attempt_end']
 assert len(starts)==len(ends)<=10 and len({e['request_id'] for e in starts})==len(starts)
 assert all(e['request_id'] in planned and e['attempt_in_invocation']==1 for e in starts)
 append_only=[r for r in m['files'] if r.endswith('completion_order.jsonl')]
 checks={'one_attempt_per_bound_missing_reviewer':True,'all10_researcher_successes_cached':sum(c=='researcher' for c,r in seen)==10,'original_files_preserved':all(A.sha(out/r)==h for r,h in m['files'].items() if r not in V.RUNTIME_FILES and r not in append_only),'old_completion_ledger_prefix_preserved':all((out/r).read_bytes().startswith((Path(m['original_snapshot'])/r).read_bytes()) for r in append_only),'canonical_unchanged':A.sha(out/'result.json')==m['expected_result_sha256']}
 failures=[e for e in ends if e.get('status')!='completed'];end=max(ends,key=lambda e:e['at']) if ends else None
 report={'passed':all(checks.values()),'checks':checks,'fixture':m['fixture'],'stage':'reviewer_continuation','native_terminal':result is not None,'status':result['status'] if result else 'checkpoint_waiting_recovery','error':error,'new_physical_attempts':len(starts),'successful_new_requests':sum(e.get('status')=='completed' for e in ends),'failed_usage_remains_unknown':True,'minimum_backoff_seconds':600,'next_retry_at':(datetime.datetime.fromtimestamp(datetime.datetime.fromisoformat(max(e['at'] for e in failures)).timestamp()+600,datetime.timezone.utc).isoformat() if failures else None),'native_zero_eligible':False,'independent_native_publication_required':True,'selection_semantics_revision':A.REVISION}
 if result is None:result={'status':'infrastructure_failure' if not error or error['type']=='InfrastructureFailure' else 'adapter_failure','terminal_reason':error,'proposal_markdown':None,'usage':None,'usd':None,'native_zero_eligible':False,'independent_native_publication_required':True}
 result.update(fixture=m['fixture'],recovery_id=m['recovery_id'],continuation_manifest=str(path),continuation_manifest_sha256=A.sha(path),same_slot=True,new_sample=False)
 V.save(out/m['candidate_filename'],result);V.save(out/m['completion_filename'],report);return report
def fixture_boundary(path,out):
 m=check_manifest(path,out);assert m['fixture'] is True;seen=set();planned={r['request_id']:A.read(r['payload']['path']) for r in m['planned_requests']};lock=threading.Lock()
 class Cached:
  def completion(self,messages,max_tokens,request_id,**kwargs):
   q=Path(m['original_snapshot'])/'researcher/api_requests'/request_id;assert A.payload(messages,max_tokens,kwargs)==A.read(q/'request.json');return A.read(q/'response.json')
 class Boundary:
  def completion(self,messages,max_tokens,request_id,**kwargs):
   assert A.payload(messages,max_tokens,kwargs)==planned[request_id]
   with lock:assert request_id not in seen;seen.add(request_id)
   raise V.InfrastructureFailure('Fixture boundary; no live transport')
 try:A.run_chain(A.read(V.INPUTS/'ai-control-deception/configuration.json'),out,{'researcher':Cached(),'reviewer':Boundary()})
 except V.InfrastructureFailure:pass
 assert len(seen)==10 and not list((out/'reviewer/api_requests').glob('*'))
 V.save(out/'namespace_fixture_acceptance.json',{'passed':True,'fixture':True,'model_calls':0,'all10_original_reviewer_boundaries_verified':True,'public_network_denied':True})
 return 0
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--manifest',required=True,type=Path);ap.add_argument('--fixture-boundary',action='store_true');a=ap.parse_args();m=A.read(a.manifest);assert m['fixture'] is a.fixture_boundary
 out=Path(m['output_dir']);V.require_offline(out)
 with (out/'run.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  if a.fixture_boundary:return fixture_boundary(a.manifest,out)
  r=execute(a.manifest,out)
 return 0 if r['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
