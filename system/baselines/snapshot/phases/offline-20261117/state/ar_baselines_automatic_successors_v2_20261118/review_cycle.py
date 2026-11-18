from pathlib import Path
import argparse,datetime,fcntl,importlib.util,json,sys,time
S=Path(__file__).resolve().parent;P=S.parents[1];sys.path.insert(0,str(P));import campaign as C,offline_gates as G
D=P/'state/cycle_slot190_automatic_successors_20261118_A';O=P/'state/ar_baselines_normal_recovery_owner_20261118T0020';read=C.read;sha=G.sha
ref=lambda p:{'path':str(p),'sha256':sha(p)}
def bound(r):
 assert sha(r['path'])==r['sha256'],r['path'];return read(r['path'])
def main(hp,expected):
 assert sha(hp)==expected;assert sha(D/'handoff.json')=='480c1116c35e647458066588bb77073c5f599d75c01f8a9fe16ae8c30032ee5b';release=read(D/'handoff.json')
 for name in ['deployment','sealed_manifest','integration_contract','reviewer_fixture','reviewer_namespace_fixture','subset_gateway_fixture']:bound(release[name])
 for p,v in read(D/'deployment_manifest.json')['bindings'].items():assert sha(p)==v,p
 h=read(hp);assert h['passed'] and not h['fixture'] and h['same_slot'] and not h['new_sample'] and h['model_calls_by_preparation']==0;pkg=hp.parent;m=bound(h['manifest']);cfg=bound(h['owner_config']);bindings=bound(h['source_bindings']);a=bound(h['admission_template']);W=S/'reviews'/pkg.name/cfg['job_key'];W.mkdir(parents=True,exist_ok=True)
 if (W/'enqueue.json').exists():return read(W/'enqueue.json')
 assert m['stage']=='reviewer_checkpoint_successor' and cfg['job_key']=='cycleresearcher__ai-control-deception__05__generation' and cfg['physical_attempt_budget']==len(m['missing_request_ids'])==len(m['failed_requests']) and m['cached_researcher_count']==10 and m['cached_reviewer_count']+cfg['physical_attempt_budget']==10
 for p,v in bindings.items():assert sha(p)==v,p
 out=Path(m['output_dir']);snap=Path(m['original_snapshot'])
 for rel,v in m['files'].items():assert sha(out/rel)==sha(snap/rel)==v,rel
 previous=bound(m['previous_manifest']);priorcfg=bound(m['previous_owner_config']);priorhealth=bound(m['previous_health']);assert priorhealth['passed'] and not priorhealth['success'] and priorhealth['new_physical_attempts']>0
 verifier=priorcfg['health_verifier'];assert sha(verifier['path'])==verifier['sha256'];sys.path.insert(0,str(Path(verifier['path']).parent));sp=importlib.util.spec_from_file_location('prior_health',verifier['path']);V=importlib.util.module_from_spec(sp);sp.loader.exec_module(V);fresh=V.target_health(priorcfg);assert fresh['passed'] and not fresh['success'] and fresh['new_physical_attempts']==priorhealth['new_physical_attempts']>0
 assert {x['start']['attempt_id'] for x in fresh['attempts']}=={x['start']['attempt_id'] for x in priorhealth['attempts']}
 for row in m['failed_requests']:
  assert row['request_id'] in m['missing_request_ids'] and not row['completed'] and row['last_end']['status']=='infrastructure_failure' and cfg['not_before_epoch']>=datetime.datetime.fromisoformat(row['last_end']['at']).timestamp()+600
 assert time.time()>=cfg['not_before_epoch'] and m['max_attempts_per_missing_request']==1 and m['minimum_failure_backoff_seconds']==600 and len(m['planned_requests'])==10
 for i,(new,old) in enumerate(zip(m['planned_requests'],previous['planned_requests'])):
  assert new['request_id']==old['request_id']==f'reviewer-{i+1:04}' and new['original_index']==old['original_index']==i
  for name in ['payload','carrier']:assert sha(new[name]['path'])==new[name]['sha256']==old[name]['sha256']==sha(old[name]['path'])
 checks={'reviewed_deployment_all_bindings':True,'original_ten_reviewer_payloads_and_carriers_unchanged':True,'all_successful_researcher_and_reviewer_caches_preserved':True,'actual_previous_API_terminal_reverified':True,'new_physical_attempts_positive_no_preparation_loop':True,'failed_subset_only_one_attempt_each':True,'actual_failure_backoff600':True,'all_original_snapshot_bindings':True,'independent_terminal_publication_required':True}
 review={'at':C.now(),'passed':True,'job_key':cfg['job_key'],'approved_normal_admission_same_input_batch':True,'config_sha256':sha(pkg/'owner_config.json'),'source_bindings_sha256':sha(pkg/'source_bindings.json'),'checks':checks,'source_handoff':ref(hp),'new_model_calls':0};C.save(W/'review.json',review);a.update(passed=True,approved_normal_admission_same_input_batch=True,independent_review=ref(W/'review.json'),at=C.now());C.save(pkg/'admission.json',a)
 sp=importlib.util.spec_from_file_location('chain',P/'state/runtime_integrity_chain_candidate_v3_20261118T0530_B/recovery_binding_chain.py');V=importlib.util.module_from_spec(sp);sp.loader.exec_module(V)
 with C.admission_lock(),(O/'queue_update.lock').open('a+') as qlock,(P/'state/methods.lock').open('a+') as ml,(P/'state/activation.lock').open('a+') as al:
  for lock in [qlock,ml,al]:fcntl.flock(lock,fcntl.LOCK_EX)
  j=read(P/'state/campaign.json')['jobs'][cfg['job_key']];assert j['status']=='infrastructure_failure' and j['launches']==cfg['expected_launches'] and not C.alive(j.get('process')) and sha(out/'result.json')==cfg['expected_result_sha256'];assert C.alive(read(O/'health.json')['process']);q=read(O/'reviewed_queue.json');assert not any(e['config']==str(pkg/'owner_config.json') for e in q['batches'])
  action={'audit_path':str(W/'review.json'),'audit_sha256':sha(W/'review.json'),'command':cfg['command'],'recovery_id':cfg['recovery_id'],'expected_result_sha256':cfg['expected_result_sha256'],'same_slot':True,'same_material':True,'new_sample':False};chain=V.verify_chain(j,action,out/'result.json');C.save(W/'chain_validation.json',chain);assert chain['passed'],chain
  methods=read(P/'state/methods.json');act=read(P/'state/activation.json');C.save(W/'methods_before.json',methods);C.save(W/'activation_before.json',act);cycle=methods['cycleresearcher'];assert cycle['eligible_slots']==[] and cycle['eligible_domains']==[];cycle['command']=cfg['command'];receipt={'at':C.now(),'passed':True,'protocol_id':'offline-common-corpus-20261117','method':'cycleresearcher','command':cfg['command'],'checks':{k:True for k in G.METHOD_CHECKS},'bindings':bindings,'independent_review':ref(W/'review.json'),'same_original_context':True,'new_sample':False};C.save(W/'offline_method_receipt.json',receipt);act['method_receipts']['cycleresearcher']=ref(W/'offline_method_receipt.json');C.save(P/'state/methods.json',methods);C.save(P/'state/activation.json',act);gate=G.check();C.save(W/'gate.json',gate);assert gate['passed'],gate
  entry={'config':str(pkg/'owner_config.json'),'review':str(W/'review.json'),'review_sha256':sha(W/'review.json')};q['batches'].append(entry);C.save(O/'reviewed_queue.json',q);receipt={'at':C.now(),'passed':True,'job_key':j['key'],'expected_next_launch':cfg['expected_launches']+1,'entry':entry,'new_model_calls':0};C.save(W/'enqueue.json',receipt);return receipt
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('handoff',type=Path);a.add_argument('sha256');v=a.parse_args();print(json.dumps(main(v.handoff,v.sha256)),flush=True)
