from pathlib import Path
import argparse,datetime,fcntl,hashlib,importlib.util,json,os,sys,time
S=Path(__file__).resolve().parent;P=S.parents[1];sys.path.insert(0,str(P));import campaign as C,offline_gates as G
O=P/'state/ar_baselines_normal_recovery_owner_20261118T0020';B=P/'state/sci_successor_builder_v1_20261118_B';read=C.read;sha=G.sha
def bound(r):
 assert sha(r['path'])==r['sha256'],r['path'];return read(r['path'])
def one(hp):
 h=read(hp);pkg=hp.parent;root=pkg.parents[1];trusted=read(S/'runtime_reviews.json')['sciagents'];runtime=trusted[sha(root/'builder_release.json')];B=Path(runtime['release']).parent;assert sha(B/'release.json')==sha(root/'builder_release.json')
 for p,v in read(B/'release.json')['bindings'].items():assert sha(p)==v,p
 W=S/'reviews'/root.name/h['job_key'];W.mkdir(parents=True,exist_ok=True)
 if (W/'enqueue.json').exists():return read(W/'enqueue.json')
 for n in ['host.py','sci_runner.py','health_verifier.py']:assert sha(root/n)==sha(B/'templates'/n)
 assert sha(h['config'])==h['config_sha256'];cfg=read(h['config']);assert sha(cfg['manifest'])==h['manifest_sha256'];m=read(cfg['manifest']);out=Path(m['output_dir']);snap=Path(m['original_snapshot']);assert sha(pkg/'source_bindings.json')==h['source_bindings_sha256']
 for p,v in read(pkg/'source_bindings.json').items():assert sha(p)==v,p
 assert cfg['method']=='sciagents' and cfg['physical_attempt_budget']==len(m['failed_requests'])==1 and cfg['new_physical_attempt_budget_per_original_failed_request']==1 and cfg['minimum_backoff_seconds']==600 and cfg['same_slot'] and cfg['same_material'] and not cfg['new_sample'] and time.time()>=cfg['not_before_epoch']
 for rel,v in m['files'].items():assert sha(out/rel)==sha(snap/rel)==v,rel
 f=read(cfg['fixture']);assert sha(cfg['fixture'])==h['fixture_sha256'] and f['passed'] and all(f['checks'].values()) and f['model_calls']==0 and f['fixture'];assert f['boundary']['full_payload_exact'] and f['boundary']['original_group_history_exact'] and f['boundary']['original_novelty_history_exact']
 for r in m['failed_requests']:
  q=out/'api_requests'/r['request_id'];assert sha(q/'request.json')==r['request_file_sha256'] and not (q/'response.json').exists() and cfg['not_before_epoch']>=datetime.datetime.fromisoformat(r['last_end']['at']).timestamp()+600
 for r in m['successful_requests']:
  q=out/'api_requests'/r['request_id'];response=read(q/'response.json');rr=read(q/'receipt.json');assert rr['status']=='completed' and response['choices'][0]['finish_reason'] in ['stop','tool_calls','function_call'] and hashlib.sha256(json.dumps(response,ensure_ascii=False).encode()).hexdigest()==rr['response_sha256']
 consumed=m.get('historical_consumed_failure_requests',[]);assert set(f['historical_consumed_errors_replayed'])=={r['request_id'] for r in consumed}
 for r in consumed:assert r['native_tool_error_already_consumed'] and r['request_id'] not in f['attempted']
 classification=read(pkg/'classification.json')
 for e in classification['all_failed_physical_evidence']:
  error=bound(e['error']);body=str(error.get('http',{}).get('body','')).lower();assert not any(x in body for x in ['cyber_policy','policy_violation','content_policy']);assert error.get('http',{}).get('status') in [408,429,500,502,503,504] or error['type'] in ['TimeoutError','URLError','ConnectionError','IncompleteRead'] or error['error']=='Stream closed before terminal completion'
 history=read(pkg/'history_preservation_acceptance.json');assert history['passed'] and all(sha(out/n)==v for n,v in history['previous_result_files'].items())
 publication=h.get('new_failure_publication');candidate=None
 if m['canonical_publication_required']:
  fm=bound(publication['manifest']);assert fm['source_files']==m['files'] and fm['expected_old_result_sha256']==m['expected_old_canonical_sha256'];candidate=bound(publication['candidate_result']);assert candidate['status']=='infrastructure_failure' and candidate['usage'] is candidate['usd'] is None and publication['candidate_result']['sha256']==cfg['expected_result_sha256']
 review={'at':C.now(),'passed':True,'job_key':cfg['job_key'],'approved_normal_admission_same_input_batch':True,'config_sha256':sha(h['config']),'source_bindings_sha256':sha(pkg/'source_bindings.json'),'checks':{'reviewed_immutable_runtime_and_source':True,'all_original_file_and_response_hashes':True,'exact_payload_and_seeded_native_histories':True,'consumed_historical_errors_replayed_without_model_call':True,'one_current_missing_request_only':True,'real_failure_minimum600s':True,'all_recovery_history_preserved':True,'policy_refusal_excluded':True,'native_and_shared_state_unchanged_by_review':True},'source_handoff':{'path':str(hp),'sha256':sha(hp)},'new_model_calls':0};C.save(W/'review.json',review)
 sp=importlib.util.spec_from_file_location('chain',P/'state/runtime_integrity_chain_candidate_v3_20261118T0530_B/recovery_binding_chain.py');V=importlib.util.module_from_spec(sp);sp.loader.exec_module(V)
 with C.admission_lock(),(out/'run.lock').open('a+') as lock,(O/'queue_update.lock').open('a+') as qlock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(qlock,fcntl.LOCK_EX);j=read(P/'state/campaign.json')['jobs'][cfg['job_key']];assert j['launches']==cfg['expected_launches'] and j['status']=='infrastructure_failure' and not C.alive(j.get('process')) and sha(out/'result.json')==m['expected_old_canonical_sha256'];assert C.alive(read(O/'health.json')['process']);q=read(O/'reviewed_queue.json');assert not any(e['config']==h['config'] for e in q['batches'])
  scope_file=B/'scope_guard.py'
  if scope_file.exists():
   sp_scope=importlib.util.spec_from_file_location('independent_original_scope',scope_file);scope=importlib.util.module_from_spec(sp_scope);sp_scope.loader.exec_module(scope)
   scope_entry,scope_spec,scope_proof=scope.admitted_job(B,P,'sciagents',j['key'],j,out)
   scope.sci_admission(scope_entry,scope_spec,out,P)
  action={'audit_path':str(W/'review.json'),'audit_sha256':sha(W/'review.json'),'command':cfg['command'],'recovery_id':cfg['recovery_id'],'expected_result_sha256':cfg['expected_result_sha256'],'same_slot':True,'same_material':True,'new_sample':False};chain=V.verify_chain(j,action,out/'result.json');C.save(W/'chain_validation.json',chain);assert chain['passed'],chain;C.save(W/'before_job.json',j);(W/'before_result.json').write_bytes((out/'result.json').read_bytes())
  if candidate:
   tmp=out/'result.sci_auto.tmp';tmp.write_bytes(Path(publication['candidate_result']['path']).read_bytes());os.replace(tmp,out/'result.json');assert sha(out/'result.json')==cfg['expected_result_sha256']
  entry={'config':h['config'],'review':str(W/'review.json'),'review_sha256':sha(W/'review.json')};q['batches'].append(entry);C.save(O/'reviewed_queue.json',q);receipt={'at':C.now(),'passed':True,'job_key':j['key'],'expected_next_launch':cfg['expected_launches']+1,'entry':entry,'new_model_calls':0};C.save(W/'enqueue.json',receipt);return receipt
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('handoff',type=Path);a.add_argument('sha256');v=a.parse_args();assert sha(v.handoff)==v.sha256;print(json.dumps(one(v.handoff)),flush=True)
