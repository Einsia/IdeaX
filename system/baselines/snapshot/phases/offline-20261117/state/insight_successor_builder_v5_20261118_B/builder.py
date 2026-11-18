"""Immutable, repeatable per-key recovery preparation; never edits shared state or calls an API."""
from pathlib import Path
import argparse,ast,copy,datetime,hashlib,json,re,shutil,subprocess,sys,traceback
S=Path(__file__).resolve().parent;P=S.parents[1];sys.path.insert(0,str(P));import campaign as C
sys.path.insert(0,str(S))
from ledger_reconciliation import validated_storage,reconcile_storage_gaps,reconcile_current_target
from provider_failure import explicit_server_failure,retry_delay_seconds
from scope_guard import fixed_scope,admitted_job,insight_admission,executed_recovery
N=P/'staging/insightagents_domain_admission_candidate_v2_20261118T0045/native/src/debate/runner.py'
read=lambda p:json.loads(Path(p).read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p):return {'path':str(p),'sha256':sha(p)}
def save(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def require(v,message):
 if not v:raise RuntimeError(message)
def parser():
 names={'_repair_json_escapes','_first_json_start','_decode_escaping_stray_quotes','_scan_json','_extract_json'};tree=ast.parse(N.read_text());nodes=[n for n in tree.body if (isinstance(n,ast.ImportFrom) and n.module=='__future__') or (isinstance(n,ast.FunctionDef) and n.name in names) or (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in {'_JSON_ESCAPE_CHARS','_ESCAPE_PAIR_RE'} for t in n.targets))];ns={'json':json,'re':re};exec(compile(ast.Module(body=nodes,type_ignores=[]),str(N),'exec'),ns);return ns['_extract_json']
def prior_manifest(job,registry):
 action=registry.get(job['key'])
 if not action:return None
 require(action['recovery_id'] in job.get('executed_recovery_ids',[]),'Prior approved recovery has not executed')
 cmd=action['command'];path=Path(cmd[cmd.index('--manifest')+1]);m=read(path)
 if 'manifest' in m:path=Path(m['manifest']);m=read(path)
 require(m['recovery_id']==action['recovery_id'],'Prior recovery manifest identity differs');executed_recovery(job,action,m,path,P);return path

def classify(key):
 job=read(P/'state/campaign.json')['jobs'][key];out=C.result_path(job).parent
 require(job['kind']=='generation' and job['method']=='insightagents','Builder scope is admitted Insight generation')
 if job['status']!='infrastructure_failure' or C.alive(job.get('process')):return {'skip':'not_idle_api_failure','job_key':key}
 entry,spec,scope_proof=admitted_job(S,P,'insightagents',key,job,out)
 if (out/'terminal.json').exists():return {'skip':'native_terminal_requires_independent_review','job_key':key}
 registry=read(P/'state/generation_recoveries.json');mp=prior_manifest(job,registry);old=read(mp) if mp else None
 if old:
  candidate=out/old.get('candidate_filename','insight_recovery_candidate_result.json')
  if candidate.exists() and read(candidate).get('status') not in ['infrastructure_failure']:return {'skip':'native_result_requires_independent_review','job_key':key,'candidate':ref(candidate)}
 missing=[p for p in (out/'model_calls').iterdir() if p.is_dir() and (p/'request.json').exists() and not (p/'native_returned.json').exists()]
 if not missing:return {'skip':'no_current_missing_response','job_key':key}
 require(len(missing)==1,'Multiple unresolved Insight calls require diagnosis');target=missing[0];physical=sorted(target.glob('physical-*'));require(bool(physical),'No physical API evidence')
 last=physical[-1];require((last/'receipt.json').exists(),'No completed transport receipt; independent classification required');rec=read(last/'receipt.json');raw=last/'response_body.bin'
 require(sha(raw)==rec['response_sha256'] and sha(last/'request_body.json')==rec['request_sha256'],'Actual response/request binding differs')
 status=rec['http_status'];provider_error=(read(raw).get('error') if status!=200 else None)
 if provider_error and any(x in json.dumps(provider_error).lower() for x in ['cyber_policy','policy_violation','content_policy']):return {'skip':'provider_policy_rejection_no_retry','job_key':key,'raw':ref(raw)}
 status=rec['http_status'];require(status in [200,408,429,500,502,503,504],'Not an admitted API transport failure')
 require(rec.get('usage') is None and (rec.get('provider_status') is None or (status==200 and rec.get('provider_status')=='failed')),'Provider outcome must be classified independently')
 terminals=[];stream_events=[];provider_failure=None;invalid_sse_frames=0
 if status==200:
  for frame in raw.read_text().replace('\r\n','\n').split('\n\n'):
   data='\n'.join(l[5:].lstrip(' ') for l in frame.splitlines() if l.startswith('data:'))
   if data and data!='[DONE]':
    try:e=json.loads(data)
    except ValueError:invalid_sse_frames+=1;continue
    stream_events.append(e)
    if str(e.get('type','')).startswith('response.refusal.'):return {'skip':'provider_refusal_no_retry','job_key':key,'raw':ref(raw)}
    if e.get('type') in ['response.completed','response.failed','response.incomplete','error']:terminals.append(e)
  if rec.get('provider_status')=='failed':
   require(invalid_sse_frames==0,'Provider failed stream has malformed event frames');provider_failure=explicit_server_failure(rec,stream_events)
  elif terminals:return {'skip':'provider_terminal_requires_independent_review','job_key':key,'raw':ref(raw)}
 else:require(isinstance(read(raw).get('error'),(dict,str)),'HTTP error body missing')
 ledger=[json.loads(l) for l in (out/'model_attempts.jsonl').read_text().splitlines()];ends=[e for e in ledger if e.get('event')=='attempt_end']
 inherited_storage=validated_storage(job,out,mp,old);storage_gaps=reconcile_storage_gaps(out,ledger,inherited_storage);latest,target_ledger_proof=reconcile_current_target(out,target,physical,ledger,storage_gaps)
 require(latest['request_sha256']==rec['request_sha256'],'Latest actual ledger differs');gatewayid=rec['headers'].get('x-offline-bridge-request-id') or (read(raw).get('request_id') if status!=200 else None);require(bool(gatewayid),'Transport error lacks an actual gateway request identity');events=[]
 with (P/'logs/model_gateway.jsonl').open() as stream:
  for line in stream:
   if gatewayid in line:
    e=json.loads(line)
    if e.get('request_id')==gatewayid:events.append(e)
 starts=[e for e in events if e['event']=='attempt_start'];stops=[e for e in events if e['event']=='attempt_end'];require(len(starts)==len(stops)==1 and all(e.get('mock') is False for e in events),'Actual unique gateway evidence absent')
 gateway_synthetic_502=status==502 and read(raw).get('error')=='Model transport unavailable' and read(raw).get('request_id')==gatewayid and stops[0]['http_status'] is None and any(e['event']=='transport_error' for e in events)
 require(all(e['request_sha256']==rec['request_sha256'] for e in starts+stops) and (stops[0]['http_status']==status or gateway_synthetic_502) and stops[0]['completed'] is False and stops[0]['usage'] is None,'Gateway failed outcome differs')
 if status==200 and provider_failure is None:require(any(e.get('event')=='transport_error' and e.get('error_type')=='IncompleteRead' for e in events),'EOF lacks actual gateway IncompleteRead')
 if old:contract=old['host_contract']
 else:
  cmd=job['command'];contracts=Path(cmd[cmd.index('--contracts')+1]);contract=ref(contracts/job['domain']/f"slot-{job['slot']:02}"/'host_contract.json')
 scope_proof['original_admission']=insight_admission(entry,contract,out,P)
 host=read(contract['path']);binding=read(out/'run_binding.json');require(sha(contract['path'])==contract['sha256'] and host['admission']['sha256']==binding['admission_receipt_sha256']==sha(host['admission']['path']) and host['manifest']['sha256']==binding['package_sha256']==sha(host['manifest']['path']),'Original admission binding changed')
 successful={}
 for rp in (out/'model_calls').glob('*/native_returned.json'):
  rr=read(rp);count=rr['physical_attempts'];require(count>=1,'Invalid success physical count')
  if count>3:
   rid=rr.get('recovery_id');launches=[x for x in job.get('recovery_launches',[]) if x['recovery_id']==rid];require(rid in job.get('executed_recovery_ids',[]) and len(launches)==1,'Extended success lacks original authorized recovery')
   cmd=launches[0]['command'];rm=read(cmd[cmd.index('--manifest')+1]);require(rm['recovery_id']==rid and rm['target_directory']==str(rp.parent.relative_to(out)) and rm['prior_physical_attempts']+1==count and rm['new_physical_attempt_budget']==1,'Extended success exceeded its admitted exact target budget')
  successful[str(rp.parent.relative_to(out))]={'receipt_sha256':sha(rp),'physical_attempts':count,'recovery_id':rr.get('recovery_id')}
 previous=old['target_directory'] if old else None;previous_success=bool(previous and (out/previous/'native_returned.json').exists())
 row={'job_key':key,'method':'insightagents','original_job':job,'output_dir':str(out),'canonical_result':ref(out/'result.json') if (out/'result.json').exists() else None,'classification':'first_failure_without_recovery_manifest' if not old else 'old_target_success_later_missing' if previous_success else 'old_target_still_missing','transport_classification':'provider_response_failed_server_error' if provider_failure else 'raw_sse_eof_without_terminal' if status==200 else 'http'+str(status),'provider_failure_terminal':provider_failure,'provider_retry_after_seconds':retry_delay_seconds(provider_failure,latest['at']),'original_recovery_manifest':ref(mp) if mp else None,'host_contract':contract,'original_domain_binding':binding,'target_directory':str(target.relative_to(out)),'target_is_previous_failed_call':previous==str(target.relative_to(out)),'previous_target_completed':previous_success,'current_target_prior_physical_attempts':len(physical),'successful_caches':len(successful),'successful_cache_receipts':successful,'checkpoint_count':len(list((out/'checkpoints').glob('*.json'))),'provider_policy_rejection_observed':False,'request':ref(target/'request.json'),'raw':ref(raw),'receipt':ref(last/'receipt.json'),'latest_failure_end':latest,'gateway_events':events,'all_known_usage_subtotal':{k:sum((e.get('usage') or {}).get(k,0) for e in ends) for k in ['input_tokens','output_tokens','total_tokens']},'all_unknown_usage_attempts':sum(e.get('usage') is None for e in ends)+len(storage_gaps),'unknown_usage_from_local_ends':sum(e.get('usage') is None for e in ends),'unknown_usage_from_reviewed_storage_gaps':len(storage_gaps),'storage_gap_ledger_reconciliation':storage_gaps,'target_ledger_reconciliation':target_ledger_proof,'usage':None,'usd':None}

 row['storage_interrupted_physical']=inherited_storage;row['original_phase_scope_proof']=scope_proof
 return row

def prepare(root,key,rid,row):
 pkg=root/'packages'/key;snap=pkg/'original_run';pkg.mkdir(parents=True);out=Path(row['output_dir']);job=row['original_job'];shutil.copytree(out,snap,symlinks=True)
 files={str(p.relative_to(snap)):sha(p) for p in sorted(snap.rglob('*')) if p.is_file()};require(all(sha(out/r)==h for r,h in files.items()),'Live source changed during snapshot');require(read(P/'state/campaign.json')['jobs'][key]==job,'Job changed during snapshot')
 save(pkg/'classification.json',row);save(pkg/'expected_prior_job.json',job);oldsha=sha(snap/'result.json') if (snap/'result.json').exists() else None;target=snap/row['target_directory'];physical=sorted(target.glob('physical-*'));checkpoints=sorted((snap/'checkpoints').glob('*.json'));host=read(row['host_contract']['path']);binding=row['original_domain_binding'];code='upstream_incomplete_read' if row['transport_classification']=='raw_sse_eof_without_terminal' else 'upstream_'+row['transport_classification'];due=datetime.datetime.fromisoformat(row['latest_failure_end']['at']).timestamp()+max(600,row.get('provider_retry_after_seconds',0))
 failure={'at':C.now(),'job_key':key,'launches':job['launches'],'status':'infrastructure_failure','archived_run':str(snap),'source_files':files,'expected_old_result_sha256':oldsha,'source_result_absent':oldsha is None,'target_directory':row['target_directory'],'target_identity':read(target/'request.json')['identity'],'target_is_previous_failed_call':row['target_is_previous_failed_call'],'previous_target_completed':row['previous_target_completed'],'successful_previous_target_never_retried':True,'original_successful_caches':row['successful_caches'],'checkpoint_count':len(checkpoints),'latest_checkpoint':ref(checkpoints[-1]) if checkpoints else None,'provider_error':{'code':code,'message':'Verified latest real transport or explicit provider server failure; no completed response or policy rejection'},'provider_failure_terminal':row.get('provider_failure_terminal'),'provider_retry_after_seconds':row.get('provider_retry_after_seconds',0),'gateway_events':row['gateway_events'],'latest_failure_at':row['latest_failure_end']['at'],'all_known_usage_subtotal':row['all_known_usage_subtotal'],'all_unknown_usage_attempts':row['all_unknown_usage_attempts'],'usage':None,'usd':None,'native_output_consumed':False,'source_classification':ref(pkg/'classification.json'),'previous_recovery_manifest':row['original_recovery_manifest'],'bindings':{row['host_contract']['path']:row['host_contract']['sha256']},'model_calls_by_capture':0};save(pkg/'failure_manifest.json',failure)
 base=read(snap/'result.json') if oldsha else {**read(snap/'input_material_version.json'),'method':'insightagents','domain':job['domain'],'slot':f"slot-{job['slot']:02}",'fixture':False,'run_id':binding['run_id'],'admission_id':binding['admission_id'],'purpose':binding['purpose']}
 candidate={**base,'status':'infrastructure_failure','terminal_reason':code,'proposal_markdown':None,'native_failure':False,'transport_retry_eligible':True,'failure_evidence':ref(pkg/'failure_manifest.json'),'usage':None,'usd':None,'cost_usd':None,'known_usage_subtotal':row['all_known_usage_subtotal'],'failed_attempts_usage_unknown':row['all_unknown_usage_attempts']};save(pkg/'candidate_failure_result.json',candidate)
 tag=hashlib.sha256(rid.encode()).hexdigest()[:20];candidate_name='insight_recovery_'+tag+'_candidate_result.json';completion_name='insight_recovery_'+tag+'_completion.json';require(not (out/candidate_name).exists() and not (out/completion_name).exists(),'Recovery output name already exists')
 m={'at':C.now(),'job_key':key,'method':'insightagents','domain':job['domain'],'slot':f"slot-{job['slot']:02}",'output_dir':str(out),'original_snapshot':str(snap),'files':files,'host_contract':row['host_contract'],'package_manifest':host['manifest'],'admission':host['admission'],'recovery_id':rid,'expected_launches':job['launches'],'expected_old_result_sha256':oldsha,'expected_result_sha256':sha(pkg/'candidate_failure_result.json'),'target_directory':row['target_directory'],'target_request_sha256':sha(target/'request.json'),'target_wire_sha256':sha(physical[-1]/'native_sdk_request_body.json'),'target_stream_wire_sha256':sha(physical[-1]/'request_body.json'),'prior_physical_attempts':len(physical),'successful_caches':row['successful_caches'],'successful_cache_receipts':row['successful_cache_receipts'],'storage_interrupted_physical':row.get('storage_interrupted_physical',{}),'checkpoint_count':len(checkpoints),'not_before_epoch':due,'failure_manifest':ref(pkg/'failure_manifest.json'),'new_physical_attempt_budget':1,'subsequent_native_sdk_max_retries':2,'provider_failure_terminal':row.get('provider_failure_terminal'),'provider_retry_after_seconds':row.get('provider_retry_after_seconds',0),'original_domain_binding':binding,'partial_output_consumed':False,'same_slot':True,'same_material':True,'new_sample':False,'new_context':False,'candidate_filename':candidate_name,'completion_filename':completion_name,'previous_recovery_result_files_preserved':True,'canonical_result_only_changes_by_independent_expected_hash_CAS':True,'builder_release':ref(S/'release.json')};save(pkg/'manifest.json',m);bind(root,pkg)
 return pkg

def bind(root,pkg):
 m=read(pkg/'manifest.json');sources=[root/n for n in ['driver.py','host.py','finalize.py','health_verifier.py','health_fixture_acceptance.json','builder_release.json']]+[pkg/n for n in ['manifest.json','classification.json','failure_manifest.json','candidate_failure_result.json','expected_prior_job.json']]+[Path(m['host_contract']['path']),Path(m['admission']['path'])]
 for name in ['object_order_diagnosis.json','history_preservation_acceptance.json']:
  if (pkg/name).exists():sources.append(pkg/name)
 save(pkg/'source_bindings.json',{str(p):sha(p) for p in sources})

def restore_order(pkg):
 m=read(pkg/'manifest.json');snap=Path(m['original_snapshot']);bad=pkg/'fixture/resume_payload_mismatch.json';require(bad.exists(),'Fixture failure is not the diagnosed object-order condition');j=read(bad);a=copy.deepcopy(j['expected']);b=copy.deepcopy(j['observed']);left=a['native_arguments']['messages'][0]['content'];right=b['native_arguments']['messages'][0]['content'];a['native_arguments']['messages'][0]['content']=right;require(a==b,'More than the exact prompt content differs');cp=read(sorted((snap/'checkpoints').glob('*.json'))[-1]);draft=cp['native_progress']['debate']['draft'];extract=parser();found=[]
 for q in (snap/'model_calls').glob('*/native_response.json'):
  v=extract(read(q)['text'] or '');options=[([],v)]+([(['updated_draft'],v.get('updated_draft'))] if isinstance(v,dict) else [])
  for pointer,value in options:
   if value!=draft:continue
   x=json.dumps(value,ensure_ascii=False,indent=2);y=json.dumps(draft,ensure_ascii=False,indent=2)
   if x==y:continue
   matches=[i for i in range(len(left)) if left.startswith(x,i) and left[:i]+y+left[i+len(x):]==right]
   if len(matches)==1:found.append({'source':str(q),'sha256':sha(q),'parsed_value_path':pointer,'source_identity':read(q.parent/'request.json')['identity'],'values_must_be_strictly_equal':True,'original_checkpoint_bytes_unchanged':True,'progress_paths':[['debate','draft']]+[['debate','draft_versions',i,'draft'] for i,v in enumerate(cp['native_progress']['debate']['draft_versions']) if v['draft']==draft]})
 require(len(found)==1,'Cannot prove unique original draft-order restoration');save(pkg/'object_order_diagnosis.json',{'restoration':found[0],'mismatch_evidence':ref(bad),'only_differing_field':'/native_arguments/messages/0/content','entire_difference_is_one_exact_original_draft_json_key_reordering':True,'parser_source':ref(N),'model_calls':0});m['resume_object_order_restoration']=found[0];save(pkg/'manifest.json',m)
 (pkg/'fixture').rename(pkg/'fixture_before_object_order_restoration');(pkg/'fixture.log').rename(pkg/'fixture_before_object_order_restoration.log');proof=read(pkg/'object_order_diagnosis.json');proof['mismatch_evidence']=ref(pkg/'fixture_before_object_order_restoration/resume_payload_mismatch.json');save(pkg/'object_order_diagnosis.json',proof);bind(pkg.parents[1],pkg)

def fixture(root,pkg):
 with (pkg/'fixture.log').open('wb') as log:r=subprocess.run(['/usr/bin/python3','-B',str(root/'host.py'),'--manifest',str(pkg/'manifest.json'),'--fixture-output',str(pkg/'fixture')],stdout=log,stderr=subprocess.STDOUT)
 return r.returncode==0

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--key',required=True);ap.add_argument('--recovery-id',required=True);ap.add_argument('--output-root',type=Path,required=True);a=ap.parse_args();release=read(S/'release.json');require(all(sha(p)==h for p,h in release['bindings'].items()),'Builder release changed');allow=fixed_scope(S,P,'insightagents');require(a.key in allow,'Key is outside the frozen original phase recovery scope');root=a.output_root.resolve();require(root.parent==P/'state' and root!=S,'Output root must be a fresh phase state child');pkg=root/'packages'/a.key
 if (pkg/'handoff.json').exists():
  require(read(pkg/'manifest.json')['recovery_id']==a.recovery_id,'Existing package has another recovery id');require(all(sha(p)==h for p,h in read(pkg/'source_bindings.json').items()),'Sealed package changed');print(json.dumps({'status':'already_sealed','handoff':ref(pkg/'handoff.json'),'live_mutations':False}));return 0
 root.mkdir(parents=True,exist_ok=True)
 for src in (S/'templates').iterdir():
  dst=root/src.name
  if dst.exists():require(sha(dst)==sha(src),'Runtime root belongs to another builder release')
  else:shutil.copyfile(src,dst)
 if (root/'builder_release.json').exists():require(sha(root/'builder_release.json')==sha(S/'release.json'),'Builder release differs')
 else:shutil.copyfile(S/'release.json',root/'builder_release.json')
 if (pkg/'manifest.json').exists():
  m=read(pkg/'manifest.json');require(m['recovery_id']==a.recovery_id,'Existing package has another recovery id');require(read(P/'state/campaign.json')['jobs'][a.key]==read(pkg/'expected_prior_job.json'),'Original job advanced; use new immutable successor id/root')
 else:
  row=classify(a.key)
  if 'skip' in row:save(root/(a.key+'_skipped.json'),row);print(json.dumps(row));return 0
  require(a.recovery_id not in row['original_job'].get('executed_recovery_ids',[]),'Recovery id already executed');pkg=prepare(root,a.key,a.recovery_id,row)
 if not (pkg/'fixture/transport_fixture_acceptance.json').exists():require(not (pkg/'fixture').exists(),'Incomplete fixture retained; independent diagnosis required');fixture(root,pkg)
 acceptance=read(pkg/'fixture/transport_fixture_acceptance.json')
 if not acceptance['passed'] and not read(pkg/'manifest.json').get('resume_object_order_restoration'):
  restore_order(pkg);require(fixture(root,pkg),'Restored fixture still failed');acceptance=read(pkg/'fixture/transport_fixture_acceptance.json')
 require(acceptance['passed'] and all(acceptance['checks'].values()) and acceptance['model_calls']==0,'Exact offline fixture failed')
 m=read(pkg/'manifest.json');history=[p for p in Path(m['original_snapshot']).glob('*') if p.is_file() and ('candidate_result' in p.name or 'completion.json' in p.name)];proof={'passed':all(sha(p)==sha(pkg/'fixture'/p.name) for p in history),'previous_result_files':{p.name:sha(p) for p in history},'model_calls':0,'live_mutations':False};require(proof['passed'],'Prior recovery history changed');save(pkg/'history_preservation_acceptance.json',proof);bind(root,pkg)
 require(read(P/'state/campaign.json')['jobs'][a.key]==read(pkg/'expected_prior_job.json'),'Job changed before sealing');require(all(sha(Path(m['output_dir'])/r)==h for r,h in m['files'].items()),'Live evidence changed before sealing')
 admitted_job(S,P,'insightagents',a.key,read(pkg/'expected_prior_job.json'),Path(m['output_dir']))
 with (pkg/'finalize.log').open('wb') as log:r=subprocess.run(['/usr/bin/python3','-B',str(root/'finalize.py'),'--key',a.key],stdout=log,stderr=subprocess.STDOUT)
 require(r.returncode==0,'Finalizer failed');save(pkg/'builder_completion.json',{'handoff':ref(pkg/'handoff.json'),'builder_release':ref(S/'release.json'),'model_calls':0,'shared_mutations':False,'independent_review_CAS_and_same_owner_enqueue_required':True});print(json.dumps(read(pkg/'builder_completion.json')));return 0
if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as exc:print(json.dumps({'status':'withheld','error':type(exc).__name__+': '+str(exc),'model_calls':0,'shared_mutations':False}));traceback.print_exc();raise SystemExit(2)
