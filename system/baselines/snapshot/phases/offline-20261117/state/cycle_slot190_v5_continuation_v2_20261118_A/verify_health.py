"""Audit actual verifier with explicitly synthetic gateway relationships and real digest convention.

Synthetic outputs remain under fixtures and are never valid service recovery evidence.
"""
from pathlib import Path
import copy,hashlib,importlib.util,json,shutil
S=Path(__file__).resolve().parent;P=S.parents[1]
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 base=S/'fixtures/gateway_health';base.mkdir(parents=True,exist_ok=False)
 sp=importlib.util.spec_from_file_location('fixture_actual_reviewer_health',S/'health_verifier.py');h=importlib.util.module_from_spec(sp);sp.loader.exec_module(h);checks={}
 def check(name,value):assert value,name;checks[name]=True
 def rejected(name,fn):
  try:fn()
  except AssertionError:check(name,True)
  else:raise AssertionError('Unexpected acceptance: '+name)
 for scenario in ['success','503']:
  root=base/scenario;out=root/'synthetic_output';shutil.copytree(S/'fixtures/offline_checks_v3'/f'{scenario}_execution',out)
  m=read(S/'fixtures/offline_checks_v3'/f'{scenario}_package/manifest.json');m['fixture']=False;manifest=root/'synthetic_manifest.json';save(manifest,m)
  for name in [m['candidate_filename'],m['completion_filename']]:
   v=read(out/name);v['fixture']=False
   if name==m['candidate_filename']:v['continuation_manifest_sha256']=sha(manifest)
   save(out/name,v)
  events=[json.loads(x) for x in (out/'reviewer/api_events.jsonl').read_text().splitlines()];gateway=[]
  for e in events:
   if e['event'] not in ['attempt_start','attempt_end']:continue
   payload=read(out/'reviewer/api_requests'/e['request_id']/'request.json');wire=hashlib.sha256(json.dumps(payload,ensure_ascii=False).encode()).hexdigest();local=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest();assert e['request_sha256']==local and local!=wire
   row={'event':e['event'],'at':e['at'],'request_id':'explicit-test-gateway-'+e['request_id'],'request_sha256':wire,'mock':False}
   if e['event']=='attempt_end':row.update(http_status=200 if e['status']=='completed' else 503,completed=e['status']=='completed',usage_known=e.get('usage_known'),usage=e.get('usage'))
   gateway.append(row)
  path=root/'logs/model_gateway.jsonl';path.parent.mkdir();h.P=root;cfg={'manifest':str(manifest),'output_dir':str(out)}
  def write_gateway(value):path.write_text(''.join(json.dumps(e)+'\n' for e in value))
  write_gateway(gateway);result=h.target_health(cfg);check(scenario+'_canonical_digest_and_wire_digest_both_validated',result['passed'] and result['new_physical_attempts']==10 and result['success']==(scenario=='success') and result['native_zero_eligible'] is False)
  if scenario=='success':
   mutations={
    'missing_gateway_never_success':[e for e in gateway if e['request_id']!='explicit-test-gateway-reviewer-0001'],
    'mock_gateway_never_real_success':[{**e,'mock':True} for e in gateway],
    'wrong_usage_never_success':[{**e,'usage':None} if e['event']=='attempt_end' else e for e in gateway],
    'future_gateway_never_success':[{**e,'at':'2099-01-01T00:00:00+00:00'} for e in gateway],
    'duplicate_gateway_identity_never_success':gateway+[{**e,'request_id':e['request_id']+'-duplicate'} for e in gateway if e['request_id']=='explicit-test-gateway-reviewer-0001']}
   for name,value in mutations.items():write_gateway(value);check(name,h.target_health(cfg)['success'] is False)
   write_gateway(gateway)
   canonical=out/'result.json';old=canonical.read_bytes();canonical.write_text('{}\n');rejected('old_canonical_mutation_rejected',lambda:h.target_health(cfg));canonical.write_bytes(old)
   ledger=out/'reviewer/api_events.jsonl';old=ledger.read_bytes();bad=copy.deepcopy(events);next(e for e in bad if e['event']=='attempt_start')['request_sha256']='0'*64;ledger.write_text(''.join(json.dumps(e)+'\n' for e in bad));rejected('wrong_local_canonical_digest_rejected',lambda:h.target_health(cfg));ledger.write_bytes(old)
  else:check('single503_retains_unknown_usage',result['unknown_usage_attempts']==1 and result['usage'] is None)
  save(root/'fixture_health_output.json',{'fixture':True,'synthetic_gateway':True,'not_service_recovery_evidence':True,'value':result})
 # Verify the convention against preserved, real attempt9 gateway evidence independently of synthetic fixtures.
 a=P/'state/cycle_slot190_v5_recovery_attempt10_20261118_A';real=read(a/'prior_canary_gateway_health.json');row=real['attempts'][0];payload=read(a/'original_run/researcher/api_requests/researcher-0007/request.json');wire=hashlib.sha256(json.dumps(payload,ensure_ascii=False).encode()).hexdigest();local=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
 check('actual_attempt9_local_digest_is_sorted_and_gateway_digest_is_wire',local==row['start']['request_sha256']==row['end']['request_sha256'] and local!=wire and wire==row['wire_sha256'] and all(g['start']['mock'] is False and g['start']['request_sha256']==wire for g in row['gateway_candidates']) and len(row['gateway_candidates'])>=1)
 save(base/'acceptance.json',{'passed':True,'fixture':True,'synthetic_gateway_only_for_reviewer_tests':True,'actual_failed_canary_digest_convention_checked':True,'checks':checks,'model_calls':0,'production_mutations':False,'health_verifier_sha256':sha(S/'health_verifier.py')});print(json.dumps({'passed':True,'checks':len(checks),'model_calls':0}))
if __name__=='__main__':main()
