"""Frozen original-request evidence and append-only checkpoint helpers; no transport."""
from pathlib import Path
import datetime,hashlib,json,os
S=Path(__file__).resolve().parent;P=S.parents[1]
KEY='cycleresearcher__ai-control-deception__05__generation';OUT=P/'runs/cycleresearcher/ai-control-deception/slot-05'
RUNTIME={'run.lock','offline_boundary.json','offline_launch.json','local_literature_service.log','local_literature_requests.jsonl'}
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
def ref(p):return {'path':str(p),'sha256':sha(p)}
def epoch(at):return datetime.datetime.fromisoformat(at.replace('Z','+00:00')).timestamp()
def rows(p):return [json.loads(x) for x in Path(p).read_text().splitlines() if x.strip()] if Path(p).exists() else []
def inventory(p):return {str(f.relative_to(p)):sha(f) for f in p.rglob('*') if f.is_file()}
def current_job():
 job=read(P/'state/campaign.json')['jobs'][KEY];handle=job.get('process') or {};pid=handle.get('pid');stat=Path(f'/proc/{pid}/stat') if pid else None
 if stat and stat.exists():
  parts=stat.read_text().rsplit(')',1)[1].split();assert parts[0]=='Z' or str(parts[19])!=str(handle.get('start')),'Original worker still active'
 assert job['status']=='infrastructure_failure','Only API infrastructure checkpoints are automatically retried'
 return job
def cached(root,component,ident,payload=None):
 q=root/component/'api_requests'/ident;receipt=read(q/'receipt.json');response=read(q/'response.json');request=read(q/'request.json')
 assert receipt['status']=='completed' and response['choices'][0]['finish_reason']=='stop' and isinstance(response['choices'][0]['message'].get('content'),str) and response['choices'][0]['message']['content'].strip(),'Terminal cache is not an ordinary completed response; no resampling'
 assert receipt['request_sha256']==hashlib.sha256(json.dumps(request,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
 assert receipt['response_sha256']==hashlib.sha256(json.dumps(response,ensure_ascii=False).encode()).hexdigest()
 if payload is not None:assert payload==request
 return response
def request_state(root,component,ident):
 q=root/component/'api_requests'/ident;events=[e for e in rows(root/component/'api_events.jsonl') if e.get('request_id')==ident];starts=[e for e in events if e['event']=='attempt_start'];ends=[e for e in events if e['event']=='attempt_end'];assert len(starts)==len(ends) and all(any(e['attempt_id']==x['attempt_id'] for e in ends) for x in starts),'Request is still active or ledger incomplete'
 if (q/'receipt.json').exists() or (q/'response.json').exists():
  cached(root,component,ident);assert ends and ends[-1]['status']=='completed';return {'component':component,'request_id':ident,'completed':True,'prior_physical_attempts':len(starts),'last_end':ends[-1],'request_file_sha256':sha(q/'request.json')}
 assert ends and ends[-1]['status']=='infrastructure_failure','Only an original transport failure may be retried'
 return {'component':component,'request_id':ident,'completed':False,'prior_physical_attempts':len(starts),'last_end':ends[-1],'request_file_sha256':sha(q/'request.json'),'usage':None,'usd':None}
def unchanged(root,snapshot,files,after=False):
 for name,h in files.items():
  assert sha(snapshot/name)==h,name
  if name in RUNTIME:continue
  if after and (name.endswith('completion_order.jsonl') or name=='reviewer/api_events.jsonl'):
   assert (root/name).read_bytes().startswith((snapshot/name).read_bytes()),name
  else:assert sha(root/name)==h,name
