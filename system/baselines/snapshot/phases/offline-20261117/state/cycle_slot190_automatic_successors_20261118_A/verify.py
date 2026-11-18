"""No-network recovery fixtures: reentrance, repeated failed original attempts and cache retention."""
from pathlib import Path
import copy,io,json,os,shutil,socket,sys,urllib.error,urllib.request
from unittest.mock import patch
import adapter_v5 as A
import checkpoint_utils as U
import builder,runner,host
S=U.S;P=U.P
C=P/'state/cycle_slot190_v5_continuation_v2_20261118_A'
def main():
 base=S/'fixtures/verification_v4';base.mkdir(exist_ok=False);checks={};job={'key':U.KEY,'launches':101,'status':'infrastructure_failure'}
 def check(name,value):assert value,name;checks[name]=True
 def reject(name,fn):
  try:fn()
  except (AssertionError,ValueError,FileNotFoundError):check(name,True)
  else:raise AssertionError('Accepted '+name)
 def denied(*a,**k):raise AssertionError('Real network forbidden in fixture')
 socket.socket.connect=socket.socket.connect_ex=denied
 source=C/'fixtures/offline_checks_v3/503_execution';previous=C/'fixtures/offline_checks_v3/503_package/manifest.json'
 handoff=builder.reviewer(source,previous,job,fixture=True);package=Path(handoff['manifest']['path']).parent;m=U.read(package/'manifest.json')
 check('one_failed_reviewer_and_nineteen_successful_caches_identified',m['missing_request_ids']==['reviewer-0001'] and m['cached_researcher_count']==10 and m['cached_reviewer_count']==9)
 check('builder_is_reentrant_before_admission',builder.reviewer(source,previous,job,fixture=True)==handoff)
 U.save(base/'reviewer_fixture_manifest.json',{'path':str(package/'manifest.json')})
 class Response:
  headers={'Content-Type':'application/json'}
  def __enter__(self):return self
  def __exit__(self,*a):return False
  def read(self):return json.dumps({'id':'fixture-restored-original-reviewer','model':'gpt-6-astra','choices':[{'index':0,'message':{'role':'assistant','content':'Fixture only: no boxed rating.'},'finish_reason':'stop'}],'usage':{'prompt_tokens':7,'completion_tokens':3,'total_tokens':10}},ensure_ascii=False).encode()
 for scenario in ['success','503']:
  out=base/('reviewer_'+scenario);shutil.copytree(source,out);calls=[];planned=U.read(m['planned_requests'][0]['payload']['path'])
  reject(scenario+'_backoff_before600_rejected',lambda:runner.check_manifest(package/'manifest.json',out,now_epoch=m['not_before_epoch']-.001))
  bad=copy.deepcopy(m);bad['missing_request_ids'].append('reviewer-0002');bad['physical_attempt_budget']=2;U.save(base/f'{scenario}_bad_completed_target.json',bad);reject(scenario+'_completed_reviewer_resampling_rejected',lambda:runner.check_manifest(base/f'{scenario}_bad_completed_target.json',out,now_epoch=m['not_before_epoch']))
  def transport(request,timeout=None):
   assert request.full_url=='http://127.0.0.1:8765/v1/chat/completions' and json.loads(request.data)==planned;calls.append(request.data)
   if scenario=='503':raise urllib.error.HTTPError(request.full_url,503,'Fixture outage',{},io.BytesIO(b'fixture503'))
   return Response()
  with patch.object(runner.time,'time',return_value=m['not_before_epoch']+1),patch.dict(os.environ,{'INSIGHTPRO_OFFLINE_ENFORCED':'1','INSIGHTPRO_OFFLINE_PHASE':str(P),'OPENAI_BASE_URL':'http://127.0.0.1:8765/v1'}),patch.object(urllib.request,'urlopen',transport):report=runner.execute(package/'manifest.json',out)
  check(scenario+'_only_failed_original_reviewer_attempted_once',len(calls)==report['new_physical_attempts']==1 and report['cached_researcher_responses']==10 and report['cached_reviewer_responses']==9)
  check(scenario+'_all_cached_raw_receipts_and_old_failure_evidence_preserved',report['passed'] and all(report['checks'].values()))
  reject(scenario+'_same_manifest_cannot_repeat_attempt',lambda:runner.check_manifest(package/'manifest.json',out,now_epoch=m['not_before_epoch']+1))
  result=U.read(out/m['candidate_filename'])
  if scenario=='success':check('final_native_selection_replays_all10_original_reviewers_and_firstmax',result['status']=='completed' and result['selected_original_index']==0 and result['completed_logical_responses']==20 and result['deployment_manifest_sha256']==U.sha(S/'deployment_manifest.json'))
  else:
   check('failed_usage_unknown_and_next_due_at_actual_failure_plus600',report['native_zero_eligible'] is False and result['usage'] is None and report['next_retry_at'] is not None)
   h2=builder.reviewer(out,package/'manifest.json',{**job,'launches':102},fixture=True);m2=U.read(h2['manifest']['path']);check('second_round_keeps_same_original_payload_and_nineteen_successful_caches',m2['missing_request_ids']==['reviewer-0001'] and m2['cached_reviewer_count']==9 and m2['failed_requests'][0]['prior_physical_attempts']==2 and U.read(m2['planned_requests'][0]['payload']['path'])==planned)
   out2=base/'reviewer_round2_success';shutil.copytree(out,out2);calls.clear()
   with patch.object(runner.time,'time',return_value=m2['not_before_epoch']+1),patch.dict(os.environ,{'INSIGHTPRO_OFFLINE_ENFORCED':'1','INSIGHTPRO_OFFLINE_PHASE':str(P),'OPENAI_BASE_URL':'http://127.0.0.1:8765/v1'}),patch.object(urllib.request,'urlopen',lambda req,timeout=None:(calls.append(req.data) or Response())):r2=runner.execute(Path(h2['manifest']['path']),out2)
   check('second_successor_finishes_without_retrying_any_success',len(calls)==r2['new_physical_attempts']==1 and r2['native_terminal'] and r2['passed'])
 canary_source=builder.T/'original_run';ch=builder.canary(canary_source,builder.T/'manifest.json',{**job,'launches':5},fixture=True)
 check('canary_builder_preserves9_successes_and_only_one_original_missing_request',ch['missing_original_request_ids']==['researcher-0007'] and ch['physical_attempt_budget']==1 and ch['next_physical_attempt']==10)
 check('canary_builder_reentrant_same_checkpoint_returns_same_package',builder.canary(canary_source,builder.T/'manifest.json',{**job,'launches':5},fixture=True)==ch)
 U.save(base/'canary_fixture_handoff.json',ch)
 U.save(base/'acceptance.json',{'passed':all(checks.values()),'checks':checks,'model_calls':0,'mock_reviewer_http_attempts':3,'canary_embedded_mock_http_attempts':2,'synthetic_fixture_only':True,'production_mutations':False,'actual_original_native_selection_used':True});print(json.dumps({'passed':True,'checks':len(checks),'model_calls':0}))
if __name__=='__main__':main()
