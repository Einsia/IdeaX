"""Read-only audit of every admitted reviewer against unique real shared-gateway attempts."""
from pathlib import Path
import datetime,hashlib,json,time
S=Path(__file__).resolve().parent;P=S.parents[1]
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def epoch(at):
 value=datetime.datetime.fromisoformat(at.replace('Z','+00:00'));assert value.tzinfo is not None;return value.timestamp()
def rows(path):return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()] if Path(path).exists() else []
def target_health(cfg):
 m=read(cfg['manifest']);assert m['fixture'] is False and 1<=m['physical_attempt_budget']<=10
 out=Path(cfg['output_dir']);snapshot=Path(m['original_snapshot']);observed=time.time();events=rows(out/'reviewer/api_events.jsonl');prior=rows(snapshot/'reviewer/api_events.jsonl');assert events[:len(prior)]==prior
 fresh=events[len(prior):];starts=[e for e in fresh if e['event']=='attempt_start'];ends=[e for e in fresh if e['event']=='attempt_end']
 if not starts:
  h={'end':max((r['last_end'] for r in m['failed_requests']),key=lambda e:epoch(e['at']))};return {'passed':False,'success':False,'classification':'preparation_failure_no_new_physical_attempt','new_physical_attempts':0,'model_calls_for_this_launch':0,'end':h['end'],'usage':None,'usd':None,'native_zero_eligible':False}
 assert len(starts)==len(ends)==m['physical_attempt_budget'] and {e['request_id'] for e in starts}==set(m['missing_request_ids'])
 planned={row['request_id']:row for row in m['planned_requests']};attempts=[]
 for start in starts:
  ident=start['request_id'];row=planned[ident];matched=[e for e in ends if e['attempt_id']==start['attempt_id'] and e['request_id']==ident];assert len(matched)==1 and start['attempt_in_invocation']==1
  end=matched[0];assert epoch(start['at'])<=epoch(end['at'])<=observed
  request=out/'reviewer/api_requests'/ident;payload=read(request/'request.json');assert payload==read(row['payload']['path']) and sha(row['payload']['path'])==row['payload']['sha256']
  wire=hashlib.sha256(json.dumps(payload,ensure_ascii=False).encode()).hexdigest();local_digest=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest();assert local_digest==start['request_sha256']==end['request_sha256']
  complete=end.get('status')=='completed'
  if complete:
   response=read(request/'response.json');receipt=read(request/'receipt.json');assert receipt['status']=='completed' and receipt['request_sha256']==local_digest and receipt['attempt_id']==start['attempt_id'] and receipt['response_sha256']==hashlib.sha256(json.dumps(response,ensure_ascii=False).encode()).hexdigest()
   assert response['choices'][0]['finish_reason']=='stop' and response['choices'][0]['message']['content'].strip() and end['usage_known'] is True and response['usage']==end['usage']
   assert all(isinstance(end['usage'].get(k),(int,float)) and not isinstance(end['usage'][k],bool) and end['usage'][k]>=0 for k in ['prompt_tokens','completion_tokens','total_tokens']) and end['usage']['total_tokens']>0
  attempts.append({'component':'reviewer','request_id':ident,'start':start,'end':end,'wire_sha256':wire,'local_terminal':complete,'usage':end.get('usage'),'usd':None})
 wanted={r['wire_sha256'] for r in attempts};gs={};ge={};gateway=P/'logs/model_gateway.jsonl'
 with gateway.open() as stream:
  for line in stream:
   event=json.loads(line)
   if event.get('request_sha256') not in wanted or event.get('mock') is not False:continue
   if event['event']=='attempt_start':gs[event['request_id']]=event
   elif event['event']=='attempt_end':ge[event['request_id']]=event
 used=set()
 for row in attempts:
  candidates=[i for i,s in gs.items() if i in ge and s['request_sha256']==row['wire_sha256'] and epoch(row['start']['at'])<=epoch(s['at'])<=epoch(row['end']['at']) and epoch(s['at'])<=epoch(ge[i]['at'])<=observed and ge[i].get('usage')==row['usage']]
  row['gateway_candidates']=[{'start':gs[i],'end':ge[i]} for i in candidates];row['gateway_identity_unique']=len(candidates)==1;row['success']=False
  if len(candidates)==1:
   ident=candidates[0];g=ge[ident];row['gateway_request_id']=ident;row['success']=bool(row['local_terminal'] and g.get('http_status')==200 and g.get('completed') is True and g.get('usage_known') is True and g.get('usage')==row['usage'] and ident not in used);used.add(ident)
 report=read(out/m['completion_filename']);result=read(out/m['candidate_filename']);assert report['passed'] and all(report['checks'].values()) and report['fixture'] is False and result['fixture'] is False and report['new_physical_attempts']==m['physical_attempt_budget']
 for name,h in m['files'].items():
  if name in ['run.lock','offline_boundary.json','offline_launch.json','local_literature_service.log','local_literature_requests.jsonl']:continue
  if name.endswith('completion_order.jsonl') or name=='reviewer/api_events.jsonl':assert (out/name).read_bytes().startswith((snapshot/name).read_bytes())
  else:assert sha(out/name)==h,name
 assert sha(out/'result.json')==m['expected_result_sha256']
 if report['native_terminal']:
  assert result['status']=='completed' and result['configuration_sha256']==m['configuration']['sha256'] and result['deployment_manifest_sha256']==m['deployment']['sha256'] and result['continuation_manifest_sha256']==sha(cfg['manifest'])
 known={k:0 for k in ['prompt_tokens','completion_tokens','total_tokens']};unknown=0
 for row in attempts:
  if row['usage'] is None:unknown+=1
  else:
   for k in known:known[k]+=row['usage'][k]
 failures=[r for r in attempts if not r['success']];end=max((r['end'] for r in failures or attempts),key=lambda e:epoch(e['at']))
 success=all(r['success'] for r in attempts) and report['native_terminal']
 return {'passed':all(bool(r['gateway_candidates']) for r in attempts),'success':success,'classification':'all_original_reviewers_completed_pending_native_review' if success else 'upstream_or_native_terminal_verification_failure','new_physical_attempts':len(starts),'attempts':attempts,'end':end,'native_terminal':report['native_terminal'],'native_candidate_status':result['status'],'native_zero_eligible':False,'known_usage_subtotal':known,'unknown_usage_attempts':unknown,'usage':known if unknown==0 else None,'usd':None,'prior_failed_usage_and_usd_remain_unknown':True,'real_gateway_required':True,'gateway_source':str(gateway),'observed_at':datetime.datetime.fromtimestamp(observed,datetime.timezone.utc).isoformat(),'independent_native_publication_required':True,'model_calls_by_verification':0}
