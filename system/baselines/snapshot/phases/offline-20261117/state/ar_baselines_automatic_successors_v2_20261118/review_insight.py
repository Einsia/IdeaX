from pathlib import Path
import argparse,datetime,fcntl,hashlib,importlib.util,json,os,sys,time
SCRIPT=Path(__file__).resolve().parent;P=SCRIPT.parents[1];W=SCRIPT;sys.path.insert(0,str(P));import campaign as C,offline_gates as G
B=None;OLD=P/'state/insight_successor_builder_v1_20261118_B/templates';O=P/'state/ar_baselines_normal_recovery_owner_20261118T0020';read=C.read;cache={}
def sha(p):
 p=Path(p);s=p.stat();k=(str(p),s.st_size,s.st_mtime_ns)
 if k not in cache:cache[k]=G.sha(p)
 return cache[k]
def ref(p):return {'path':str(p),'sha256':sha(p)}
def bound(r):
 assert sha(r['path'])==r['sha256'],r['path'];return read(r['path'])
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
sp=importlib.util.spec_from_file_location('strict_chain',P/'state/runtime_integrity_chain_candidate_v3_20261118T0530_B/recovery_binding_chain.py');V=importlib.util.module_from_spec(sp);sp.loader.exec_module(V)
a=argparse.ArgumentParser();a.add_argument('index',type=Path);a.add_argument('sha256');args=a.parse_args();assert sha(args.index)==args.sha256;idx=read(args.index);assert idx['model_calls']==0 and idx['shared_mutations'] is False;B=args.index.parent;W=SCRIPT/'reviews'/B.name;W.mkdir(parents=True,exist_ok=True)
trusted=read(SCRIPT/'runtime_reviews.json')['insightagents'];runtime=trusted[sha(B/'builder_release.json')];RELEASE=Path(runtime['release']);assert sha(RELEASE)==sha(B/'builder_release.json');OLD=RELEASE.parent/'templates'
for p,v in read(RELEASE)['bindings'].items():assert sha(p)==v,p
for name in ['driver.py','host.py','health_verifier.py']:assert sha(B/name)==sha(OLD/name)
# Independent raw ledger membership is checked before any admission.
wanted=set();pre=[]
for entry in idx['ready']:
 h=bound(entry['handoff']);pkg=Path(entry['handoff']['path']).parent;D=W/h['job_key'];D.mkdir(exist_ok=True)
 if (D/'enqueue.json').exists():continue
 fm=bound(h['new_failure_publication']['manifest']);events=fm['gateway_events'];starts=[e for e in events if e['event']=='attempt_start'];ends=[e for e in events if e['event']=='attempt_end'];assert len(starts)==len(ends)==1 and starts[0]['request_id']==ends[0]['request_id'];assert ends[0]['mock'] is False and ends[0]['completed'] is False and ends[0]['usage'] is None and (ends[0]['http_status'] in [200,408,429,500,502,503,504] or (ends[0]['http_status'] is None and any(e.get('event')=='transport_error' for e in events)))
 assert not any('cyber_policy' in json.dumps(e) for e in events)
 wanted.update(digest(e) for e in events);pre.append((entry,h,pkg,D,fm))
seen=set()
for line in (P/'logs/model_gateway.jsonl').open():
 try:e=json.loads(line)
 except ValueError:continue
 v=digest(e)
 if v in wanted:seen.add(v)
assert seen==wanted,('missing real gateway',len(wanted-seen))
receipts=[]
for entry,h,pkg,D,fm in pre:
 assert sha(h['config'])==h['config_sha256'] and sha(pkg/'source_bindings.json')==h['source_bindings_sha256'];cfg=read(h['config']);assert sha(cfg['manifest'])==cfg['manifest_sha256'];m=read(cfg['manifest']);out=Path(m['output_dir']);snap=Path(m['original_snapshot']);source_map=read(pkg/'source_bindings.json');assert str(out/'result.json') not in source_map
 for p,v in source_map.items():assert sha(p)==v,p
 assert cfg['method']==m['method']=='insightagents' and cfg['job_key']==m['job_key']==h['job_key'];assert cfg['expected_launches']==m['expected_launches']==h['expected_launches'];assert cfg['new_sample'] is m['new_sample'] is False and cfg['same_slot'] and cfg['same_material'];assert cfg['physical_attempt_budget']==m['new_physical_attempt_budget']==1 and cfg['minimum_backoff_seconds']==600
 assert cfg['not_before_epoch']==m['not_before_epoch']>=datetime.datetime.fromisoformat(fm['latest_failure_at']).timestamp()+600 and time.time()>=cfg['not_before_epoch'];assert cfg['subsequent_native_sdk_max_retries']==m['subsequent_native_sdk_max_retries']==2
 fixture=bound(h['fixture']);assert fixture['passed'] and fixture['model_calls']==0 and len(fixture['checks'])==10 and all(fixture['checks'].values());assert len(fixture['events'])==1 and fixture['events'][0]['full_original_request_exact'] and fixture['events'][0]['native_sdk_wire_exact'] and fixture['events'][0]['stream_wire_exact']
 assert fixture['recovery_id']==m['recovery_id']==cfg['recovery_id'];assert fixture['events'][0]['logical_request_sha256']==m['target_request_sha256']
 for rel,v in m['files'].items():assert sha(snap/rel)==v and (rel=='result.json' or sha(out/rel)==v),(h['job_key'],rel)
 assert fm['source_files']==m['files'];assert fm['successful_previous_target_never_retried'] and fm['native_output_consumed'] is False and m['partial_output_consumed'] is False
 target=out/m['target_directory'];assert sha(target/'request.json')==m['target_request_sha256'];assert len(list(target.glob('physical-*')))==m['prior_physical_attempts'];assert not (target/'native_response.json').exists() and not (target/'native_returned.json').exists()
 for name in ['host_contract','package_manifest','admission']:bound(m[name])
 binding=read(out/'run_binding.json');assert binding==m['original_domain_binding'];assert binding['domain']==m['domain'] and binding['slot']==m['slot'] and binding['model']=='gpt-6-astra' and binding['effort']=='xhigh' and binding['fixture'] is False
 from review_insight_outcome import verify_outcome
 verify_outcome(pkg,m,fm,RELEASE)
 candidate=bound(h['new_failure_publication']['candidate_result']);assert candidate['status']=='infrastructure_failure' and candidate['native_failure'] is False and candidate['usage'] is None and candidate['usd'] is None and candidate['failed_attempts_usage_unknown']==fm['all_unknown_usage_attempts'];assert candidate['known_usage_subtotal']==fm['all_known_usage_subtotal']
 for key in ['run_id','admission_id','method','domain','slot','comparison_scope']:assert candidate[key]==binding[key]
 for rel,item in m['successful_cache_receipts'].items():
  rr=read(out/rel/'native_returned.json');assert sha(out/rel/'native_returned.json')==item['receipt_sha256'] and rr['physical_attempts']==item['physical_attempts']
  if item['physical_attempts']>3:
   job=read(P/'state/campaign.json')['jobs'][h['job_key']];launches=[x for x in job['recovery_launches'] if x['recovery_id']==item['recovery_id']];assert len(launches)==1 and item['recovery_id'] in job['executed_recovery_ids'];command=launches[0]['command'];prior=read(command[command.index('--manifest')+1]);assert prior['target_directory']==rel and prior['prior_physical_attempts']+1==item['physical_attempts'] and prior['new_physical_attempt_budget']==1
 if m.get('resume_object_order_restoration'):
  from review_order import verify_order
  verify_order(pkg,m)
 history=read(pkg/'history_preservation_acceptance.json');assert history['passed'];assert all(sha(out/n)==v for n,v in history['previous_result_files'].items())
 review={'at':C.now(),'passed':True,'job_key':h['job_key'],'approved_normal_admission_same_input_batch':True,'config_sha256':sha(h['config']),'source_bindings_sha256':sha(pkg/'source_bindings.json'),'checks':{'reviewed_versioned_successor_runtime_exact':True,'original_cache_attempt_limits_bound_to_prior_admissions':True,'original_order_restoration_only_when_exactly_proven':True,'all_prior_recovery_candidate_and_completion_files_preserved':True,'all_static_bindings_and_original_snapshot_rehashed':True,'all_original_successes_and_checkpoints_preserved':True,'one_missing_original_request_actual_sdk_and_wire_fixture':True,'real_gateway_failure_raw_membership':True,'backoff600_elapsed':True,'failure_canonical_expected_hash_CAS':True,'native_protocol_model_material_and_slot_unchanged':True,'no_policy_refusal_retry':True},'source_handoff':entry['handoff'],'physical_attempt_budget':1,'successful_cached_responses':m['successful_caches'],'checkpoints':m['checkpoint_count'],'new_model_calls':0};C.save(D/'review.json',review)
 with C.admission_lock(),(out/'.slot.lock').open('a+') as lock,(O/'queue_update.lock').open('a+') as qlock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(qlock,fcntl.LOCK_EX);state=read(P/'state/campaign.json');job=state['jobs'][h['job_key']];assert job['status']=='infrastructure_failure' and job['launches']==cfg['expected_launches'] and not C.alive(job.get('process'));absent=h['new_failure_publication']['expected_old_result_absent'];assert absent==fm['source_result_absent'];assert (not (out/'result.json').exists() and h['expected_old_result_sha256'] is None) if absent else sha(out/'result.json')==h['expected_old_result_sha256'];assert cfg['recovery_id'] not in job.get('executed_recovery_ids',[])
  for rel,v in m['files'].items():assert sha(out/rel)==v,(h['job_key'],rel)
  queue=read(O/'reviewed_queue.json');assert not any(e['config']==h['config'] for e in queue['batches']);assert C.alive(read(O/'health.json')['process']);assert read(P/'state/methods.json')['insightagents']['eligible_slots'] in [[],[1,2,3,4,5]]
  scope_file=RELEASE.parent/'scope_guard.py'
  if scope_file.exists():
   sp_scope=importlib.util.spec_from_file_location('independent_original_scope',scope_file);scope=importlib.util.module_from_spec(sp_scope);sp_scope.loader.exec_module(scope)
   scope_entry,scope_spec,scope_proof=scope.admitted_job(RELEASE.parent,P,'insightagents',job['key'],job,out)
   scope.insight_admission(scope_entry,m['host_contract'],out,P)
  action={'audit_path':str(D/'review.json'),'audit_sha256':sha(D/'review.json'),'command':cfg['command'],'recovery_id':cfg['recovery_id'],'expected_result_sha256':cfg['expected_result_sha256'],'same_slot':True,'same_material':True,'new_sample':False};chain=V.verify_chain(job,action,out/'result.json');C.save(D/'chain_validation.json',chain);assert chain['passed'],chain
  C.save(D/'before_job.json',job)
  if absent:C.save(D/'before_result_absent.json',{'expected_absent':True,'job_key':job['key'],'failure_manifest':h['new_failure_publication']['manifest']})
  else:(D/'before_result.json').write_bytes((out/'result.json').read_bytes())
  tmp=out/'result.api_automatic_successor.tmp';tmp.write_bytes(Path(h['new_failure_publication']['candidate_result']['path']).read_bytes());os.replace(tmp,out/'result.json');assert sha(out/'result.json')==cfg['expected_result_sha256']
  entry2={'config':h['config'],'review':str(D/'review.json'),'review_sha256':sha(D/'review.json')};queue['batches'].append(entry2);C.save(O/'reviewed_queue.json',queue)
  receipt={'at':C.now(),'passed':True,'job_key':h['job_key'],'expected_next_launch':cfg['expected_launches']+1,'canonical_failure_sha256':sha(out/'result.json'),'entry':entry2,'same_owner':read(O/'health.json')['process'],'successful_caches':m['successful_caches'],'checkpoints':m['checkpoint_count'],'new_model_calls':0,'new_sample':False};C.save(D/'enqueue.json',receipt);receipts.append(receipt);print(json.dumps({'enqueued':h['job_key'],'next_launch':receipt['expected_next_launch']}),flush=True)
summary={'at':C.now(),'passed':True,'source_index':ref(args.index),'newly_enqueued':len(receipts),'receipts':receipts,'raw_gateway_events_verified':len(wanted),'model_calls':0,'same_normal_owner':True};C.save(W/(args.index.stem+'_enqueue.json'),summary);print(json.dumps({k:v for k,v in summary.items() if k!='receipts'}),flush=True)
