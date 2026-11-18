"""Build immutable current-missing Sci successors with exact seeded native replay and no API calls."""
from pathlib import Path
import argparse,datetime,hashlib,json,re,shutil,subprocess,sys,traceback
S=Path(__file__).resolve().parent;P=S.parents[1];sys.path.insert(0,str(P));import campaign as C
sys.path.insert(0,str(S))
from scope_guard import fixed_scope,admitted_job,sci_admission,executed_recovery
read=lambda p:json.loads(Path(p).read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p):return {'path':str(p),'sha256':sha(p)}
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def require(v,msg):
 if not v:raise RuntimeError(msg)
def classify(key):
 job=read(P/'state/campaign.json')['jobs'][key];out=C.result_path(job).parent
 require(job['method']=='sciagents' and job['kind']=='generation','Sci generation only')
 if job['status']!='infrastructure_failure' or C.alive(job.get('process')):return {'skip':'not_idle_api_failure','job_key':key}
 entry,spec,scope_proof=admitted_job(S,P,'sciagents',key,job,out);scope_proof['original_admission']=sci_admission(entry,spec,out,P)
 oldpath=None;old=None;action=read(P/'state/generation_recoveries.json').get(key)
 if action:
  if action['recovery_id'] not in job.get('executed_recovery_ids',[]):return {'skip':'approved_recovery_not_executed','job_key':key}
  cmd=action['command'];oldpath=Path(cmd[cmd.index('--manifest')+1]);old=read(oldpath)
  if 'manifest' in old:oldpath=Path(old['manifest']);old=read(oldpath)
  executed_recovery(job,action,old,oldpath,P)
  candidate=out/old.get('candidate_filename','original_transport_candidate_result.json')
  if candidate.exists() and read(candidate).get('status')!='infrastructure_failure':return {'skip':'native_result_requires_independent_review','job_key':key,'candidate':ref(candidate)}
 ledger=[json.loads(l) for l in (out/'api_events.jsonl').read_text().splitlines()];requests=[];transport=[]
 for req in sorted((out/'api_requests').glob('*/request.json')):
  rr=read(req.parent/'receipt.json') if (req.parent/'receipt.json').exists() else {};ident=req.parent.name;ends=[e for e in ledger if e.get('event')=='attempt_end' and e.get('request_id')==ident];require(bool(ends),'Request has no original physical ledger');done=rr.get('status')=='completed'
  if rr.get('status')=='native_failure':return {'skip':'native_length_failure_requires_independent_review','job_key':key}
  if done:
   response=read(req.parent/'response.json');require(response['choices'][0]['finish_reason'] in ['stop','tool_calls','function_call'] and rr['request_sha256']==hashlib.sha256(json.dumps(read(req),ensure_ascii=False,sort_keys=True).encode()).hexdigest() and rr['response_sha256']==hashlib.sha256(json.dumps(response,ensure_ascii=False).encode()).hexdigest(),'Successful response binding invalid')
  else:
   for end in ends:
    errpath=req.parent/'attempts'/end['attempt_id']/'error.json';error=read(errpath);require(error['error']==end['error'] and error['type']==end['error_type'],'Original error ledger differs');http=error.get('http',{});body=http.get('body','')
    try:bodyvalue=json.loads(body)
    except ValueError:bodyvalue={}
    structured=bodyvalue.get('error',{}) if isinstance(bodyvalue,dict) else {};structured=json.dumps(structured).lower()
    if any(x in structured for x in ['cyber_policy','policy_violation','content_policy']):return {'skip':'provider_policy_rejection_no_retry','job_key':key,'error':ref(errpath)}
    require(http.get('status') in [408,429,500,502,503,504] or error['type'] in ['TimeoutError','URLError','ConnectionError','IncompleteRead'] or (error['type']=='InfrastructureFailure' and error['error']=='Stream closed before terminal completion'),'Non-transport error requires diagnosis')
    transport.append({'request_id':ident,'attempt_id':end['attempt_id'],'error':ref(errpath),'usage':None,'usd':None})
  requests.append({'component':'','request_id':ident,'completed':done,'request_file_sha256':sha(req),'prior_physical_attempts':len(ends),'last_end':ends[-1],'usage':rr.get('usage'),'usd':None})
 missing=[r for r in requests if not r['completed']]
 if not missing:return {'skip':'no_current_missing_response','job_key':key}
 target=max(missing,key=lambda r:r['last_end']['at']);history=read(out/'native_partial_chat_history.json');wire=read(out/'api_requests'/target['request_id']/'request.json');consumed=[]
 for row in missing:
  if row==target:continue
  text='Error: '+row['last_end']['error'];indices=[i for i,x in enumerate(history) if x.get('role')=='tool' and x.get('content')==text];require(indices and any(x.get('role')=='tool' and x.get('content')==text for x in wire['messages']),'Earlier missing failure not proven consumed by native tool history');consumed.append({**row,'native_tool_error_already_consumed':True,'original_groupchat_error_message_indices':indices})
 return {'original_phase_scope_proof':scope_proof,'job_key':key,'original_job':job,'output_dir':str(out),'canonical_result':ref(out/'result.json'),'requests':requests,'target':target,'historical_consumed_failure_requests':consumed,'successful_requests':[r for r in requests if r['completed']],'all_failed_physical_evidence':transport,'previous_recovery_manifest':ref(oldpath) if oldpath else None,'prior_candidate_filename':old.get('candidate_filename','original_transport_candidate_result.json') if old else None,'all_unknown_usage_attempts':sum(e.get('event')=='attempt_end' and e.get('usage') is None for e in ledger),'usage':None,'usd':None}

def prepare(root,key,rid,row):
 pkg=root/'packages'/key;snap=pkg/'original_run';pkg.mkdir(parents=True);out=Path(row['output_dir']);job=row['original_job'];shutil.copytree(out,snap,symlinks=True);files={str(q.relative_to(snap)):sha(q) for q in sorted(snap.rglob('*')) if q.is_file()};require(all(sha(out/r)==h for r,h in files.items()) and read(P/'state/campaign.json')['jobs'][key]==job,'Live evidence changed during freeze');save(pkg/'classification.json',row);save(pkg/'expected_prior_job.json',job)
 oldsha=sha(out/'result.json');canonical=read(out/'result.json');candidate=snap/row['prior_candidate_filename'] if row['prior_candidate_filename'] else None;publish=bool(candidate and candidate.exists());prior_candidate=read(candidate) if publish else {}
 failure={'at':C.now(),'job_key':key,'launches':job['launches'],'status':'infrastructure_failure','expected_old_result_sha256':oldsha,'archived_run':str(snap),'source_files':dict(files),'failed_requests':[row['target']],'historical_consumed_failure_requests':row['historical_consumed_failure_requests'],'successful_requests':row['successful_requests'],'latest_failure_at':row['target']['last_end']['at'],'unknown_usage_attempts':row['all_unknown_usage_attempts'],'usage':None,'usd':None,'old_failure_canonical_preserved':True,'model_calls_by_audit':0,'source_classification':ref(pkg/'classification.json'),'previous_recovery_manifest':row['previous_recovery_manifest']};save(pkg/'predecessor_failure_manifest.json',failure)
 if publish:
  canonical={**canonical,**prior_candidate,'status':'infrastructure_failure','terminal_reason':row['target']['last_end']['error'],'failure_evidence':ref(pkg/'predecessor_failure_manifest.json'),'latest_failure_at':row['target']['last_end']['at'],'usage':None,'usd':None};save(pkg/'candidate_failure_result.json',canonical)
 domain=P/'inputs'/job['domain']/'domain.json';tag=hashlib.sha256(rid.encode()).hexdigest()[:20];candidate_name='sci_recovery_'+tag+'_candidate_result.json';completion_name='sci_recovery_'+tag+'_completion.json';require(not (out/candidate_name).exists() and not (out/completion_name).exists(),'Recovery output name already exists')
 # Keep the frozen original canonical; the host stages the reviewed failure candidate for fixtures.
 expected=sha(pkg/'candidate_failure_result.json') if publish else oldsha
 m={'at':C.now(),'job_key':key,'method':'sciagents','domain':job['domain'],'slot':job['slot'],'output_dir':str(out),'domain_json':str(domain),'domain_sha256':sha(domain),'original_snapshot':str(snap),'expected_result_sha256':expected,'expected_old_canonical_sha256':oldsha,'canonical_publication_required':publish,'expected_launches':job['launches'],'recovery_id':rid,'files':files,'requests':row['requests'],'failed_requests':[row['target']],'historical_consumed_failure_requests':row['historical_consumed_failure_requests'],'successful_requests':row['successful_requests'],'minimum_backoff_seconds':600,'not_before_epoch':datetime.datetime.fromisoformat(row['target']['last_end']['at']).timestamp()+600,'same_slot':True,'same_material':True,'new_sample':False,'new_candidate_pool':False,'additional_physical_attempts_per_original_failed_request':1,'unknown_usage_and_usd':None,'original_job':job,'model_calls_by_preparation':0,'graph_manifest':canonical['manifest_path'],'graph_manifest_sha256':canonical['manifest_sha256'],'candidate_filename':candidate_name,'completion_filename':completion_name,'builder_release':ref(S/'release.json')};save(pkg/'manifest.json',m);graph=read(m['graph_manifest']);require(sha(m['graph_manifest'])==m['graph_manifest_sha256'] and all(sha(q)==h for q,h in graph['bindings'].items()),'Original graph changed')
 sources=[root/n for n in ['host.py','sci_runner.py','finalize_ready.py','health_verifier.py','health_fixture_acceptance.json','builder_release.json']]+[pkg/n for n in ['manifest.json','expected_prior_job.json','classification.json','predecessor_failure_manifest.json']]+[Path(m['graph_manifest']),P/'adapters/common.py',P/'adapters/sciagents.py',P/'adapters/sciagents_matched_graph.py',P/'runtime/offline_exec.py']
 if publish:sources.append(pkg/'candidate_failure_result.json')
 bindings={str(q):sha(q) for q in sources};bindings.update(graph['bindings']);save(pkg/'source_bindings.json',bindings);return pkg

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--key',required=True);ap.add_argument('--recovery-id',required=True);ap.add_argument('--output-root',type=Path,required=True);ap.add_argument('--fixture-only',action='store_true');a=ap.parse_args();release=read(S/'release.json');require(all(sha(p)==h for p,h in release['bindings'].items()),'Builder release changed');allow=fixed_scope(S,P,'sciagents');require(a.key in allow,'Key outside frozen original phase Sci recovery scope');root=a.output_root.resolve();require(root.parent==P/'state' and root!=S,'Output root must be a phase state child');pkg=root/'packages'/a.key
 if (pkg/'handoff.json').exists():require(read(pkg/'manifest.json')['recovery_id']==a.recovery_id and all(sha(p)==h for p,h in read(pkg/'source_bindings.json').items()),'Sealed package changed');print(json.dumps({'status':'already_sealed','handoff':ref(pkg/'handoff.json')}));return 0
 if (pkg/'fixture_only_acceptance.json').exists():require(a.fixture_only,'Fixture-only package cannot become a live successor');print(json.dumps(ref(pkg/'fixture_only_acceptance.json')));return 0
 root.mkdir(parents=True,exist_ok=True)
 for src in (S/'templates').iterdir():
  dst=root/src.name
  if dst.exists():require(sha(dst)==sha(src),'Different runtime root revision')
  else:shutil.copyfile(src,dst)
 if (root/'builder_release.json').exists():require(sha(root/'builder_release.json')==sha(S/'release.json'),'Builder release differs')
 else:shutil.copyfile(S/'release.json',root/'builder_release.json')
 if not (pkg/'manifest.json').exists():
  row=classify(a.key)
  if 'skip' in row:save(root/(a.key+'_skipped.json'),row);print(json.dumps(row));return 0
  require(a.recovery_id not in row['original_job'].get('executed_recovery_ids',[]),'Recovery already executed');pkg=prepare(root,a.key,a.recovery_id,row)
 else:require(read(pkg/'manifest.json')['recovery_id']==a.recovery_id and read(P/'state/campaign.json')['jobs'][a.key]==read(pkg/'expected_prior_job.json'),'Job advanced; use new successor identity')
 if not (pkg/'fixture/transport_fixture_acceptance.json').exists():
  require(not (pkg/'fixture').exists(),'Incomplete fixture retained for diagnosis')
  with (pkg/'fixture.log').open('wb') as log:r=subprocess.run(['/usr/bin/python3','-B',str(root/'host.py'),'--manifest',str(pkg/'manifest.json'),'--fixture-output',str(pkg/'fixture')],stdout=log,stderr=subprocess.STDOUT)
 accept=read(pkg/'fixture/transport_fixture_acceptance.json');require(accept['passed'] and all(accept['checks'].values()) and accept['model_calls']==0,'Exact native fixture failed');m=read(pkg/'manifest.json');history=[p for p in Path(m['original_snapshot']).glob('*') if p.is_file() and ('candidate_result' in p.name or 'completion.json' in p.name)];proof={'passed':all(sha(p)==sha(pkg/'fixture'/p.name) for p in history),'previous_result_files':{p.name:sha(p) for p in history},'model_calls':0};require(proof['passed'],'Old recovery results changed');save(pkg/'history_preservation_acceptance.json',proof);bindings=read(pkg/'source_bindings.json');bindings[str(pkg/'history_preservation_acceptance.json')]=sha(pkg/'history_preservation_acceptance.json');save(pkg/'source_bindings.json',bindings)
 if a.fixture_only:save(pkg/'fixture_only_acceptance.json',{'passed':True,'fixture':ref(pkg/'fixture/transport_fixture_acceptance.json'),'builder':ref(S/'builder.py'),'release':ref(S/'release.json'),'no_live_handoff':True,'model_calls':0,'shared_mutations':False});print(json.dumps(ref(pkg/'fixture_only_acceptance.json')));return 0
 require(read(P/'state/campaign.json')['jobs'][a.key]==read(pkg/'expected_prior_job.json') and all(sha(Path(m['output_dir'])/r)==h for r,h in m['files'].items()),'Job/evidence advanced before seal');save(root/'frozen_inventory.json',{'slots':[{'job_key':a.key,'method':'sciagents','package':str(pkg),'manifest_sha256':sha(pkg/'manifest.json'),'canonical_publication_required':m['canonical_publication_required'],'successful_responses':len(m['successful_requests']),'failed_requests':1}],'model_calls':0})
 admitted_job(S,P,'sciagents',a.key,read(pkg/'expected_prior_job.json'),Path(m['output_dir']))
 with (pkg/'finalize.log').open('wb') as log:r=subprocess.run(['/usr/bin/python3','-B',str(root/'finalize_ready.py'),'--key',a.key],stdout=log,stderr=subprocess.STDOUT)
 require(r.returncode==0 and (pkg/'handoff.json').exists(),'Finalizer failed');print(json.dumps({'handoff':ref(pkg/'handoff.json'),'model_calls':0,'shared_mutations':False,'independent_review_CAS_and_same_owner_enqueue_required':True}));return 0
if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as exc:print(json.dumps({'status':'withheld','error':type(exc).__name__+': '+str(exc),'model_calls':0,'shared_mutations':False}));traceback.print_exc();raise SystemExit(2)
