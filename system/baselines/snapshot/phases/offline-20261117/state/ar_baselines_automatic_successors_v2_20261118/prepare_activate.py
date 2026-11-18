from pathlib import Path
import copy,fcntl,hashlib,importlib.util,json,os,signal,subprocess,sys,time
S=Path(__file__).resolve().parent;P=S.parents[1];OLD=P/'state/ar_baselines_automatic_successors_20261118';O=P/'state/ar_baselines_normal_recovery_owner_20261118T0020';sys.path.insert(0,str(P));import campaign as C,offline_gates as G
read=C.read;sha=G.sha
ref=lambda p:{'path':str(p),'sha256':sha(p)}
sp=importlib.util.spec_from_file_location('new_original_hook',S/'hook.py');H=importlib.util.module_from_spec(sp);sp.loader.exec_module(H)
trusted=read(S/'runtime_reviews.json');oldcfg=read(OLD/'configuration.json');builders=copy.deepcopy(oldcfg['builders']);allowed=[k for k in oldcfg['allowed_keys'] if k.startswith('cycleresearcher__')];reviews=[]
for method,directory,release_hash,delivery_hash in [('insightagents','insight_successor_builder_v5_20261118_B','be51370a1a15d17b95c9fc898e622c328df7c72b270e994af00c0582843ffa8a','1a002ee3df31826be2c69a8a723e211f5d1dd582d2175b8a615f04238fc07487'),('sciagents','sci_successor_builder_v2_20261118_B','f7991aeb612eefd4c05738054481b3888ee6595bf046a71f67c904afe5ece578','a4609e301fbfaa93d204eaaaef1df708c2ed6f5df63f23320d8b99106e3f2408')]:
 b=P/'state'/directory;assert sha(b/'release.json')==release_hash and sha(b/'delivery.json')==delivery_hash
 release=read(b/'release.json');delivery=read(b/'delivery.json')
 for path,digest in release['bindings'].items():assert sha(path)==digest,path
 for key in ['builder','release','scope_guard','frozen_scope','acceptance','predecessor_release']:
  r=delivery[key];assert sha(r['path'])==r['sha256'],r['path']
 acceptance=read(delivery['acceptance']['path']);assert acceptance['passed'] and all(row['passed'] for row in acceptance['checks']) and len(acceptance['checks'])==48
 previous=Path(delivery['predecessor_release']['path']).parent
 for q in (b/'templates').iterdir():assert sha(q)==sha(previous/'templates'/q.name),q
 if method=='insightagents':
  for name in ['provider_failure.py','ledger_reconciliation.py']:assert sha(b/name)==sha(previous/name)
 spec=importlib.util.spec_from_file_location('scope_'+method,b/'scope_guard.py');scope=importlib.util.module_from_spec(spec);spec.loader.exec_module(scope);rows=scope.fixed_scope(b,P,method);assert len(rows)==190;allowed.extend(rows)
 trusted[method][release_hash]={'release':str(b/'release.json')};builders[method]={'command':['/usr/bin/python3','-B',str(b/'builder.py')],'release':ref(b/'release.json')};reviews.append({'method':method,'original_slots':len(rows),'release':ref(b/'release.json'),'scope':ref(b/'frozen_scope.json'),'scope_fixture':delivery['acceptance'],'frozen_native_runtime_templates_unchanged':True})
assert len(allowed)==len(set(allowed))==381
C.save(S/'runtime_reviews.json',trusted)
bindings={p:h for p,h in oldcfg['bindings'].items() if not Path(p).is_relative_to(OLD) and Path(p).name!='owner_v3.py'}
for q in [*S.glob('*.py'),S/'runtime_reviews.json',S/'guard_acceptance.json',O/'owner_v4.py',O/'owner_v4_base.py']:
 bindings[str(q)]=sha(q)
for r in reviews:
 for field in ['release','scope','scope_fixture']:bindings[r[field]['path']]=r[field]['sha256']
config={**oldcfg,'at':C.now(),'revision':'reviewed-original-input-successors-v2-fixed381-first-failures','allowed_keys':sorted(allowed),'builders':builders,'bindings':bindings,'original_scope_count':381,'first_original_failure_supported':True,'backoff_waits_do_not_block_other_slots':True,'individual_evidence_errors_do_not_block_other_slots':True,'scope_membership_never_grants_original_admission':True}
C.save(S/'configuration.json',config)
review={'at':C.now(),'passed':True,'checks':{'fixed_original_scope_381_exact':True,'both_scope_guards48_each_passed':True,'original_native_runtime_and_response_semantics_unchanged':True,'independent_review_rechecks_original_admission_before_CAS':True,'first_failure_without_registry_supported':True,'per_slot_backoff_isolation':True,'zero_physical_requires_repair':True,'single_existing_owner_lock_and_queue':True,'existing_raw_failure_and_unknown_usage_preserved':True,'hard_global230_scoring20_HTTP250':True},'configuration':ref(S/'configuration.json'),'builders':reviews,'guard_fixture':ref(S/'guard_acceptance.json'),'new_model_calls':0};C.save(S/'implementation_review.json',review)
# Adopt an independently prepared new-original first failure without duplicate builders.
hp=P/'state/insight_fresh_scope_successor_20261118_B/packages/insightagents__continual-learning__03__generation/handoff.json';assert sha(hp)=='5beb80c65942817f5be2e46237547e197982958a4e5589a9c2afc6bf7238efc5';h=read(hp);hc=read(h['config']);assert sha(h['config'])==h['config_sha256'];m=read(hc['manifest']);assert all(sha(path)==digest for path,digest in read(hp.parent/'source_bindings.json').items());f=read(h['fixture']['path']);assert sha(h['fixture']['path'])==h['fixture']['sha256'] and f['passed'] and all(f['checks'].values()) and f['model_calls']==0
job=read(P/'state/campaign.json')['jobs'][h['job_key']];assert job==read(hp.parent/'expected_prior_job.json');ok,reason,evidence=H.first_attempt_evidence(job,Path(m['output_dir']));assert ok;signature=hashlib.sha256(json.dumps({'job_key':job['key'],'launches':job['launches'],'prior_evidence':evidence,'builder_revision':config['revision']},sort_keys=True).encode()).hexdigest()[:24]
waiting={signature:{'signature':signature,'job_key':job['key'],'method':job['method'],'prior_launches':job['launches'],'prior_evidence':evidence,'stage':'waiting_backoff','handoff':str(hp),'not_before_epoch':hc['not_before_epoch'],'strict_review_still_required':True,'new_model_calls_by_builder':0,'builder_handoff':ref(hp)}}
with C.admission_lock(),(P/'state/methods.lock').open('a+') as ml:
 fcntl.flock(ml,fcntl.LOCK_EX);state=read(P/'state/campaign.json');methods=read(P/'state/methods.json');control=read(P/'state/control.json');assert control['request_concurrency']==250 and control['generation_workers']==230 and control['scoring_workers']==20
 owner=read(O/'health.json')['process'];assert owner['pid']==429752 and owner['start']=='78738333' and C.alive(owner);cmd=[x.decode() for x in Path(f'/proc/{owner["pid"]}/cmdline').read_bytes().split(b'\0') if x];assert str(O/'owner_v3.py') in cmd
 prior_active=read(OLD/'active.json',{});assert not prior_active or (prior_active['stage']=='waiting_backoff' and not C.alive(prior_active.get('process')))
 if prior_active:
  pp=Path(prior_active['handoff']);ph=read(pp);pc=read(ph['config']);assert pc['not_before_epoch']==prior_active['not_before_epoch'];assert sha(ph['config'])==ph['config_sha256'];waiting[prior_active['signature']]=copy.deepcopy(prior_active)
 future=copy.deepcopy(methods);assert methods['sciagents']['max_generation_workers']==8;future['sciagents']['max_generation_workers']=230
 assert {k:v for k,v in future['sciagents'].items() if k!='max_generation_workers'}=={k:v for k,v in methods['sciagents'].items() if k!='max_generation_workers'}
 oldread=G.read
 def virtual(path,default=None):return future if Path(path)==P/'state/methods.json' else oldread(path,default)
 G.read=virtual
 try:gate=G.check()
 finally:G.read=oldread
 C.save(S/'prepared_offline_gate.json',gate);assert gate['passed']
 for name,value in [('old_owner',owner),('old_active',prior_active),('methods_before',methods),('control_before',control),('queue_before',read(O/'reviewed_queue.json'))]:C.save(S/(name+'.json'),value)
 assert read(OLD/'active.json',{})==prior_active;os.kill(owner['pid'],signal.SIGTERM)
 for _ in range(50):
  if not C.alive(owner):break
  time.sleep(.1)
 assert not C.alive(owner)
 with (O/'owner.lock').open('a+') as ownerlock:fcntl.flock(ownerlock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 C.save(S/'waiting.json',waiting);C.save(S/'active.json',{});C.save(P/'state/methods.json',future);gate=G.check();C.save(S/'live_offline_gate.json',gate);assert gate['passed']
 with (S/'owner_v4.log').open('ab') as log:proc=subprocess.Popen(['/usr/bin/python3','-B',str(O/'owner_v4.py')],cwd=P,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 receipt={'at':C.now(),'passed':True,'old_owner':owner,'new_owner':C.handle(proc.pid),'same_owner_lock':str(O/'owner.lock'),'same_reviewed_queue':str(O/'reviewed_queue.json'),'old_waiting_package_preserved':bool(prior_active),'adopted_waiting_packages':len(waiting),'scope_original_keys':381,'insight_original_keys':190,'sci_original_keys':190,'cycle_original_keys':1,'first_failure_without_registry_supported':True,'Sci_method_cap_before':8,'Sci_method_cap_after':230,'original_domain_and_slot_gates_unchanged':True,'control_unchanged':read(P/'state/control.json')==control,'request_cap':250,'generation_cap':230,'scoring_cap':20,'native_worker_signals':0,'scheduler_signals':0,'configuration':ref(S/'configuration.json'),'review':ref(S/'implementation_review.json'),'guard_fixture':ref(S/'guard_acceptance.json'),'new_model_calls_by_activation':0};C.save(S/'activation.json',receipt);print(json.dumps(receipt),flush=True)
