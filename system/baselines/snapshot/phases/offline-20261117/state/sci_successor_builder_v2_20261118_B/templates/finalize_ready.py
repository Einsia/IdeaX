from pathlib import Path
import argparse,datetime,hashlib,json
S=Path(__file__).resolve().parent;P=S.parents[1];read=lambda p:json.loads(Path(p).read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
ap=argparse.ArgumentParser();ap.add_argument('--key',action='append');a=ap.parse_args();ready=[]
for item in read(S/'frozen_inventory.json')['slots']:
 if a.key and item['job_key'] not in a.key:continue
 pkg=Path(item['package']);fixture=pkg/'fixture/transport_fixture_acceptance.json'
 if not fixture.exists():continue
 accept=read(fixture)
 if not accept['passed']:continue
 assert all(accept['checks'].values()) and accept['model_calls']==0
 if (pkg/'handoff.json').exists():ready.append(read(pkg/'handoff.json'));continue
 m=read(pkg/'manifest.json');out=Path(m['output_dir']);assert sha(out/'result.json') in [m['expected_old_canonical_sha256'],m['expected_result_sha256']]
 assert all((out/r).is_file() and (r=='result.json' or sha(out/r)==h) for r,h in m['files'].items()),item['job_key']
 first=m['failed_requests'][0];cfg={'method':m['method'],'job_key':m['job_key'],'recovery_id':m['recovery_id'],'manifest':str(pkg/'manifest.json'),'manifest_sha256':sha(pkg/'manifest.json'),'expected_result_sha256':m['expected_result_sha256'],'expected_launches':m['expected_launches'],'output_dir':m['output_dir'],'original_snapshot':m['original_snapshot'],'not_before_epoch':m['not_before_epoch'],'minimum_backoff_seconds':600,'failed_requests':m['failed_requests'],'new_physical_attempt_budget_per_original_failed_request':1,'physical_attempt_budget':len(m['failed_requests']),'component':first['component'],'failed_request_id':first['request_id'],'request_file_sha256':first['request_file_sha256'],'fixture':str(fixture),'command':['/usr/bin/python3',str(S/'host.py'),'--manifest',str(pkg/'manifest.json')],'health_verifier':{'path':str(S/'health_verifier.py'),'sha256':sha(S/'health_verifier.py'),'function':'target_health'},'same_slot':True,'same_material':True,'new_sample':False,'next_native_requests_original_semantics':True,'independent_native_publication_required':True,'preparation_failure_is_not_an_upstream_attempt':True}
 save(pkg/'owner_config.json',cfg);bindings=read(pkg/'source_bindings.json');bindings.update({str(p):sha(p) for p in [pkg/'owner_config.json',fixture,S/'health_verifier.py',S/'health_fixture_acceptance.json']});save(pkg/'source_bindings.json',bindings)
 entry={**item,'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'ready_for_independent_review_and_same_input_queue','config':str(pkg/'owner_config.json'),'config_sha256':sha(pkg/'owner_config.json'),'source_bindings_sha256':sha(pkg/'source_bindings.json'),'fixture_sha256':sha(fixture),'fixture_checks':len(accept['checks']),'expected_launches':m['expected_launches'],'expected_result_sha256':m['expected_result_sha256'],'expected_old_canonical_sha256':m['expected_old_canonical_sha256'],'canonical_publication_required':m['canonical_publication_required'],'candidate_filename':m['candidate_filename'],'completion_filename':m['completion_filename'],'fixture_model_calls':0,'live_mutations':False}
 if m['canonical_publication_required']:entry['new_failure_publication']={'manifest':{'path':str(pkg/'predecessor_failure_manifest.json'),'sha256':sha(pkg/'predecessor_failure_manifest.json')},'candidate_result':{'path':str(pkg/'candidate_failure_result.json'),'sha256':sha(pkg/'candidate_failure_result.json')},'expected_old_result_sha256':m['expected_old_canonical_sha256']}
 save(pkg/'handoff.json',entry);ready.append(entry)
save(S/'ready_handoffs.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'ready':ready,'model_calls':0,'live_mutations':False});print(json.dumps({'ready':len(ready),'keys':[x['job_key'] for x in ready]},indent=2))
