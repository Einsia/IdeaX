"""Replay the original seeded matched-graph native conversation to its missing response."""
from pathlib import Path
import argparse,copy,fcntl,hashlib,json,sys
S=Path(__file__).resolve().parent;P=S.parents[1];sys.path.insert(0,str(P/'adapters'))
import sciagents as N,sciagents_matched_graph as M
from common import read,save,now,safe,InfrastructureFailure,NativeFailure
from offline_support import require_offline
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
class FixtureBoundary(BaseException):pass

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--manifest',type=Path,required=True);ap.add_argument('--fixture',action='store_true');a=ap.parse_args();m=read(a.manifest);out=Path(m['output_dir']);snap=Path(m['original_snapshot']);require_offline(out);assert sha(out/'result.json')==m['expected_result_sha256'] and sha(m['domain_json'])==m['domain_sha256']
 for p,h in read(a.manifest.parent/'source_bindings.json').items():assert sha(p)==h,p
 graph=read(m['graph_manifest']);assert sha(m['graph_manifest'])==m['graph_manifest_sha256']
 for p,h in graph['bindings'].items():assert sha(p)==h,p
 known={r['request_id']:r for r in m['requests']};consumed={r['request_id']:r for r in m.get('historical_consumed_failure_requests',[])};failed={r['request_id'] for r in m['failed_requests']};success={k for k,r in known.items() if r['completed']};replayed=set();replayed_errors=set();attempted=set();resolved=set();new=[];native={};boundary={}
 original_completion=N.AstraClient.completion;original_setup=M.setup;original_require=M.require_offline
 def setup(*args,**kwargs):
  value=original_setup(*args,**kwargs);native.update(value);return value
 def require_bound(output,*args,**kwargs):
  assert Path(output).resolve()==out;return require_offline(output)
 def completion(self,messages,system=None,max_tokens=32768,request_id=None,**kwargs):
  value={'model':'gpt-6-astra','messages':([{'role':'system','content':system}]+list(messages)) if system is not None else list(messages),'reasoning_effort':'xhigh','max_completion_tokens':max_tokens,'stream':True,'stream_options':{'include_usage':True}}
  for k in ['tools','tool_choice','response_format','stop','n','seed','parallel_tool_calls']:
   if kwargs.get(k) is not None:value[k]=kwargs[k]
  if request_id in known:
   req=snap/'api_requests'/request_id;assert value==read(req/'request.json'),'Original full native SciAgents payload differs'
   assert request_id not in replayed|attempted|replayed_errors
   if request_id in consumed:
    record=consumed[request_id]
    assert record['native_tool_error_already_consumed'] and record['last_end']['status']=='infrastructure_failure'
    replayed_errors.add(request_id)
    raise InfrastructureFailure(record['last_end']['error'])
   if request_id in success:
    receipt=read(req/'receipt.json');response=read(req/'response.json');assert receipt['status']=='completed' and response['choices'][0]['finish_reason'] in ['stop','tool_calls','function_call'];assert hashlib.sha256(json.dumps(response,ensure_ascii=False).encode()).hexdigest()==receipt['response_sha256'];replayed.add(request_id);return copy.deepcopy(response)
   attempted.add(request_id);assert replayed==success and replayed_errors==set(consumed)
   history=native['groupchat'].messages;novelty=native['novelty_admin'].chat_messages.get(native['novelty_assistant'],[])
   assert history==read(snap/'native_partial_chat_history.json'),'Original groupchat context differs'
   assert novelty==read(snap/'native_novelty_chat_history.json'),'Original novelty subchat context differs'
   boundary.update(request_id=request_id,full_payload_exact=True,original_group_history_exact=True,original_novelty_history_exact=True,all_original83_responses_replayed=len(replayed),original_seed_sha256=sha(out/'random_seed.json'))
   if a.fixture:raise FixtureBoundary()
   limit=self.max_attempts;self.max_attempts=1
   try:answer=original_completion(self,messages,system=system,max_tokens=max_tokens,request_id=request_id,**kwargs);resolved.add(request_id);return answer
   finally:self.max_attempts=limit
  assert resolved==failed and replayed==success and replayed_errors==set(consumed),'New model request before original missing response completed';assert not a.fixture;new.append(request_id)
  return original_completion(self,messages,system=system,max_tokens=max_tokens,request_id=request_id,**kwargs)
 with (out/'run.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);M.setup=setup;M.require_offline=require_bound;N.AstraClient.completion=completion;reached=False
  try:result=M.generate(read(m['domain_json']),out,Path(graph['graph_bundle']))
  except FixtureBoundary:reached=True;result={'status':'infrastructure_failure','terminal_reason':'Fixture stopped at original missing response'}
  except InfrastructureFailure as exc:result={'status':'infrastructure_failure','proposal_markdown':None,'terminal_reason':safe(exc),'usage':None,'usd':None}
  except NativeFailure as exc:result={'status':'native_failure','proposal_markdown':None,'terminal_reason':safe(exc),'usage':None,'usd':None}
  except Exception as exc:result={'status':'adapter_failure','proposal_markdown':None,'terminal_reason':safe(exc),'error_type':type(exc).__name__}
  finally:M.setup=original_setup;M.require_offline=original_require;N.AstraClient.completion=original_completion
  protected={r:h for r,h in m['files'].items() if r.startswith('api_requests/') or r in ['random_seed.json','input_material_version.json']}
  checks={'historical_consumed_api_errors_replayed_without_retry':replayed_errors==set(consumed),'all83_original_responses_replayed_once':replayed==success,'only_original_missing_response_attempted':attempted==failed,'original_full_payload_and_both_native_histories_exact':bool(boundary),'old_api_and_seed_material_preserved':all(sha(out/r)==h for r,h in protected.items()),'old_api_ledger_prefix_preserved':(out/'api_events.jsonl').read_bytes().startswith((snap/'api_events.jsonl').read_bytes()),'canonical_failure_unchanged':sha(out/'result.json')==m['expected_result_sha256'],'same_matched_graph_manifest':sha(m['graph_manifest'])==m['graph_manifest_sha256']}
  report={'at':now(),'passed':all(checks.values()),'checks':checks,'model_calls':0 if a.fixture else None,'fixture':a.fixture,'boundary':boundary,'replayed':sorted(replayed),'historical_consumed_errors_replayed':sorted(replayed_errors),'attempted':sorted(attempted),'resolved':sorted(resolved),'new_native_requests':new,'recovery_id':m['recovery_id'],'native_result_status':result['status'],'error':result.get('terminal_reason')}
  if a.fixture:
   checks.update(model_transport_stopped=reached,api_ledger_bytewise_unchanged=sha(out/'api_events.jsonl')==sha(snap/'api_events.jsonl'),no_proposal=not (out/'proposal.md').exists());report['passed']=all(checks.values());save(out/'transport_fixture_acceptance.json',report);return 0 if report['passed'] else 2
  result.update(recovery_id=m['recovery_id'],same_slot=True,same_material=True,new_sample=False,independent_publication_required=True,original_failure_manifest=str(a.manifest),original_failure_manifest_sha256=sha(a.manifest),comparison_scope='matched-domain-abstract-graph',graph_sha256=graph['graph_sha256'])
  if not report['passed']:result.update(status='adapter_failure',proposal_markdown=None,terminal_reason='Original native conversation replay preservation failed')
  save(out/m['candidate_filename'],result);save(out/m['completion_filename'],report);return 0 if report['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
