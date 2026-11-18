"""Bind Insight's actual extra physical request to its original gateway identity."""
from pathlib import Path
import datetime,hashlib,json,time
P=Path(__file__).resolve().parents[2]
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def target_health(cfg):
 m=read(cfg['manifest']);out=Path(m['output_dir']);snap=Path(m['original_snapshot']);target=out/m['target_directory'];old=(snap/'model_attempts.jsonl').read_bytes();current=(out/'model_attempts.jsonl').read_bytes();assert current.startswith(old)
 assert sha(target/'request.json')==m['target_request_sha256']
 rows=[json.loads(l) for l in current[len(old):].splitlines()];fresh=[r for r in rows if r.get('logical_call')==str(target)]
 starts=[r for r in fresh if r['event']=='attempt_start'];ends=[r for r in fresh if r['event'] in ['attempt_end','attempt_error']]
 if not starts:
  assert not ends
  failure=read(m['failure_manifest']['path'])
  return {'passed':True,'success':False,'classification':'preparation_failure_no_new_physical_attempt','new_physical_attempts':0,'model_calls_for_this_launch':0,'end':{'at':failure['latest_failure_at']},'usage':None,'usd':None}
 assert len(starts)==len(ends)==1,'Expected exactly one completed additional physical target attempt'
 start,end=starts[0],ends[0];assert start['physical_attempt']==end['physical_attempt']==m['prior_physical_attempts']+1
 assert start['request_sha256']==m['target_stream_wire_sha256']
 assert start['at']<=end['at'] and datetime.datetime.fromisoformat(end['at']).timestamp()<=time.time()
 attempt=target/f"physical-{m['prior_physical_attempts']+1:02}"
 assert sha(attempt/'request_body.json')==m['target_stream_wire_sha256'] and sha(attempt/'native_sdk_request_body.json')==m['target_wire_sha256']
 gateway_id=(end.get('headers') or {}).get('x-offline-bridge-request-id');gateway=[]
 for line in (P/'logs/model_gateway.jsonl').open():
  if (gateway_id and gateway_id in line) or (not gateway_id and m['target_stream_wire_sha256'] in line):
   e=json.loads(line)
   if e.get('mock') is False and e.get('request_sha256')==m['target_stream_wire_sha256']:gateway.append(e)
 gs={e['request_id']:e for e in gateway if e['event']=='attempt_start'};ge={e['request_id']:e for e in gateway if e['event']=='attempt_end'}
 candidates=[i for i,s in gs.items() if start['at']<=s['at']<=end['at'] and i in ge and abs((datetime.datetime.fromisoformat(ge[i]['at'])-datetime.datetime.fromisoformat(end['at'])).total_seconds())<=1]
 assert candidates,'No real matching upstream physical request'
 if gateway_id:assert candidates==[gateway_id]
 unique=len(candidates)==1;gstart=gs[candidates[0]] if unique else None;gend=ge[candidates[0]] if unique else None
 success=end.get('provider_status')=='completed' and end.get('http_status')==200 and bool(end.get('usage'))
 if success:
  assert unique and gend.get('completed') is True and gend['http_status']==200 and gend.get('usage')==end['usage']
  receipt=read(target/'native_returned.json');assert receipt['physical_attempts']==m['prior_physical_attempts']+1 and receipt['request_sha256']==m['target_request_sha256']
  assert receipt['native_response_sha256']==sha(target/'native_response.json')
  final=read(attempt/'stream_terminal_response.json');proof=read(attempt/'stream_reassembly.json')
  assert final['status']=='completed' and final['usage']==end['usage'] and proof['terminal_event']=='response.completed' and proof['raw_sse_sha256']==sha(attempt/'response_body.bin')
 return {'passed':True,'success':success,'new_physical_attempts':1,'start':start,'end':end,'gateway_identity_unique':unique,'gateway_candidates':candidates,'gateway_start':gstart,'gateway_end':gend,'target_request_exact':True,'all_previous_evidence_preserved':True,'terminal_finish_and_usage_verified':success,'usage':end.get('usage'),'usd':None,'partial_response_consumed':False,'independent_native_terminal_publication_required':True}
