"""Derive all ten original reviewer payloads from successful native generation caches."""
from pathlib import Path
import argparse,copy,datetime,hashlib,importlib.util,json,shutil,sys,threading
import adapter_v5 as A
S=A.S;P=A.P;V=A.V;CANARY=P/'state/cycle_slot190_v5_recovery_20261118_A'
def save(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
def ref(p):return {'path':str(p),'sha256':A.sha(p)}
def files(root):return {str(f.relative_to(root)):A.sha(f) for f in root.rglob('*') if f.is_file()}
def build(package,source,health_reference=None,fixture=False,canary_config=None):
 assert package.is_relative_to(S/'fixtures') if fixture else package.is_relative_to(S/'packages')
 assert not package.exists();package.mkdir(parents=True)
 original=P/'runs/cycleresearcher/ai-control-deception/slot-05'
 if not fixture:
  assert source==original and health_reference
  health=A.read(health_reference);assert health['success'] is True and health['passed'] is True and health['new_physical_attempts']==1 and health['probe_done'] is True and health['reviewer_stage_entered'] is False
  assert health['attempts'][0]['gateway_identity_unique'] is True and health['attempts'][0]['local_terminal'] is True
  assert canary_config;cfg=A.read(canary_config);verifier=cfg['health_verifier'];assert A.sha(verifier['path'])==verifier['sha256'] and cfg['job_key']=='cycleresearcher__ai-control-deception__05__generation' and cfg['stop_after_target'] and cfg['reviewer_api_allowed'] is False
  sys.path.insert(0,str(Path(verifier['path']).parent));spec=importlib.util.spec_from_file_location('cycle190_live_canary_health',verifier['path']);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
  fresh=h.target_health(cfg);assert fresh['success'] and fresh['passed']
  assert fresh['attempts'][0]['gateway_request_id']==health['attempts'][0]['gateway_request_id']
 assert not list((source/'reviewer/api_requests').glob('*/request.json')),'Initial continuation only; existing reviewer attempts require a new checkpoint manifest'
 snapshot=package/'original_run';shutil.copytree(source,snapshot);inventory=files(snapshot)
 config=A.read(V.INPUTS/'ai-control-deception/configuration.json');plan={};used=set();lock=threading.Lock();stage=package/'native_plan'
 class CachedResearcher:
  def completion(self,messages,max_tokens,request_id,**kwargs):
   q=snapshot/'researcher/api_requests'/request_id;payload=A.payload(messages,max_tokens,kwargs);assert payload==A.read(q/'request.json')
   receipt=A.read(q/'receipt.json');response=A.read(q/'response.json');assert receipt['status']=='completed' and response['choices'][0]['finish_reason']=='stop'
   assert hashlib.sha256(json.dumps(response,ensure_ascii=False).encode()).hexdigest()==receipt['response_sha256']
   with lock:assert request_id not in used;used.add(request_id)
   return response
 class ReviewerBoundary:
  def completion(self,messages,max_tokens,request_id,**kwargs):
   value=A.payload(messages,max_tokens,kwargs)
   with lock:assert request_id not in plan;plan[request_id]=value
   raise V.InfrastructureFailure('Recorded unstarted original reviewer boundary; no model transport')
 error=None
 try:A.run_chain(config,stage,{'researcher':CachedResearcher(),'reviewer':ReviewerBoundary()})
 except V.InfrastructureFailure as exc:error=str(exc)
 assert error and len(used)==len(plan)==10 and sorted(plan)==[f'reviewer-{i:04}' for i in range(1,11)]
 assert not (stage/'selection_v5.json').exists() and not list((stage/'reviewer/api_requests').glob('*'))
 planned=[]
 for i,ident in enumerate(sorted(plan)):
  body=plan[ident];carrier=stage/'carriers'/f'{i:02}.txt';assert body['messages'][-1]['content']==carrier.read_text() and body['max_completion_tokens']==35000
  path=package/'planned_requests'/f'{ident}.json';save(path,body);planned.append({'component':'reviewer','request_id':ident,'original_index':i,'payload':ref(path),'carrier':ref(carrier),'max_attempts':1,'prior_physical_attempts':0})
 job=A.read(P/'state/campaign.json')['jobs']['cycleresearcher__ai-control-deception__05__generation']
 manifest={'stage':'reviewer_continuation','fixture':fixture,'method':'cycleresearcher','domain':'ai-control-deception','slot':5,'job_key':job['key'],'recovery_id':'cycleresearcher__ai-control-deception__05__generation-v5-reviewer-'+package.name,'output_dir':str(original),'original_snapshot':str(snapshot),'files':inventory,'expected_launches':job['launches'],'expected_result_sha256':A.sha(source/'result.json'),'original_binding':A.read(source/'run_binding.json'),'selection_semantics_revision':A.REVISION,'configuration':ref(S/'configuration_v5.json'),'deployment':ref(S/'deployment_manifest.json'),'canary_health':ref(health_reference) if health_reference else None,'canary_owner_config':ref(canary_config) if canary_config else None,'planned_requests':planned,'physical_attempt_budget':10,'max_attempts_per_missing_request':1,'minimum_failure_backoff_seconds':600,'successful_cache_replay_only':True,'new_sample':False,'candidate_filename':'cycle_v5_full_candidate_result.json','completion_filename':'cycle_v5_full_completion.json','native_plan_generated_with_actual_upstream_generator_and_Standard4_reviewer':True,'public_network_denied':True,'shared_request_cap':250,'coordinator_service_recovery_admission_required':True,'model_calls_by_preparation':0}
 save(package/'manifest.json',manifest);save(package/'preparation_acceptance.json',{'passed':True,'checks':{'all10_original_generation_responses_cached_once':len(used)==10,'all10_original_native_reviewer_payloads_bound':len(plan)==10,'original_carrier_order_preserved':True,'no_model_transport_constructed':True,'v5_configuration_and_actual_deployment_bound':True,'original_files_unchanged':files(source)==inventory},'fixture':fixture,'model_calls':0,'manifest':ref(package/'manifest.json')})
 if not fixture:
  end=datetime.datetime.fromisoformat(health['end']['at']).timestamp()
  owner={'method':'cycleresearcher','job_key':job['key'],'recovery_id':manifest['recovery_id'],'manifest':str(package/'manifest.json'),'manifest_sha256':A.sha(package/'manifest.json'),'expected_result_sha256':manifest['expected_result_sha256'],'expected_launches':job['launches'],'output_dir':str(original),'original_snapshot':str(snapshot),'not_before_epoch':end,'minimum_backoff_seconds':600,'physical_attempt_budget':10,'new_physical_attempt_budget_per_original_failed_request':1,'max_attempts_per_missing_request':1,'command':['/usr/bin/python3',str(S/'host.py'),'--manifest',str(package/'manifest.json'),'--admission',str(package/'admission.json')],'health_verifier':{**ref(S/'health_verifier.py'),'function':'target_health'},'same_slot':True,'same_material':True,'new_sample':False,'next_native_requests_original_semantics':True,'independent_native_publication_required':True,'preparation_failure_is_not_an_upstream_attempt':True,'reviewer_api_allowed':True,'all10_researcher_cache_only':True,'native_zero_eligible':False,'selection_semantics_revision':A.REVISION,'service_recovery_evidence':ref(health_reference),'fixture':str(S/'fixtures/namespace_acceptance.json')}
  save(package/'owner_config.json',owner)
  bindings=dict(A.read(S/'deployment_manifest.json')['bindings']);bindings[str(S/'deployment_manifest.json')]=A.sha(S/'deployment_manifest.json');bindings[str(health_reference)]=A.sha(health_reference);bindings[str(canary_config)]=A.sha(canary_config)
  for f in package.rglob('*'):
   if f.is_file():bindings[str(f)]=A.sha(f)
  for f in [S/'fixtures/acceptance.json',S/'fixtures/namespace_acceptance.json']:bindings[str(f)]=A.sha(f)
  save(package/'source_bindings.json',bindings)
  save(package/'admission_template.json',{'passed':False,'approved_normal_admission_same_input_batch':False,'verified_service_recovered':False,'manifest_sha256':A.sha(package/'manifest.json'),'deployment_manifest_sha256':A.sha(S/'deployment_manifest.json'),'physical_attempt_budget':10,'max_attempts_per_missing_request':1,'minimum_failure_backoff_seconds':600,'service_health':ref(health_reference),'bindings':{str(package/'owner_config.json'):A.sha(package/'owner_config.json'),str(package/'source_bindings.json'):A.sha(package/'source_bindings.json')},'coordinator_independent_review_required':True,'user_confirmation_required':False})
 assert files(source)==inventory
 return manifest
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--package',required=True,type=Path);ap.add_argument('--canary-health',required=True,type=Path);ap.add_argument('--canary-owner-config',required=True,type=Path);args=ap.parse_args()
 m=build(args.package.resolve(),P/'runs/cycleresearcher/ai-control-deception/slot-05',args.canary_health.resolve(),canary_config=args.canary_owner_config.resolve());print(json.dumps({'manifest':str(args.package/'manifest.json'),'sha256':A.sha(args.package/'manifest.json'),'planned_requests':len(m['planned_requests']),'model_calls':0}))
if __name__=='__main__':main()
