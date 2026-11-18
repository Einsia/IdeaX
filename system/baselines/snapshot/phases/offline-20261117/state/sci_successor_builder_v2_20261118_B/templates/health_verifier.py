"""Verify every bounded original failed request using append-only native and real gateway evidence."""
from pathlib import Path
import datetime,hashlib,json,time
P=Path(__file__).resolve().parents[2]
read=lambda p:json.loads(Path(p).read_text())
def epoch(at):
 value=datetime.datetime.fromisoformat(at.replace('Z','+00:00'));assert value.tzinfo is not None;return value.timestamp()
def target_health(cfg):
 observed=time.time();out=Path(cfg['output_dir']);snap=Path(cfg['original_snapshot']);m=read(cfg['manifest']);attempts=[];fresh_all=[]
 components=sorted({r['component'] for r in m['failed_requests']});new_starts=[]
 for component in components:
  old_bytes=(snap/component/'api_events.jsonl').read_bytes();new_bytes=(out/component/'api_events.jsonl').read_bytes();assert new_bytes.startswith(old_bytes)
  new_starts.extend(json.loads(line) for line in new_bytes[len(old_bytes):].decode().splitlines() if line.strip() and json.loads(line).get('event')=='attempt_start')
 if not new_starts:
  last=max((r['last_end'] for r in m['failed_requests']),key=lambda e:epoch(e['at']))
  return {'passed':False,'success':False,'classification':'preparation_failure_no_new_physical_attempt','new_physical_attempts':0,'model_calls_for_this_launch':0,'prior_failed_usage_and_usd_remain_unknown':True,'usage':None,'usd':None,'end':last,'next_retry_basis':'Last actual physical failure end + 600 seconds; no artificial new transport backoff','observed_at':datetime.datetime.fromtimestamp(observed,datetime.timezone.utc).isoformat()}
 for component in sorted({r['component'] for r in m['failed_requests']}):
  ledger=out/component/'api_events.jsonl';prior=[json.loads(x) for x in (snap/component/'api_events.jsonl').read_text().splitlines()];events=[json.loads(x) for x in ledger.read_text().splitlines()];assert events[:len(prior)]==prior;fresh=events[len(prior):];fresh_all.extend(fresh)
  for row in m['failed_requests']:
   if row['component']!=component:continue
   ident=row['request_id'];starts=[e for e in fresh if e['event']=='attempt_start' and e['request_id']==ident];ends=[e for e in fresh if e['event']=='attempt_end' and e['request_id']==ident];assert len(starts)==len(ends)==1,'Each original failed request permits exactly one physical attempt';start,end=starts[0],ends[0];assert start['attempt_id']==end['attempt_id']
   assert epoch(start['at'])<=epoch(end['at'])<=observed;request=out/component/'api_requests'/ident;payload=read(request/'request.json');assert hashlib.sha256((request/'request.json').read_bytes()).hexdigest()==row['request_file_sha256'];wire=hashlib.sha256(json.dumps(payload,ensure_ascii=False).encode()).hexdigest();terminal=end.get('status')=='completed';response=None
   if terminal:
    receipt,response=read(request/'receipt.json'),read(request/'response.json');allowed=['stop','tool_calls','function_call'] if m['method']=='sciagents' else ['stop'];assert receipt['status']=='completed' and receipt['attempt_id']==end['attempt_id'] and response['choices'][0]['finish_reason'] in allowed
    assert receipt['request_sha256']==start['request_sha256']==end['request_sha256'];assert end.get('usage_known') is True and isinstance(end.get('usage'),dict) and response.get('usage')==end['usage'];assert all(isinstance(end['usage'].get(k),(int,float)) and not isinstance(end['usage'][k],bool) and end['usage'][k]>=0 for k in ['prompt_tokens','completion_tokens','total_tokens']) and end['usage']['total_tokens']>0
   attempts.append({'component':component,'request_id':ident,'start':start,'end':end,'wire_sha256':wire,'local_terminal':terminal,'usage':end.get('usage'),'usd':None})
 wanted={r['wire_sha256'] for r in attempts};gs={};ge={};source=P/'logs/model_gateway.jsonl'
 with source.open() as stream:
  for line in stream:
   event=json.loads(line)
   if event.get('request_sha256') not in wanted or event.get('mock') is not False:continue
   if event['event']=='attempt_start':gs[event['request_id']]=event
   elif event['event']=='attempt_end':ge[event['request_id']]=event
 used=set()
 for row in attempts:
  candidates=[i for i,s in gs.items() if i in ge and s['request_sha256']==row['wire_sha256'] and epoch(row['start']['at'])<=epoch(s['at'])<=epoch(row['end']['at']) and epoch(s['at'])<=epoch(ge[i]['at'])<=observed and ge[i].get('usage')==row['end'].get('usage')]
  row['gateway_candidates']=[{'start':gs[i],'end':ge[i]} for i in candidates];row['gateway_identity_unique']=len(candidates)==1;row['success']=False
  if len(candidates)==1:
   ident=candidates[0];g=ge[ident];row['gateway_request_id']=ident
   row['success']=bool(row['local_terminal'] and g.get('http_status')==200 and g.get('completed') is True and g.get('usage_known') is True and g.get('usage')==row['usage'] and ident not in used)
   if row['success']:used.add(ident)
  # Concurrent failed requests may have indistinguishable transport envelopes.
  # Preserve all possible gateway matches rather than claiming a unique assignment.
 end=max((r['end'] for r in attempts),key=lambda e:epoch(e['at']));known={'prompt_tokens':0,'completion_tokens':0,'total_tokens':0};unknown=0
 for row in attempts:
  if row['usage'] is None:unknown+=1
  else:
   for k in known:known[k]+=row['usage'].get(k,0)
 candidate=read(out/'original_transport_candidate_result.json') if (out/'original_transport_candidate_result.json').exists() else None
 return {'classification':'all_original_targets_completed' if all(r['success'] for r in attempts) else 'upstream_or_terminal_verification_failure','new_physical_attempts':len(new_starts),'passed':all(bool(r['gateway_candidates']) for r in attempts),'success':all(r['success'] for r in attempts),'observed_at':datetime.datetime.fromtimestamp(observed,datetime.timezone.utc).isoformat(),'gateway_source':str(source),'real_gateway_required':True,'future_times_rejected':True,'all_original_failed_requests_observed':len(attempts),'new_physical_attempt_budget_per_original_failed_request':1,'attempts':attempts,'end':end,'known_usage_subtotal':known,'unknown_usage_attempts':unknown,'usage':known if unknown==0 else None,'usd':None,'native_candidate_status':candidate.get('status') if candidate else None,'independent_native_publication_required':True,'model_calls_by_verification':0}
