"""Resume each original domain checkpoint with one exact missing-call exception."""
from pathlib import Path
import argparse, copy, inspect, json, socket, sys, textwrap, time, traceback
from dataclasses import asdict
S=Path(__file__).resolve().parent;P=S.parents[1]
R=P/'staging/insightagents_domain_admission_candidate_v2_20261118T0045'
sys.path[:0]=[str(R),str(R/'native/src'),str(P/'adapters')]
import adapter as A
import journal_client as J
import stream_transport as T
from evidence import digest,encode,event,freeze,freeze_bytes,sha

class Matched(BaseException):pass
class Rejected(BaseException):pass
def require(v,m):
 if not v:raise Rejected(m)
def read(p):return json.loads(Path(p).read_text())

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--manifest',type=Path,required=True);ap.add_argument('--fixture',action='store_true');args=ap.parse_args()
 m=read(args.manifest);out=Path(m['output_dir']);snap=Path(m['original_snapshot']);target=out/m['target_directory'];contract=read(m['host_contract']['path']);original_hash=sha(out/'result.json')
 require(original_hash==m['expected_result_sha256'],'Canonical predecessor differs')
 for p,h in read(args.manifest.parent/'source_bindings.json').items():require(sha(p)==h,'Bound source changed: '+p)
 for rel,h in m['files'].items():
  if rel not in ['result.json','offline_boundary.json','offline_launch.json','local_literature_service.log','local_literature_requests.jsonl']:
   require(sha(out/rel)==h,'Original source differs: '+rel)
 require(not (out/'terminal.json').exists() and not (target/'native_returned.json').exists(),'Original slot or target already completed')
 require(read(out/'run_binding.json')==m['original_domain_binding'],'Original domain binding differs')
 if not args.fixture:
  require(time.time()>=m['not_before_epoch'],'Backoff not elapsed')
  with (out/(m['recovery_id']+'_claim.json')).open('x') as f:json.dump({'recovery_id':m['recovery_id'],'target_new_physical_attempts':1},f)
 # Keep the exact original method and only replace its unresolved-call rejection.
 source=textwrap.dedent(inspect.getsource(J.JournaledLLMClient.complete))
 old="raise IncompleteOriginalCall('Original call has unresolved attempts; coordinator recovery is required')"
 new="return self.recover(directory, request, system_prompt, messages, tools, max_tokens, required_tool_name, stage)"
 require(source.count(old)==1,'Original missing-call guard changed')
 source=source.replace(old,new).replace('super().complete(system_prompt,','LLMClient.complete(self, system_prompt,')
 source=source.replace("raise EvidenceViolation('Original native call identity now has a different exact payload')", "freeze(self.output / 'resume_payload_mismatch.json', {'expected': json.loads((directory / 'request.json').read_text()), 'observed': request, 'directory': str(directory)})\n            raise EvidenceViolation('Original native call identity now has a different exact payload')")
 exec(compile(source,str(S/'driver.py'),'exec'),J.__dict__)
 J.JournaledLLMClient.complete=J.complete
 # Only this missing call may contain its one reviewed additional physical attempt.
 source=textwrap.dedent(inspect.getsource(J.JournaledLLMClient.validate_cache)).replace('@staticmethod\n','')
 old="not 1 <= receipt['physical_attempts'] <= 3"
 require(source.count(old)==1,'Original cache attempt guard changed')
 J.RECOVERY_ALLOWED_COUNTS={str((out/rel).resolve()):item['physical_attempts'] for rel,item in m['successful_cache_receipts'].items()}
 J.RECOVERY_ALLOWED_COUNTS[str(target.resolve())]=m['prior_physical_attempts']+1
 source=source.replace(old,"not 1 <= receipt['physical_attempts'] <= RECOVERY_ALLOWED_COUNTS.get(str(directory.resolve()), 3)")
 exec(compile(source,str(S/'driver.py'),'exec'),J.__dict__)
 J.JournaledLLMClient.validate_cache=staticmethod(J.validate_cache)
 # A separately audited storage interruption has no fabricated HTTP receipt.
 # Only its exact preserved physical files can satisfy this historical branch.
 J.STORAGE_INTERRUPTED_PHYSICAL={str((out/rel).resolve()):proof for rel,proof in m.get('storage_interrupted_physical',{}).items()}
 def validate_storage_interruption(physical):
  proof=J.STORAGE_INTERRUPTED_PHYSICAL.get(str(physical.resolve()))
  require(proof is not None and proof['classification']=='storage_interrupted_inflight_unknown','Unreviewed missing physical receipt')
  require(proof['worker_identity_confirmed_exited'] and proof['raw_provider_terminal_absent'],'Storage interruption does not bind exited worker and absent terminal')
  require(not (physical/'receipt.json').exists() and not (physical/'error.json').exists(),'Storage gap now has different terminal evidence')
  require({p.name:sha(p) for p in physical.iterdir() if p.is_file()}==proof['physical_files'],'Storage interruption original physical bytes differ')
  require(sha(physical/'request_body.json')==proof['stream_request_sha256'] and sha(physical/'native_sdk_request_body.json')==proof['native_request_sha256'],'Storage interruption exact original wire differs')
 J.validate_storage_interruption=validate_storage_interruption
 for physical_path in J.STORAGE_INTERRUPTED_PHYSICAL:validate_storage_interruption(Path(physical_path))
 needle="kind = 'receipt.json' if (physical / 'receipt.json').exists() else 'error.json'"
 replacement="if not (physical / 'receipt.json').exists() and not (physical / 'error.json').exists():\n            validate_storage_interruption(physical)\n            continue\n        "+needle
 require(source.count(needle)==1,'Original physical evidence guard changed')
 source=source.replace(needle,replacement)
 exec(compile(source,str(S/'driver.py'),'exec'),J.__dict__)
 J.JournaledLLMClient.validate_cache=staticmethod(J.validate_cache)

 restoration=m.get('resume_object_order_restoration')
 def restore_original_draft_order(progress):return progress
 if restoration:
  require(sha(restoration['source'])==restoration['sha256'],'Original moderator response changed')
  from debate.runner import _extract_json
  ordered_draft=_extract_json(read(restoration['source'])['text'])
  for key in restoration['parsed_value_path']:ordered_draft=ordered_draft[key]
  def restore_original_draft_order(progress):
   for path in restoration['progress_paths']:
    parent=progress
    for key in path[:-1]:parent=parent[key]
    require(parent[path[-1]]==ordered_draft,'Original moderator/checkpoint draft values differ')
    parent[path[-1]]=copy.deepcopy(ordered_draft)
   return progress
 A.restore_original_draft_order=restore_original_draft_order
 source=inspect.getsource(A.run_slot);old="freeze(output / 'result.json',"
 old_progress="progress = copy.deepcopy(latest['native_progress']) if latest else experiment._new_progress(row['topic'], 'semantic_scholar')"
 require(source.count(old_progress)==1,'Original checkpoint restore changed')
 source=source.replace(old_progress,"progress = restore_original_draft_order(copy.deepcopy(latest['native_progress'])) if latest else experiment._new_progress(row['topic'], 'semantic_scholar')")
 require(source.count(old)==1,'Original result writer changed')
 source=source.replace(old,"freeze(output / "+repr(m['candidate_filename'])+",")
 exec(compile(source,str(S/'driver.py'),'exec'),A.__dict__)
 seen=[]
 class TargetPolicy(J.FreshStreamPolicy):
  def __init__(self,output,context):
   super().__init__(output,context)
   self.contract={'target_wire_sha256':m['target_wire_sha256'],'target_stream_wire_sha256':m['target_stream_wire_sha256'],'original_physical_attempts':m['prior_physical_attempts']}
  def is_target(self,directory):return Path(directory).resolve()==target.resolve()
 class Client(J.JournaledLLMClient):
  def recover(self,directory,request,system_prompt,messages,tools,max_tokens,required_tool_name,stage):
   require(directory==target and not seen,'Unreviewed or duplicate missing request')
   require(sha(directory/'request.json')==m['target_request_sha256'],'Original full logical request differs')
   seen.append({'identity':request['identity'],'logical_request_sha256':sha(directory/'request.json'),'full_original_request_exact':True})
   self.recorder.begin(directory);self.recorder.physical_index=m['prior_physical_attempts'];self.recorder.policy=TargetPolicy(out,self.scope_context)
   previous=len(self.call_log);old_retries=self._client.max_retries;self._client.max_retries=0
   original_handle=self.recorder.handle_request
   if args.fixture:
    def matched(req):
     native=req.read();require(json.loads(native)==self.recorder.expected_body,'Native SDK input differs')
     require(digest(native)==m['target_wire_sha256'] and digest(T.stream_wire(native))==m['target_stream_wire_sha256'],'Complete original wire differs')
     seen[0].update(native_sdk_wire_exact=True,stream_wire_exact=True,fixture_model_calls=0)
     raise Matched()
    self.recorder.handle_request=matched
   event(out/'logical_calls.jsonl','reviewed_original_call_continuation',identity=request['identity'],**self.scope_context,recovery_id=m['recovery_id'],new_physical_attempt_budget=1)
   try:
    response=J.LLMClient.complete(self,system_prompt,messages,tools,max_tokens,required_tool_name,stage=stage)
    require(self.recorder.physical_index==m['prior_physical_attempts']+1,'Target physical budget differs')
    freeze(directory/'native_response.json',asdict(response))
    freeze(directory/'native_returned.json',{'identity':request['identity'],'request_sha256':sha(directory/'request.json'),'native_response_sha256':sha(directory/'native_response.json'),'native_usage_rows':self.call_log[previous:],'physical_attempts':self.recorder.physical_index,'physical_files':{str(p.relative_to(directory)):sha(p) for p in sorted(directory.glob('physical-*/*')) if p.is_file()},'unknown_failed_usage_and_usd_preserved_in_attempt_ledger':True,'recovery_id':m['recovery_id']})
    J.JournaledLLMClient.validate_cache(directory)
    event(out/'logical_calls.jsonl','native_call_returned',identity=request['identity'],**self.scope_context,native_response_sha256=sha(directory/'native_response.json'),physical_attempts=self.recorder.physical_index,recovery_id=m['recovery_id'])
    return response
   finally:
    self._client.max_retries=old_retries;self.recorder.handle_request=original_handle
 matched=False;error=None;terminal=None
 original_socket=socket.socket
 if args.fixture:
  def forbidden(*a,**kw):raise Rejected('Fixture network forbidden')
  socket.socket=forbidden
 try:
  terminal=A.run_slot(out,m['package_manifest']['path'],m['domain'],m['slot'],resume=True,fixture=False,client_factory=Client,admission_receipt=m['admission']['path'],admission_sha256=m['admission']['sha256'])
 except Matched:matched=True
 except BaseException as exc:error=type(exc).__name__+': '+str(exc);traceback.print_exc()
 finally:socket.socket=original_socket
 preserved={rel:sha(out/rel)==h for rel,h in m['files'].items() if rel.startswith(('model_calls/','checkpoints/','retrieval/')) or rel in ['run_binding.json','input_material_version.json']}
 prefix={rel:(out/rel).read_bytes().startswith((snap/rel).read_bytes()) for rel in ['model_attempts.jsonl','logical_calls.jsonl','retrieval_events.jsonl','failures.jsonl'] if (snap/rel).exists()}
 checks={'same_domain_contract_and_binding':read(out/'run_binding.json')==m['original_domain_binding'],'all_original_successes_requests_and_failed_attempts_preserved':all(preserved.values()),'all_original_checkpoint_files_preserved':all(v for k,v in preserved.items() if k.startswith('checkpoints/')),'old_ledger_prefixes_preserved':all(prefix.values()),'canonical_predecessor_unchanged':sha(out/'result.json')==original_hash,'exact_target_logical_request_reached_once':len(seen)==1}
 if args.fixture:
  checks.update(stopped_at_exact_original_sdk_and_stream_wire=matched and seen[0].get('native_sdk_wire_exact') and seen[0].get('stream_wire_exact'),zero_physical_attempts=(out/'model_attempts.jsonl').read_bytes()==(snap/'model_attempts.jsonl').read_bytes(),no_terminal_or_proposal=not (out/'terminal.json').exists() and not (out/'proposal.md').exists(),network_forbidden=True)
  report={'passed':all(checks.values()),'checks':checks,'events':seen,'error':error,'model_calls':0,'live_mutations':False,'fixture':True,'recovery_id':m['recovery_id']}
  (out/'transport_fixture_acceptance.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return 0 if report['passed'] else 2
 if error:
  result={**read(out/'result.json'),'status':'infrastructure_failure','terminal_reason':error,'proposal_markdown':None,'usage':None,'usd':None,'recovery_id':m['recovery_id']}
  freeze(out/m['candidate_filename'],result)
 else:
  result=read(out/m['candidate_filename'])
 report={'passed':all(checks.values()),'checks':checks,'events':seen,'error':error,'status':result['status'],'fixture':False,'recovery_id':m['recovery_id'],'new_physical_attempt_budget':1,'independent_native_terminal_publication_required':True}
 freeze(out/m['completion_filename'],report);print(json.dumps(report,indent=2));return 0 if not error and all(checks.values()) else 2

if __name__=='__main__':raise SystemExit(main())
