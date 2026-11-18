"""Actual native continuation with fake HTTP, fixed cached generation and negative gates."""
from pathlib import Path
import copy,io,json,os,socket,shutil,urllib.error,urllib.request
from unittest.mock import patch
import adapter_v5 as A
import prepare,runner,host
S=A.S;P=A.P;V=A.V
def save(p,v):p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 base=S/'fixtures/offline_checks_v3';base.mkdir(exist_ok=False);checks={}
 def check(n,v):assert v,n;checks[n]=True
 def reject(n,fn):
  try:fn()
  except (AssertionError,RuntimeError,ValueError,FileNotFoundError):check(n,True)
  else:raise AssertionError('Accepted '+n)
 def forbidden(*a,**k):raise AssertionError('No real model or public network allowed')
 socket.socket.connect=socket.socket.connect_ex=forbidden
 source=P/'state/cycle_slot190_v5_recovery_20261118_A/fixtures/offline_checks_v2/probe_success'
 for scenario in ['success','503']:
  package=base/(scenario+'_package');m=prepare.build(package,source,fixture=True);out=base/(scenario+'_execution');shutil.copytree(package/'original_run',out);path=package/'manifest.json'
  check(scenario+'_ten_original_reviewer_payloads_derived_without_api',len(m['planned_requests'])==10)
  bad=dict(m,max_attempts_per_missing_request=2);save(package/'bad_manifest.json',bad);reject(scenario+'_unbounded_retry_rejected',lambda:runner.check_manifest(package/'bad_manifest.json',out))
  planned={r['request_id']:A.read(r['payload']['path']) for r in m['planned_requests']};reverse={json.dumps(v,ensure_ascii=False,sort_keys=True):k for k,v in planned.items()};calls=[]
  class Response:
   headers={'Content-Type':'application/json'}
   def __init__(self,ident):self.ident=ident
   def __enter__(self):return self
   def __exit__(self,*a):return False
   def read(self):return json.dumps({'id':'fixture-'+self.ident,'model':'gpt-6-astra','choices':[{'index':0,'message':{'role':'assistant','content':'Fixture only: no boxed numeric rating.'},'finish_reason':'stop'}],'usage':{'prompt_tokens':7,'completion_tokens':3,'total_tokens':10}},ensure_ascii=False).encode()
  def transport(req,timeout=None):
   assert req.full_url=='http://127.0.0.1:8765/v1/chat/completions';ident=reverse[json.dumps(json.loads(req.data),ensure_ascii=False,sort_keys=True)];calls.append(ident)
   if scenario=='503' and ident=='reviewer-0001':raise urllib.error.HTTPError(req.full_url,503,'Service unavailable',{},io.BytesIO(b'fixture 503'))
   return Response(ident)
  with patch.dict(os.environ,{'INSIGHTPRO_OFFLINE_ENFORCED':'1','INSIGHTPRO_OFFLINE_PHASE':str(P),'OPENAI_BASE_URL':'http://127.0.0.1:8765/v1'}),patch.object(urllib.request,'urlopen',transport):report=runner.execute(path,out)
  result=A.read(out/m['candidate_filename']);check(scenario+'_exact_ten_bound_reviewer_calls_once',len(calls)==len(set(calls))==10 and report['new_physical_attempts']==10)
  check(scenario+'_result_explicitly_marked_fixture',result['fixture'] is True and report['fixture'] is True)
  check(scenario+'_canonical_and_generation_caches_unchanged',report['passed'] and report['checks']['original_files_preserved'] and report['checks']['canonical_unchanged'])
  reject(scenario+'_same_manifest_cannot_repeat_any_request',lambda:runner.check_manifest(path,out))
  if scenario=='success':
   check('official_allzero_firstmax_succeeds',result['status']=='completed' and result['selected_original_index']==0)
   check('v5_configuration_not_legacy_blocking_policy',result['configuration_sha256']==A.sha(S/'configuration_v5.json') and result['configuration_id']==A.read(S/'configuration_v5.json')['configuration_id'] and result['missing_score_policy']=='upstream_internal_zero_then_first_max')
   check('actual_v5_adapter_runner_manifest_bound',result['deployment_manifest_sha256']==A.sha(S/'deployment_manifest.json') and result['deployment_manifest_sha256']!=result['original_deployment_manifest_sha256'])
   check('old_configuration_retained_only_as_original_reference',result['original_configuration_sha256']==A.read(S/'configuration_v5.json')['original_configuration_sha256'] and result['configuration_sha256']!=result['original_configuration_sha256'])
  else:check('single503_keeps_checkpoint_unknown_and_backoff',result['status']=='infrastructure_failure' and report['next_retry_at'] is not None and report['minimum_backoff_seconds']==600 and not report['native_zero_eligible'])
  save(package/'fake_admission.json',{'passed':True,'approved_normal_admission_same_input_batch':True,'verified_service_recovered':True})
  reject(scenario+'_fixture_manifest_never_admitted_live',lambda:host.admission(path,package/'fake_admission.json'))
 save(base/'acceptance.json',{'passed':all(checks.values()),'checks':checks,'model_calls':0,'mock_reviewer_http_attempts':20,'real_generation_caches_per_fixture':9,'synthetic_canary_response_per_fixture':1,'public_network_calls':0,'production_mutations':False,'fixture_outputs_not_real_native_results':True});save(S/'fixtures/acceptance.json',A.read(base/'acceptance.json'));print(json.dumps({'passed':True,'checks':len(checks),'model_calls':0}))
if __name__=='__main__':main()
