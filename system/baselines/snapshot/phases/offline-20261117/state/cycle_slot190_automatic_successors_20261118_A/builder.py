"""Reentrant private builder for original Cycle190 transport failures. Never calls a model or changes shared state."""
from pathlib import Path
import argparse,copy,datetime,fcntl,hashlib,importlib.util,json,shutil,subprocess,sys,threading
import adapter_v5 as A
import checkpoint_utils as U
S=U.S;P=U.P;V=A.V;T=P/'state/cycle_slot190_v5_recovery_attempt10_20261118_A'
def verify_previous(config,health):
 cfg=U.read(config);assert cfg['job_key']==U.KEY and cfg['same_slot'] and cfg['new_sample'] is False
 assert U.sha(cfg['manifest'])==cfg['manifest_sha256'];verifier=cfg['health_verifier'];assert U.sha(verifier['path'])==verifier['sha256'];value=U.read(health)
 assert value['success'] is False and value.get('native_zero_eligible') is False
 sys.path.insert(0,str(Path(verifier['path']).parent));sp=importlib.util.spec_from_file_location('cycle190_previous_health_'+U.sha(config)[:12],verifier['path']);h=importlib.util.module_from_spec(sp);sp.loader.exec_module(h);fresh=h.target_health(cfg)
 assert fresh['success'] is False and fresh['new_physical_attempts']==value['new_physical_attempts']
 if fresh['new_physical_attempts']:
  assert fresh['passed'] and value['passed'];assert {r['start']['attempt_id'] for r in fresh['attempts']}=={r['start']['attempt_id'] for r in value['attempts']}
 else:assert fresh['classification']==value['classification']=='preparation_failure_no_new_physical_attempt'
 return cfg,U.read(cfg['manifest'])
def allocate(kind,source,previous,job,fixture=False):
 files=U.inventory(source);stable={k:v for k,v in files.items() if k not in U.RUNTIME};fingerprint=hashlib.sha256(json.dumps({'kind':kind,'files':stable,'previous_manifest':U.sha(previous),'launches':job['launches']},sort_keys=True).encode()).hexdigest();root=((S/'fixtures/builds_v4').resolve() if fixture else S/'packages')/kind;root.mkdir(parents=True,exist_ok=True)
 matches=sorted(root.glob(f'{fingerprint[:20]}-*'))
 for package in matches:
  if (package/'handoff.json').exists():
   handoff=U.read(package/'handoff.json');assert handoff['source_fingerprint']==fingerprint
   for p,h in U.read(package/'source_bindings.json').items():assert U.sha(p)==h
   return package,files,fingerprint,True
 package=root/f'{fingerprint[:20]}-{len(matches)+1:02}';package.mkdir();return package,files,fingerprint,False
def seal(package,m,owner,fingerprint,fixture=False):
 U.save(package/'manifest.json',m);owner.update(manifest=str(package/'manifest.json'),manifest_sha256=U.sha(package/'manifest.json'));U.save(package/'owner_config.json',owner)
 bindings=dict(U.read(S/'deployment_manifest.json')['bindings']);bindings[str(S/'deployment_manifest.json')]=U.sha(S/'deployment_manifest.json')
 for f in package.rglob('*'):
  if f.is_file() and f.name not in ['source_bindings.json']:bindings[str(f)]=U.sha(f)
 if not fixture:
  for f in [S/'fixtures/final_acceptance.json',S/'fixtures/namespace_acceptance.json']:bindings[str(f)]=U.sha(f)
 U.save(package/'source_bindings.json',bindings)
 U.save(package/'admission_template.json',{'passed':False,'approved_normal_admission_same_input_batch':False,'manifest_sha256':U.sha(package/'manifest.json'),'deployment_manifest_sha256':U.sha(S/'deployment_manifest.json'),'physical_attempt_budget':m['physical_attempt_budget'],'request_ids':m['missing_request_ids'],'max_attempts_per_missing_request':1,'minimum_failure_backoff_seconds':600,'bindings':{str(package/'owner_config.json'):U.sha(package/'owner_config.json'),str(package/'source_bindings.json'):U.sha(package/'source_bindings.json')},'user_confirmation_required':False})
 handoff={'passed':True,'fixture':fixture,'source_fingerprint':fingerprint,'owner_config':U.ref(package/'owner_config.json'),'manifest':U.ref(package/'manifest.json'),'source_bindings':U.ref(package/'source_bindings.json'),'admission_template':U.ref(package/'admission_template.json'),'missing_original_request_ids':m['missing_request_ids'],'physical_attempt_budget':m['physical_attempt_budget'],'not_before_epoch':m['not_before_epoch'],'same_slot':True,'new_sample':False,'model_calls_by_preparation':0,'shared_state_writes':False,'normal_owner':str(P/'state/ar_baselines_normal_recovery_owner_20261118T0020/owner_v2.py'),'automatic_next_checkpoint_successor_supported':True,'native_zero_eligible':False}
 U.save(package/'handoff.json',handoff);return handoff
def reviewer(source,previous_manifest,job,previous_config=None,previous_health=None,fixture=False):
 previous=U.read(previous_manifest);assert previous['stage'] in ['reviewer_continuation','reviewer_checkpoint_successor'] and len(previous['planned_requests'])==10
 package,files,fingerprint,reused=allocate('reviewer',source,previous_manifest,job,fixture)
 if reused:return U.read(package/'handoff.json')
 rows=[U.request_state(source,'reviewer',f'reviewer-{i:04}') for i in range(1,11)];failed=[r for r in rows if not r['completed']];assert failed,'No missing original reviewer remains; terminal verification must not resample successful responses'
 for i in range(1,11):U.cached(source,'researcher',f'researcher-{i:04}')
 snapshot=package/'original_run';shutil.copytree(source,snapshot);plan={};lock=threading.Lock()
 class Generation:
  def completion(self,messages,max_tokens,request_id,**kwargs):return U.cached(snapshot,'researcher',request_id,A.payload(messages,max_tokens,kwargs))
 class Boundary:
  def completion(self,messages,max_tokens,request_id,**kwargs):
   with lock:assert request_id not in plan;plan[request_id]=A.payload(messages,max_tokens,kwargs)
   raise V.InfrastructureFailure('Original fixed reviewer boundary; no model transport')
 try:A.run_chain(U.read(V.INPUTS/'ai-control-deception/configuration.json'),package/'native_plan',{'researcher':Generation(),'reviewer':Boundary()})
 except V.InfrastructureFailure:pass
 assert len(plan)==10;planned=[]
 for i,row in enumerate(previous['planned_requests']):
  ident=f'reviewer-{i+1:04}';assert row['request_id']==ident and row['original_index']==i and U.sha(row['payload']['path'])==row['payload']['sha256'] and U.sha(row['carrier']['path'])==row['carrier']['sha256']
  assert plan[ident]==U.read(row['payload']['path'])==U.read(source/'reviewer/api_requests'/ident/'request.json')
  carrier=package/'native_plan/carriers'/f'{i:02}.txt';assert U.sha(carrier)==row['carrier']['sha256'];payload=package/'planned_requests'/f'{ident}.json';U.save(payload,plan[ident]);planned.append({**row,'payload':U.ref(payload),'carrier':U.ref(carrier),'prior_physical_attempts':rows[i]['prior_physical_attempts']})
 ids=[r['request_id'] for r in failed];due=max(U.epoch(r['last_end']['at'])+600 for r in failed);rid='cycleresearcher__ai-control-deception__05__generation-v5-reviewer-checkpoint-'+fingerprint[:20]
 m={'stage':'reviewer_checkpoint_successor','fixture':fixture,'method':'cycleresearcher','domain':'ai-control-deception','slot':5,'job_key':U.KEY,'recovery_id':rid,'output_dir':str(U.OUT),'original_snapshot':str(snapshot),'files':files,'expected_launches':job['launches'],'expected_result_sha256':U.sha(source/'result.json'),'original_binding':U.read(source/'run_binding.json'),'selection_semantics_revision':A.REVISION,'configuration':U.ref(S/'configuration_v5.json'),'deployment':U.ref(S/'deployment_manifest.json'),'previous_manifest':U.ref(previous_manifest),'previous_owner_config':U.ref(previous_config) if previous_config else None,'previous_health':U.ref(previous_health) if previous_health else None,'planned_requests':planned,'failed_requests':failed,'missing_request_ids':ids,'cached_researcher_count':10,'cached_reviewer_count':10-len(failed),'physical_attempt_budget':len(failed),'max_attempts_per_missing_request':1,'minimum_failure_backoff_seconds':600,'not_before_epoch':due,'new_sample':False,'candidate_filename':'cycle_v5_checkpoint_'+fingerprint[:20]+'_candidate.json','completion_filename':'cycle_v5_checkpoint_'+fingerprint[:20]+'_completion.json','shared_request_cap':250,'model_calls_by_preparation':0}
 owner={'method':'cycleresearcher','job_key':U.KEY,'recovery_id':rid,'expected_result_sha256':m['expected_result_sha256'],'expected_launches':job['launches'],'output_dir':str(U.OUT),'original_snapshot':str(snapshot),'not_before_epoch':due,'minimum_backoff_seconds':600,'failed_requests':failed,'physical_attempt_budget':len(failed),'new_physical_attempt_budget_per_original_failed_request':1,'command':['/usr/bin/python3',str(S/'host.py'),'--manifest',str(package/'manifest.json'),'--admission',str(package/'admission.json')],'health_verifier':{**U.ref(S/'health_verifier.py'),'function':'target_health'},'same_slot':True,'same_material':True,'new_sample':False,'independent_native_publication_required':True,'preparation_failure_is_not_an_upstream_attempt':True,'native_zero_eligible':False,'fixture':str(S/'fixtures/namespace_acceptance.json')}
 result=seal(package,m,owner,fingerprint,fixture);assert U.inventory(source)==files;return result
def canary(source,previous_manifest,job,previous_config=None,previous_health=None,fixture=False):
 previous=U.read(previous_manifest);assert previous['stage']=='researcher_canary' and previous['allowed_missing_requests']==[{'component':'researcher','request_id':'researcher-0007'}]
 package,files,fingerprint,reused=allocate('canary',source,previous_manifest,job,fixture)
 if reused:return U.read(package/'handoff.json')
 rows=[U.request_state(source,'researcher',f'researcher-{i:04}') for i in range(1,11)];failed=[r for r in rows if not r['completed']];assert len(failed)==1 and failed[0]['request_id']=='researcher-0007' and not list((source/'reviewer/api_requests').glob('*/request.json'))
 snapshot=package/'original_run';shutil.copytree(source,snapshot);due=U.epoch(failed[0]['last_end']['at'])+600;attempt=failed[0]['prior_physical_attempts']+1;rid=f'cycleresearcher__ai-control-deception__05__generation-v5-canary-attempt{attempt}-'+fingerprint[:12]
 for name in ['adapter_v5.py','runner.py','host.py','legacy_target_health.py','health_verifier.py','verify.py']:
  text=(T/name).read_text()
  if name=='adapter_v5.py':text=text.replace('P=S.parents[1]',f'P=Path({str(P)!r})')
  elif name=='host.py':
   text=text.replace('P=S.parents[1]',f'P=Path({str(P)!r})').replace("  assert time.time()>=m['not_before_epoch'];","  assert not m.get('fixture_package',False),'Fixture package cannot launch live';assert time.time()>=m['not_before_epoch'];")
   text=text.replace('offline_exec.build_command(out,socketpath','offline_exec.build_command(original if a.fixture_output else out,socketpath').replace("  i=argv.index('--chdir');argv[i:i]=['--bind',str(out),str(original)]","  targets=[i for i in range(len(argv)-2) if argv[i]=='--bind' and argv[i+1:i+3]==[str(original),str(original)]];assert len(targets)==1;argv[targets[0]+1]=str(out)")
  elif name=='legacy_target_health.py':text=text.replace('P=Path(__file__).resolve().parents[2]',f'P=Path({str(P)!r})')
  elif name=='verify.py':
   text=text.replace('def main():', "def private_fixture_boundary(out):\n assert Path(out).resolve().is_relative_to((S/'fixtures').resolve()) and os.environ.get('INSIGHTPRO_OFFLINE_ENFORCED')=='1' and os.environ.get('OPENAI_BASE_URL')=='http://127.0.0.1:8765/v1'\ndef main():")
   text=text.replace("with patch.object(R.time,'time',", "with patch.object(V,'require_offline',private_fixture_boundary),patch.object(R.time,'time',")
  (package/name).write_text(text)
 m=copy.deepcopy(previous);m.update(original_snapshot=str(snapshot),files=files,expected_launches=job['launches'],original_job=job,recovery_id=rid,requests=rows,failed_requests=failed,cached_requests=[r for r in rows if r['completed']],not_before_epoch=due,candidate_filename=f'cycle_v5_canary_attempt{attempt}_{fingerprint[:12]}_result.json',completion_filename=f'cycle_v5_canary_attempt{attempt}_{fingerprint[:12]}_completion.json',previous_manifest=U.ref(previous_manifest),previous_owner_config=U.ref(previous_config) if previous_config else None,previous_health=U.ref(previous_health) if previous_health else None,prepared_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),fixture_package=fixture)
 U.save(package/'manifest.json',m);U.save(package/'original_job.json',job)
 cfg=U.read(T/'owner_config.json');cfg.update(recovery_id=rid,manifest=str(package/'manifest.json'),manifest_sha256=U.sha(package/'manifest.json'),expected_launches=job['launches'],original_snapshot=str(snapshot),not_before_epoch=due,failed_requests=failed,command=['/usr/bin/python3',str(package/'host.py'),'--manifest',str(package/'manifest.json')],health_verifier={**U.ref(package/'health_verifier.py'),'function':'target_health'},fixture=str(package/'fixtures/namespace/transport_fixture_acceptance.json'),probe_outcome_path=str(U.OUT/m['completion_filename']))
 U.save(package/'owner_config.json',cfg);bindings={**U.read(T/'source_bindings.json'),**U.read(S/'deployment_manifest.json')['bindings'],str(S/'deployment_manifest.json'):U.sha(S/'deployment_manifest.json')}
 for f in package.iterdir():
  if f.is_file():bindings[str(f)]=U.sha(f)
 U.save(package/'source_bindings.json',bindings)
 # Real native fixtures use only cached responses and mocked HTTP; bwrap fixture uses an unconnected private socket.
 commands=[[str(P/'environments/cycleresearcher/venv/bin/python'),'-B',str(package/'verify.py')],['/usr/bin/python3',str(package/'host.py'),'--manifest',str(package/'manifest.json'),'--fixture-output',str(package/'fixtures/namespace')]]
 for i,command in enumerate(commands):
  with (package/f'fixture_{i}.log').open('x') as log:code=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT).returncode
  assert code==0,f'Canary fixture failed: {package}/fixture_{i}.log'
 for f in [package/'fixtures/negative_acceptance.json',package/'fixtures/namespace/transport_fixture_acceptance.json']:assert U.read(f)['passed'];bindings[str(f)]=U.sha(f)
 (package/'source_bindings.json').write_text(json.dumps(bindings,ensure_ascii=False,indent=2)+'\n');assert U.inventory(source)==files
 handoff={'passed':True,'fixture':fixture,'source_fingerprint':fingerprint,'owner_config':U.ref(package/'owner_config.json'),'manifest':U.ref(package/'manifest.json'),'source_bindings':U.ref(package/'source_bindings.json'),'missing_original_request_ids':['researcher-0007'],'physical_attempt_budget':1,'next_physical_attempt':attempt,'not_before_epoch':due,'same_slot':True,'new_sample':False,'model_calls_by_preparation':0,'shared_state_writes':False,'normal_owner':str(P/'state/ar_baselines_normal_recovery_owner_20261118T0020/owner_v2.py'),'automatic_next_checkpoint_successor_supported':True,'stop_after_target':True,'reviewer_api_allowed':False,'native_zero_eligible':False,'negative_fixture':U.ref(package/'fixtures/negative_acceptance.json'),'namespace_fixture':U.ref(package/'fixtures/namespace/transport_fixture_acceptance.json')}
 U.save(package/'handoff.json',handoff);return handoff
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--kind',choices=['canary','reviewer'],required=True);ap.add_argument('--previous-owner-config',type=Path,required=True);ap.add_argument('--previous-health',type=Path,required=True);a=ap.parse_args()
 with (S/'builder.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);job=U.current_job();cfg,m=verify_previous(a.previous_owner_config,a.previous_health);result=globals()[a.kind](U.OUT,Path(cfg['manifest']),job,a.previous_owner_config,a.previous_health);print(json.dumps(result),flush=True)
if __name__=='__main__':main()
